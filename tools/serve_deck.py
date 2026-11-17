#!/usr/bin/env python3
"""
serve_deck.py — 静态服务这份 HTML 幻灯片（默认只绑 127.0.0.1，供 cloudflared 反代）

用法：
    python3 tools/serve_deck.py                          # 127.0.0.1:8899，根目录=本项目
    python3 tools/serve_deck.py --port 8899 --root .
    python3 tools/serve_deck.py --host 0.0.0.0           # 局域网直连（谨慎，无鉴权）

特性：正确的 MIME（含 .pptx/.pdf/.md）、禁止目录列表、html 不缓存 / 静态资源短缓存、
      HEAD 支持、线程化、访问日志输出到 stdout 并立即刷新。
      另含 PPTX 导入 API（/api/*，仅限 Host=127.0.0.1/localhost 直连；
      经 cloudflared 隧道的公网请求 Host 是站点域名 → 一律 403），
      供根目录 import.html 调用：体检 / 导入（SSE 进度）/ 取消 / 入库。
"""
import argparse
import gzip
import json
import os
import re
import shlex
import signal
import subprocess
import sys
import threading
import time
from email.utils import formatdate
from datetime import datetime, timezone
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

EXTRA_MIME = {
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".ppt": "application/vnd.ms-powerpoint",
    ".pdf": "application/pdf",
    ".md": "text/markdown; charset=utf-8",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".webp": "image/webp",
}

# 导入任务状态（单飞：同一时刻只允许一个导入子进程）
_IMPORT_LOCK = threading.Lock()
_IMPORT_PROC = {"proc": None}


