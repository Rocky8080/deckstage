#!/usr/bin/env python3
"""tools/preview_pptx.py — 把生成的 .pptx 渲染成 PNG 做视觉自查

本机没有 PowerPoint / LibreOffice，这里用 Pillow 按 pptx 里的真实几何
（位置/尺寸/字号/颜色/填充/图片）近似重绘，只为检查版式问题：
文字溢出、文本框错位、图层顺序、图片缺失、色块没出来。

⚠️ 不是像素级还原：字体是替身（Songti/PingFang -> 本机可用字体），
   断行也只是近似。用途是「看结构」，不是「比像素」。

用法：
  python3 tools/preview_pptx.py out.pptx --out /tmp/preview
  python3 tools/preview_pptx.py out.pptx --slides 1,3,5
"""
import argparse
import io
import os
import sys

from PIL import Image, ImageDraw, ImageFont
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE
from pptx.util import Emu

EMU_IN = 914400.0
DPI = 120.0  # 1600px / 13.3333in —— 与设计坐标 1:1


def px(emu):
    return float(emu) / EMU_IN * DPI


SERIF_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Songti.ttc",
    "/System/Library/Fonts/STHeiti Medium.ttc",
]
SANS_CANDIDATES = [
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
]
LATIN_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
]


def _first_existing(paths):
    for p in paths:
        if os.path.exists(p):
            return p
    return None


_SERIF = _first_existing(SERIF_CANDIDATES)
_SANS = _first_existing(SANS_CANDIDATES)
_LATIN = _first_existing(LATIN_CANDIDATES)


_CJK_FACE_HINTS = ("song", "ping", "hiragino", "yahei", "hei", "kai", "宋", "simsun",
                   "fangsong", "noto serif", "noto sans cjk", "stsong", "stheit", "source han")


def pick_font_path(font_face, text):
    face = (font_face or "").lower()
    cjk = any("\u3400" <= ch <= "\u9fff" for ch in text or "")
    if cjk and not any(h in face for h in _CJK_FACE_HINTS):
        return _SANS            # 拉丁/等宽字体没有中文字形 -> 用中文字体替身
    if "song" in face or "serif" in face or "宋" in face:
        return _SERIF or _SANS
    if "mono" in face or "menlo" in face or "consolas" in face:
        return _first_existing(["/System/Library/Fonts/Menlo.ttc"]) or _LATIN or _SANS
    if cjk:
        return _SANS
    return _LATIN or _SANS


_font_cache = {}

# .ttc 里真正的粗体 face 索引（用 ink 覆盖率测出来的，避免 PIL 假粗体的偏移 bug）
_BOLD_INDEX = {
    "/System/Library/Fonts/Hiragino Sans GB.ttc": 2,
    "/System/Library/Fonts/Supplemental/Songti.ttc": 1,
}
_REGULAR_INDEX = {
    "/System/Library/Fonts/Supplemental/Songti.ttc": 3,   # Songti SC Light 更接近 regular
}


def get_font(path, size, bold=False):
    idx = (_BOLD_INDEX.get(path, 0) if bold else _REGULAR_INDEX.get(path, 0))
    key = (path, int(size), idx)
    if key not in _font_cache:
        try:
            _font_cache[key] = ImageFont.truetype(path, int(size), index=idx)
        except Exception:  # noqa: BLE001
            try:
                _font_cache[key] = ImageFont.truetype(path, int(size))
            except Exception:  # noqa: BLE001
                _font_cache[key] = ImageFont.load_default()
    return _font_cache[key]


def wrap_text(text, font, max_w):
    lines, cur = [], ""
    for ch in text:
        if ch == "\n":
            lines.append(cur)
            cur = ""
            continue
        trial = cur + ch
        if max_w > 4 and font.getlength(trial) > max_w and cur:
            idx = cur.rfind(" ")
            if idx > 0 and (len(cur) - idx) < 10:
                lines.append(cur[:idx])
                cur = cur[idx + 1:] + ch
            else:
                lines.append(cur)
                cur = ch
        else:
            cur = trial
    if cur:
        lines.append(cur)
    return lines or [""]


