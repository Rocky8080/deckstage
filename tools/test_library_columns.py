#!/usr/bin/env python3
"""
test_library_columns.py — 展示台首页 2 / 3 / 4 列切换自测

用法: python3 tools/test_library_columns.py
退出码 0 = 全部通过

在临时目录起独立服务（不碰本机 data/），用 Chrome 无头验证列数、记忆与响应式降级。
"""
from __future__ import annotations

import os
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

ok, fail = [], []


def check(name: str, cond: bool, extra: str = ""):
    (ok if cond else fail).append(name)
    print(("  ✓ " if cond else "  ✗ ") + name + (f"   {extra}" if extra and not cond else ""))


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def column_count(page) -> int:
    """按卡片左边缘去重得到当前列数（比读 CSS 更接近真实渲染）。"""
    return page.evaluate(
        "() => new Set([...document.querySelectorAll('.card')]"
        ".map(c => Math.round(c.getBoundingClientRect().left))).size")


def state(page) -> dict:
    return page.evaluate("""() => ({
      cols: document.documentElement.getAttribute('data-cols'),
      pressed: [...document.querySelectorAll('.cols button')].map(
        b => b.getAttribute('data-cols') + ':' + b.getAttribute('aria-pressed')),
      saved: localStorage.getItem('deck_library_cols'),
    })""")


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="deckstage-columns-"))
    site = tmp / "site"
    proc = None
    try:
        site.mkdir()
        (site / "index.html").write_text("<!doctype html><title>columns test</title>",
                                         encoding="utf-8")
        shutil.copy(ROOT / "library.html", site / "library.html")
        shutil.copy(ROOT / "decks.json", site / "decks.json")
        shutil.copytree(ROOT / "decks", site / "decks")
        port = free_port()
        base = f"http://127.0.0.1:{port}"
        proc = subprocess.Popen(
            [sys.executable, str(ROOT / "tools/serve_deck.py"),
             "--root", str(site), "--port", str(port)],
            cwd=str(ROOT), env=dict(os.environ, DECK_ADMIN_PASSWORD="columns-test"),
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
            page.goto(base + "/", wait_until="load")
            page.wait_for_timeout(400)

            check("默认 2 列", column_count(page) == 2, str(column_count(page)))
            check("默认选中 2 列", state(page)["cols"] == "2" and
                  state(page)["pressed"] == ["2:true", "3:false", "4:false"])
            check("首次访问无本机记忆", state(page)["saved"] is None)

            page.click('.cols button[data-cols="3"]')
            page.wait_for_timeout(250)
            check("点 3 列后渲染 3 列", column_count(page) == 3, str(column_count(page)))
            check("3 列按钮选中", state(page)["pressed"] == ["2:false", "3:true", "4:false"])
            check("记住 3 列", state(page)["saved"] == "3")

            page.click('.cols button[data-cols="4"]')
            page.wait_for_timeout(250)
            check("点 4 列后渲染 4 列", column_count(page) == 4, str(column_count(page)))
            check("4 列按钮选中", state(page)["pressed"] == ["2:false", "3:false", "4:true"])
            check("记住 4 列", state(page)["saved"] == "4")

            page.reload(wait_until="load")
            page.wait_for_timeout(400)
            check("刷新后仍是 4 列", column_count(page) == 4 and state(page)["cols"] == "4")
            check("刷新后按钮回显正确", state(page)["pressed"] == ["2:false", "3:false", "4:true"])

            page.set_viewport_size({"width": 390, "height": 844})
            page.wait_for_timeout(300)
            check("手机宽度降为 1 列", column_count(page) == 1, str(column_count(page)))
            check("手机宽度隐藏列数按钮", not page.locator(".colbar").is_visible())

            page.set_viewport_size({"width": 1000, "height": 900})
            page.wait_for_timeout(300)
            check("1000px 时 4 列降为 3 列", column_count(page) == 3, str(column_count(page)))

            page.set_viewport_size({"width": 860, "height": 900})
            page.wait_for_timeout(300)
            check("860px 时 4 列降为 2 列", column_count(page) == 2, str(column_count(page)))

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
