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
      以及 /admin 管理后台（tools/admin_core.py + admin_site.py）：
      访问追踪（/api/track/*，前端脚本由本服务注入 HTML）、deck 门禁（密码 / 下架，
      library.html 服务端实时过滤）、访问统计面板。运行时数据在 <root>/data/。
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
from urllib.parse import urlparse, parse_qs

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

# /admin 后台：懒加载 tools/admin_core.py（数据层）与 admin_site.py（页面模板）
_STORE = None
_MODS = {}


def get_store(root):
    global _STORE
    if _STORE is None:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import admin_core
        import admin_site
        _MODS["core"], _MODS["site"] = admin_core, admin_site
        _STORE = admin_core.Store(root)
    return _STORE


# 追踪 init 防刷：每 IP 10 分钟最多 120 次
_INIT_TIMES = {}
_INIT_LOCK = threading.Lock()


class DeckHandler(SimpleHTTPRequestHandler):
    server_version = "deck-static/1.0"
    sys_version = ""
    protocol_version = "HTTP/1.1"

    extensions_map = {**SimpleHTTPRequestHandler.extensions_map, **EXTRA_MIME}

    def end_headers(self):
        path = self.path.split("?")[0].lower()
        if (path.endswith((".html", ".htm")) or path in ("/", "")
                or path.startswith(("/api/", "/admin"))
                or re.match(r"^/decks/[^/]+/?$", path)):
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
        site = self._store()
        slug = None
        m = re.match(r"^/decks/([a-z0-9-]+)(/|$)", raw)
        if m:
            slug = m.group(1)
            cfg = site.deck_cfg(slug)
            if not cfg["enabled"]:                      # 下架：整目录 404（含缩略图）
                return self._send_html(404, _MODS["site"].disabled_page(self._deck_title(slug)))
            if cfg["locked"] and not site.check_token(
                    f"deck:{slug}", self._cookies().get(f"deck_auth_{slug}")):
                # 本机 + ?export=1 是缩略图采集专用通道；公网带此参数一律照样拦
                qs = parse_qs(urlparse(self.path).query)
                if not (qs.get("export") == ["1"] and self._is_local()):
                    if raw.endswith("/thumb.jpg"):
                        return self._send_bytes(200, "image/svg+xml", _MODS["site"].locked_thumb())
                    return self._send_html(200, _MODS["site"].gate_page(
                        slug, self._deck_title(slug), cfg["hint"]))
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
        rel = os.path.relpath(path, self.directory)
        # decks.json 同步剔除下架 deck（公网直拉元数据也不泄漏）
        if rel == "decks.json" and self.command == "GET":
            disabled = {s for s, c in site.access_map().items() if c and c.get("enabled") is False}
            if disabled:
                try:
                    dj = json.loads(data.decode("utf-8"))
                    dj["decks"] = [d for d in dj.get("decks", []) if d.get("slug") not in disabled]
                    data = json.dumps(dj, ensure_ascii=False, indent=2).encode("utf-8")
                except (json.JSONDecodeError, AttributeError):
                    pass
        # HTML 注入追踪脚本（?export=1 的本机缩略图采集不注入）；展示台首页额外做门禁过滤
        if ctype.startswith("text/html") and self.command == "GET":
            if not (parse_qs(urlparse(self.path).query).get("export") == ["1"] and self._is_local()):
                text = data.decode("utf-8", errors="replace")
                if slug:
                    tracker = _MODS["site"].tracker_script(slug)
                elif rel in ("library.html", "index.html", "index-web.html"):
                    if rel == "library.html":
                        text = _MODS["site"].filter_library_html(text, site.access_map())
                    tracker = _MODS["site"].tracker_script("__library")
                else:
                    tracker = None
                if tracker and "</body>" in text:
                    data = text.replace("</body>", tracker + "</body>", 1).encode("utf-8")

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
        if path.rstrip("/") == "/admin":
            return self._send_html(200, _MODS["site"].admin_page())
        if path.startswith("/api/"):
            return self.api_get(path)
        self._serve(head_only=False)

    def do_HEAD(self):
        path = self.path.split("?")[0]
        if path.rstrip("/") == "/admin":
            return self._send_html(200, _MODS["site"].admin_page())
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

    def _json_response(self, code, obj, headers=()):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        for k, v in headers:
            self.send_header(k, v)
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
        if path.startswith("/api/admin/"):
            return self.admin_get(path)
        if not self._api_guard():
            return
        if path == "/api/ping":
            return self._json_response(200, {"ok": True, "feature": "import"})
        if path == "/api/slug-exists":
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
        if path.startswith("/api/admin/"):
            return self.admin_post(path)
        if path.startswith("/api/track/"):
            return self.track_post(path)
        if path == "/api/access":
            return self.access_post()
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

    # ------------------------------------------------------------ /admin 管理后台 + 访问追踪 + 门禁
    # 这些接口经隧道公网也可用（追踪必须公网可写；admin 有密码 + 限流），
    # 不走导入 API 的本机 Host 守卫 —— 那道守卫只保护 /api/inventory|import|cancel|publish。
    ADMIN_COOKIE = "deck_admin"
    DECK_COOKIE_TTL = 30 * 86400

    def _store(self):
        return get_store(self.directory)

    def _cookies(self):
        out = {}
        for part in (self.headers.get("Cookie") or "").split(";"):
            if "=" in part:
                k, v = part.split("=", 1)
                out[k.strip()] = v.strip()
        return out

    def _client_ip(self):
        ip = self.headers.get("CF-Connecting-IP")          # cloudflared 隧道真实来源
        if not ip:
            xff = self.headers.get("X-Forwarded-For")
            if xff:
                ip = xff.split(",")[0].strip()
        return (ip or self.client_address[0])[:64]

    def _is_local(self):
        return bool(self.LOCAL_HOST.match((self.headers.get("Host") or "").strip()))

    def _deck_title(self, slug):
        try:
            with open(os.path.join(self.directory, "decks", slug, "deck.json"),
                      encoding="utf-8") as fh:
                meta = json.load(fh)
            if meta.get("title"):
                return str(meta["title"])
        except (OSError, json.JSONDecodeError):
            pass
        return slug

    def _send_html(self, code, text, headers=()):
        self._send_bytes(code, "text/html; charset=utf-8", text.encode("utf-8"), headers)

    def _send_bytes(self, code, ctype, body, headers=()):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in headers:
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    # ---- admin API ----
    def _admin_authed(self):
        return self._store().check_token("admin", self._cookies().get(self.ADMIN_COOKIE))

    def admin_get(self, path):
        st = self._store()
        if path == "/api/admin/session":
            return self._json_response(200, {"ok": True, "authed": self._admin_authed()})
        if not self._admin_authed():
            return self._json_response(401, {"ok": False, "error": "未登录"})
        if path == "/api/admin/overview":
            return self._json_response(200, {"ok": True, "stats": st.overview()})
        if path == "/api/admin/visits":
            q = parse_qs(urlparse(self.path).query)
            return self._json_response(200, {"ok": True,
                                             "visits": st.recent_visits((q.get("limit") or ["100"])[0])})
        if path == "/api/admin/decks":
            stats = st.deck_stats()
            decks = []
            for d in st.deck_list():
                d.update(st.deck_cfg(d["slug"]))
                d["stats"] = stats.get(d["slug"], {})
                decks.append(d)
            return self._json_response(200, {"ok": True, "decks": decks})
        if path == "/api/admin/slides":
            q = parse_qs(urlparse(self.path).query)
            deck = (q.get("deck") or ["__library"])[0]
            return self._json_response(200, {"ok": True, "deck": deck,
                                             "rows": st.slide_stats(deck)})
        return self._json_response(404, {"ok": False, "error": f"未知 API：{path}"})

    def admin_post(self, path):
        st = self._store()
        ip = self._client_ip()
        if path == "/api/admin/login":
            if not st.login_allowed(ip):
                return self._json_response(429, {"ok": False,
                                                 "error": "尝试次数过多，请 10 分钟后再试"})
            body = self._read_body()
            if body is None:
                return
            try:
                req = json.loads(body.decode("utf-8"))
            except Exception:
                return self._json_response(400, {"ok": False, "error": "JSON 解析失败"})
            if not isinstance(req.get("password"), str) or not st.verify_admin_password(req["password"]):
                st.login_fail(ip)
                return self._json_response(401, {"ok": False, "error": "密码不对"})
            tok = st.make_token("admin", _MODS["core"].SESSION_TTL)
            return self._json_response(200, {"ok": True}, headers=[(
                "Set-Cookie", f"{self.ADMIN_COOKIE}={tok}; Path=/; "
                              f"Max-Age={_MODS['core'].SESSION_TTL}; HttpOnly; SameSite=Lax")])
        if not self._admin_authed():
            return self._json_response(401, {"ok": False, "error": "未登录"})
        if path == "/api/admin/logout":
            return self._json_response(200, {"ok": True}, headers=[(
                "Set-Cookie", f"{self.ADMIN_COOKIE}=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax")])
        if path == "/api/admin/stats/clear":
            st.clear_stats()
            return self._json_response(200, {"ok": True})
        body = self._read_body() or b"{}"
        try:
            req = json.loads(body.decode("utf-8"))
        except Exception:
            return self._json_response(400, {"ok": False, "error": "JSON 解析失败"})
        if path == "/api/admin/deck":
            slug = str(req.get("slug") or "")
            if not re.fullmatch(r"[a-z0-9-]+", slug) or \
                    not os.path.isdir(os.path.join(self.directory, "decks", slug)):
                return self._json_response(400, {"ok": False, "error": "未知 deck"})
            kwargs = {}
            if "enabled" in req:
                kwargs["enabled"] = bool(req["enabled"])
            if "password" in req:                      # None/"" = 移除密码
                kwargs["password"] = req["password"]
            if "hint" in req:
                kwargs["hint"] = str(req["hint"])[:200]
            st.set_deck(slug, **kwargs)
            return self._json_response(200, {"ok": True, "cfg": st.deck_cfg(slug)})
        if path == "/api/admin/password":
            old, new = req.get("old"), req.get("new")
            if not isinstance(old, str) or not isinstance(new, str) or len(new) < 6:
                return self._json_response(400, {"ok": False, "error": "新密码至少 6 位"})
            if not st.verify_admin_password(old):
                return self._json_response(401, {"ok": False, "error": "当前密码不对"})
            st.set_admin_password(new)
            tok = st.make_token("admin", _MODS["core"].SESSION_TTL)
            return self._json_response(200, {"ok": True}, headers=[(
                "Set-Cookie", f"{self.ADMIN_COOKIE}={tok}; Path=/; "
                              f"Max-Age={_MODS['core'].SESSION_TTL}; HttpOnly; SameSite=Lax")])
        return self._json_response(404, {"ok": False, "error": f"未知 API：{path}"})

    # ---- 追踪 API（公网可写）----
    def track_post(self, path):
        st = self._store()
        body = self._read_body()
        if body is None:
            return
        try:
            req = json.loads(body.decode("utf-8"))
        except Exception:
            return self._json_response(400, {"ok": False, "error": "JSON 解析失败"})
        if path == "/api/track/init":
            deck = str(req.get("deck") or "")
            if deck != "__library" and not re.fullmatch(r"[a-z0-9-]{1,80}", deck):
                return self._json_response(400, {"ok": False, "error": "bad deck"})
            ip = self._client_ip()
            now = time.time()
            with _INIT_LOCK:                           # 轻量防刷
                times = [t for t in _INIT_TIMES.get(ip, []) if now - t < 600]
                if len(times) >= 120:
                    return self._json_response(429, {"ok": False, "error": "too many"})
                times.append(now)
                _INIT_TIMES[ip] = times
            vid = st.track_init(deck, str(req.get("visitor") or "")[:64] or "anon",
                                ip, self.headers.get("User-Agent") or "",
                                str(req.get("ref") or ""), req.get("n") or 0)
            return self._json_response(200, {"ok": True, "v": vid})
        if path in ("/api/track/beat", "/api/track/end"):
            try:
                vid = int(req.get("v"))
            except (TypeError, ValueError):
                return self._json_response(400, {"ok": False, "error": "bad visit"})
            items = req.get("items") if isinstance(req.get("items"), list) else []
            return self._json_response(200, {"ok": st.track_beat(vid, req.get("a") or 0, items)})
        return self._json_response(404, {"ok": False, "error": f"未知 API：{path}"})

    # ---- deck 门禁密码（公网可用，带限流）----
    def access_post(self):
        st = self._store()
        body = self._read_body()
        if body is None:
            return
        try:
            req = json.loads(body.decode("utf-8"))
        except Exception:
            return self._json_response(400, {"ok": False, "error": "JSON 解析失败"})
        slug = str(req.get("deck") or "")
        if not re.fullmatch(r"[a-z0-9-]+", slug):
            return self._json_response(400, {"ok": False, "error": "bad deck"})
        if not st.deck_cfg(slug)["locked"]:
            return self._json_response(200, {"ok": True, "redirect": f"/decks/{slug}/"})
        key = f"deck:{slug}:{self._client_ip()}"
        if not st.login_allowed(key):
            return self._json_response(429, {"ok": False, "error": "尝试次数过多，请 10 分钟后再试"})
        if not st.verify_deck_password(slug, str(req.get("password") or "")):
            st.login_fail(key)
            return self._json_response(401, {"ok": False, "error": "密码不对，再试试"})
        tok = st.make_token(f"deck:{slug}", self.DECK_COOKIE_TTL)
        cookie = (f"deck_auth_{slug}={tok}; Path=/; Max-Age={self.DECK_COOKIE_TTL}; "
                  f"HttpOnly; SameSite=Lax")
        return self._json_response(200, {"ok": True, "redirect": f"/decks/{slug}/"},
                                   headers=[("Set-Cookie", cookie)])

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
    ap.add_argument("--admin-password", metavar="PW",
                    help="设置/重置 /admin 管理员密码后退出（首次启动也可用环境变量 DECK_ADMIN_PASSWORD 初始化）")
    args = ap.parse_args()

    root = os.path.abspath(args.root)
    if not os.path.isfile(os.path.join(root, "index.html")):
        sys.exit(f"{root} 下没有 index.html")

    store = get_store(root)
    if args.admin_password:
        store.set_admin_password(args.admin_password)
        print("[admin] 管理员密码已更新（data/admin.json）", flush=True)
        return

    handler = partial(DeckHandler, directory=root)
    httpd = ThreadingHTTPServer((args.host, args.port), handler)
    httpd.daemon_threads = True
    print(f"[deck] {root}  →  http://{args.host}:{args.port}/", flush=True)
    if store.generated_password:
        print(f"[admin] 初始管理密码：{store.generated_password}", flush=True)
        print(f"[admin] → http://{'127.0.0.1' if args.host.startswith('127') or args.host == 'localhost' or args.host == '0.0.0.0' else args.host}:{args.port}/admin/（已写入 data/admin.json，不会再显示；可用 --admin-password PW 重置）", flush=True)
    else:
        print(f"[admin] /admin/ 已启用，登录密码见 data/admin.json（哈希存放，可 --admin-password PW 重置）", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[deck] bye", flush=True)


if __name__ == "__main__":
    main()
