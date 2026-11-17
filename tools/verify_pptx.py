#!/usr/bin/env python3
"""tools/verify_pptx.py — 校验 .pptx（页数 / 尺寸 / 每页文本块与图片数 / 越界）

用法：
  python3 tools/verify_pptx.py FILE.pptx
  python3 tools/verify_pptx.py FILE.pptx --expect-slides 17 --json

退出码：0 通过，1 校验失败（文件打不开 / 页数不符 / 空白页 / 尺寸不是 16:9）
"""
import argparse
import json
import os
import sys

from pptx import Presentation
from pptx.util import Emu

EMU_IN = 914400.0


def analyze(path):
    prs = Presentation(path)
    w_in = prs.slide_width / EMU_IN
    h_in = prs.slide_height / EMU_IN
    out = {
        "file": os.path.abspath(path),
        "bytes": os.path.getsize(path),
        "slideCount": len(prs.slides),
        "widthIn": round(w_in, 4),
        "heightIn": round(h_in, 4),
        "aspect": round(w_in / h_in, 4) if h_in else None,
        "slides": [],
        "problems": [],
    }
    for i, slide in enumerate(prs.slides):
        texts, pics, shapes, chars, overflow = 0, 0, 0, 0, 0
        for sh in slide.shapes:
            shapes += 1
            try:
                if sh.shape_type is not None and int(sh.shape_type) == 13:  # PICTURE
                    pics += 1
            except (ValueError, TypeError):
                pass
            if getattr(sh, "has_text_frame", False) and sh.has_text_frame:
                t = sh.text_frame.text.strip()
                if t:
                    texts += 1
                    chars += len(t)
            # 越界检查（容差 0.03in）
            try:
                if sh.left is not None and sh.top is not None and sh.width and sh.height:
                    if (sh.left < -27200 or sh.top < -27200
                            or sh.left + sh.width > prs.slide_width + 27200
                            or sh.top + sh.height > prs.slide_height + 27200):
                        overflow += 1
            except (TypeError, ValueError):
                pass
        rec = {
            "index": i + 1,
            "title": slide.name if getattr(slide, "name", None) else "",
            "texts": texts,
            "pictures": pics,
            "shapes": shapes,
            "chars": chars,
            "overflow": overflow,
        }
        out["slides"].append(rec)
        if texts == 0 and pics == 0:
            out["problems"].append("第 %d 页既没有文字也没有图片" % (i + 1))
        if overflow:
            out["problems"].append("第 %d 页有 %d 个元素越出幻灯片边界" % (i + 1, overflow))

    out["totalTexts"] = sum(s["texts"] for s in out["slides"])
    out["totalPictures"] = sum(s["pictures"] for s in out["slides"])
    out["totalChars"] = sum(s["chars"] for s in out["slides"])
    if abs(out["aspect"] - 16 / 9) > 0.01:
        out["problems"].append("宽高比不是 16:9（实际 %.4f）" % out["aspect"])
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="校验生成的 .pptx")
    ap.add_argument("file")
    ap.add_argument("--expect-slides", type=int, default=None)
    ap.add_argument("--json", action="store_true", help="只输出 JSON")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args(argv)

    if not os.path.exists(a.file):
        print("找不到文件: %s" % a.file, file=sys.stderr)
        return 1
    try:
        rep = analyze(a.file)
    except Exception as e:  # noqa: BLE001
        print("❌ 打不开（python-pptx 解析失败）: %s" % e, file=sys.stderr)
        return 1

    ok = True
    if a.expect_slides is not None and rep["slideCount"] != a.expect_slides:
        rep["problems"].append("页数 %d != 期望 %d" % (rep["slideCount"], a.expect_slides))
        ok = False
    if rep["problems"]:
        ok = False

    if a.json:
        print(json.dumps(rep, ensure_ascii=False, indent=2))
    else:
        print("文件: %s" % rep["file"])
        print("大小: %.1f KB" % (rep["bytes"] / 1024.0))
        print("页数: %d    尺寸: %.4f x %.4f in   宽高比: %.4f" % (
            rep["slideCount"], rep["widthIn"], rep["heightIn"], rep["aspect"]))
        print("合计: 文本块 %d / 图片 %d / 字符 %d" % (
            rep["totalTexts"], rep["totalPictures"], rep["totalChars"]))
        if not a.quiet:
            print("\n页码  文本块  图片  形状  字符  越界  标题")
            for s in rep["slides"]:
                print("%4d %6d %5d %5d %5d %5d  %s" % (
                    s["index"], s["texts"], s["pictures"], s["shapes"],
                    s["chars"], s["overflow"], s["title"]))
        if rep["problems"]:
            print("\n问题:")
            for p in rep["problems"]:
                print("  ⚠️  " + p)
        else:
            print("\n✅ 校验通过")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
