#!/usr/bin/env python3
"""tools/export_pptx_images.py — 无头「像素保真图片版」导出（B 路径）

Playwright 打开 http://127.0.0.1:PORT/index.html?export=1（导出模式，隐藏所有 chrome），
逐屏截图 3200×1800（1600×900 CSS × dsf2），再用 python-pptx 生成
13.333×7.5in 全出血（无白边）图片版 .pptx。

用法：
  python3 tools/export_pptx_images.py                        # 真实 deck -> 项目根
  python3 tools/export_pptx_images.py --root tools/fixtures \
      --out tools/fixtures/out/fixture-images.pptx

退出码：0 成功，1 失败
"""
import argparse
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from serve import start_server, project_root  # noqa: E402

DEFAULT_NAME = "deck-保真图片版.pptx"
EMU_W = 12192000  # 13.3333in * 914400
EMU_H = 6858000   # 7.5in  * 914400
CSS_W, CSS_H = 1600, 900
DSF = 2

FORCE_EXPORT_JS = r"""
() => {
  const out = { deck: false, stageReset: false };
  // 1) 优先用 deck 提供的缩放钩子
  try {
    const d = window.__deck;
    if (d) {
      out.deck = true;
      if (typeof d.setScale === 'function') { d.setScale(1); }
      else if (typeof d.withScale1 === 'function') {
        // 只用来触发一次「缩放到 1」，随即恢复由下面 inline style 接管
        d.withScale1(() => {});
      }
    }
  } catch (e) { out.deckError = String(e); }
  // 2) 强制舞台 transform 为 none（inline !important 覆盖样式表）
  const sels = ['.stage', '.deck-stage', '#stage', '.deck-viewport', '.stage-inner'];
  for (const sel of sels) {
    for (const el of document.querySelectorAll(sel)) {
      el.style.setProperty('transform', 'none', 'important');
      el.style.setProperty('transition', 'none', 'important');
      el.style.setProperty('zoom', '1', 'important');
      out.stageReset = true;
    }
  }
  // 3) 导出模式：隐藏 chrome（deck.js 在 ?export=1 时也会做，这里兜底）
  document.body.classList.add('exporting');
  document.documentElement.classList.add('exporting');
  const css = document.createElement('style');
  css.id = '__pptx_export_hide_chrome';
  css.textContent = `
    body.exporting .deck-chrome, body.exporting .deck-topbar, body.exporting .deck-toolbar,
    body.exporting .deck-progress, body.exporting .deck-pager, body.exporting .deck-nav,
    body.exporting .deck-hint, body.exporting [data-chrome], body.exporting [data-export] {
      display: none !important;
    }
    body.exporting { overflow: visible !important; }
    html.exporting { overflow: visible !important; }
  `;
  document.head.appendChild(css);
  return out;
}
"""

WAIT_IMAGES_JS = r"""
() => {
  const imgs = Array.from(document.images).filter(i => !i.complete);
  return Promise.all(imgs.map(i => i.decode().catch(() => null))).then(() => {
    const bg = getComputedStyle(document.body).backgroundImage;
    return { pending: imgs.length, bodyBg: bg === 'none' ? null : 'has-bg' };
  });
}
"""

# 关键：?export=1 下所有 .slide 都是 position:absolute; inset:0 叠在一起，
# 直接对元素截图会全部截到同一屏 —— 每屏截图前只留目标屏可见。
ISOLATE_JS = r"""
(i) => {
  const sel = %s;
  const els = Array.from(document.querySelectorAll(sel));
  els.forEach((e, j) => {
    if (j === i) e.style.removeProperty('display');
    else e.style.display = 'none';
  });
  return { total: els.length, visible: i };
}
"""

ISOLATE_RESTORE_JS = r"""
() => {
  document.querySelectorAll(%s).forEach(e => e.style.removeProperty('display'));
  return true;
}
"""


