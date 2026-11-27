#!/usr/bin/env python3
"""export_audit.py — 端到端检查「页面背景」和「页面导出的可编辑 PPTX 背景」是否一致

用法:
    python3 tools/export_audit.py --index decks/sample-deck/index.html
    python3 tools/export_audit.py --index ... --out exports/fixed.pptx

它会：
  1. 用无头浏览器读取每一页在 DOM 里的 computed background；
  2. 点击页面里的「导出 PPTX」，拿到真实导出文件；
  3. 逐页读取 ppt/slides/slideN.xml 的 <p:bg>，与 DOM 背景比对；
  4. 页数不一致、背景缺失、颜色不一致 → 退出 1。

这是对「slide.bkgd 压过 slide.background」这类导出回归的端到端门禁。
"""
from __future__ import annotations

import _platform  # noqa: F401  — Windows GBK 管道下的 stdout UTF-8 兜底（见 _platform.py）
import argparse
import re
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def rgb_to_hex(value: str) -> str | None:
    m = re.match(r'rgba?\(\s*(\d+)[,\s]+(\d+)[,\s]+(\d+)(?:[,\s/]+([\d.]+))?\s*\)', value or '')
    if not m:
        return None
    if m.group(4) is not None and float(m.group(4)) < 0.995:
        return None
    return ''.join(f'{int(m.group(i)):02X}' for i in (1, 2, 3))


def slide_bg_xml(pptx: Path, slide_no: int) -> tuple[str | None, str]:
    z = zipfile.ZipFile(pptx)
    name = f'ppt/slides/slide{slide_no}.xml'
    xml = z.read(name).decode('utf-8')
    bg = re.search(r'<p:bg>.*?</p:bg>', xml, re.S)
    if not bg:
        return None, 'no-p:bg'
    m = re.search(r'<a:srgbClr val="([0-9A-Fa-f]{6})"', bg.group(0))
    if not m:
        return None, 'non-solid-p:bg'
    return m.group(1).upper(), 'ok'


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--index', required=True, help='deck 入口，如 decks/sample-deck/index.html')
    ap.add_argument('--out', default='', help='把导出文件另存到这个路径')
    ap.add_argument('--warn-only', action='store_true')
    ap.add_argument('--timeout', type=int, default=240, help='导出等待秒数')
    a = ap.parse_args()

    index = ROOT / a.index
    if not index.exists():
        sys.exit(f'找不到 {index}，先运行 node build.mjs')
    url = f'http://127.0.0.1:8899/{a.index}'

    from playwright.sync_api import sync_playwright
    tmp = Path(tempfile.mkdtemp(prefix='pptx-audit-')) / 'export.pptx'
    try:
        with sync_playwright() as p:
            browser = _platform.launch_chromium(p, headless=True)
            page = browser.new_context(viewport={'width': 1600, 'height': 900}, accept_downloads=True).new_page()
            page.goto(url, wait_until='load', timeout=30000)
            page.wait_for_timeout(1200)

            expected = page.evaluate("""() => [...document.querySelectorAll('.slide')].map((s, i) => {
              const cs = getComputedStyle(s);
              return { i: i + 1, id: s.id, bg: cs.backgroundColor, img: cs.backgroundImage };
            })""")
            total = len(expected)
            if not page.query_selector('[data-act="export"]'):
                sys.exit('页面没有 [data-act="export"] 导出按钮')
            with page.expect_download(timeout=a.timeout * 1000) as dl:
                page.click('[data-act="export"]')
            dl.value.save_as(str(tmp))
            browser.close()

        z = zipfile.ZipFile(tmp)
        slide_files = sorted(
            [n for n in z.namelist() if re.fullmatch(r'ppt/slides/slide\d+\.xml', n)],
            key=lambda n: int(re.search(r'(\d+)', n).group(1)),
        )
        if len(slide_files) != total:
            print(f'✗ 页数不一致：页面 {total} 页，PPTX {len(slide_files)} 页')
            sys.exit(1)

        mismatches = []
        for item in expected:
            exp = rgb_to_hex(item['bg'])
            has_img = bool(item['img'] and item['img'] != 'none')
            got, why = slide_bg_xml(tmp, item['i'])
            if has_img:
                # 背景是渐变/图片时，可编辑版可能用图片背景，单独标出
                mismatches.append((item['i'], item['id'], 'image-bg-skip', exp, why))
                continue
            if not exp:
                mismatches.append((item['i'], item['id'], 'dom-bg-not-solid', item['bg'], why))
                continue
            if got != exp:
                mismatches.append((item['i'], item['id'], 'mismatch', exp, got or why))

        print('=' * 70)
        print(f'export_audit · {total} 页 · 背景不一致 {len(mismatches)} 个')
        print('=' * 70)
        for i, sid, kind, exp, got in mismatches:
            print(f'  ✗ {i:02d} {sid}  {kind}  DOM={exp}  PPTX={got}')
        if not mismatches:
            print(f'  ✓ {total}/{total} 页背景一致；导出页数也一致')

        if a.out:
            Path(a.out).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(tmp, a.out)
            print(f'  导出文件 → {a.out}')
        if mismatches and not a.warn_only:
            sys.exit(1)
    finally:
        shutil.rmtree(tmp.parent, ignore_errors=True)


if __name__ == '__main__':
    main()
