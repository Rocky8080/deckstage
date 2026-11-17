#!/usr/bin/env python3
"""
import_pptx.py — 一条命令把外部 PPTX 自动导入为展示台 deck（自动转换 pipeline）

把两个 x-lab deck 导入过程中沉淀的能力串成一条流水线：

  [0/6] 体检      字体清单 / 画幅 / 页数 / 表格·组合·自动缩放统计（--dry-run 只做这步）
  [1/6] 字体规整   默认保留原字体（LibreOffice 原生回退，已验证可用）；
                  --rewrite-fonts 统一改写 / --map 单点映射 / --install-font 安装下载的字体直用
  [2/6] 版式预修   验证配方：短行禁折 → 表格缩字 ×0.9 → 全局缩字 ×0.95；
                  实验手段 --prefit / --track N / --group-k 0.9 默认关闭
  [3/6] 渲染      soffice → PDF → 逐页 1600×900 JPEG（PDF 按 pptx 修改时间缓存）
  [4/6] 补字层    PDF 里没画出来 / 缺字方块的文字，按原坐标补成 HTML 覆盖层
  [5/6] 组装      模板生成 src-<slug>/（shell + deck.css + slides + deck.json）→ build.mjs --deck
  [6/6] 报告      build/import/<slug>/report.json

用法：
  python3 tools/import_pptx.py 源.pptx --slug my-deck
  python3 tools/import_pptx.py 源.pptx --slug my-deck --dry-run          # 只体检，不写任何文件
  python3 tools/import_pptx.py 源.pptx --slug my-deck \
      --install-font "Microsoft YaHei=/path/msyh.ttf"                    # 下载的字体装入 ~/Library/Fonts 后直用
  python3 tools/import_pptx.py 源.pptx --slug my-deck \
      --rail-map "About:1-6 Programs:7-13 Tournaments:14-19 Global:20-33" --publish

行为约定：
  · 已存在 src-<slug>/ 或 decks/<slug>/ 时拒绝执行（--force 才覆盖，防误删已调好的 deck）
  · 默认不动 library 页；--publish 才重拍全部缩略图并刷新 decks.json / library.html
  · --rounds N（默认 1）：第 1 轮用给定参数渲染；若补字过多则自动加码（缩字逐轮 ×0.97）重渲，取补字最少的一轮
"""
import argparse
import contextlib
import datetime
import io
import json
import re
import shutil
import subprocess
import sys
import zipfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))

SOFFICE = "/Applications/LibreOffice.app/Contents/MacOS/soffice"
PREFIT_FONT = Path("/Applications/LibreOffice.app/Contents/Resources/fonts/truetype/Arial Unicode.ttf")
W, H = 1600, 900
RAILS = ["About", "Programs", "Tournaments", "Global"]

# 经验映射（两个 x-lab deck 验证过）：@CJK/@LATIN 是占位，运行时替换为本机实际目标
DEFAULT_MAP = {
    "微软雅黑": "@CJK", "微软雅黑 Light": "@CJK", "思源黑体 CN": "@CJK", "思源黑体": "@CJK",
    "宋体": "@CJK", "黑体": "@CJK", "楷体": "@CJK", "仿宋": "@CJK", "等线": "@CJK", "等线 Light": "@CJK",
    "SimSun": "@CJK", "SimHei": "@CJK", "Microsoft YaHei": "@CJK", "Microsoft YaHei Light": "@CJK",
    "Source Han Sans CN": "@CJK", "Source Han Sans SC": "@CJK", "Noto Sans CJK SC": "@CJK",
    "DengXian": "@CJK", "KaiTi": "@CJK", "FangSong": "@CJK",
    "Arial": "@LATIN", "Times New Roman": "@LATIN", "Calibri": "@LATIN", "Calibri Light": "@LATIN",
    "Inter": "Helvetica Neue", "Poppins": "Helvetica Neue", "Poppins Light": "Helvetica Neue",
}
CJK_NAME = re.compile(
    r"[\u4e00-\u9fff]|yahei|simsun|simhei|songti|heiti|kaiti|fangsong|dengxian"
    r"|source han|noto.*cjk|pingfang|hiragino", re.I)
