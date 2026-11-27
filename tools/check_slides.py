#!/usr/bin/env python3
"""
check_slides.py — HTML 幻灯片体检（溢出 / 文字截断 / 重叠 / 图片 / 控制台报错）

用法:
    python3 tools/check_slides.py                  # 全部屏检查
    python3 tools/check_slides.py --shots          # 顺带每屏截图到 /tmp/qa/
    python3 tools/check_slides.py --only s07,s08   # 只查指定屏
    python3 tools/check_slides.py --shots --only s16

退出码: 0 = 没问题, 1 = 有问题（终端会列出可操作的清单）
"""
import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / "index.html"
SHOT_DIR = Path("/tmp/qa")

JS_COLLECT = r"""
() => {
  const slides = [...document.querySelectorAll('.slide')];
  const out = [];
  for (const slide of slides) {
    const sb = slide.getBoundingClientRect();
    const issues = [];
    const imported = slide.hasAttribute('data-imported');   // 几何直接来自 pptx：允许层叠与出血
    const seen = new Set();

    // 1) 画布自身溢出（有 data-bleed 装饰性出血的屏跳过）
    const hasBleed = !!slide.querySelector('[data-bleed]');
    if (!hasBleed && (slide.scrollHeight > __H__ + 2 || slide.scrollWidth > __W__ + 2)) {
      issues.push({ kind: 'slide-overflow', detail: `scroll ${slide.scrollWidth}x${slide.scrollHeight} > __W__x__H__` });
    }

    if (imported) {
      for (const img of slide.querySelectorAll('img')) {
        if (!img.complete || img.naturalWidth === 0) issues.push({ kind: 'img-broken', el: 'img' });
      }
      out.push({ id: slide.id, rail: slide.dataset.rail || '', title: slide.dataset.title || '', issues });
      continue;
    }
    // 2) 元素越界（右侧/下方/上方）
    const all = [...slide.querySelectorAll('*')];
    for (const el of all) {
      if (el.closest('.notes')) continue;
      const cs = getComputedStyle(el);
      if (cs.display === 'none' || cs.visibility === 'hidden' || +cs.opacity < 0.02) continue;
      if (cs.position === 'fixed') continue;
      if (el.closest('[data-bleed]')) continue;   // 有意出血的装饰
      const r = el.getBoundingClientRect();
      if (r.width === 0 || r.height === 0) continue;
      const id = el.tagName.toLowerCase() + (el.className && typeof el.className === 'string'
        ? '.' + el.className.trim().split(/\s+/).slice(0, 3).join('.') : '');
      const label = (el.textContent || '').trim().slice(0, 26);

      if (r.right > sb.right + 1.5) issues.push({ kind: 'overflow-right', el: id, text: label, by: +(r.right - sb.right).toFixed(1) });
      if (r.bottom > sb.bottom + 1.5) issues.push({ kind: 'overflow-bottom', el: id, text: label, by: +(r.bottom - sb.bottom).toFixed(1) });
      if (r.left < sb.left - 1.5) issues.push({ kind: 'overflow-left', el: id, text: label, by: +(sb.left - r.left).toFixed(1) });
      if (r.top < sb.top - 1.5) issues.push({ kind: 'overflow-top', el: id, text: label, by: +(sb.top - r.top).toFixed(1) });

      // 3) 文字被框截断（有固定宽高又 overflow hidden 的元素）
      if (cs.overflow === 'hidden' && el.scrollWidth > el.clientWidth + 2 && (el.textContent || '').trim()) {
        issues.push({ kind: 'text-clipped-x', el: id, text: label, by: el.scrollWidth - el.clientWidth });
      }
      if (cs.overflow === 'hidden' && el.scrollHeight > el.clientHeight + 2 && (el.textContent || '').trim()
          && el.clientHeight > 0 && cs.display !== 'inline') {
        issues.push({ kind: 'text-clipped-y', el: id, text: label, by: el.scrollHeight - el.clientHeight });
      }

      // 4) 图片没加载
      if (el.tagName === 'IMG' && (!el.complete || el.naturalWidth === 0)) {
        issues.push({ kind: 'img-broken', el: id, text: el.getAttribute('src') });
      }
    }

    // 5) 文本块互相重叠（只报高度重合的）
    const texts = [...slide.querySelectorAll('h1,h2,h3,h4,p,li,span,div,strong,em,figcaption')]
      .filter(el => {
        if (el.closest('.notes')) return false;
        const hasOwnText = [...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim().length > 1);
        if (!hasOwnText) return false;
        const cs = getComputedStyle(el);
        if (cs.display === 'none' || cs.visibility === 'hidden' || +cs.opacity < 0.05) return false;
        const r = el.getBoundingClientRect();
        return r.width > 8 && r.height > 8;
      })
      .map(el => ({ el, r: el.getBoundingClientRect(), t: (el.textContent || '').trim().slice(0, 24) }));

    for (let i = 0; i < texts.length; i++) {
      for (let j = i + 1; j < texts.length; j++) {
        const a = texts[i], b = texts[j];
        if (a.el.contains(b.el) || b.el.contains(a.el)) continue;
        const ox = Math.min(a.r.right, b.r.right) - Math.max(a.r.left, b.r.left);
        const oy = Math.min(a.r.bottom, b.r.bottom) - Math.max(a.r.top, b.r.top);
        if (ox > 4 && oy > 4) {
          const minArea = Math.min(a.r.width * a.r.height, b.r.width * b.r.height);
          const ratio = (ox * oy) / minArea;
          if (ratio > 0.55) {
            const key = [a.t, b.t].sort().join('|');
            if (!seen.has(key)) {
              seen.add(key);
              issues.push({ kind: 'text-overlap', a: a.t, b: b.t, ratio: +ratio.toFixed(2) });
            }
          }
        }
      }
    }

    out.push({
      id: slide.id,
      title: slide.dataset.title || '',
      rail: slide.dataset.rail || '',
      active: slide.classList.contains('is-active'),
      issues
    });
  }
  return out;
}
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--shots", action="store_true", help="每屏截图到 /tmp/qa/")
    ap.add_argument("--only", default="", help="只检查指定屏，如 s07,s08")
    ap.add_argument("--max-report", type=int, default=6, help="每屏最多列几条")
    ap.add_argument("--index", default="", help="指定要检查的 deck 入口，如 decks/tsinghua-xlab/index.html")
    ap.add_argument("--ratio", default="16:9", choices=["16:9", "4:3"], help="画幅：16:9(1600) / 4:3(1200)")
    args = ap.parse_args()

    index_path = ROOT / args.index if args.index else INDEX
    if not index_path.exists():
        sys.exit("找不到 index.html，先运行 node build.mjs")

    from playwright.sync_api import sync_playwright

    only = {s.strip() for s in args.only.split(",") if s.strip()}
    EXPECT = {"16:9": (1600, 900), "4:3": (1200, 900)}
    DES_W, DES_H = EXPECT[args.ratio]
    if args.index:      # 指定 deck 走本地服务（图片是站点绝对路径，file:// 读不到）
        url = f"http://127.0.0.1:8899/{args.index}?export=1" + ("&ratio=4:3" if args.ratio == "4:3" else "")
    else:
        url = index_path.as_uri() + "?export=1" + ("&ratio=4:3" if args.ratio == "4:3" else "")

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        page = browser.new_context(viewport={"width": DES_W, "height": DES_H},
                                   device_scale_factor=1).new_page()
        errors = []
        page.on("console", lambda m: errors.append(f"{m.type}: {m.text}")
                if m.type in ("error", "warning") else None)
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        page.goto(url, wait_until="load")
        page.wait_for_timeout(700)

        # 让所有 reveal 立即就位（导出模式下 CSS 已处理），等字体与图片
        page.evaluate("() => document.fonts ? document.fonts.ready : null")
        # 按屏懒加载的 deck：先把当前屏/全屏图片水合回来，再等图片与字体
        page.evaluate("() => window.__deckHydrate && window.__deckHydrate(0, 999)")
        page.evaluate("""() => Promise.all([...document.images].map(i => i.complete ? 1 :
            new Promise(r => { i.onload = i.onerror = r; })))""")
        page.wait_for_timeout(300)

        data = page.evaluate(JS_COLLECT.replace('__W__', str(DES_W)).replace('__H__', str(DES_H)))

        if args.shots:
            SHOT_DIR.mkdir(parents=True, exist_ok=True)
            for s in data:
                # 导出模式下所有屏叠在一起，截图前只留当前屏
                page.evaluate(
                    """(id) => {
                        document.querySelectorAll('.slide').forEach(el => {
                            el.style.display = (el.id === id) ? 'flex' : 'none';
                        });
                    }""", s["id"])
                page.wait_for_timeout(120)
                el = page.query_selector(f"#{s['id']}")
                if el:
                    el.screenshot(path=str(SHOT_DIR / f"{s['id']}.png"))
            page.evaluate("() => document.querySelectorAll('.slide').forEach(el => el.style.display = '')")
            print(f"截图已保存到 {SHOT_DIR}\n")

        browser.close()

    if only:
        data = [d for d in data if d["id"] in only]

    total_issues = sum(len(d["issues"]) for d in data)
    kinds = {}
    for d in data:
        for i in d["issues"]:
            kinds[i["kind"]] = kinds.get(i["kind"], 0) + 1

    print("=" * 78)
    print(f"check_slides · {len(data)} 屏 · 问题 {total_issues} 个"
          + (f" · {kinds}" if kinds else ""))
    print("=" * 78)
    for d in data:
        if not d["issues"]:
            print(f"  ✓ {d['id']}  [{d['rail']}]  {d['title']}")
            continue
        print(f"  ✗ {d['id']}  [{d['rail']}]  {d['title']}   {len(d['issues'])} 个问题")
        for i in d["issues"][: args.max_report]:
            detail = " ".join(f"{k}={v}" for k, v in i.items() if k != "kind")
            print(f"      · {i['kind']}: {detail}")
        if len(d["issues"]) > args.max_report:
            print(f"      … 还有 {len(d['issues']) - args.max_report} 条")

    if errors:
        print("\n控制台:")
        for e in errors[:12]:
            print("   !", e[:200])

    print()
    sys.exit(1 if (total_issues or errors) else 0)


if __name__ == "__main__":
    main()
