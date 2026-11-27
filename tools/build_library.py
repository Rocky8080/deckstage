#!/usr/bin/env python3
"""
build_library.py — 扫描 decks/ 里每一套 PPT，生成缩略图、decks.json 与 library.html

用法：
    python3 tools/build_library.py              # 缺缩略图才生成
    python3 tools/build_library.py --force      # 全部重拍缩略图

约定（一套 PPT 一个目录）：
    decks/<slug>/
        index.html   ← 幻灯片本体（build.mjs --deck <slug> 生成）
        deck.json    ← 元数据：title / subtitle / author / date / tags / order
        thumb.jpg    ← 首页缩略图（本脚本自动生成，800×450）
"""
from __future__ import annotations

import _platform  # noqa: F401  — Windows GBK 管道下的 stdout UTF-8 兜底（见 _platform.py）
import argparse
import html
import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import admin_core  # noqa: E402  展示台首页手工排序（data/library.json）

ROOT = Path(__file__).resolve().parent.parent
DECKS = ROOT / "decks"
THUMB_W, THUMB_H = 800, 450


def load_meta(folder: Path) -> dict | None:
    index = folder / "index.html"
    if not index.is_file():
        return None
    meta = {}
    cfg = folder / "deck.json"
    if cfg.is_file():
        try:
            meta = json.loads(cfg.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            print(f"  ⚠ {folder.name}/deck.json 解析失败：{exc}", file=sys.stderr)
    text = index.read_text(encoding="utf-8", errors="ignore")
    slides = len(re.findall(r'<section[^>]*class="slide', text)) or len(re.findall(r"data-title=", text))
    first = re.search(r'<section class="slide"[^>]*data-title="([^"]*)"', text)
    meta.setdefault("slug", folder.name)
    meta.setdefault("title", first.group(1) if first else folder.name)
    meta.setdefault("subtitle", "")
    meta.setdefault("author", "")
    meta.setdefault("tags", [])
    meta.setdefault("order", 99)
    meta["slides"] = slides
    if not meta.get("date"):
        meta["date"] = datetime.fromtimestamp(index.stat().st_mtime).strftime("%Y-%m-%d")
    return meta


def ensure_thumb(folder: Path, force: bool) -> Path:
    thumb = folder / "thumb.jpg"
    index = folder / "index.html"
    if thumb.is_file() and not force and thumb.stat().st_mtime >= index.stat().st_mtime:
        return thumb
    from playwright.sync_api import sync_playwright

    # 优先走本地服务（共享运行时 /_shared/ 是站点绝对路径，file:// 下会 404）
    slug = folder.name
    http_url = f"http://127.0.0.1:8899/decks/{slug}/?export=1"
    file_url = index.resolve().as_uri() + "?export=1"
    url = http_url
    with sync_playwright() as p:
        browser = _platform.launch_chromium(p, headless=True)
        page = browser.new_context(viewport={"width": 1600, "height": 900},
                                   device_scale_factor=1).new_page()
        try:
            page.goto(url, wait_until="load", timeout=20000)
        except Exception:                                   # 服务没起来就退回 file://
            page.goto(file_url, wait_until="load", timeout=30000)
        page.wait_for_timeout(1600)          # 让入场动画落定
        page.evaluate("""() => {
            document.querySelectorAll('.slide').forEach((s, i) => {
                s.style.opacity = i === 0 ? 1 : 0;
                s.style.visibility = i === 0 ? 'visible' : 'hidden';
                s.style.transform = 'none';
                s.style.animation = 'none';
            });
            document.querySelectorAll('.reveal, .stagger > *, .draw, [style*="--d"]').forEach(el => {
                el.style.opacity = 1;
                el.style.transform = 'none';
                el.style.animation = 'none';
                el.style.strokeDashoffset = 0;
            });
            document.querySelectorAll('.chrome, .overview, .notebar, .stage__bar').forEach(el => {
                el.style.display = 'none';
            });
        }""")
        page.wait_for_timeout(400)
        page.screenshot(path=str(thumb), clip={"x": 0, "y": 0, "width": 1600, "height": 900},
                        type="jpeg", quality=86)
        browser.close()
    print(f"  ✓ 缩略图 {folder.name}/thumb.jpg")
    return thumb


PAGE = """<!doctype html>
<html lang="zh-CN" data-cols="2">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>PPT 展示台</title>
<script>
  // 先套用本机记住的列数，避免刷新时从 2 列闪一下再变
  (function () {{
    var n = 2;
    try {{
      var saved = parseInt(localStorage.getItem('deck_library_cols'), 10);
      if (saved === 3 || saved === 4) n = saved;
    }} catch (e) {{}}
    document.documentElement.setAttribute('data-cols', String(n));
  }})();
</script>
<style>
  :root {{
    --paper: #F7F3EA; --paper-2: #FCFAF4; --ink: #14201B; --ink-2: #33453D;
    --ink-3: #5F6E66; --ink-4: #8A968F; --green: #1E5B47; --green-2: #2E7D62;
    --line: rgba(20,32,27,.12); --line-soft: rgba(20,32,27,.07);
    --serif: "Songti SC", "Source Han Serif SC", "Noto Serif SC", serif;
    --sans: "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", system-ui, sans-serif;
    --mono: ui-monospace, "SF Mono", Menlo, monospace;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; min-height: 100vh; background: var(--paper); color: var(--ink);
    font-family: var(--sans); -webkit-font-smoothing: antialiased;
  }}
  .wrap {{ max-width: 1280px; margin: 0 auto; padding: 56px 40px 72px; }}
  header.top {{ display: flex; align-items: flex-end; justify-content: space-between; gap: 32px; flex-wrap: wrap; }}
  .brand {{ font-family: var(--mono); font-size: 11px; letter-spacing: .22em; color: var(--green); margin: 0 0 14px; }}
  h1 {{ font-family: var(--serif); font-size: 48px; line-height: 1.1; letter-spacing: .02em; margin: 0 0 12px; font-weight: 600; }}
  .lede {{ margin: 0; color: var(--ink-3); font-size: 16px; line-height: 1.7; max-width: 56ch; }}
  .topRight {{ display: flex; flex-direction: column; align-items: flex-end; gap: 14px; }}
  .stats {{ display: flex; gap: 28px; }}
  .colbar {{ display: flex; align-items: center; gap: 10px; }}
  .colbar__label {{ font-family: var(--mono); font-size: 10.5px; letter-spacing: .14em; color: var(--ink-4); }}
  .cols {{ display: inline-flex; padding: 3px; border: 1px solid var(--line); border-radius: 999px; background: var(--paper-2); }}
  .cols button {{ border: 0; background: transparent; color: var(--ink-3); font: 500 12px/1 var(--sans);
    padding: 7px 13px; border-radius: 999px; cursor: pointer; letter-spacing: .04em;
    transition: background .15s, color .15s; }}
  .cols button:hover {{ color: var(--green); }}
  .cols button:focus-visible {{ outline: 2px solid var(--green-2); outline-offset: 2px; }}
  .cols button[aria-pressed="true"] {{ background: var(--green); color: var(--paper); }}
  .stat b {{ display: block; font-family: var(--mono); font-size: 30px; font-weight: 600; letter-spacing: -.02em; color: var(--ink); }}
  .stat span {{ font-size: 11px; letter-spacing: .1em; color: var(--ink-4); }}
  .rule {{ height: 1px; background: var(--line); margin: 40px 0 30px; }}

  .grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 520px)); justify-content: start; gap: 28px; }}
  html[data-cols="3"] .grid {{ grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 24px; }}
  html[data-cols="4"] .grid {{ grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 20px; }}
  .card {{
    display: block; background: var(--paper-2); border: 1px solid var(--line);
    border-radius: 14px; overflow: hidden; text-decoration: none; color: inherit;
    transition: transform .22s cubic-bezier(.2,.7,.3,1), box-shadow .22s, border-color .22s;
  }}
  .card:hover, .card:focus-visible {{
    transform: translateY(-4px); box-shadow: 0 16px 40px rgba(20,32,27,.12);
    border-color: rgba(30,91,71,.35); outline: none;
  }}
  .card__thumb {{ position: relative; aspect-ratio: 16/9; background: #E8E2D4; overflow: hidden; }}
  .card__thumb img {{ width: 100%; height: 100%; object-fit: cover; display: block; transition: transform .5s cubic-bezier(.2,.7,.3,1); }}
  .card:hover .card__thumb img {{ transform: scale(1.02); }}
  .card__open {{
    position: absolute; right: 14px; bottom: 14px; padding: 7px 14px; border-radius: 999px;
    background: rgba(20,32,27,.82); color: #F7F3EA; font-size: 12px; letter-spacing: .06em;
    opacity: 0; transform: translateY(6px); transition: opacity .2s, transform .2s;
  }}
  .card:hover .card__open {{ opacity: 1; transform: none; }}
  .card__body {{ padding: 18px 20px 20px; }}
  .card__title {{ font-family: var(--serif); font-size: 22px; letter-spacing: .02em; margin: 0 0 6px; font-weight: 600; }}
  .card__sub {{ margin: 0; font-size: 13px; color: var(--ink-3); line-height: 1.6; }}
  .card__meta {{ display: flex; align-items: center; gap: 9px; margin-top: 14px; font-family: var(--mono); font-size: 10.5px; letter-spacing: .06em; color: var(--ink-4); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
  .dot {{ width: 3px; height: 3px; border-radius: 50%; background: var(--ink-4); }}
  .tags {{ display: flex; gap: 6px; margin-top: 12px; flex-wrap: wrap; }}
  .tag {{ padding: 3px 8px; border-radius: 4px; background: rgba(30,91,71,.08); color: var(--green); font-size: 10px; letter-spacing: .04em; }}
  .empty {{ padding: 60px 0; color: var(--ink-3); font-size: 15px; }}

  /* 4 列时卡片更窄，标题与内边距同步收紧 */
  @media (min-width: 901px) {{
    html[data-cols="4"] .card__body {{ padding: 15px 16px 16px; }}
    html[data-cols="4"] .card__title {{ font-size: 19px; }}
    html[data-cols="4"] .card__sub {{ font-size: 12.5px; }}
    html[data-cols="4"] .card__meta {{ margin-top: 12px; }}
  }}

  footer.bot {{ margin-top: 56px; padding-top: 22px; border-top: 1px solid var(--line); display: flex; flex-wrap: wrap; gap: 8px 26px; font-family: var(--mono); font-size: 11px; letter-spacing: .08em; color: var(--ink-4); }}
  .import-btn {{ display: inline-flex; align-items: center; gap: 8px; padding: 10px 20px; border-radius: 999px;
    background: var(--green); color: var(--paper); font: 600 13px/1 var(--sans); letter-spacing: .04em;
    text-decoration: none; transition: transform .15s, box-shadow .15s; }}
  .import-btn:hover {{ transform: translateY(-1px); box-shadow: 0 8px 20px rgba(30,91,71,.28); }}
  footer.bot b {{ color: var(--ink-3); font-weight: 500; }}
  @media (max-width: 1080px) {{
    html[data-cols="4"] .grid {{ grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 24px; }}
  }}
  @media (max-width: 900px) {{
    html[data-cols="3"] .grid,
    html[data-cols="4"] .grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 24px; }}
  }}
  @media (max-width: 720px) {{
    .wrap {{ padding: 36px 20px 56px; }}
    h1 {{ font-size: 32px; }}
    .topRight {{ align-items: flex-start; }}
    .stats {{ gap: 20px; }}
    .colbar {{ display: none; }}
    .grid,
    html[data-cols="3"] .grid,
    html[data-cols="4"] .grid {{ grid-template-columns: 1fr; gap: 20px; }}
  }}
</style>
</head>
<body>
<div class="wrap">
  <header class="top">
    <div>
      <p class="brand">PRESENTATION LIBRARY · {year}</p>
      <h1>PPT 展示台</h1>
      <p class="lede">每一套都是可以直接放映的 HTML 幻灯片：方向键/空格翻页，两侧边缘点击翻页，G 总览，N 备注，F 全屏放映。</p>
    </div>
    <div class="topRight">
      <div class="colbar">
        <span class="colbar__label">每行列数</span>
        <div class="cols" role="group" aria-label="首页每行显示列数">
          <button type="button" data-cols="2" aria-pressed="true">2 列</button>
          <button type="button" data-cols="3" aria-pressed="false">3 列</button>
          <button type="button" data-cols="4" aria-pressed="false">4 列</button>
        </div>
      </div>
      <div class="stats">
        <a class="import-btn" href="/import.html" id="importBtn">＋ 导入 PPTX</a>
        <div class="stat"><b>{n}</b><span>套</span></div>
        <div class="stat"><b>{total}</b><span>屏</span></div>
      </div>
    </div>
  </header>

  <div class="rule"></div>

  <main class="grid">
{cards}
  </main>

  <footer class="bot">
    <span><b>← →</b> 翻页</span><span><b>空格</b> 逐步展开</span><span><b>G</b> 总览</span>
    <span><b>N</b> 演讲备注</span><span><b>F</b> 全屏放映</span><span><b>Esc</b> 退出</span>
  </footer>
</div>
<script>
  // 兼容旧链接：/#s12 → 直接进那套 deck 的第 12 屏
  (function () {{
    var m = location.hash.match(/^#s(\d+)$/);
    if (!m) return;
    var first = document.querySelector('.card');
    if (!first) return;
    location.replace(first.getAttribute('href') + '#s' + m[1]);
  }})();
  // 导入按钮：只在本地伴生服务（serve_deck.py）下可用，公网/file:// 给出提示
  (function () {{
    var btn = document.getElementById('importBtn');
    if (!btn) return;
    btn.addEventListener('click', function (e) {{
      e.preventDefault();
      fetch('/api/ping', {{ cache: 'no-store' }}).then(function (r) {{
        if (!r.ok) throw 0;
        location.href = '/import.html';
      }}).catch(function () {{
        alert('导入功能只在本地可用：在项目目录运行 python3 tools/serve_deck.py，然后打开 http://127.0.0.1:8899/import.html');
      }});
    }});
  }})();
  // 首页列数：2 / 3 / 4 列，选择记在本机浏览器
  (function () {{
    var root = document.documentElement;
    var buttons = Array.prototype.slice.call(document.querySelectorAll('.cols button'));
    if (!buttons.length) return;
    function apply(n, persist) {{
      root.setAttribute('data-cols', String(n));
      buttons.forEach(function (btn) {{
        btn.setAttribute('aria-pressed', String(Number(btn.getAttribute('data-cols')) === n));
      }});
      if (persist) {{
        try {{ localStorage.setItem('deck_library_cols', String(n)); }} catch (e) {{}}
      }}
    }}
    buttons.forEach(function (btn) {{
      btn.addEventListener('click', function () {{
        apply(Number(btn.getAttribute('data-cols')), true);
      }});
    }});
    var current = Number(root.getAttribute('data-cols'));
    apply(current === 3 || current === 4 ? current : 2, false);
  }})();
</script>
</body>
</html>
"""

CARD = """    <a class="card" href="/{href}/" aria-label="打开 {title}">
      <div class="card__thumb">
        <img src="/{href}/thumb.jpg?v={thumb_version}" alt="{title} 首页缩略图" loading="lazy">
        <span class="card__open">打开 →</span>
      </div>
      <div class="card__body">
        <h2 class="card__title">{title}</h2>
        <p class="card__sub">{subtitle}</p>
        <div class="card__meta"><span>{slides} 屏</span><i class="dot"></i><span>{date}</span>{author}</div>
        {tags}
      </div>
    </a>"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="全部重拍缩略图")
    ap.add_argument("--deck", help="只强制重拍这一套 deck 的缩略图，然后重建展示台")
    args = ap.parse_args()

    if not DECKS.is_dir():
        print("没有 decks/ 目录", file=sys.stderr)
        return 1

    decks = []
    for folder in sorted(DECKS.iterdir()):
        if not folder.is_dir():
            continue
        meta = load_meta(folder)
        if not meta:
            continue
        thumbs = (folder / "thumb.jpg").is_file()
        target = bool(args.deck) and folder.name == args.deck
        if args.force or target or not thumbs:
            try:
                ensure_thumb(folder, args.force or target)
            except Exception as exc:                      # noqa: BLE001
                print(f"  ⚠ {folder.name} 缩略图失败：{type(exc).__name__} {exc}", file=sys.stderr)
        meta["href"] = f"decks/{folder.name}"
        thumb_path = folder / "thumb.jpg"
        meta["thumb_version"] = str(int(thumb_path.stat().st_mtime_ns)) if thumb_path.is_file() else "0"
        decks.append(meta)

    manual = admin_core.read_library_order(str(ROOT))
    decks = admin_core.sort_library_decks(decks, manual)

    cards = []
    for d in decks:
        tags = "".join(f'<span class="tag">{html.escape(t)}</span>' for t in d.get("tags", [])[:3])
        cards.append(CARD.format(
            href=d["href"],
            title=html.escape(d.get("title", "")),
            subtitle=html.escape(d.get("subtitle", "")),
            slides=d.get("slides", 0),
            date=html.escape(("v" + d["version"]) if d.get("version") else d.get("date", "")),
            author=(f'<i class="dot"></i><span>{html.escape(d["author"])}</span>' if d.get("author") else ""),
            tags=(f'<div class="tags">{tags}</div>' if tags else ""),
            thumb_version=d.get("thumb_version", "0"),
        ))

    page = PAGE.format(
        year=datetime.now().year,
        n=len(decks),
        total=sum(d.get("slides", 0) for d in decks),
        cards="\n".join(cards) if cards else '<p class="empty">decks/ 里还没有幻灯片。</p>',
    )
    (ROOT / "library.html").write_text(page, encoding="utf-8")
    (ROOT / "decks.json").write_text(
        json.dumps({"generated": datetime.now().isoformat(timespec="seconds"), "decks": decks},
                   ensure_ascii=False, indent=2),
        encoding="utf-8")
    print(f"[library] library.html · {len(decks)} 套 · "
          f"{sum(d.get('slides', 0) for d in decks)} 屏 · "
          f"{'自定义顺序' if manual else '默认顺序'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