def shape_geom(shape):
    return (px(shape.left), px(shape.top), px(shape.width), px(shape.height))


def preset_of(shape):
    try:
        prst = shape._element.spPr.find(
            "{http://schemas.openxmlformats.org/drawingml/2006/main}prstGeom")
        if prst is not None:
            return prst.get("prst")
    except Exception:  # noqa: BLE001
        pass
    return "rect"


def fill_of(shape):
    """返回 (rgb_tuple, alpha 0..1) 或 None"""
    try:
        el = shape._element.spPr.find(
            "{http://schemas.openxmlformats.org/drawingml/2006/main}solidFill")
        if el is None:
            return None
        clr = el.find("{http://schemas.openxmlformats.org/drawingml/2006/main}srgbClr")
        if clr is None:
            return None
        rgb = tuple(int(clr.get("val")[i:i + 2], 16) for i in (0, 2, 4))
        alpha = 1.0
        a = clr.find("{http://schemas.openxmlformats.org/drawingml/2006/main}alpha")
        if a is not None:
            alpha = int(a.get("val")) / 100000.0
        return rgb, alpha
    except Exception:  # noqa: BLE001
        return None


def line_of(shape):
    try:
        ln = shape._element.spPr.find(
            "{http://schemas.openxmlformats.org/drawingml/2006/main}ln")
        if ln is None:
            return None
        w = ln.get("w")
        if not w or int(w) == 0:
            return None
        sf = ln.find("{http://schemas.openxmlformats.org/drawingml/2006/main}solidFill")
        if sf is None:
            return None
        clr = sf.find("{http://schemas.openxmlformats.org/drawingml/2006/main}srgbClr")
        if clr is None:
            return None
        rgb = tuple(int(clr.get("val")[i:i + 2], 16) for i in (0, 2, 4))
        return rgb, max(1, int(round(int(w) / 12700.0 / 0.6)))  # pt -> 设计px
    except Exception:  # noqa: BLE001
        return None


