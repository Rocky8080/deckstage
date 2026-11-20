#!/usr/bin/env python3
"""
test_admin_ui.py — 后台「首页排序」面板的浏览器交互自测（↑↓ / 拖动 / 恢复默认）

用法: python3 tools/test_admin_ui.py
退出码 0 = 全部通过

和 test_admin_order.py 一样在临时目录起独立服务；需要 Chrome（playwright channel="chrome"）。
"""
from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

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


def card_slugs(base: str) -> list[str]:
    html = urllib.request.urlopen(base + "/", timeout=5).read().decode("utf-8")
    grid = re.search(r'<main class="grid">([\s\S]*?)</main>', html)
    return re.findall(r'href="/decks/([a-z0-9-]+)/"', grid.group(1)) if grid else []


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="deckstage-admin-ui-"))
    site = tmp / "site"
    proc = None
    try:
        site.mkdir()
        (site / "index.html").write_text("<!doctype html><title>admin ui test</title>",
                                         encoding="utf-8")
        shutil.copy(ROOT / "library.html", site / "library.html")
        shutil.copy(ROOT / "decks.json", site / "decks.json")
        shutil.copytree(ROOT / "decks", site / "decks")
        port = free_port()
        base = f"http://127.0.0.1:{port}"
        proc = subprocess.Popen(
            [sys.executable, str(ROOT / "tools/serve_deck.py"),
             "--root", str(site), "--port", str(port)],
            cwd=str(ROOT), env=dict(os.environ, DECK_ADMIN_PASSWORD=PASSWORD),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        for _ in range(150):
            try:
                urllib.request.urlopen(base + "/", timeout=1)
                break
            except Exception:                                   # noqa: BLE001
                time.sleep(0.1)
        else:
            print("服务没有起来：")
            try:
                print(proc.communicate(timeout=3)[0])
            except Exception:                                   # noqa: BLE001
                pass
            return 1
        print(f"\n临时站点 {site}  ·  {base}\n")

        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=True)
            page = browser.new_context(viewport={"width": 1440, "height": 1000}).new_page()
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(base + "/admin/", wait_until="load")
            page.fill("#pw", PASSWORD)
            page.click("#loginBtn")
            page.wait_for_selector("#orderBox li", timeout=10000)
            page.wait_for_timeout(400)

            api = page.evaluate(
                "() => fetch('/api/admin/decks').then(r => r.json())")
            default_order = api.get("order") or []
            dom_order = page.evaluate(
                "[...document.querySelectorAll('#orderBox li')].map(li => li.dataset.slug)")
            check("排序面板列出全部 deck", len(dom_order) == len(default_order),
                  f"{len(dom_order)} != {len(default_order)}")
            check("面板顺序与接口一致", dom_order == default_order)
            check("默认顺序不显示「恢复默认」", page.locator("#orderReset").is_hidden())

            # ↓ 把第一项下移一位 → 自动保存并即时重排首页
            with page.expect_response(lambda r: "/api/admin/library/order" in r.url):
                page.click("#orderBox li:first-child .ord-down")
            page.wait_for_timeout(1000)
            want = [default_order[1], default_order[0]] + default_order[2:]
            check("点击 ↓ 后首页立即换位", card_slugs(base) == want)
            check("自定义顺序后显示「恢复默认」",
                  page.locator("#orderReset").is_visible())

            # HTML5 拖动：把第一项拖到最后一位
            page.evaluate("""() => {
              const list = document.getElementById('orderList');
              const items = [...list.querySelectorAll('li')];
              const first = items[0], last = items[items.length - 1];
              const dt = new DataTransfer();
              first.dispatchEvent(new DragEvent('dragstart', {bubbles: true, dataTransfer: dt}));
              const rect = last.getBoundingClientRect();
              last.dispatchEvent(new DragEvent('dragover', {bubbles: true, cancelable: true,
                dataTransfer: dt, clientY: rect.bottom - 1}));
              last.dispatchEvent(new DragEvent('drop', {bubbles: true, cancelable: true,
                dataTransfer: dt}));
              first.dispatchEvent(new DragEvent('dragend', {bubbles: true, dataTransfer: dt}));
            }""")
            page.wait_for_timeout(1200)
            dragged = card_slugs(base)
            check("拖拽后首项移到末尾", dragged == want[1:] + [want[0]])
            check("拖拽结束后整理状态",
                  page.locator("#orderBox li.dragging").count() == 0)

            # 恢复默认
            page.on("dialog", lambda d: d.accept())
            with page.expect_response(lambda r: "/api/admin/library/order" in r.url):
                page.click("#orderReset")
            page.wait_for_timeout(1000)
            check("恢复默认顺序后首页复原", card_slugs(base) == default_order)
            check("恢复默认后隐藏「恢复默认」按钮",
                  page.locator("#orderReset").is_hidden())
            check("页面没有脚本错误", not errors, " | ".join(errors)[:200])
            browser.close()
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
