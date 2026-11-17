#!/usr/bin/env python3
"""只缩小表格（a:tbl）内的字号：表格列宽固定，字体变宽就会折行。"""
import re, shutil, sys, zipfile


def main(src, dst, k=0.90):
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
                    tbl = m.group(0)

                    def rc(mm):
                        nonlocal n
                        n += 1
                        return 'sz="%d"' % max(600, int(int(mm.group(1)) * k))

                    return re.sub(r'sz="(\d+)"', rc, tbl)

                xml = re.sub(r"<a:tbl>.*?</a:tbl>", fix, xml, flags=re.S)
                data = xml.encode("utf-8")
            zout.writestr(item, data)
    import os; os.remove(dst + ".tmp")
    print(f"[tableshrink] {n} 处表格字号 ×{k} → {dst}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], float(sys.argv[3]) if len(sys.argv) > 3 else 0.90)
