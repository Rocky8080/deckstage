#!/usr/bin/env python3
"""通用 PPTX 导入：渲染保真 + 自动补字。

用法：
  python3 tools/pptx_import.py --pptx /tmp/x.pptx --slug my-deck --src src-my
流程：soffice → PDF（缓存）→ 逐页 1600×900 JPEG → 检测未渲染文字 → 生成 slides/*.html
"""
import argparse, io, pathlib, re, subprocess
import numpy as np
import fitz
from PIL import Image
from pptx import Presentation

SOFFICE = "/Applications/LibreOffice.app/Contents/MacOS/soffice"
W, H = 1600, 900

FONT_MAP = {
    "Times New Roman": "'Times New Roman', 'Songti SC', serif",
    "Calibri": "'Calibri', 'Carlito', 'Helvetica Neue', Arial, sans-serif",
    "Arial": "Arial, 'Helvetica Neue', sans-serif",
    "微软雅黑": "'Microsoft YaHei', 'PingFang SC', sans-serif",
    "宋体": "'Songti SC', 'SimSun', serif",
    "等线": "'PingFang SC', 'Helvetica Neue', sans-serif",
}


def font_stack(name):
    for k, v in FONT_MAP.items():
        if k.lower() in (name or "").lower():
            return v
    return "'Helvetica Neue', Arial, 'PingFang SC', sans-serif"


def rail_of(title, n, total):
    """按标题关键字粗分章节（用于顶部导轨）"""
    t = (title or "").lower()
    if "tournament" in t or "competition" in t or "cup" in t:
        return "Tournaments"
    if "international" in t or "cooperation" in t or "global" in t or "tum" in t or "mit" in t:
        return "Global"
    if "program" in t or "education" in t or "camp" in t or "accelerator" in t or "alumni" in t:
        return "Programs"
    return "About"


def to_pdf(pptx: pathlib.Path, pdf: pathlib.Path):
    if pdf.exists() and pdf.stat().st_mtime >= pptx.stat().st_mtime:
        return pdf
    pdf.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([SOFFICE, "--headless", "--norestore", "--convert-to", "pdf",
                    "--outdir", str(pdf.parent), str(pptx)], check=True, timeout=1800)
    return pdf


