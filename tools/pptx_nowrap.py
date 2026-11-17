#!/usr/bin/env python3
"""对“短文本”文本框禁用自动换行（原稿里本来就是一行，因字体宽度差异被迫折行）。"""
import re, shutil, sys, zipfile

MAXLEN = 16


def main(src, dst, maxlen=MAXLEN):
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
                    texts = re.findall(r"<a:t>([^<]*)</a:t>", block)
                    if not texts:
                        return block
                    plain = "".join(texts).strip()
                    if not plain or len(plain) > maxlen or "\n" in plain:
                        return block
                    if 'wrap=' in block.split("<a:bodyPr", 1)[-1][:200]:
                        return block
                    block = re.sub(r'<a:bodyPr', '<a:bodyPr wrap="none"', block, count=1)
                    n += 1
                    return block

                xml = re.sub(r'<p:sp>.*?</p:sp>', fix, xml, flags=re.S)
                data = xml.encode("utf-8")
            zout.writestr(item, data)
    import os; os.remove(dst + ".tmp")
    print(f"[nowrap] {n} 个短文本禁用换行 → {dst}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else MAXLEN)