def render_slide(slide, prs):
    W = int(round(px(prs.slide_width)))
    H = int(round(px(prs.slide_height)))
    img = Image.new("RGB", (W, H), (255, 255, 255))
    draw = ImageDraw.Draw(img, "RGBA")

    # 背景
    try:
        bg = slide.background
        fc = bg.fill
        if fc.type is not None and fc.fore_color and fc.fore_color.rgb is not None:
            draw.rectangle([0, 0, W, H], fill=tuple(fc.fore_color.rgb))
    except Exception:  # noqa: BLE001
        pass
    # 背景图（<p:bg><a:blipFill>）
    try:
        blip = slide._element.find(
            ".//{http://schemas.openxmlformats.org/presentationml/2006/main}bg//"
            "{http://schemas.openxmlformats.org/drawingml/2006/main}blip")
        if blip is not None:
            rid = blip.get(
                "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed")
            part = slide.part.related_part(rid)
            bimg = Image.open(io.BytesIO(part.blob)).convert("RGBA").resize((W, H))
            img.paste(bimg, (0, 0), bimg)
    except Exception:  # noqa: BLE001
        pass

    for shape in slide.shapes:
        x, y, w, h = shape_geom(shape)
        if shape.shape_type == MSO_SHAPE_TYPE.PICTURE:
            try:
                pimg = Image.open(io.BytesIO(shape.image.blob)).convert("RGBA")
                pimg = pimg.resize((max(1, int(w)), max(1, int(h))))
                img.paste(pimg, (int(x), int(y)), pimg)
            except Exception as e:  # noqa: BLE001
                draw.rectangle([x, y, x + w, y + h], outline=(255, 0, 0), width=2)
                print("  ! 图片渲染失败: %s" % e, file=sys.stderr)
            continue

        f = fill_of(shape)
        l = line_of(shape)
        prst = preset_of(shape)
        if f or l:
            rgb, alpha = f if f else ((255, 255, 255), 0.0)
            fill = rgb if alpha >= 0.999 else None
            outline = rgb if 0 < alpha < 0.999 else None
            if prst == "ellipse":
                draw.ellipse([x, y, x + w, y + h], fill=fill, outline=outline,
                             width=max(1, int(l[1])) if l else 1)
            elif prst == "roundRect":
                r = min(w, h) * 0.16
                draw.rounded_rectangle([x, y, x + w, y + h], radius=r, fill=fill,
                                       outline=outline)
            else:
                draw.rectangle([x, y, x + w, y + h], fill=fill,
                               outline=(l[0] if l else None), width=(l[1] if l else 1))

        if not (getattr(shape, "has_text_frame", False) and shape.has_text_frame):
            continue
        tf = shape.text_frame
        if not tf.text.strip():
            continue
        nowrap = False
        try:
            bodyPr = shape._element.find(
                ".//{http://schemas.openxmlformats.org/drawingml/2006/main}bodyPr")
            if bodyPr is not None and bodyPr.get("wrap") == "none":
                nowrap = True
        except Exception:  # noqa: BLE001
            pass
        cy = y
        for para in tf.paragraphs:
            text = "".join(r.text for r in para.runs)
            if not text:
                cy += 6
                continue
            r0 = para.runs[0]
            size_pt = r0.font.size.pt if r0.font.size else 12.0
            size_px = size_pt / 0.6
            face = r0.font.name
            color = (30, 30, 30)
            try:
                if r0.font.color and r0.font.color.rgb is not None:
                    color = tuple(r0.font.color.rgb)
            except Exception:  # noqa: BLE001
                pass
            bold = bool(r0.font.bold)
            path = pick_font_path(face, text)
            font = get_font(path, size_px, bold)
            ls = para.line_spacing
            if isinstance(ls, float) and 0.5 < ls < 4:
                lh = size_px * ls * 1.2
            elif ls is not None:
                lh = float(ls.pt) / 0.6
            else:
                lh = size_px * 1.2
            lines = [text] if nowrap else wrap_text(text, font, w)
            align = str(para.alignment) if para.alignment is not None else "LEFT"
            for line in lines:
                lw = font.getlength(line)
                if "CENTER" in align:
                    tx = x + (w - lw) / 2
                elif "RIGHT" in align:
                    tx = x + w - lw
                else:
                    tx = x
                draw.text((tx, cy), line, font=font, fill=color)
                if bold and path not in _BOLD_INDEX:   # 没有粗体 face 时才做伪粗体
                    draw.text((tx + 0.7, cy), line, font=font, fill=color)
                cy += lh
    return img


def main(argv=None):
    ap = argparse.ArgumentParser(description="把 pptx 近似渲染成 PNG 做版式自查")
    ap.add_argument("file")
    ap.add_argument("--out", default=None, help="输出目录，默认 <file 所在目录>/preview")
    ap.add_argument("--slides", default=None, help="只渲染这些页，如 1,3,5")
    a = ap.parse_args(argv)

    out_dir = a.out or os.path.join(os.path.dirname(os.path.abspath(a.file)), "preview")
    os.makedirs(out_dir, exist_ok=True)
    prs = Presentation(a.file)
    want = None
    if a.slides:
        want = set(int(s) for s in a.slides.split(",") if s.strip())
    for i, slide in enumerate(prs.slides, 1):
        if want and i not in want:
            continue
        im = render_slide(slide, prs)
        path = os.path.join(out_dir, "preview-%02d.png" % i)
        im.save(path)
        print("%s  %dx%d" % (path, im.width, im.height))
    return 0


if __name__ == "__main__":
    sys.exit(main())