def erase_tofu(draw, img, box, pad=None):
    """抹掉缺字方块：逐列取“背景分位数”颜色（排除文字像素），再横向平滑填充。"""
    x0, y0, x1, y1 = box
    if pad is None:
        pad = max(2, int((y1 - y0) * 0.22))
    x0 = max(0, x0 - pad); y0 = max(0, y0 - pad)
    x1 = min(img.width, x1 + pad); y1 = min(img.height, y1 + pad)
    if x1 - x0 < 2 or y1 - y0 < 2:
        return
    px = img.load()
    cols = []
    for x in range(x0, x1):
        vals = [px[x, y] for y in range(y0, y1)]
        vals.sort(key=lambda c: c[0] * 0.299 + c[1] * 0.587 + c[2] * 0.114)
        mid = vals[len(vals) // 2]
        mid_lum = mid[0] * 0.299 + mid[1] * 0.587 + mid[2] * 0.114
        idx = int(len(vals) * (0.82 if mid_lum > 128 else 0.18))
        cols.append(vals[min(len(vals) - 1, idx)])
    # 横向 5 像素滑动平均，消除残留噪声
    sm = []
    for i in range(len(cols)):
        seg = cols[max(0, i - 2): i + 3]
        sm.append(tuple(sum(c[k] for c in seg) // len(seg) for k in range(3)))
    for x, c in zip(range(x0, x1), sm):
        for y in range(y0, y1):
            px[x, y] = c


def looks_like_tofu(crop_rgb):
    """判断裁剪区是不是缺字方块：边框有墨、中心空白。"""
    import numpy as _np
    a = _np.asarray(crop_rgb.convert("RGB"), dtype=_np.int16)
    h, w = a.shape[:2]
    if h < 6 or w < 6:
        return False
    # 以四边中位色为底色，明显偏离即为“墨”
    border = _np.concatenate([a[0, :, :], a[-1, :, :], a[:, 0, :], a[:, -1, :]])
    base = _np.median(border, axis=0)
    ink = (_np.abs(a - base).sum(axis=2) > 120)
    # 去掉边缘一圈后的外框 / 中心
    ring = _np.concatenate([ink[0:2, :].ravel(), ink[-2:, :].ravel(),
                            ink[:, 0:2].ravel(), ink[:, -2:].ravel()])
    ch0, ch1 = int(h * 0.3), int(h * 0.7)
    cw0, cw1 = int(w * 0.3), int(w * 0.7)
    center = ink[ch0:ch1, cw0:cw1]
    ring_frac = ring.mean() if ring.size else 0
    center_frac = center.mean() if center.size else 0
    return ring_frac > 0.10 and center_frac < 0.06


def invisible_overlay(page, img, scale=W / 960.0, sy=None):
    """PDF 里有文字但没画出来（或因缺字体画成方块）的行 → 按原坐标补成 HTML

    scale / sy：PDF→1600×900 画布的 x / y 缩放比。16:9 页两者相等；
    4:3 页（如 720×540pt）被拉伸成 1600×900 后两者不同，必须分别传入。
    """
    from PIL import ImageDraw
    sx = scale
    syy = scale if sy is None else sy
    draw = ImageDraw.Draw(img)
    out = []
    for b in page.get_text("dict")["blocks"]:
        for l in b.get("lines", []):
            for sp in l.get("spans", []):
                t = sp["text"]
                if not t.strip() or t.strip() in {"•", "·", "…"}:
                    continue
                x0, y0, x1, y1 = sp["bbox"][0] * sx, sp["bbox"][1] * syy, sp["bbox"][2] * sx, sp["bbox"][3] * syy
                w_px, h_px = x1 - x0, y1 - y0
                baseline = round(sp["origin"][1] * syy, 1) if sp.get("origin") else round(y1, 1)
                if w_px < 2 or h_px < 2:
                    continue
                box = (int(x0), int(y0), int(max(x1, x0 + 1)), int(max(y1, y0 + 1)))
                # Wingdings 项目符号等私用区字符 → 抹掉方块，画成 •
                if t and all("\ue000" <= ch <= "\uf8ff" for ch in t):
                    erase_tofu(draw, img, box, pad=max(2, int((y1 - y0) * 0.12)))
                    size_b = round(max(6.0, (y1 - y0) * 0.8), 1)
                    out.append(
                        f'<span class="xl3__t" data-bl="{baseline}" data-fs="{size_b}" '
                        f'style="left:{round(x0, 1)}px;top:{round(y0, 1)}px;'
                        f'font-size:{size_b}px;line-height:{round(size_b, 1)}px;'
                        f'color:#%06X;font-family:system-ui">•</span>' % sp["color"])
                    continue
                crop = np.asarray(img.crop(box).convert("L"), dtype=np.float32)
                has_cjk = any("\u4e00" <= ch <= "\u9fff" for ch in t)
                drawn = bool(crop.size) and float(crop.std()) > 6
                if drawn:
                    continue      # 已经画出来（含中文）→ 不补、不擦
                # 纯拉丁文字若未绘制，也补（沿用原逻辑）
                # 自动缩放文本框在 PDF 里记录的是未缩放字号 → 用框宽反推真实字号
                cjk = sum(1 for ch in t if "\u4e00" <= ch <= "\u9fff")
                em = cjk * 1.0 + (len(t) - cjk) * 0.52
                by_width = w_px / em if em > 0 else h_px * 0.84
                size = round(max(6.0, min(by_width * 0.99, h_px * 0.92)), 1)
                text = t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                fam = ("'PingFang SC','Hiragino Sans GB','Microsoft YaHei',sans-serif"
                       if any("\u4e00" <= ch <= "\u9fff" for ch in t)
                       else font_stack(sp.get("font")))
                out.append(
                    f'<span class="xl3__t" data-w="{round(max(4.0, w_px), 1)}" data-fs="{size}" '
                    f'data-bl="{baseline}" style="left:{round(x0, 1)}px;top:{round(y0, 1)}px;'
                    f'font-size:{size}px;line-height:{round(size * 1.05, 1)}px;'
                    f'color:#%06X;font-family:{fam}">{text}</span>'
                    % sp["color"])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pptx", required=True)
    ap.add_argument("--slug", required=True, help="资源目录名，如 xlab-2026-10")
    ap.add_argument("--src", required=True, help="内容源目录，如 src-xlab2")
    ap.add_argument("--pdf", default="")
    args = ap.parse_args()

    src = pathlib.Path(args.pptx)
    pdf = pathlib.Path(args.pdf) if args.pdf else pathlib.Path("/tmp") / (src.stem + ".pdf")
    assets = pathlib.Path("assets") / args.slug
    slides = pathlib.Path(args.src) / "slides"
    assets.mkdir(parents=True, exist_ok=True)
    slides.mkdir(parents=True, exist_ok=True)
    for f in slides.glob("*-slide.html"):
        f.unlink()

    doc = fitz.open(to_pdf(src, pdf))
    total = len(doc)

    # 原稿文本（写进讲稿面板）
    prs = Presentation(str(src))
    texts = {}
    for i, s in enumerate(prs.slides, 1):
        tt = [sh.text_frame.text.strip() for sh in s.shapes
              if sh.has_text_frame and sh.text_frame.text.strip()]
        texts[i] = (tt[0] if tt else f"{args.slug} · {i}", "\n".join(tt))

    fixes = 0
    for i, page in enumerate(doc, 1):
        pix = page.get_pixmap(matrix=fitz.Matrix(W / page.rect.width, H / page.rect.height))
        im = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB").resize((W, H), Image.LANCZOS)
        jpg = assets / f"slide{i:02d}.jpg"
        # 先补字（会擦掉方块字），再保存图片
        overlay = invisible_overlay(page, im)
        im.save(jpg, "JPEG", quality=88, optimize=True, progressive=True)
        fixes += len(overlay)
        title, alltext = texts.get(i, (f"{args.slug} · {i}", ""))
        title_clean = title.replace("\n", " ").replace('"', "&quot;")[:60]
        rail = rail_of(title, i, total)
        notes = (alltext.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                 .replace("\n", "<br>"))
        (slides / f"{i:02d}-slide.html").write_text(
            f'''<section data-imported="pptx" class="slide xl3" id="s{i:02d}" data-title="{title_clean}" data-rail="{rail}">
  <img class="xl3__bg" data-src="assets/{args.slug}/{jpg.name}" alt="{title_clean}" loading="lazy">
  <div class="xl3__fix">{"".join(overlay)}</div>
  <aside class="notes">{notes}</aside>
</section>
''', encoding="utf-8")

    print(f"[import] {total} 屏 · 补字 {fixes} 处 · 资源 assets/{args.slug}/")


if __name__ == "__main__":
    main()
