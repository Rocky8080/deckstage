#!/usr/bin/env python3
"""对超框的段落收紧字距（spc），避免因字体变宽而多折一行。"""
import _platform  # noqa: F401  — Windows GBK 管道下的 stdout UTF-8 兜底（见 _platform.py）
import re, shutil, sys, zipfile
from PIL import ImageFont

FONT = "/Applications/wpsoffice.app/Contents/Resources/office6/fonts/HYQiHei-55J.ttf"
CACHE = {}
EMU_PX = 9525          # 1px = 9525 EMU（96dpi），画布 1600px 对应 13.33in


def f(size):
    k = max(6, int(size))
    if k not in CACHE:
        CACHE[k] = ImageFont.truetype(FONT, k)
    return CACHE[k]


def main(src, dst, tighten=-40):
    shutil.copy(src, dst + ".tmp")
    n = 0
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename.startswith("ppt/slides/slide") and item.filename.endswith(".xml"):
                try:
                    xml = data.decode("utf-8")
                except UnicodeDecodeError:
                    zout.writestr(item, data); continue

                def fix(m):
                    nonlocal n
                    block = m.group(0)
                    ext = re.search(r'<a:ext cx="(\d+)"', block)
                    if not ext:
                        return block
                    box_w = int(ext.group(1)) / EMU_PX * 1.333      # → 1600 画布 px
                    changed = False
                    # 逐段落判断
                    for para in re.findall(r"<a:p>.*?</a:p>", block, flags=re.S):
                        texts = re.findall(r"<a:t>([^<]*)</a:t>", para)
                        if not texts:
                            continue
                        line = "".join(texts)
                        if len(line) > 60 or not line.strip():
                            continue
                        sizes = [int(s) / 100 for s in re.findall(r'<a:rPr[^>]*sz="(\d+)"', para)]
                        pt = max(sizes) if sizes else 18
                        px = pt * 1.333
                        need = f(px).getlength(line)
                        if need > box_w * 1.02:
                            changed = True
                    if not changed:
                        return block
                    block = re.sub(r"<a:rPr(?![^>]*\bspc=)", f'<a:rPr spc="{tighten}"', block)
                    n += 1
                    return block

                xml = re.sub(r'<p:sp>.*?</p:sp>', fix, xml, flags=re.S)
                data = xml.encode("utf-8")
            zout.writestr(item, data)
    import os; os.remove(dst + ".tmp")
    print(f"[track] 收紧 {n} 个文本框字距 → {dst}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else -40)
