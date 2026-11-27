#!/usr/bin/env python3
"""
test_admin_order.py — 后台「首页排序」集成自测（API → library.html / decks.json 即时生效）

用法: python3 tools/test_admin_order.py
退出码 0 = 全部通过

测试在临时根目录里起一个独立 serve_deck.py，不碰本机 data/ 与已运行的服务。
"""
from __future__ import annotations

import _platform  # noqa: F401  — Windows GBK 管道下的 stdout UTF-8 兜底（见 _platform.py）
import http.cookiejar
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PASSWORD = "test-admin-order-pw"

ok, fail = [], []


def check(name: str, cond: bool, extra: str = ""):
    (ok if cond else fail).append(name)
    print(("  ✓ " if cond else "  ✗ ") + name + (f"   {extra}" if extra and not cond else ""))


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def card_slugs(html: str) -> list[str]:
    grid = re.search(r'<main class="grid">([\s\S]*?)</main>', html)
    return re.findall(r'href="/decks/([a-z0-9-]+)/"', grid.group(1)) if grid else []


class Client:
    def __init__(self, base: str):
        self.base = base
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.jar))

    def call(self, method: str, path: str, payload=None):
        data = None
        headers = {}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(self.base + path, data=data, method=method,
                                     headers=headers)
        try:
            with self.opener.open(req, timeout=10) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read()

    def json(self, method: str, path: str, payload=None):
        status, body = self.call(method, path, payload)
        try:
            return status, json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return status, {}

    def html(self, path: str = "/") -> str:
        status, body = self.call("GET", path)
        return body.decode("utf-8", errors="replace") if status == 200 else ""


def wait_ready(base: str, proc: subprocess.Popen, timeout: float = 15.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            return False
        try:
            with urllib.request.urlopen(base + "/", timeout=1) as resp:
                if resp.status == 200:
                    return True
        except (urllib.error.URLError, ConnectionError, TimeoutError):
            time.sleep(0.1)
    return False


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="deckstage-order-"))
    site = tmp / "site"
    proc = None
    try:
        site.mkdir()
        (site / "index.html").write_text("<!doctype html><title>order test</title>",
                                         encoding="utf-8")
        shutil.copy(ROOT / "library.html", site / "library.html")
        shutil.copy(ROOT / "decks.json", site / "decks.json")
        shutil.copytree(ROOT / "decks", site / "decks")

        port = free_port()
        base = f"http://127.0.0.1:{port}"
        env = dict(os.environ, DECK_ADMIN_PASSWORD=PASSWORD)
        proc = subprocess.Popen(
            [sys.executable, str(ROOT / "tools/serve_deck.py"),
             "--root", str(site), "--port", str(port)],
            cwd=str(ROOT), env=env, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True)
        if not wait_ready(base, proc):
            print("服务没有起来：")
            try:
                print(proc.communicate(timeout=3)[0])
            except Exception:                                   # noqa: BLE001
                pass
            return 1
        print(f"\n临时站点 {site}  ·  {base}\n")

        anon = Client(base)
        status, _ = anon.call("GET", "/api/admin/decks")
        check("未登录读内容清单 → 401", status == 401, str(status))
        status, _ = anon.call("POST", "/api/admin/library/order",
                              {"slugs": ["x"]})
        check("未登录写顺序 → 401", status == 401, str(status))

        client = Client(base)
        status, body = client.json("POST", "/api/admin/login", {"password": "wrong"})
        check("错误管理密码 → 401", status == 401 and body.get("ok") is False, str(status))
        status, body = client.json("POST", "/api/admin/login", {"password": PASSWORD})
        check("正确管理密码可登录", status == 200 and body.get("ok") is True, str(status))

        status, body = client.json("GET", "/api/admin/decks")
        default_order = body.get("order") or []
        check("内容清单返回顺序数组", status == 200 and bool(default_order), str(status))
        check("初始为默认顺序", body.get("custom_order") is False, str(body.get("custom_order")))
        decks = {d["slug"]: d for d in body.get("decks", []) if d["slug"] != "__library"}
        check("顺序数组与 deck 清单一致",
              set(default_order) == set(decks) and len(default_order) == len(decks))
        check("每套 deck 都有首页位置",
              all(d.get("position") for d in decks.values()))
        check("初始首页按默认顺序（即便静态页曾按自定义顺序构建）",
              card_slugs(client.html("/")) == default_order)

        wanted = list(reversed(default_order))
        status, body = client.json("POST", "/api/admin/library/order", {"slugs": wanted})
        check("保存自定义顺序 → 200", status == 200 and body.get("ok") is True, str(status))
        check("接口回显新顺序", body.get("order") == wanted, str(body.get("order")))
        check("标记为自定义顺序", body.get("custom_order") is True)

        order_file = site / "data" / "library.json"
        check("顺序写入 data/library.json", order_file.is_file())
        if order_file.is_file():
            saved = json.loads(order_file.read_text(encoding="utf-8"))
            check("落盘顺序与请求一致", saved.get("order") == wanted)
            check("顺序文件权限为 0600", (order_file.stat().st_mode & 0o777) == 0o600,
                  oct(order_file.stat().st_mode & 0o777))

        home = client.html("/")
        check("首页卡片按新顺序展示", card_slugs(home) == wanted, str(card_slugs(home))[:120])
        static = client.html("/library.html")
        check("library.html 直连同样生效", card_slugs(static) == wanted)
        status, raw = client.call("GET", "/decks.json")
        served = json.loads(raw.decode("utf-8"))
        check("decks.json 同步重排",
              [d["slug"] for d in served.get("decks", [])] == wanted)
        with urllib.request.urlopen(base + "/decks.json", timeout=10) as resp:
            check("decks.json 禁用客户端缓存", "no-cache" in (resp.headers.get("Cache-Control") or ""),
                  resp.headers.get("Cache-Control") or "")
        status, body = client.json("GET", "/api/admin/decks")
        check("管理端回读自定义顺序", body.get("order") == wanted and
              body.get("custom_order") is True)
        new_rows = {d["slug"]: d for d in body.get("decks", []) if d["slug"] != "__library"}
        check("管理端位置编号按新顺序",
              bool(new_rows) and all(new_rows[s]["position"] == i + 1
                                     for i, s in enumerate(wanted)))

        for bad, note in ((["nope"], "未知 deck"),
                          ([wanted[0], wanted[0]], "重复 slug"),
                          ([], "空数组"),
                          ("not-a-list", "非数组")):
            status, body = client.json("POST", "/api/admin/library/order",
                                       {"slugs": bad})
            check(f"拒绝{note}（400）", status == 400 and body.get("ok") is False, str(status))

        status, body = client.json("POST", "/api/admin/library/order", {"reset": True})
        check("恢复默认顺序 → 200", status == 200 and body.get("ok") is True, str(status))
        check("恢复后回到默认顺序", body.get("order") == default_order,
              str(body.get("order"))[:120])
        check("恢复后标记为默认", body.get("custom_order") is False)
        check("恢复后删除顺序文件", not order_file.exists())
        check("首页恢复默认顺序", card_slugs(client.html("/")) == default_order)

        status, body = client.json("GET", "/api/admin/decks")
        check("恢复后管理端顺序同步", body.get("order") == default_order and
              body.get("custom_order") is False)
    finally:
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        shutil.rmtree(tmp, ignore_errors=True)

    print(f"\n{len(ok)} 通过 · {len(fail)} 失败")
    return 0 if not fail else 1


if __name__ == "__main__":
    sys.exit(main())
