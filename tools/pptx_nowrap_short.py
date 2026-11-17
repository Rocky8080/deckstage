#!/usr/bin/env python3
"""所有“短文本”（≤8 字、无换行）一律禁止自动换行：数字、标题不应被拆成两行。"""
import re, shutil, sys, zipfile


def main(src, dst, maxlen=8):
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
                    sp = m.group(0)
                    texts = re.findall(r"<a:t>([^<]*)</a:t>", sp)
                    if not texts:
                        return sp
                    plain = "".join(texts).strip()
                    if not plain or len(plain) > maxlen or "\n" in plain:
                        return sp
                    n += 1
                    if 'wrap="square"' in sp:
                        sp = sp.replace('wrap="square"', 'wrap="none"', 1)
                    elif 'wrap=' in sp.split("<a:bodyPr", 1)[-1][:160]:
                        return sp
                    else:
                        sp = re.sub(r"<a:bodyPr", '<a:bodyPr wrap="none"', sp, count=1)
                    # 窄框里的纯数字：再缩一点，保证单行
                    ext = re.search(r'<a:ext cx="(\d+)"', sp)
                    if ext and re.fullmatch(r"[0-9.,%+\-]{1,8}", plain):
                        w_px = int(ext.group(1)) / 9525 / 72 * 96 * 1.333
                        sz = re.search(r'sz="(\d+)"', sp)
                        if sz:
                            need = len(plain) * int(sz.group(1)) / 100 * 1.333 * 0.62
                            k = max(0.55, min(1.0, (w_px * 0.92) / need)) if need > 0 else 1.0
                            if k < 0.995:
                                sp = re.sub(r'sz="(\d+)"',
                                            lambda mm: 'sz="%d"' % max(600, int(int(mm.group(1)) * k)), sp)
                    return sp

                xml = re.sub(r"<p:sp>.*?</p:sp>", fix, xml, flags=re.S)
                data = xml.encode("utf-8")
            zout.writestr(item, data)
    import os; os.remove(dst + ".tmp")
    print(f"[nowrap-short] {n} 个短文本禁止换行 → {dst}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 8)
