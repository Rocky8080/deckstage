#!/usr/bin/env python3
"""按比例缩小所有字号（只改 sz 属性，不动 XML 结构），缓解字体替换导致的折行。"""
import re, shutil, sys, zipfile


def main(src, dst, k=0.96):
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

                def repl(m):
                    nonlocal n
                    n += 1
                    return 'sz="%d"' % max(600, int(int(m.group(1)) * k))

                xml = re.sub(r'sz="(\d+)"', repl, xml)
                data = xml.encode("utf-8")
            zout.writestr(item, data)
    import os; os.remove(dst + ".tmp")
    print(f"[shrink] {n} 处字号 ×{k} → {dst}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], float(sys.argv[3]) if len(sys.argv) > 3 else 0.96)
