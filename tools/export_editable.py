#!/usr/bin/env python3
"""tools/export_editable.py — 无头跑「浏览器内可编辑版」导出（A 路径）

用 Playwright(本机 Chrome) 打开页面，执行 page.evaluate("window.deckExportPptx()")
并拦截浏览器下载，把 .pptx 存到指定位置。

用法：
  # 对真实 deck（项目根 index.html）
  python3 tools/export_editable.py

  # 对 3 屏自测页
  python3 tools/export_editable.py --root tools/fixtures --out tools/fixtures/out/fixture-editable.pptx

  # 只测量不下载（排查 DOM -> PPT 还原问题）
  python3 tools/export_editable.py --dry-run

退出码：0 成功，1 失败
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from serve import start_server, project_root  # noqa: E402

DEFAULT_NAME = "deck-可编辑.pptx"


def main(argv=None):
    ap = argparse.ArgumentParser(description="无头导出可编辑版 PPTX")
    ap.add_argument("--root", default=None, help="站点根目录，默认项目根")
    ap.add_argument("--page", default="index.html", help="入口页面")
    ap.add_argument("--query", default="export=1",
                    help="附加 query，默认 export=1（静态终态：揭示动画全显示、数字落终值、隐藏 chrome）")
    ap.add_argument("--out", default=None, help="输出路径，默认 <项目根>/<默认文件名>")
    ap.add_argument("--port", type=int, default=0, help="静态服务器端口，0=自动")
    ap.add_argument("--timeout", type=float, default=240.0, help="下载等待秒数")
    ap.add_argument("--dry-run", action="store_true", help="只测量并打印报告，不生成文件")
    ap.add_argument("--headed", action="store_true", help="显示浏览器窗口")
    ap.add_argument("--viewport", default="1680x1000")
    ap.add_argument("--no-serve", default=None, help="直接用这个 URL，不启动本地服务器（也支持 file://）")
    ap.add_argument("--click", default=None,
                    help="不调 API，改为点击页面元素触发导出（模拟用户点按钮），如 '[data-act=export]'")
    a = ap.parse_args(argv)

    root = os.path.abspath(a.root or project_root())
    out = a.out or os.path.join(root, DEFAULT_NAME)
    if not a.dry_run:
        os.makedirs(os.path.dirname(os.path.abspath(out)) or ".", exist_ok=True)

    httpd = None
    if a.no_serve:
        url = a.no_serve
    else:
        httpd, port, _ = start_server(root, a.port)
        if a.query:
            sep = "&" if "?" in a.page else "?"
            url = "http://127.0.0.1:%d/%s%s%s" % (port, a.page, sep, a.query)
        else:
            url = "http://127.0.0.1:%d/%s" % (port, a.page)

    from playwright.sync_api import sync_playwright

    vw, vh = (int(x) for x in a.viewport.lower().split("x"))
    report = None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=not a.headed)
            context = browser.new_context(
                viewport={"width": vw, "height": vh},
                device_scale_factor=1,
                accept_downloads=True,
            )
            page = context.new_page()
            page.on("console", lambda m: print("[page:%s] %s" % (m.type, m.text)) if m.type in ("error", "warning") else None)
            page.on("pageerror", lambda e: print("[pageerror] %s" % e, file=sys.stderr))

            print("→ 打开 %s" % url, flush=True)
            page.goto(url, wait_until="networkidle", timeout=60000)
            page.wait_for_function("() => typeof window.deckExportPptx === 'function'", timeout=30000)
            # 等字体 + 图片 decode 完成，否则测量到的是「还没渲染」的状态
            page.evaluate("() => (document.fonts && document.fonts.ready) || true")
            page.evaluate(
                "() => Promise.all(Array.from(document.images).map("
                "i => i.complete ? 1 : new Promise(r => { i.onload = i.onerror = r; })))"
            )
            page.wait_for_timeout(300)

            if a.dry_run:
                report = page.evaluate("() => window.deckExportPptx({dryRun: true})")
                print(json.dumps(report, ensure_ascii=False, indent=2))
            else:
                if a.click:
                    print("→ 点击 %s 触发导出（模拟用户点按钮）…" % a.click, flush=True)
                    with page.expect_download(timeout=a.timeout * 1000) as dl_info:
                        page.click(a.click)
                    page.wait_for_timeout(400)
                    report = page.evaluate("() => window.deckExportPptx.lastReport")
                else:
                    print("→ 执行 window.deckExportPptx() …", flush=True)
                    with page.expect_download(timeout=a.timeout * 1000) as dl_info:
                        report = page.evaluate("() => window.deckExportPptx()")
                download = dl_info.value
                suggested = download.suggested_filename
                download.save_as(out)
                size = os.path.getsize(out)
                print("→ 浏览器建议文件名: %s" % suggested)
                print("→ 已保存: %s (%.1f KB)" % (out, size / 1024.0))
                if report:
                    report["savedAs"] = out
                    report["bytes"] = size
                    print(json.dumps(report, ensure_ascii=False, indent=2))
            browser.close()
    finally:
        if httpd is not None:
            httpd.shutdown()
            httpd.server_close()

    if report is None:
        print("❌ 没有拿到导出报告", file=sys.stderr)
        return 1
    warnings = report.get("warnings") or []
    if warnings:
        print("\n⚠️  %d 条警告:" % len(warnings), file=sys.stderr)
        for w in warnings[:20]:
            print("   - %s" % w, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