class DeckHandler(SimpleHTTPRequestHandler):
    server_version = "deck-static/1.0"
    sys_version = ""
    protocol_version = "HTTP/1.1"

    extensions_map = {**SimpleHTTPRequestHandler.extensions_map, **EXTRA_MIME}

    def end_headers(self):
        path = self.path.split("?")[0].lower()
        if path.endswith((".html", ".htm")) or path in ("/", ""):
            self.send_header("Cache-Control", "no-cache, must-revalidate")
        else:
            self.send_header("Cache-Control", "public, max-age=3600")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        super().end_headers()

    USE_GZIP = False   # 默认关闭：Cloudflare 边缘会自动压缩，源站压缩反而拖慢隧道

    COMPRESSIBLE = ("text/", "application/javascript", "application/json",
                    "application/xml", "image/svg+xml")

    def _serve(self, head_only=False):
        # /decks/<slug> → /decks/<slug>/（避免相对路径解析出错）
        raw = self.path.split("?")[0]
        if re.match(r"^/decks/[^/]+$", raw):
            self.send_response(301)
            self.send_header("Location", raw + "/")
            self.end_headers()
            return
        path = self.translate_path(self.path)
        if os.path.isdir(path):
            # 目录索引顺序：library.html（展示台首页）> index-web.html（轻量版）> index.html
            for name in ("library.html", "index-web.html", "index.html"):
                index = os.path.join(path, name)
                if os.path.isfile(index):
                    path = index
                    break
            else:
                return self.send_error(403, "Directory listing disabled")
        if not os.path.isfile(path):
            return self.send_error(404, "Not Found")

        try:
            with open(path, "rb") as fh:
                data = fh.read()
        except OSError:
            return self.send_error(404, "Not Found")

        ctype = self.guess_type(path)
        body, encoding = data, None
        accept = (self.headers.get("Accept-Encoding") or "").lower()
        if self.USE_GZIP and "gzip" in accept and len(data) > 1024 and ctype.startswith(self.COMPRESSIBLE):
            body, encoding = gzip.compress(data, 6), "gzip"

        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Last-Modified", formatdate(os.path.getmtime(path), usegmt=True))
        self.send_header("Accept-Ranges", "none")
        if encoding:
            self.send_header("Content-Encoding", encoding)
            self.send_header("Vary", "Accept-Encoding")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if not head_only:
            self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path.startswith("/api/"):
            return self.api_get(path)
        self._serve(head_only=False)

    def do_HEAD(self):
        path = self.path.split("?")[0]
        if path.startswith("/api/"):
            return self.api_get(path)
        self._serve(head_only=True)

    def do_POST(self):
        path = self.path.split("?")[0]
        if path.startswith("/api/"):
            return self.api_post(path)
        self.send_error(405, "POST not allowed")

    # ------------------------------------------------------------ PPTX 导入 API
    LOCAL_HOST = re.compile(r"^(127\.0\.0\.1|localhost|\[::1\]|::1)(:\d+)?$", re.I)
    MAX_UPLOAD = 300 * 1024 * 1024

    def _api_guard(self) -> bool:
        """导入 API 只允许本机直连；经隧道/局域网的请求 Host 不是 loopback → 403。"""
        host = (self.headers.get("Host") or "").strip().lower()
        if self.LOCAL_HOST.match(host):
            return True
        self._json_response(403, {"ok": False, "error": "导入 API 仅限本机使用（127.0.0.1 / localhost）"})
        return False

    def _json_response(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self):
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            n = 0
        if n <= 0 or n > self.MAX_UPLOAD:
            self._json_response(413, {"ok": False,
                                      "error": f"请求体大小超限（≤{self.MAX_UPLOAD // 1024 // 1024}MB）"})
            return None
        return self.rfile.read(n)

    def _sse_start(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True

    def _sse(self, obj):
        try:
            self.wfile.write(f"data: {json.dumps(obj, ensure_ascii=False)}\n\n".encode("utf-8"))
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            raise

    def api_get(self, path):
        if not self._api_guard():
            return
        if path == "/api/ping":
            return self._json_response(200, {"ok": True, "feature": "import"})
        if path == "/api/slug-exists":
            from urllib.parse import urlparse, parse_qs
            q = parse_qs(urlparse(self.path).query)
            slug = (q.get("slug") or [""])[0].strip()
            if not re.fullmatch(r"[a-z0-9-]+", slug):
                return self._json_response(400, {"ok": False, "error": "slug 只能含小写字母/数字/连字符"})
            root = self.directory
            exists = any(os.path.exists(os.path.join(root, d, slug))
                         for d in ("decks", "assets")) or os.path.isdir(os.path.join(root, f"src-{slug}"))
            return self._json_response(200, {"ok": True, "exists": exists})
        self._json_response(404, {"ok": False, "error": f"未知 API：{path}"})

    def api_post(self, path):
        if not self._api_guard():
            return
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        if path == "/api/inventory":
            return self.api_inventory()
        if path == "/api/import":
            return self.api_import()
        if path == "/api/cancel":
            return self.api_cancel()
        if path == "/api/publish":
            return self.api_publish()
        self._json_response(404, {"ok": False, "error": f"未知 API：{path}"})

    def _uploads_dir(self):
        d = os.path.join(self.directory, "build", "import", "_uploads")
        os.makedirs(d, exist_ok=True)
        for name in os.listdir(d):                      # 清掉一天前的旧上传
            p = os.path.join(d, name)
            if os.path.isfile(p) and time.time() - os.path.getmtime(p) > 86400:
                os.remove(p)
        return d

    def api_inventory(self):
        body = self._read_body()
        if body is None:
            return
        # 中文文件名经 query 传入（HTTP header 是 latin-1，放中文名会乱码）
        from urllib.parse import urlparse, parse_qs
        q = parse_qs(urlparse(self.path).query)
        raw_name = (q.get("name") or [self.headers.get("X-Filename") or "upload.pptx"])[0]
        fname = re.sub(r"[^\w.\-\u4e00-\u9fff]+", "_", raw_name) or "upload.pptx"
        if not fname.lower().endswith(".pptx"):
            return self._json_response(400, {"ok": False, "error": "只支持 .pptx 文件"})
        dst = os.path.join(self._uploads_dir(), f"{int(time.time())}-{fname}")
        with open(dst, "wb") as fh:
            fh.write(body)
        try:
            import import_pptx as ip
            inv = ip.inventory(__import__("pathlib").Path(dst))
        except Exception as e:
            return self._json_response(400, {"ok": False, "error": f"无法解析 PPTX：{e}"})
        stem = os.path.splitext(fname)[0].lstrip("0123456789-")
        self._json_response(200, {
            "ok": True, "path": dst,
            "inventory": {"slides": inv["slides"], "ratio": inv["ratio"],
                          "tables": inv["tables"], "groups": inv["groups"],
                          "autofit": inv["autofit"], "cjk": inv["cjk_chars"],
                          "latin": inv["latin_chars"],
                          "fonts": sorted(dict(inv["fonts"]).keys())},
            "suggest": {"slug": ip.slugify(stem), "title": stem},
        })

    def _run_streamed(self, argv, done_note):
        """跑子进程并把 stdout 逐行推成 SSE。返回退出码。"""
        proc = subprocess.Popen(argv, cwd=self.directory, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, bufsize=1,
                                start_new_session=True)
        with _IMPORT_LOCK:
            _IMPORT_PROC["proc"] = proc
        try:
            for line in proc.stdout:
                line = line.rstrip()
                if not line:
                    continue
                m = re.match(r"^\[(\d)/6\]", line)
                if m:
                    self._sse({"type": "stage", "n": int(m.group(1)), "line": line})
                else:
                    self._sse({"type": "log", "line": line})
            code = proc.wait()
        finally:
            with _IMPORT_LOCK:
                _IMPORT_PROC["proc"] = None
        self._sse({"type": "exit", "code": code})
        return code

    def api_import(self):
        if _IMPORT_PROC["proc"] is not None:
            return self._json_response(409, {"ok": False, "error": "已有导入在进行中，请等它结束或先取消"})
        body = self._read_body()
        if body is None:
            return
        try:
            req = json.loads(body.decode("utf-8"))
        except Exception:
            return self._json_response(400, {"ok": False, "error": "JSON 解析失败"})
        uploads = os.path.realpath(self._uploads_dir())
        src = os.path.realpath(req.get("path") or "")
        if not src.startswith(uploads + os.sep) or not os.path.isfile(src):
            return self._json_response(400, {"ok": False, "error": "非法的源文件路径（须先经 /api/inventory 上传）"})
        o = req.get("options") or {}
        slug = str(o.get("slug") or "")
        if not re.fullmatch(r"[a-z0-9-]+", slug):
            return self._json_response(400, {"ok": False, "error": "slug 只能含小写字母/数字/连字符"})

        argv = [sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                             "import_pptx.py"), src, "--slug", slug]
        FLAG_STR = {"title": "--title", "subtitle": "--subtitle", "author": "--author",
                    "date": "--date", "version": "--version", "accent": "--accent",
                    "brand": "--brand", "brand_sub": "--brand-sub",
                    "rail_map": "--rail-map", "overview_foot": "--overview-foot",
                    "lang": "--lang", "shrink": "--shrink", "table_k": "--table-k",
                    "group_k": "--group-k", "track": "--track", "rounds": "--rounds"}
        for key, flag in FLAG_STR.items():
            if o.get(key) not in (None, "", False):
                argv += [flag, str(o[key])]
        if o.get("tags"):
            argv += ["--tags", ",".join(o["tags"]) if isinstance(o["tags"], list) else str(o["tags"])]
        if isinstance(o.get("order"), int):
            argv += ["--order", str(o["order"])]
        for key, flag in (("prefit", "--prefit"), ("rewrite_fonts", "--rewrite-fonts"),
                          ("no_nowrap", "--no-nowrap"), ("skip_build", "--skip-build"),
                          ("force", "--force")):
            if o.get(key):
                argv.append(flag)
        if isinstance(o.get("rail_labels"), dict) and o["rail_labels"]:
            pairs = ",".join(f"{k}={v}" for k, v in o["rail_labels"].items() if v)
            if pairs:
                argv += ["--rail-labels", pairs]

        self._sse_start()
        self._sse({"type": "log", "line": f"$ {shlex.join(argv)}"})
        try:
            code = self._run_streamed(argv, "import")
        except Exception as e:
            self._sse({"type": "error", "message": str(e)})
            return
        if code != 0:
            self._sse({"type": "error", "message": f"导入失败（退出码 {code}），见上方日志"})

    def api_cancel(self):
        with _IMPORT_LOCK:
            proc = _IMPORT_PROC["proc"]
        if proc is None:
            return self._json_response(200, {"ok": True, "cancelled": False, "note": "没有进行中的任务"})
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except ProcessLookupError:
            pass
        return self._json_response(200, {"ok": True, "cancelled": True})

    def api_publish(self):
        body = self._read_body() or b"{}"
        try:
            force = bool(json.loads(body.decode("utf-8") or "{}").get("force"))
        except Exception:
            force = False
        py = sys.executable
        for cand in ("/usr/bin/python3", "/opt/homebrew/bin/python3"):
            r = subprocess.run([cand, "-c", "import playwright"], capture_output=True)
            if r.returncode == 0:
                py = cand
                break
        argv = [py, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 "build_library.py")] + (["--force"] if force else [])
        self._sse_start()
        self._sse({"type": "log", "line": f"$ {shlex.join(argv)}"})
        try:
            code = self._run_streamed(argv, "publish")
        except Exception as e:
            self._sse({"type": "error", "message": str(e)})
            return
        if code != 0:
            self._sse({"type": "error", "message": f"入库失败（退出码 {code}），见上方日志"})
        else:
            self._sse({"type": "log", "line": "✅ 展示台已刷新（decks.json / library.html / 缩略图）"})

    def list_directory(self, path):
        # 不列目录
        self.send_error(403, "Directory listing disabled")
        return None

    def log_message(self, fmt, *args):
        stamp = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S")
        sys.stdout.write(f"{stamp} {self.address_string()} {fmt % args}\n")
        sys.stdout.flush()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8899)
    args = ap.parse_args()

    root = os.path.abspath(args.root)
    if not os.path.isfile(os.path.join(root, "index.html")):
        sys.exit(f"{root} 下没有 index.html")

    handler = partial(DeckHandler, directory=root)
    httpd = ThreadingHTTPServer((args.host, args.port), handler)
    httpd.daemon_threads = True
    print(f"[deck] {root}  →  http://{args.host}:{args.port}/", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[deck] bye", flush=True)


if __name__ == "__main__":
    main()