def main(argv=None):
    ap = argparse.ArgumentParser(description="无头导出像素保真图片版 PPTX")
    ap.add_argument("--root", default=None, help="站点根目录，默认项目根")
    ap.add_argument("--page", default="index.html")
    ap.add_argument("--query", default="export=1", help="附加 query（默认 export=1）")
    ap.add_argument("--out", default=None, help="输出路径，默认 <项目根>/<默认文件名>")
    ap.add_argument("--port", type=int, default=0)
    ap.add_argument("--selector", default="section.slide", help="幻灯片元素选择器")
    ap.add_argument("--expect-slides", type=int, default=0, help="期望页数（>0 时校验）")
    ap.add_argument("--keep-shots", default=None, help="把 PNG 截图保留到这个目录")
    ap.add_argument("--headed", action="store_true")
    ap.add_argument("--settle-ms", type=int, default=350, help="每屏截图前等待毫秒")
    ap.add_argument("--no-serve", default=None, help="直接用这个 URL")
    a = ap.parse_args(argv)

    from PIL import Image

    root = os.path.abspath(a.root or project_root())
    out = a.out or os.path.join(root, DEFAULT_NAME)
    os.makedirs(os.path.dirname(os.path.abspath(out)) or ".", exist_ok=True)

    if a.keep_shots:
        shots_dir = os.path.abspath(a.keep_shots)
        os.makedirs(shots_dir, exist_ok=True)
        tmp = None
    else:
        tmp = tempfile.mkdtemp(prefix="pptx-shots-")
        shots_dir = tmp

    httpd = None
    if a.no_serve:
        url = a.no_serve
    else:
        httpd, port, _ = start_server(root, a.port)
        sep = "&" if "?" in a.page else "?"
        url = "http://127.0.0.1:%d/%s%s%s" % (port, a.page, sep, a.query)

    from playwright.sync_api import sync_playwright

    shots = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=not a.headed)
            context = browser.new_context(
                viewport={"width": CSS_W, "height": CSS_H},
                device_scale_factor=DSF,
            )
            page = context.new_page()
            page.on("pageerror", lambda e: print("[pageerror] %s" % e, file=sys.stderr))
            print("→ 打开 %s" % url, flush=True)
            page.goto(url, wait_until="networkidle", timeout=90000)
            page.wait_for_timeout(500)
            info = page.evaluate(FORCE_EXPORT_JS)
            print("→ 导出模式: %s" % info)
            page.evaluate("() => (document.fonts && document.fonts.ready) || true")
            page.evaluate(WAIT_IMAGES_JS)
            page.wait_for_timeout(a.settle_ms)

            loc = page.locator(a.selector)
            n = loc.count()
            print("→ 找到 %d 屏（%s）" % (n, a.selector))
            if n == 0:
                raise SystemExit("没有找到任何幻灯片元素：%s" % a.selector)
            if a.expect_slides and n != a.expect_slides:
                print("⚠️ 页数 %d != 期望 %d" % (n, a.expect_slides), file=sys.stderr)

            for i in range(n):
                # 1) 隔离：只让第 i 屏可见（其余 display:none），否则会全是同一屏
                page.evaluate(ISOLATE_JS % json.dumps(a.selector), i)
                page.wait_for_timeout(60)
                el = loc.nth(i)
                el.scroll_into_view_if_needed()
                page.wait_for_timeout(120)
                path = os.path.join(shots_dir, "slide-%02d.png" % (i + 1))
                el.screenshot(path=path, animations="disabled")
                with Image.open(path) as im:
                    w, h = im.size
                # 2) 尺寸不符（被裁剪/被缩放）时用 page.screenshot(clip=...) 兜底
                if (w, h) != (CSS_W * DSF, CSS_H * DSF):
                    box = el.bounding_box()
                    if box:
                        print("   ⚠️ 元素截图 %dx%d 不符，改用 clip 兜底 (%s)" % (w, h, box), file=sys.stderr)
                        page.screenshot(path=path, clip={
                            "x": box["x"], "y": box["y"],
                            "width": box["width"], "height": box["height"],
                        })
                        with Image.open(path) as im:
                            w, h = im.size
                shots.append((i + 1, path, w, h))
                print("   [%02d/%02d] %dx%d  %s" % (i + 1, n, w, h, os.path.basename(path)))
            page.evaluate(ISOLATE_RESTORE_JS % json.dumps(a.selector))
            browser.close()
    finally:
        if httpd is not None:
            httpd.shutdown()
            httpd.server_close()

    # ---- 组装 pptx ----
    from pptx import Presentation
    from pptx.util import Emu

    prs = Presentation()
    prs.slide_width = Emu(EMU_W)
    prs.slide_height = Emu(EMU_H)
    blank = prs.slide_layouts[6]  # Blank
    mismatched = []
    for idx, path, w, h in shots:
        if (w, h) != (CSS_W * DSF, CSS_H * DSF):
            mismatched.append((idx, w, h))
        slide = prs.slides.add_slide(blank)
        slide.shapes.add_picture(path, Emu(0), Emu(0), width=Emu(EMU_W), height=Emu(EMU_H))
    prs.save(out)

    size = os.path.getsize(out)
    print("\n✅ 已生成: %s (%.1f KB)" % (out, size / 1024.0))
    print("   页数: %d   尺寸: %.4f x %.4f in (16:9)   图片: 全出血" % (
        len(shots), EMU_W / 914400.0, EMU_H / 914400.0))
    if mismatched:
        print("⚠️ 以下截图不是 %dx%d（会被拉伸到满屏）：%s" % (
            CSS_W * DSF, CSS_H * DSF, mismatched), file=sys.stderr)
    if a.keep_shots:
        print("   PNG 保留在: %s" % shots_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
