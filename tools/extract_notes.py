#!/usr/bin/env python3
"""
extract_notes.py — 从各屏的 <aside class="notes"> 汇总成讲稿 docs/本地笔记/讲稿.md

用法: python3 tools/extract_notes.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SLIDES = sorted((ROOT / "src" / "slides").glob("*.html"))
OUT = ROOT / "docs" / "本地笔记" / "讲稿.md"

# 中文讲稿语速：约 240 字/分钟
CPS_PER_MIN = 240


def read_slide(path):
    html = path.read_text(encoding="utf-8")
    title = re.search(r'data-title="([^"]*)"', html)
    rail = re.search(r'data-rail="([^"]*)"', html)
    kicker = re.search(r'<p class="kicker[^"]*">(.*?)</p>', html, re.S)
    h1 = re.search(r'<h1 class="[^"]*title[^"]*">(.*?)</h1>', html, re.S)
    notes = re.search(r'<aside class="notes">(.*?)</aside>', html, re.S)

    def clean(t):
        if not t:
            return ""
        t = re.sub(r"<br\s*/?>", "\n", t)
        t = re.sub(r"<[^>]+>", "", t)
        t = re.sub(r"&nbsp;", " ", t)
        lines = [ln.strip() for ln in t.splitlines()]
        return "\n".join(ln for ln in lines if ln)

    return {
        "file": path.name,
        "title": clean(title.group(1)) if title else path.stem,
        "rail": clean(rail.group(1)) if rail else "",
        "kicker": clean(kicker.group(1)) if kicker else "",
        "heading": clean(h1.group(1)) if h1 else "",
        "notes": clean(notes.group(1)) if notes else "",
    }


def main():
    rows = [read_slide(p) for p in SLIDES]
    total_chars = sum(len(r["notes"]) for r in rows)
    minutes = max(1, round(total_chars / CPS_PER_MIN))

    out = ["# 讲稿 · AI 改变学习方式", ""]
    out.append(f"> 共 {len(rows)} 屏，备注合计约 {total_chars} 字，按每分钟 {CPS_PER_MIN} 字估算约 **{minutes} 分钟**。")
    out.append("> 本文由各屏 `<aside class=\"notes\">` 自动汇总，改备注即改讲稿：`python3 tools/extract_notes.py`。")
    out.append("")
    out.append("| # | 三幕 | 屏幕标题 | 字数 |")
    out.append("|---|---|---|---|")
    for i, r in enumerate(rows, 1):
        out.append(f"| {i:02d} | {r['rail'] or '—'} | {r['title']} | {len(r['notes'])} |")
    out.append("")
    out.append("---")
    out.append("")

    for i, r in enumerate(rows, 1):
        out.append(f"## {i:02d} · {r['title']}")
        if r["kicker"] or r["heading"]:
            line = " — ".join(x for x in (r["kicker"], re.sub(r"\s+", " ", r["heading"])) if x)
            out.append(f"*{line}*")
            out.append("")
        if r["notes"]:
            for para in r["notes"].split("\n"):
                out.append(para)
                out.append("")
        else:
            out.append("_（这一屏没有备注）_")
            out.append("")

    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text("\n".join(out), encoding="utf-8")
    print(f"已写出 {OUT.relative_to(ROOT)} · {len(rows)} 屏 · 约 {total_chars} 字 / {minutes} 分钟")

    missing = [r["file"] for r in rows if not r["notes"]]
    if missing:
        print("缺备注：" + "、".join(missing))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
