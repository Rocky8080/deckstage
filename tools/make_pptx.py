#!/usr/bin/env python3
"""
make_pptx.py — 像素保真版 PPTX（每屏 3200×1800 截图，全出血贴进 13.333×7.5in 幻灯片）

用法:
    python3 tools/make_pptx.py                      # → deck-图片版.pptx（-o 改名）
    python3 tools/make_pptx.py -o out.pptx --dpi 2

特点：所见即所得，不可改字。需要改字请用页面内「导出 PPTX（可编辑）」。
"""
import argparse
import io
import sys
from pathlib import Path

from pptx import Presentation
from pptx.util import Inches, Emu

ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / "index.html"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-o", "--out", default="deck-图片版.pptx")
    ap.add_argument("--dpi", type=float, default=2.0, help="截图倍率（2 → 3200×1800）")
    ap.add_argument("--width", type=int, default=1600)
    ap.add_argument("--height", type=int, default=900)
    args = ap.parse_args()

    if not INDEX.exists():
        sys.exit("找不到 index.html，先 node build.mjs")

    from playwright.sync_api import sync_playwright

    url = INDEX.as_uri() + "?export=1"
    shots = []

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        page = browser.new_context(
            viewport={"width": args.width, "height": args.height},
            device_scale_factor=args.dpi,
        ).new_page()
        page.goto(url, wait_until="load")
        page.wait_for_timeout(600)
        page.evaluate("() => document.fonts ? document.fonts.ready : null")
        # 按屏懒加载的 deck：先把当前屏/全屏图片水合回来，再等图片与字体
        page.evaluate("() => window.__deckHydrate && window.__deckHydrate(0, 999)")
        page.evaluate("""() => Promise.all([...document.images].map(i => i.complete ? 1 :
            new Promise(r => { i.onload = i.onerror = r; })))""")
        page.wait_for_timeout(400)

        ids = page.evaluate("() => [...document.querySelectorAll('.slide')].map(s => s.id)")
        print(f"屏数 {len(ids)}")

        for sid in ids:
            # 关键：导出模式下所有屏叠在一起，逐屏隔离后再截
            page.evaluate(
                """(id) => {
                    document.querySelectorAll('.slide').forEach(el => {
                        el.style.display = (el.id === id) ? 'flex' : 'none';
                    });
                }""", sid)
            page.wait_for_timeout(140)
            png = page.query_selector(f"#{sid}").screenshot()
            shots.append((sid, png))
            print(f"  {sid}  {len(png)//1024} KB")

        browser.close()

    prs = Presentation()
    prs.slide_width = Inches(13.333333)
    prs.slide_height = Inches(7.5)
    blank = prs.slide_layouts[6]

    for sid, png in shots:
        s = prs.slides.add_slide(blank)
        s.shapes.add_picture(io.BytesIO(png), 0, 0,
                             width=prs.slide_width, height=prs.slide_height)

    out = ROOT / args.out
    prs.save(out)
    print(f"\n已生成 {out.relative_to(ROOT)} · {len(shots)} 页 · "
          f"{out.stat().st_size/1e6:.1f} MB · 13.333×7.5in")


if __name__ == "__main__":
    main()