THEME_EA = {"+mn-ea", "+mj-ea"}     # 主题里的东亚字体占位


def log(stage, msg):
    print(f"  [{stage}] {msg}")


# ---------------------------------------------------------------- 依赖自愈
def ensure_deps():
    """本解释器缺核心依赖时，找一台装齐的 Python 重新执行自己。"""
    missing = []
    for m in ("PIL", "fitz", "numpy", "pptx"):
        try:
            __import__(m)
        except ImportError:
            missing.append(m)
    if not missing:
        return
    import os, shutil
    probe = "import PIL, fitz, numpy, pptx"
    seen = {sys.executable}
    cands = ["/usr/bin/python3", "/opt/homebrew/bin/python3"] + \
            sorted(map(str, Path("/opt/homebrew/bin").glob("python3.*"))) + \
            [shutil.which("python3") or ""]
    for c in cands:
        if not c or c in seen or not Path(c).exists():
            continue
        seen.add(c)
        if subprocess.run([c, "-c", probe], capture_output=True).returncode == 0:
            print(f"[deps] 当前解释器缺 {'/'.join(missing)}，改用 {c} 重跑……")
            os.execv(c, [c, str(Path(__file__).resolve()), *sys.argv[1:]])
    sys.exit(f"当前 python3 缺依赖（{'/'.join(missing)}），且没找到装齐的解释器。"
             "试：/usr/bin/python3 tools/import_pptx.py …")


# ---------------------------------------------------------------- [0] 体检
def inventory(pptx: Path) -> dict:
    fonts, slides = Counter(), 0
    tbl = grp = autofit = cjk_chars = latin_chars = 0
    with zipfile.ZipFile(pptx) as z:
        for name in z.namelist():
            if not re.match(r"ppt/(slides|slideLayouts|slideMasters|theme)/[^/]+\.xml$", name):
                continue
            xml = z.read(name).decode("utf-8", "ignore")
            fonts.update(re.findall(r'typeface="([^"]+)"', xml))
            if "/slides/" in name:
                slides += 1
                tbl += xml.count("<a:tbl>")
                grp += xml.count("<p:grpSp>")
                autofit += xml.count("normAutofit")
                # 语言看实际文本：主题字体清单里常带中文字体名，不足为凭
                body = "".join(re.findall(r"<a:t>([^<]*)</a:t>", xml))
                cjk_chars += sum(1 for ch in body if "\u4e00" <= ch <= "\u9fff")
                latin_chars += sum(1 for ch in body if ch.isascii() and ch.isalpha())
        pres = z.read("ppt/presentation.xml").decode("utf-8", "ignore")
    m = re.search(r'<p:sldSz cx="(\d+)" cy="(\d+)"', pres)
    cw, ch = (int(m.group(1)), int(m.group(2))) if m else (12192000, 6858000)
    ratio = cw / ch
    label = "16:9" if ratio > 1.6 else ("4:3" if 1.2 < ratio <= 1.6 else f"{ratio:.2f}")
    return {"fonts": fonts, "slides": slides, "tables": tbl, "groups": grp,
            "autofit": autofit, "cjk_chars": cjk_chars, "latin_chars": latin_chars,
            "size_pt": (cw / 12700, ch / 12700), "ratio": label}


def pick_targets() -> tuple[str, str]:
    """渲染用字体目标：拉丁 → Arial Unicode MS（LibreOffice 自带，prefit 用它度量）；
    中文 → Hiragino Sans GB（macOS 内置，LibreOffice 中文渲染实际命中的字体）。"""
    latin = "Arial Unicode MS" if PREFIT_FONT.exists() else "Helvetica Neue"
    return latin, "Hiragino Sans GB"


