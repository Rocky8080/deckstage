#!/usr/bin/env python3
"""
design_audit.py — 视觉质量体检：文字对比度 / 大色块面积 / 低对比水印

用法:
    python3 tools/design_audit.py --index decks/sample-deck/index.html
    python3 tools/design_audit.py --index decks/sample-deck/index.html --ratio 4:3
    python3 tools/design_audit.py --index ... --only s18 --warn-only

规则:
  · 正常文字 >= 4.5:1；大字（>=24px，或 >=18.66px 且粗体）>= 3:1
  · 承载信息的大字不能做低对比水印
  · 字号下限 11.5px（标签档）；低于下限记 font-too-small，且小字同样查对比度
  · 单块高饱和强调色面积 > 8% 警告，> 12% 视为问题
  · 元素加 data-design-allow 可显式豁免；.notes 不检查

退出码: 0 = 通过；1 = 有问题；--warn-only 只报告不失败。
"""
from __future__ import annotations

import _platform  # noqa: F401  — Windows GBK 管道下的 stdout UTF-8 兜底（见 _platform.py）
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

JS_COLLECT = r"""
() => {
  const slides = [...document.querySelectorAll('.slide')];
  const PAPER = {r:247,g:243,b:234,a:1};

  const parse = (value) => {
    if (!value) return null;
    const m = String(value).match(/rgba?\(\s*([\d.]+)[,\s]+([\d.]+)[,\s]+([\d.]+)(?:[,\s/]+([\d.]+))?\s*\)/i);
    if (!m) return null;
    return {r:+m[1], g:+m[2], b:+m[3], a:m[4] === undefined ? 1 : +m[4]};
  };
  const blend = (fg, bg) => {
    const a = fg.a + bg.a * (1 - fg.a);
    if (a <= 0.0001) return {r:0,g:0,b:0,a:0};
    return {
      a,
      r:(fg.r * fg.a + bg.r * bg.a * (1 - fg.a)) / a,
      g:(fg.g * fg.a + bg.g * bg.a * (1 - fg.a)) / a,
      b:(fg.b * fg.a + bg.b * bg.a * (1 - fg.a)) / a,
    };
  };
  const lin = (v) => { v /= 255; return v <= .03928 ? v/12.92 : Math.pow((v+.055)/1.055, 2.4); };
  const lum = (c) => .2126*lin(c.r) + .7152*lin(c.g) + .0722*lin(c.b);
  const ratio = (a, b) => { const x=lum(a), y=lum(b); return (Math.max(x,y)+.05)/(Math.min(x,y)+.05); };
  const sat = (c) => {
    const r=c.r/255, g=c.g/255, b=c.b/255;
    const mx=Math.max(r,g,b), mn=Math.min(r,g,b), l=(mx+mn)/2;
    return { s: mx===mn ? 0 : (mx-mn)/(1-Math.abs(2*l-1)), l };
  };
  const hex = (c) => '#' + [c.r,c.g,c.b].map(v => Math.round(v).toString(16).padStart(2,'0')).join('');
  const ownText = (el) => [...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim().length > 1);
  const visible = (el) => {
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden') return false;
    const r = el.getBoundingClientRect();
    return r.width > 4 && r.height > 4;
  };
  const skip = (el) => !!el.closest('.notes') || el.hasAttribute('data-design-allow') || el.closest('[data-design-allow]');

  const out = [];
  for (const slide of slides) {
    const issues = [];
    const sb = slide.getBoundingClientRect();
    const slideArea = sb.width * sb.height;
    let base = parse(getComputedStyle(slide).backgroundColor) || PAPER;
    if (base.a < .99) base = blend(base, PAPER);
    const slideHasImage = getComputedStyle(slide).backgroundImage !== 'none';

    // 1) 文字对比度
    const textEls = slide.querySelectorAll('h1,h2,h3,h4,p,li,span,div,strong,em,figcaption,td,th,pre,code');
    for (const el of textEls) {
      if (skip(el) || !ownText(el) || !visible(el)) continue;
      const cs = getComputedStyle(el);
      if (String(el.textContent).trim().length < 2) continue;
      if (cs.mixBlendMode && cs.mixBlendMode !== 'normal') continue;
      const fs = parseFloat(cs.fontSize);
      // 字号下限：标签档 11.5px。低于下限记一条；小字对比度照查（最容易不合格的就是它们）。
      if (el.getAttribute('aria-hidden') !== 'true' && fs < 11.5) {
        issues.push({
          kind: 'font-too-small',
          text: String(el.textContent).trim().slice(0, 24),
          el: el.tagName.toLowerCase() + (typeof el.className === 'string' && el.className ? '.' + el.className.trim().split(/\s+/).slice(0,2).join('.') : ''),
          fs: +fs.toFixed(1),
          need: '>=11.5'
        });
      }
      const fg0 = parse(cs.color);
      if (!fg0) continue;

      // 逐层合成祖先背景；遇到 background-image 无法可靠判断，跳过
      const layers = [];
      let unknown = false;
      for (let n = el; n && n !== slide.parentElement; n = n.parentElement) {
        const s = getComputedStyle(n);
        if (s.backgroundImage && s.backgroundImage !== 'none') { unknown = true; break; }
        const c = parse(s.backgroundColor);
        if (c && c.a > .001) layers.push(c);
        if (n === slide) break;
      }
      if (unknown || slideHasImage) continue;
      let bg = base;
      for (let i = layers.length - 1; i >= 0; i--) bg = blend(layers[i], bg);

      let opacity = 1;
      for (let n = el; n && n !== slide.parentElement; n = n.parentElement) opacity *= parseFloat(getComputedStyle(n).opacity || '1');
      if (opacity < .25) continue;
      const fg = blend({...fg0, a: fg0.a * opacity}, bg);
      const cr = ratio(fg, bg);
      const weight = parseInt(cs.fontWeight, 10) || 400;
      const large = fs >= 24 || (fs >= 18.66 && weight >= 600);
      const need = large ? 3 : 4.5;
      const isDeco = el.getAttribute('aria-hidden') === 'true' || opacity < .6;

      if (isDeco && fs < 48) continue;             // 小的纯装饰文字不当作信息
      if (cr + .05 < need) {
        issues.push({
          kind: isDeco ? 'contrast-watermark' : (large ? 'contrast-low-large' : 'contrast-low'),
          text: String(el.textContent).trim().slice(0, 24),
          el: el.tagName.toLowerCase() + (typeof el.className === 'string' && el.className ? '.' + el.className.trim().split(/\s+/).slice(0,2).join('.') : ''),
          ratio: +cr.toFixed(2),
          need,
          fs: +fs.toFixed(1),
          color: hex(fg),
          bg: hex(bg)
        });
      }
    }

    // 2) 高饱和大色块（强调色面积）
    for (const el of slide.querySelectorAll('*')) {
      if (skip(el) || el === slide) continue;
      const cs = getComputedStyle(el);
      if (cs.display === 'none' || cs.visibility === 'hidden') continue;
      if (cs.backgroundImage && cs.backgroundImage !== 'none') continue;
      const c = parse(cs.backgroundColor);
      if (!c || c.a < .5) continue;
      const r = el.getBoundingClientRect();
      const area = r.width * r.height;
      if (area < slideArea * .08) continue;
      const {s, l} = sat(c);
      if (s < .28 || l < .12 || l > .9) continue;
      const pct = +(area / slideArea * 100).toFixed(1);
      issues.push({
        kind: 'accent-block',
        text: (el.textContent || '').trim().replace(/\s+/g, ' ').slice(0, 24),
        el: el.tagName.toLowerCase() + (typeof el.className === 'string' && el.className ? '.' + el.className.trim().split(/\s+/).slice(0,2).join('.') : ''),
        area: pct,
        color: hex(c),
        level: pct > 12 ? 'P1' : 'P2'
      });
    }

    out.push({id: slide.id, title: slide.dataset.title || '', rail: slide.dataset.rail || '', issues});
  }
  return out;
}
"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", default="index.html", help="deck 入口，如 decks/sample-deck/index.html")
    ap.add_argument("--ratio", default="16:9", choices=["16:9", "4:3"])
    ap.add_argument("--only", default="", help="只查指定屏，如 s17,s18")
    ap.add_argument("--max-report", type=int, default=8)
    ap.add_argument("--warn-only", action="store_true", help="只报告，不因问题返回非 0")
    args = ap.parse_args()

    index_path = ROOT / args.index
    if not index_path.exists():
        sys.exit(f"找不到 {index_path}，先运行 node build.mjs")
    url = f"http://127.0.0.1:8899/{args.index}?export=1" + ("&ratio=4:3" if args.ratio == "4:3" else "")
    only = {s.strip() for s in args.only.split(",") if s.strip()}

    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = _platform.launch_chromium(p, headless=True)
        page = browser.new_context(viewport={"width": 1600 if args.ratio == "16:9" else 1200, "height": 900},
                                   device_scale_factor=1).new_page()
        page.goto(url, wait_until="load", timeout=30000)
        page.wait_for_timeout(800)
        page.evaluate("() => document.fonts ? document.fonts.ready : null")
        data = page.evaluate(JS_COLLECT)
        browser.close()

    if only:
        data = [d for d in data if d["id"] in only]

    total = sum(len(d["issues"]) for d in data)
    kinds = {}
    for d in data:
        for i in d["issues"]:
            kinds[i["kind"]] = kinds.get(i["kind"], 0) + 1

    print("=" * 74)
    print(f"design_audit · {len(data)} 屏 · 问题 {total} 个" + (f" · {kinds}" if kinds else ""))
    print("=" * 74)
    for d in data:
        if not d["issues"]:
            print(f"  ✓ {d['id']}  {d['title']}")
            continue
        print(f"  ✗ {d['id']}  {d['title']}   {len(d['issues'])} 个问题")
        for i in d["issues"][:args.max_report]:
            detail = " ".join(f"{k}={v}" for k, v in i.items() if k != "kind")
            print(f"      · {i['kind']}: {detail}")
        if len(d["issues"]) > args.max_report:
            print(f"      … 还有 {len(d['issues']) - args.max_report} 条")

    print()
    if total and not args.warn_only:
        sys.exit(1)


if __name__ == "__main__":
    main()
