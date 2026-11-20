#!/usr/bin/env python3
"""check_pptx_bg.py — 检查 PPTX 每页背景色（防止 '导出全白' 回归）

用法:
    python3 tools/check_pptx_bg.py exports/部门AI应用实践-六实践-可编辑-修色.pptx --expect F8F4EC
    python3 tools/check_pptx_bg.py file.pptx --allow F8F4EC,FFFFFF

退出码: 0 = 每页背景都命中；1 = 有缺失/不一致。
"""
from __future__ import annotations
import argparse, re, sys, zipfile
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("pptx")
    ap.add_argument("--expect", default="F8F4EC", help="期望背景色（不带 #），默认纸色 F8F4EC")
    ap.add_argument("--allow", default="", help="额外允许的背景色，逗号分隔")
    a = ap.parse_args()
    path = Path(a.pptx)
    if not path.exists():
        sys.exit(f"找不到 {path}")
    allow = {a.expect.upper().lstrip('#')} | {x.strip().upper().lstrip('#') for x in a.allow.split(',') if x.strip()}
    z = zipfile.ZipFile(path)
    slides = sorted([n for n in z.namelist() if re.fullmatch(r'ppt/slides/slide\d+\.xml', n)],
                    key=lambda n: int(re.search(r'(\d+)', n).group(1)))
    if not slides:
        sys.exit('PPTX 里没有 slide*.xml')
    bad = []
    for n in slides:
        xml = z.read(n).decode('utf-8')
        m = re.search(r'<p:bg>.*?</p:bg>', xml, re.S)
        color = re.search(r'<a:srgbClr val="([0-9A-Fa-f]{6})"', m.group(0)).group(1).upper() if m else None
        if color not in allow:
            bad.append((n, color))
    if bad:
        print(f'✗ {path.name} · {len(bad)}/{len(slides)} 页背景不在允许清单 {sorted(allow)}')
        for n, c in bad[:20]:
            print(f'   {n}: {c or "无 <p:bg>"}')
        sys.exit(1)
    print(f'✓ {path.name} · {len(slides)} 页背景均命中 {sorted(allow)}')


if __name__ == '__main__':
    main()
