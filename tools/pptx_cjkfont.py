#!/usr/bin/env python3
"""把 PPTX 里的文字统一指向某个中文字体（只用于渲染），并可给自动缩放留余量。"""
import _platform  # noqa: F401  — Windows GBK 管道下的 stdout UTF-8 兜底（见 _platform.py）
import re, shutil, sys, zipfile

TARGET = "Hiragino Sans GB"
SRC_FONTS = ["Arial", "Times New Roman", "Calibri", "Calibri Light", "微软雅黑",
             "思源黑体 CN", "思源黑体", "等线", "Inter", "Poppins Light", "Poppins"]


def rewrite(xml: str, target: str, shrink: float) -> str:
    for f in SRC_FONTS:
        xml = xml.replace(f'typeface="{f}"', f'typeface="{target}"')
    xml = xml.replace('typeface="+mn-ea"', f'typeface="{target}"').replace('typeface="+mj-ea"', f'typeface="{target}"')
    if shrink < 0.999:
        pct = int(round(shrink * 100000))
        xml = re.sub(r'fontScale="(\d+)"',
                     lambda m: 'fontScale="%d"' % max(20000, int(int(m.group(1)) * shrink)), xml)
        xml = re.sub(r'<a:normAutofit(?![^>]*fontScale)[^>]*/?>',
                     lambda m: m.group(0).replace('<a:normAutofit', f'<a:normAutofit fontScale="{pct}"', 1), xml)
    return xml


def main(src, dst, target=TARGET, shrink=1.0):
    shutil.copy(src, dst + ".tmp")
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename.endswith(".xml") and any(k in item.filename for k in
                                                     ("slide", "theme", "layout", "master")):
                try:
                    data = rewrite(data.decode("utf-8"), target, shrink).encode("utf-8")
                except UnicodeDecodeError:
                    pass
            zout.writestr(item, data)
    import os; os.remove(dst + ".tmp")
    print(f"[cjkfont] {dst} · {target} · shrink={shrink}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2],
         sys.argv[3] if len(sys.argv) > 3 else TARGET,
         float(sys.argv[4]) if len(sys.argv) > 4 else 1.0)
