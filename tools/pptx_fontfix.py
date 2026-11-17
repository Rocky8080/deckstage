#!/usr/bin/env python3
"""把 PPTX 里本机没有的字体名替换为本机可用字体（只用于渲染，不改原文件）。"""
import re, shutil, sys, zipfile

SHRINK = 1.0   # 由命令行第二参数控制（如 0.96）

MAP = {
    "Arial": "Arial Unicode MS",
    "Times New Roman": "Arial Unicode MS",
    "Calibri": "Arial Unicode MS",
    "Calibri Light": "Arial Unicode MS",
    "微软雅黑": "Arial Unicode MS",
    "思源黑体 CN": "Arial Unicode MS",
    "思源黑体": "Arial Unicode MS",
    "等线": "Arial Unicode MS",
    "微软雅黑 Light": "Arial Unicode MS",
    "Inter": "Helvetica Neue",
    "Poppins Light": "Helvetica Neue",
    "Poppins": "Helvetica Neue",
}

def apply_shrink(xml: str, k: float) -> str:
    """给自动缩放文本框留出余量：已有 fontScale 的按比例缩小，没有的补上。"""
    if k >= 0.999:
        return xml
    pct = int(round(k * 100000))
    # 已有 fontScale
    def repl_scale(m):
        cur = int(m.group(1))
        return 'fontScale="%d"' % max(20000, int(cur * k))
    xml = re.sub(r'fontScale="(\d+)"', repl_scale, xml)
    # bodyPr 里带 normAutofit 但无 fontScale → 补上
    def repl_auto(m):
        seg = m.group(0)
        if 'fontScale' in seg:
            return seg
        return seg.replace('<a:normAutofit', f'<a:normAutofit fontScale="{pct}"', 1)
    xml = re.sub(r'<a:normAutofit[^>]*/?>', repl_auto, xml)
    return xml


def main(src, dst, shrink=1.0):
    shutil.copy(src, dst)
    tmp = dst + ".tmp"
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename.endswith(".xml") and ("slide" in item.filename or "theme" in item.filename
                                                  or "layout" in item.filename or "master" in item.filename):
                try:
                    txt = data.decode("utf-8")
                except UnicodeDecodeError:
                    zout.writestr(item, data); continue
                for k, v in MAP.items():
                    txt = txt.replace(f'typeface="{k}"', f'typeface="{v}"')
                txt = apply_shrink(txt, shrink)
                data = txt.encode("utf-8")
            zout.writestr(item, data)
    shutil.move(tmp, dst)
    print(f"[fontfix] {dst}")

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], float(sys.argv[3]) if len(sys.argv) > 3 else 1.0)
