#!/usr/bin/env python3
"""预排适配：量出每段文字的真实宽度，超框时按比例缩小字号（写回 PPTX 的 normAutofit）。

目的：PowerPoint 里刚好一行的标题，在 LibreOffice 里用回退字体时不要多折一行。
"""
import re, shutil, sys, zipfile
from PIL import ImageFont

FONT_PATH = "/Applications/LibreOffice.app/Contents/Resources/fonts/truetype/Arial Unicode.ttf"
CACHE = {}


def font_at(size_px):
    key = int(size_px)
    if key not in CACHE:
        CACHE[key] = ImageFont.truetype(FONT_PATH, max(6, key))
    return CACHE[key]


def text_width(text, size_px):
    f = font_at(size_px)
    return f.getlength(text)


def fit_scale(lines, size_px, avail_px):
    if not lines or avail_px <= 0:
        return 1.0
    need = max(text_width(l, size_px) for l in lines)
    if need <= 0:
        return 1.0
    k = avail_px / need
    return max(0.72, min(1.0, k))


def main(src, dst, emu_per_px=9525):
    shutil.copy(src, dst + ".tmp")
    changed = 0
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename.startswith("ppt/slides/slide") and item.filename.endswith(".xml"):
                try:
                    xml = data.decode("utf-8")
                except UnicodeDecodeError:
                    zout.writestr(item, data); continue

                def fix_shape(m):
                    nonlocal changed
                    block = m.group(0)
                    # 只处理有文本的 sp；取 xfrm 尺寸与字号
                    ext = re.search(r'<a:ext cx="(\d+)" cy="(\d+)"/>', block)
                    if not ext:
                        return block
                    width_px = int(ext.group(1)) / emu_per_emu(emu_per_px)
                    texts = re.findall(r"<a:t>([^<]*)</a:t>", block)
                    if not texts:
                        return block
                    sizes = [int(s) / 100 for s in re.findall(r'<a:rPr[^>]*sz="(\d+)"', block)]
                    if not sizes:
                        return block
                    size_px = max(sizes) * (96 / 72) * 1.333  # pt → 画布 px（1600/13.33in ≈ 120dpi）
                    lines = []
                    cur = ""
                    for t in texts:
                        parts = t.split("\n")
                        for i, p in enumerate(parts):
                            cur += p
                            if i < len(parts) - 1:
                                lines.append(cur); cur = ""
                    if cur:
                        lines.append(cur)
                    k = fit_scale(lines, size_px, width_px)
                    if k >= 0.985:
                        return block
                    pct = int(round(k * 100000))
                    if "<a:normAutofit" in block:
                        block = re.sub(r'<a:normAutofit[^>]*/?>',
                                       f'<a:normAutofit fontScale="{pct}"/>', block, count=1)
                    else:
                        # bodyPr 可能自闭合（/>）也可能带收尾标签：前者补上闭合，后者只插子元素
                        def add_autofit(mm):
                            head, tail = mm.group(1), mm.group(2)
                            child = f'<a:normAutofit fontScale="{pct}"/>'
                            if tail == "/>":
                                return head + ">" + child + "</a:bodyPr>"
                            return head + ">" + child
                        block = re.sub(r'(<a:bodyPr[^>]*?)(/>|>)', add_autofit, block, count=1)
                    changed += 1
                    return block

                # 逐 sp 处理
                xml = re.sub(r'<p:sp>.*?</p:sp>', fix_shape, xml, flags=re.S)
                data = xml.encode("utf-8")
            zout.writestr(item, data)
    import os; os.remove(dst + ".tmp")
    print(f"[prefit] 调整 {changed} 个文本框 → {dst}")


def emu_per_emu(v):
    return v


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
