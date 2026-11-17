#!/usr/bin/env python3
"""缩小组合（grpSp）内“短文本”的字号：这类卡片标题在字体变宽后容易折行。"""
import re, shutil, sys, zipfile

MAXLEN = 18


def main(src, dst, k=0.90, maxlen=MAXLEN):
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

                def fix_group(m):
                    nonlocal n
                    grp = m.group(0)

                    def fix_sp(mm):
                        nonlocal n
                        sp = mm.group(0)
                        texts = re.findall(r"<a:t>([^<]*)</a:t>", sp)
                        if not texts:
                            return sp
                        plain = "".join(texts).strip()
                        if not plain or len(plain) > maxlen or "\n" in plain:
                            return sp
                        # 纯数字/百分比：禁止换行（否则会拆成上下两行）
                        if re.fullmatch(r"[0-9.,%+\-]{1,8}", plain):
                            if "wrap=" not in sp.split("<a:bodyPr", 1)[-1][:160]:
                                sp = re.sub(r"<a:bodyPr", '<a:bodyPr wrap="none"', sp, count=1)
                            n += 1
                            return sp
                        sp = re.sub(r'sz="(\d+)"',
                                    lambda z: 'sz="%d"' % max(600, int(int(z.group(1)) * k)), sp)
                        n += 1
                        return sp

                    return re.sub(r"<p:sp>.*?</p:sp>", fix_sp, grp, flags=re.S)

                xml = re.sub(r"<p:grpSp>.*?</p:grpSp>", fix_group, xml, flags=re.S)
                data = xml.encode("utf-8")
            zout.writestr(item, data)
    import os; os.remove(dst + ".tmp")
    print(f"[groupfit] {n} 个组合内短标题字号 ×{k} → {dst}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], float(sys.argv[3]) if len(sys.argv) > 3 else 0.90,
         int(sys.argv[4]) if len(sys.argv) > 4 else MAXLEN)