def build_font_map(used: Counter, user_map: dict, latin: str, cjk: str) -> dict:
    """显式 user_map 优先；其余按经验表 / CJK 名字探测路由。"""
    mapping = {}
    for name in used:
        if name in THEME_EA:
            mapping[name] = cjk
            continue
        if name in user_map:
            mapping[name] = user_map[name]
            continue
        tgt = DEFAULT_MAP.get(name)
        if tgt is None:
            tgt = cjk if CJK_NAME.search(name) else latin
        mapping[name] = {"@CJK": cjk, "@LATIN": latin}.get(tgt, tgt)
    return mapping


def apply_font_map(pptx: Path, dst: Path, mapping: dict) -> int:
    """把 typeface="原字体" 改写为映射目标（只写渲染副本，不动原文件）。长名优先防子串误替换。"""
    n = 0
    items = sorted(mapping.items(), key=lambda kv: -len(kv[0]))
    with zipfile.ZipFile(pptx) as zin, zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename.endswith(".xml") and any(
                    k in item.filename for k in ("slide", "theme", "layout", "master")):
                try:
                    xml = data.decode("utf-8")
                except UnicodeDecodeError:
                    zout.writestr(item, data); continue
                for old, new in items:
                    hit = f'typeface="{old}"'
                    c = xml.count(hit)
                    if c:
                        xml = xml.replace(hit, f'typeface="{new}"')
                        n += c
                data = xml.encode("utf-8")
            zout.writestr(item, data)
    return n


# ---------------------------------------------------------------- [2] 版式预修
def fix_chain(src: Path, dst: Path, opts) -> Path:
    """按验证过的顺序逐级预修（m3 配方：nowrap + 全局缩字 + 表格缩字；其余为显式开启的实验手段）"""
    import pptx_nowrap_short, pptx_nowrap, pptx_tableshrink, pptx_groupfit
    import pptx_prefit, pptx_track, pptx_shrink

    steps = []
    if not opts.no_nowrap:
        steps.append(("短行禁折(≤8字)", lambda a, b: pptx_nowrap_short.main(a, b, 8)))
        steps.append(("短行禁折(≤16字)", lambda a, b: pptx_nowrap.main(a, b, 16)))
    if opts.table_k < 0.999:
        steps.append((f"表格缩字 ×{opts.table_k}", lambda a, b: pptx_tableshrink.main(a, b, opts.table_k)))
    if opts.group_k < 0.999:
        steps.append((f"组合内短文本缩字 ×{opts.group_k}", lambda a, b: pptx_groupfit.main(a, b, opts.group_k, 18)))
    if opts.prefit:
        if PREFIT_FONT.exists():
            steps.append(("实测预排 prefit", lambda a, b: pptx_prefit.main(a, b)))
        else:
            log("2/6", f"⚠ 未找到 {PREFIT_FONT}，跳过 prefit")
    if opts.track:
        steps.append((f"收紧字距 {opts.track}", lambda a, b: pptx_track.main(a, b, opts.track)))
    if opts.shrink < 0.999:
        steps.append((f"全局缩字 ×{opts.shrink}", lambda a, b: pptx_shrink.main(a, b, opts.shrink)))
    if not steps:
        shutil.copyfile(src, dst)
        return dst

    f = src
    for i, (label, fn) in enumerate(steps):
        tmp = dst.with_suffix(f".step{i}.pptx")
        fn(str(f), str(tmp))
        if f != src:
            f.unlink()
        f = tmp
        log("2/6", f"{label} → {tmp.name}")
    shutil.move(str(f), dst)
    return dst


def validate_pptx(path: Path) -> list:
    """检查 slide/layout/master/theme 的 XML 是否良构（防修复链写坏结构）。"""
    import xml.etree.ElementTree as ET
    bad = []
    with zipfile.ZipFile(path) as z:
        for name in z.namelist():
            if re.match(r"ppt/(slides|slideLayouts|slideMasters|theme)/[^/]+\.xml$", name):
                try:
                    ET.fromstring(z.read(name))
                except ET.ParseError as e:
                    bad.append(f"{name}: {e}")
    return bad


