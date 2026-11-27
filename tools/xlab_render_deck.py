#!/usr/bin/env python3
"""用 LibreOffice 把原 PPTX 渲染成逐屏底图，生成视觉 1:1 的 HTML 幻灯片。

流程：soffice → PDF → 每页 JPEG(1600×900) → src-xlab/slides/NN-slide.html
每屏 = 渲染图（懒加载）+ 原文文本层（讲稿面板可检索/复制）
"""
import _platform  # noqa: F401  — Windows GBK 管道下的 stdout UTF-8 兜底（见 _platform.py）
import io, pathlib, subprocess
import numpy as np
import fitz
from PIL import Image
from pptx import Presentation

SRC = pathlib.Path("/tmp/xlab.pptx")
PDF = pathlib.Path("/tmp/lo_out/xlab.pdf")
ASSETS = pathlib.Path("assets/xlab3")
SLIDES = pathlib.Path("src-xlab/slides")
SOFFICE = _platform.find_soffice()
W, H = 1600, 900

# 章节归属（按原稿结构）
def rail_of(n):
    if n <= 8:   return "About"
    if n <= 16:  return "Programs"
    if n <= 18:  return "Tournaments"
    if n <= 23:  return "Global"
    return "About"


def to_pdf():
    if PDF.exists() and PDF.stat().st_mtime >= SRC.stat().st_mtime:
        return PDF
    PDF.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([SOFFICE, "--headless", "--norestore", "--convert-to", "pdf",
                    "--outdir", str(PDF.parent), str(SRC)], check=True, timeout=900)
    return PDF


def render(pdf):
    ASSETS.mkdir(parents=True, exist_ok=True)
    doc = fitz.open(pdf)
    out = []
    total_fix = 0
    for i, page in enumerate(doc, 1):
        pix = page.get_pixmap(matrix=fitz.Matrix(W / page.rect.width, H / page.rect.height))
        im = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB").resize((W, H), Image.LANCZOS)
        f = ASSETS / f"slide{i:02d}.jpg"
        im.save(f, "JPEG", quality=88, optimize=True, progressive=True)
        overlay = invisible_overlay(page, im)
        total_fix += len(overlay)
        out.append((i, f, overlay))
    print(f"[render] {len(out)} 屏 · {sum(f.stat().st_size for _, f, _ in out)/1e6:.1f} MB · 补字 {total_fix} 处")
    return out


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


def invisible_overlay(page, img, scale=W / 960.0):
    """找出 PDF 里没被画出来的文字，按原稿坐标/字号/颜色补成 HTML（保真版）。

    不做重排、不放大小字号：字号取「PDF 声明字号」与「实际行高」的较小者，
    位置严格用 PDF bbox —— 与 PowerPoint 里的观感一致。
    """
    out = []
    for b in page.get_text("dict")["blocks"]:
        for l in b.get("lines", []):
            for sp in l.get("spans", []):
                t = sp["text"]
                if not t.strip() or t.strip() in {"•", "·", "…"}:
                    continue
                x0, y0, x1, y1 = [v * scale for v in sp["bbox"]]
                w_px, h_px = x1 - x0, y1 - y0
                if w_px < 2 or h_px < 2:
                    continue
                crop = np.asarray(img.crop((int(x0), int(y0), int(max(x1, x0 + 1)),
                                            int(max(y1, y0 + 1)))).convert("L"), dtype=np.float32)
                if crop.size and float(crop.std()) > 6:      # 已经画出来了
                    continue
                col = "#%06X" % sp["color"]
                # 自动缩放的文本框：PDF 记录的 size 是「未缩放」值，与真实绘制不符。
                # 用「框宽 ÷ 字符数」反推真实字号最可靠（中文 1 字 ≈ 1 个字号宽，西文约 0.52）
                cjk = sum(1 for ch in t if "\u4e00" <= ch <= "\u9fff")
                em = cjk * 1.0 + (len(t) - cjk) * 0.52
                by_width = w_px / em if em > 0 else h_px * 0.84
                size = round(max(6.0, min(by_width * 0.99, h_px * 0.92)), 1)
                text = t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                out.append(
                    f'<span class="xl3__t" data-w="{round(max(4.0, w_px), 1)}" data-fs="{size}" '
                    f'style="left:{round(x0, 1)}px;top:{round(y0, 1)}px;'
                    f'font-size:{size}px;line-height:{round(size * 1.05, 1)}px;'
                    f'color:{col};font-family:{font_stack(sp.get("font"))}">{text}</span>')
    return out


def slide_texts():
    p = Presentation(str(SRC))
    res = {}
    for i, s in enumerate(p.slides, 1):
        titles, body = [], []
        for sh in s.shapes:
            if sh.has_text_frame and sh.text_frame.text.strip():
                t = sh.text_frame.text.strip()
                (titles if not titles else body).append(t)
        res[i] = (titles[0] if titles else f"Tsinghua x-lab · {i}",
                  "\n".join(titles + body))
    return res


def build(items, texts):
    SLIDES.mkdir(parents=True, exist_ok=True)
    for f in SLIDES.glob("*-slide.html"):
        f.unlink()
    for n, jpg, overlay in items:
        title, alltext = texts[n]
        title = title.replace("\n", " ").replace('"', "&quot;")[:60]
        rail = rail_of(n)
        notes = alltext.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>")
        html = f'''<section class="slide xl3" id="s{n:02d}" data-title="{title}" data-rail="{rail}">
  <img class="xl3__bg" data-src="assets/xlab3/{jpg.name}" alt="{title}" loading="lazy">
  <div class="xl3__fix">{"".join(overlay)}</div>
  <aside class="notes">{notes}</aside>
</section>
'''
        (SLIDES / f"{n:02d}-slide.html").write_text(html, encoding="utf-8")
    print(f"[deck] 生成 {len(items)} 屏")


if __name__ == "__main__":
    build(render(to_pdf()), slide_texts())
