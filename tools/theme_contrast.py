#!/usr/bin/env python3
"""theme_contrast.py — 配色主题（C 键 / 配色浮窗）下的文字对比度体检

为什么要单独一把尺子：`design_audit.py` 查的是 deck 自己的原始配色；而六套预设主题
是 `tools/deck_themes.py` 在运行时覆盖 `--paper/--ink*/--green*/--terra*/--gold*` 得来的，
同一屏换主题后完全可能出现「深面板上的字变成深色」这类只在该主题下才有的问题。

本工具逐主题把调色板注入页面，再逐屏逐文字节点算「前景（含透明度合成）对最近实心底」
的对比度，按 WCAG 阈值报问题：

    普通文字 ≥4.5:1    大字（≥24px，或 ≥18.66px 且 ≥600 字重）≥3:1

用法:
    python3 tools/theme_contrast.py --index decks/prompt-engineering/index.html
    python3 tools/theme_contrast.py --index decks/24steps/index.html --theme celadon
    python3 tools/theme_contrast.py --index decks/xlab-ai-practice/index.html --json
    python3 tools/theme_contrast.py --index ... --warn-only

退出码: 0 = 没有低于阈值的信息文字, 1 = 有（--warn-only 时恒为 0）, 2 = 环境不可用。
默认主题（deck 原配色）请用 design_audit.py 检查，本工具只查预设主题。

约定：`--dark*` 深面板在全部主题里都保持深底，所以面板里的文字必须用固定的浅色
（如 #F7F3EA / #9CC7B4 / #C9A75A），不能用会随主题反转的 `--paper` / `--gold`。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

COLLECT_JS = r"""
() => {
  const parse = (c) => {
    const m = c.match(/rgba?\(([^)]+)\)/);
    if (!m) return null;
    const p = m[1].split(/[,\s\/]+/).map(Number);
    return [p[0], p[1], p[2], p.length > 3 ? p[3] : 1];
  };
  const hex = (c) => '#' + c.slice(0, 3).map(v => Math.round(v).toString(16).padStart(2, '0')).join('').toUpperCase();
  const lum = (c) => {
    const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
    return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2]);
  };
  const ratio = (a, b) => {
    const l1 = lum(a), l2 = lum(b), hi = Math.max(l1, l2), lo = Math.min(l1, l2);
    return (hi + 0.05) / (lo + 0.05);
  };
  const effBg = (el) => {
    let n = el;
    while (n && n.nodeType === 1) {
      const cs = getComputedStyle(n);
      const bg = parse(cs.backgroundColor);
      if (bg && bg[3] > 0.55) return bg;
      if (cs.backgroundImage && cs.backgroundImage !== 'none') return [27, 33, 31, 1];
      n = n.parentElement;
    }
    return [27, 33, 31, 1];
  };
  const SKIP = ['.foot', '.chrome', '.overview', '.notebar'];
  const out = [];
  document.querySelectorAll('.slide').forEach((slide, si) => {
    const walker = document.createTreeWalker(slide, NodeFilter.SHOW_TEXT);
    let node;
    while ((node = walker.nextNode())) {
      const text = (node.textContent || '').trim();
      if (!text) continue;
      const el = node.parentElement;
      if (!el || SKIP.some(sel => el.closest(sel))) continue;
      const cs = getComputedStyle(el);
      if (cs.visibility === 'hidden' || cs.display === 'none') continue;
      const fg = parse(cs.color);
      if (!fg) continue;
      const bg = effBg(el);
      const a = fg[3] === undefined ? 1 : fg[3];
      const comp = [fg[0] * a + bg[0] * (1 - a), fg[1] * a + bg[1] * (1 - a), fg[2] * a + bg[2] * (1 - a), 1];
      const fs = parseFloat(cs.fontSize);
      const bold = parseInt(cs.fontWeight, 10) >= 600;
      const large = fs >= 24 || (fs >= 18.66 && bold);
      const need = large ? 3 : 4.5;
      const r = ratio(comp, bg);
      if (r < need - 0.02) {
        out.push({
          slide: si + 1,
          id: slide.id || '',
          text: text.slice(0, 40),
          cls: (el.className || '').toString().slice(0, 48),
          fg: hex(fg), bg: hex(bg),
          fs: Math.round(fs), ratio: +r.toFixed(2), need,
        });
      }
    }
  });
  return out;
}
"""


def load_themes():
    from deck_themes import THEMES
    return [t for t in THEMES if t["id"] and t["vars"]]


def palette_css(vars_: dict) -> str:
    body = "\n".join(f"  {k}: {v};" for k, v in vars_.items() if isinstance(v, str) and v.startswith("#"))
    return ":root{\n" + body + "\n}"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="检查预设配色主题下的文字对比度")
    ap.add_argument("--index", default="index.html", help="deck 入口，如 decks/prompt-engineering/index.html")
    ap.add_argument("--theme", default="all", help="all 或主题 id：paper-white / navy / terra / violet / celadon / ink-dark")
    ap.add_argument("--json", action="store_true", help="输出机器可读 JSON")
    ap.add_argument("--warn-only", action="store_true", help="只报告，不因问题返回非 0")
    ap.add_argument("--max-report", type=int, default=4, help="每个主题最多列几条（默认 4）")
    args = ap.parse_args(argv)

    try:
        from serve import start_server, project_root
        from playwright.sync_api import sync_playwright
    except Exception as exc:                                  # noqa: BLE001
        print(f"[theme_contrast] 环境不可用：{exc}", file=sys.stderr)
        return 2

    themes = load_themes()
    if args.theme != "all":
        themes = [t for t in themes if t["id"] == args.theme]
        if not themes:
            print(f"[theme_contrast] 没有这个主题：{args.theme}", file=sys.stderr)
            return 2

    root = str(project_root())
    httpd, port, _ = start_server(root, 0)
    report = {}
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=True)
            page = browser.new_page(viewport={"width": 1680, "height": 1000})
            page.goto(f"http://127.0.0.1:{port}/{args.index}?export=1", wait_until="networkidle", timeout=60000)
            page.wait_for_timeout(600)
            for t in themes:
                page.evaluate("() => document.querySelectorAll('style[data-theme-audit]').forEach(e => e.remove())")
                page.evaluate(
                    """(css) => {
                        const s = document.createElement('style');
                        s.dataset.themeAudit = '1';
                        s.textContent = css;
                        document.head.appendChild(s);
                    }""", palette_css(t["vars"]))
                page.wait_for_timeout(180)
                report[t["id"]] = page.evaluate(COLLECT_JS)
            browser.close()
    finally:
        httpd.shutdown()
        httpd.server_close()

    total = sum(len(v) for v in report.values())
    name = {t["id"]: t["name"] for t in load_themes()}
    if args.json:
        print(json.dumps({"index": args.index, "total": total,
                          "themes": {k: {"name": name.get(k, k), "issues": v} for k, v in report.items()}},
                         ensure_ascii=False, indent=2))
    else:
        print("=" * 78)
        print(f"theme_contrast · {args.index} · 主题 {len(report)} 套 · 问题 {total} 个")
        print("=" * 78)
        for tid, issues in report.items():
            mark = "✓" if not issues else "✗"
            print(f"  {mark} {name.get(tid, tid):4s} ({tid})  {len(issues)} 处")
            for it in issues[: args.max_report]:
                print(f"      s{it['slide']:02d} ratio={it['ratio']} need={it['need']} fs={it['fs']} "
                      f"fg={it['fg']} bg={it['bg']} .{it['cls']}  «{it['text']}»")
            if len(issues) > args.max_report:
                print(f"      … 还有 {len(issues) - args.max_report} 条")
        if total:
            print("\n  修法：深面板（--dark*）里的文字用固定浅色（#F7F3EA / #9CC7B4 / #C9A75A），")
            print("        不要用会随主题反转的 --paper / --gold；纸面小字用 ≥4.5:1 的主题色。")
    return 0 if (args.warn_only or total == 0) else 1


if __name__ == "__main__":
    sys.exit(main())