# ---------------------------------------------------------------- [3][4] 渲染 + 补字层
def render_round(pptx_path: Path, work: Path, slug: str, rail_of_slide: dict, meta: dict):
    """soffice → PDF → 逐页 JPEG + 补字层 slides/*.html。返回 (补字数, 页数)。"""
    try:
        import fitz, numpy  # noqa: F401
        from PIL import Image
        from pptx import Presentation
    except ImportError as e:
        sys.exit(f"缺少依赖：{e.name} —— pip install pymupdf numpy pillow python-pptx")
    import pptx_import as imp

    # soffice 输出文件名跟随输入名（round1.pptx → round1.pdf），所以 pdf 名取 pptx 的 stem
    pdf = work / (pptx_path.stem + ".pdf")
    imp.to_pdf(pptx_path, pdf)

    prs = Presentation(str(pptx_path))
    texts = {}
    for i, s in enumerate(prs.slides, 1):
        tt = [sh.text_frame.text.strip() for sh in s.shapes
              if sh.has_text_frame and sh.text_frame.text.strip()]
        texts[i] = (tt[0] if tt else f"{slug} · {i}", "\n".join(tt))

    assets = work / "assets"
    slides = work / "slides"
    assets.mkdir(parents=True, exist_ok=True)
    slides.mkdir(parents=True, exist_ok=True)
    repairs = 0
    doc = fitz.open(pdf)
    for i, page in enumerate(doc, 1):
        sx, sy = W / page.rect.width, H / page.rect.height
        pix = page.get_pixmap(matrix=fitz.Matrix(sx, sy))
        img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
        overlay = imp.invisible_overlay(page, img, scale=sx, sy=sy)
        repairs += len(overlay)
        jpg = assets / f"slide{i:02d}.jpg"
        img.save(jpg, "JPEG", quality=88, optimize=True, progressive=True)
        title, alltext = texts.get(i, (f"{slug} · {i}", ""))
        title_clean = title.replace("\n", " ").replace('"', "&quot;")[:60]
        rail = rail_of_slide.get(i) or imp.rail_of(title, i, len(doc))
        notes = (alltext.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                 .replace("\n", "<br>"))
        (slides / f"{i:02d}-slide.html").write_text(
            f'''<section data-imported="pptx" class="slide xl3" id="s{i:02d}" data-title="{title_clean}" data-rail="{rail}">
  <img class="xl3__bg" data-src="assets/{slug}/{jpg.name}" alt="{title_clean}" loading="lazy">
  <div class="xl3__fix">{"".join(overlay)}</div>
  <aside class="notes">{notes}</aside>
</section>
''', encoding="utf-8")
    return repairs, len(doc)


# ---------------------------------------------------------------- [5] 组装
def mix_hex(color: str, k: float) -> str:
    """把 #RRGGBB 向白色混合 k（0..1），生成 accent 的浅色变体。"""
    r, g, b = (int(color[i:i + 2], 16) for i in (1, 3, 5))
    r, g, b = (round(v + (255 - v) * k) for v in (r, g, b))
    return f"#{r:02X}{g:02X}{b:02X}"


def assemble(slug: str, meta: dict, total: int, opts) -> None:
    tmpl_dir = TOOLS / "templates" / "import"
    src_dir = ROOT / f"src-{slug}"
    src_dir.mkdir(exist_ok=True)

    labels = dict(opts.rail_labels) if opts.rail_labels else {r: r for r in RAILS}
    rail_buttons = "\n".join(
        f'    <button data-rail-jump="{r}"><em>{i:02d}</em>{labels[r]}</button>'
        for i, r in enumerate(RAILS, 1))
    shell = (tmpl_dir / "shell.html").read_text(encoding="utf-8")
    for k, v in {
        "{{LANG}}": "zh-CN" if meta.get("lang") == "zh" else "en",
        "{{TITLE}}": meta["title"],
        "{{DESC}}": meta.get("subtitle") or meta["title"],
        "{{BRAND}}": meta.get("brand") or meta["title"],
        "{{BRAND_SUB}}": meta.get("brand_sub") or meta.get("date") or "",
        "{{RAIL_BUTTONS}}": rail_buttons,
        "{{COUNT}}": str(total),
        "{{OVERVIEW_FOOT}}": meta.get("overview_foot") or " · ".join(labels[r] for r in RAILS),
    }.items():
        shell = shell.replace(k, v)
    leftover = re.findall(r"\{\{[A-Z_]+\}\}", shell)
    if leftover:
        sys.exit(f"模板占位符未替换：{leftover}")
    (src_dir / "shell.html").write_text(shell, encoding="utf-8")

    accent = meta.get("accent", "#2F5D8C")
    css = (tmpl_dir / "deck.css").read_text(encoding="utf-8")
    css = (css.replace("{{ACCENT}}", accent)
              .replace("{{ACCENT_2}}", mix_hex(accent, 0.28))
              .replace("{{ACCENT_3}}", mix_hex(accent, 0.55)))
    (src_dir / "deck.css").write_text(css, encoding="utf-8")

    deck_json = {
        "slug": slug,
        "title": meta["title"],
        "subtitle": meta.get("subtitle", ""),
        "author": meta.get("author", ""),
        "date": meta.get("date", datetime.date.today().isoformat()),
        "version": meta.get("version") or meta.get("date", datetime.date.today().isoformat()).replace("-", "."),
        "tags": meta.get("tags", ["导入"]),
        "accent": accent,
        "order": meta.get("order", 90),
    }
    if opts.rail_labels:
        deck_json["rail"] = " · ".join(opts.rail_labels[r] for r in RAILS)
    (ROOT / "decks" / slug).mkdir(parents=True, exist_ok=True)
    (ROOT / "decks" / slug / "deck.json").write_text(
        json.dumps(deck_json, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


# ---------------------------------------------------------------- 参数
def parse_kv(s: str, sep=",", kv="=") -> dict:
    out = {}
    for part in filter(None, (p.strip() for p in s.split(sep))):
        k, _, v = part.partition(kv)
        if not v:
            sys.exit(f"参数格式错误（应为 key{kv}value）：{part}")
        out[k.strip()] = v.strip()
    return out


def parse_rail_map(s: str) -> dict:
    """'About:1-6,9 Programs:7-13' → {1:'About',...}"""
    out = {}
    for tok in s.split():
        name, _, ranges = tok.partition(":")
        for seg in ranges.split(","):
            m = re.fullmatch(r"(\d+)(?:-(\d+))?", seg)
            if not m:
                sys.exit(f"--rail-map 区间格式错误：{seg}")
            a, b = int(m.group(1)), int(m.group(2) or m.group(1))
            out.update({i: name for i in range(a, b + 1)})
    return out


def slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9-]+", "-", name.lower()).strip("-")
    return re.sub(r"-{2,}", "-", s) or "imported-deck"


def main():
    ensure_deps()
    ap = argparse.ArgumentParser(description="PPTX → 展示台 deck 自动导入 pipeline",
                                 formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog=__doc__.split("用法：")[1].split("行为约定：")[0])
    ap.add_argument("pptx", type=Path)
    ap.add_argument("--slug", help="deck 目录名（默认从文件名生成）")
    # 元数据
    ap.add_argument("--title", help="deck 标题（默认用文件名）")
    ap.add_argument("--subtitle", default="")
    ap.add_argument("--author", default="")
    ap.add_argument("--date", default=datetime.date.today().isoformat())
    ap.add_argument("--version", default="")
    ap.add_argument("--tags", default="导入", help="逗号分隔，如 '机构介绍,中文'")
    ap.add_argument("--order", type=int, default=90)
    ap.add_argument("--accent", default="#2F5D8C", help="主题色 #RRGGBB")
    # 外壳
    ap.add_argument("--brand", help="左上角品牌名（默认 --title）")
    ap.add_argument("--brand-sub", help="品牌副题（默认 --date）")
    ap.add_argument("--rail-labels", type=lambda s: parse_kv(s), default=None,
                    help="导轨标签 About=关于,Programs=教育项目,...")
    ap.add_argument("--rail-map", type=parse_rail_map, default=None,
                    help="显式分章 About:1-6 Programs:7-13 ...（默认按标题关键词粗分）")
    ap.add_argument("--overview-foot", default="")
    ap.add_argument("--lang", choices=["zh", "en"], default=None, help="默认自动探测")
    # 字体（默认不改字体——LibreOffice 原生回退已验证可用；仅显式指定时改写）
    ap.add_argument("--map", action="append", default=[], help="字体映射 A=B（可多次）")
    ap.add_argument("--install-font", action="append", default=[],
                    help='安装下载的字体并启用：字体名=/path/xxx.ttf（可多次）')
    ap.add_argument("--rewrite-fonts", action="store_true",
                    help="把全部字体统一改写为本机目标（拉丁→Arial Unicode MS / 中文→Hiragino Sans GB）")
    # 预修旋钮（默认 = m3 验证配方：nowrap + 全局缩字 0.95 + 表格 0.9；prefit/track/groupfit 为实验手段，显式开启）
    ap.add_argument("--table-k", type=float, default=0.90)
    ap.add_argument("--group-k", type=float, default=1.0, help="组合内短文本缩字（默认关；如 0.9 开启）")
    ap.add_argument("--track", type=int, default=0, help="收紧字距（默认关；如 -40 开启）")
    ap.add_argument("--prefit", action="store_true", help="开启实测预排（默认关）")
    ap.add_argument("--shrink", type=float, default=0.95, help="全局字号缩放（第一轮，默认 0.95）")
    ap.add_argument("--no-nowrap", action="store_true")
    # 控制
    ap.add_argument("--rounds", type=int, default=1, help="≥2 时补字过多会自动加码重渲")
    ap.add_argument("--dry-run", action="store_true", help="只做 [0] 体检")
    ap.add_argument("--force", action="store_true", help="覆盖已存在的同名 deck")
    ap.add_argument("--skip-build", action="store_true", help="跳过 node build.mjs")
    ap.add_argument("--publish", action="store_true", help="完成后重拍缩略图并刷新 library")
    opts = ap.parse_args()

    src = opts.pptx.resolve()
    if not src.exists():
        sys.exit(f"找不到文件：{src}")
    slug = opts.slug or slugify(src.stem)
    if not re.fullmatch(r"[a-z0-9-]+", slug):
        sys.exit(f"--slug 只能含小写字母/数字/连字符：{slug}")
    for probe in (ROOT / f"src-{slug}", ROOT / "decks" / slug):
        if probe.exists() and not opts.force and not opts.dry_run:
            sys.exit(f"已存在 {probe.name}/ —— 加 --force 才覆盖（防误删已调好的 deck）")

    # ---- [0/6] 体检
    t0 = datetime.datetime.now()
    inv = inventory(src)
    latin, cjk = pick_targets()
    print(f"[0/6] 体检 {src.name}")
    log("0/6", f"{inv['slides']} 页 · 画幅 {inv['ratio']} · 表格 {inv['tables']} · 组合 {inv['groups']} · 自动缩放 {inv['autofit']}")
    log("0/6", f"字体 {len(inv['fonts'])} 个：{', '.join(dict(inv['fonts']).keys())}")
    lang = opts.lang or ("zh" if inv["cjk_chars"] >= inv["latin_chars"] * 0.25 else "en")
    log("0/6", f"语言 {lang}（CJK/Latin = {inv['cjk_chars']}/{inv['latin_chars']}）· 渲染目标 拉丁={latin} / 中文={cjk}")
    if opts.dry_run:
        user_map = {}
        for s in opts.map:
            user_map.update(parse_kv(s))
        for s in opts.install_font:
            user_map.update({k: v for k, v in parse_kv(s, sep=",").items()})
        mapping = build_font_map(inv["fonts"], user_map, latin, cjk)
        for old, new in mapping.items():
            if old not in THEME_EA:
                log("dry", f"{old}  →  {new}")
        print("[dry-run] 未写任何文件。")
        return

    if not Path(SOFFICE).exists():
        sys.exit(f"未找到 LibreOffice：{SOFFICE}")
    work = ROOT / "build" / "import" / slug
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    report = {"source": str(src), "slug": slug, "inventory": {
        "slides": inv["slides"], "ratio": inv["ratio"], "tables": inv["tables"],
        "groups": inv["groups"], "autofit": inv["autofit"], "cjk_chars": inv["cjk_chars"], "latin_chars": inv["latin_chars"],
        "fonts": dict(inv["fonts"])}, "lang": lang, "targets": {"latin": latin, "cjk": cjk},
        "rounds": []}

    # ---- [1/6] 字体规整（--install-font 先装入 ~/Library/Fonts）
    print("[1/6] 字体规整")
    user_map = {}
    for s in opts.map:
        user_map.update(parse_kv(s))
    fonts_dir = Path.home() / "Library" / "Fonts"
    for s in opts.install_font:
        for fam, font_path in parse_kv(s).items():
            font_path = Path(font_path).expanduser()
            if not font_path.exists():
                sys.exit(f"--install-font 找不到文件：{font_path}")
            fonts_dir.mkdir(exist_ok=True)
            target = fonts_dir / font_path.name
            shutil.copyfile(font_path, target)
            user_map[fam] = fam
            log("1/6", f"已安装 {font_path.name} → {target}（映射 {fam} → 自身）")
            if subprocess.run(["pgrep", "-f", "soffice"], capture_output=True).returncode == 0:
                log("1/6", "⚠ LibreOffice 正在运行，新装的字体可能要等它退出后才生效")
    # 默认不改字体（m3 配方：LibreOffice 原生回退已验证可用）；仅 --rewrite-fonts / --map / --install-font 时改写
    if opts.rewrite_fonts or user_map:
        mapping = build_font_map(inv["fonts"], user_map, latin, cjk)
        normalized = work / "normalized.pptx"
        n = apply_font_map(src, normalized, mapping)
        log("1/6", f"改写 {n} 处字体引用 · {len(mapping)} 个名字")
        for old, new in mapping.items():
            if old not in THEME_EA and old != new:
                log("1/6", f"{old}  →  {new}")
        report["font_map"] = {k: v for k, v in mapping.items() if k not in THEME_EA}
        report["font_rewrites"] = n
    else:
        normalized = src
        log("1/6", "保留原字体（LibreOffice 原生回退）· 如需统一改写加 --rewrite-fonts")
        report["font_map"] = {}
        report["font_rewrites"] = 0

    # ---- [2..4] 预修 + 渲染 + 补字层（可多轮，取补字最少的一轮）
    rounds = []
    for r in range(max(1, opts.rounds)):
        shrink = opts.shrink if r == 0 else round(opts.shrink * (0.97 ** r), 3)
        print(f"[2/6] 版式预修（第 {r + 1} 轮 · 全局缩字 {shrink}）" + ("" if r == 0 else "（自动加码）"))
        opts_r = argparse.Namespace(**{**vars(opts), "shrink": shrink})
        fixed = fix_chain(normalized, work / f"round{r + 1}.pptx", opts_r)
        bad = validate_pptx(fixed)
        if bad:
            for b in bad[:5]:
                log("2/6", f"⚠ XML 损坏 {b}")
            sys.exit("修复链产生了损坏的 XML —— 中止（源文件未动）。请报告该源文件。")
        print(f"[3/6] 渲染（soffice → PDF → JPEG）")
        print(f"[4/6] 补字层")
        repairs, total = render_round(fixed, work / f"round{r + 1}" if opts.rounds > 1 else work,
                                      slug, opts.rail_map or {}, {"lang": lang})
        log("4/6", f"{total} 页 · 补字 {repairs} 处")
        rounds.append({"round": r + 1, "shrink": shrink, "repairs": repairs, "total": total})
        if r + 1 < opts.rounds and repairs <= max(6, inv["slides"] // 3):
            log("4/6", "补字已足够少，提前结束")
            break
        if r + 1 < opts.rounds and fixed != normalized:
            fixed.unlink()          # 只清轮间产物，最终轮保留供调参检查
    best = min(rounds, key=lambda x: x["repairs"])
    report["rounds"] = rounds
    report["repairs"] = best["repairs"]
    if opts.rounds > 1:
        log("4/6", f"取第 {best['round']} 轮（补字 {best['repairs']} 处）")
        winner = work / f"round{best['round']}"
    else:
        winner = work

    # ---- [5/6] 组装
    print("[5/6] 组装 deck")
    assets_dir = ROOT / "assets" / slug
    slides_dir = ROOT / f"src-{slug}" / "slides"
    if assets_dir.exists():
        shutil.rmtree(assets_dir)
    shutil.copytree(winner / "assets", assets_dir)
    total = best["total"]
    stale = [p for p in assets_dir.glob("slide*.jpg")
             if int(re.search(r"(\d+)", p.stem).group(1)) > total]
    for p in stale:
        p.unlink()
    meta = {"title": opts.title or src.stem, "subtitle": opts.subtitle,
            "author": opts.author, "tags": [t.strip() for t in opts.tags.split(",") if t.strip()],
            "order": opts.order, "version": opts.version,
            "brand": opts.brand, "brand_sub": opts.brand_sub,
            "accent": opts.accent, "overview_foot": opts.overview_foot,
            "date": opts.date, "lang": lang}
    assemble(slug, meta, total, opts)
    slides_dir.mkdir(parents=True, exist_ok=True)
    for p in slides_dir.glob("*-slide.html"):
        p.unlink()
    for p in sorted((winner / "slides").glob("*-slide.html")):
        shutil.copyfile(p, slides_dir / p.name)
    log("5/6", f"src-{slug}/（{total} 屏）+ assets/{slug}/ + decks/{slug}/deck.json")
    if not opts.skip_build:
        r = subprocess.run(["node", "build.mjs", "--src", f"src-{slug}", "--deck", slug],
                           cwd=ROOT, capture_output=True, text=True)
        print(r.stdout.strip())
        if r.returncode != 0:
            sys.exit(f"build.mjs 失败：\n{r.stderr}")

    # ---- [6/6] 报告
    report["outputs"] = {"assets": str(assets_dir), "src": str(slides_dir.parent),
                         "deck": str(ROOT / "decks" / slug / "index.html")}
    report["seconds"] = round((datetime.datetime.now() - t0).total_seconds(), 1)
    (work / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[6/6] 报告 {work / 'report.json'}")
    print(f"\n✅ 导入完成：{total} 屏 · 补字 {best['repairs']} 处 · 用时 {report['seconds']}s")
    print(f"   预览：decks/{slug}/index.html" + ("" if opts.skip_build else "（build.mjs 已生成）"))
    if opts.publish:
        r = subprocess.run([sys.executable, "tools/build_library.py", "--force"], cwd=ROOT)
        if r.returncode != 0:
            sys.exit("build_library.py 失败")
    else:
        print(f"   入库：确认效果后运行 python3 tools/build_library.py --force 刷新展示台与缩略图")


if __name__ == "__main__":
    main()
