#!/usr/bin/env python3
"""layout_audit.py — 版式骨架覆盖与重复检查（建议级设计质量门禁）

同一套 deck 如果每屏都是「标题 + 三张卡 + 一句结论」，讲得再对也会让人走神。
本工具给每一屏打一个「页面骨架签名」，统计这套 deck 用了多少种骨架、有没有
相邻两屏撞结构、某一种骨架是不是被反复复用，最后给出可执行的改版建议。

用法：
  python3 tools/layout_audit.py --src src-sample/slides
  python3 tools/layout_audit.py --index decks/sample-deck/index.html
  python3 tools/layout_audit.py --index decks/sample-deck/index.html --json
  python3 tools/layout_audit.py --self-test

输入（二选一）：
  --src <目录>   源码形态：目录下每个 .html 是一屏（一屏一个 <section class="slide">）
  --index <文件> 构建后的单文件 deck：按标签深度切出每个 <section class="slide">，
                 所以屏内嵌套的 <section>、<script> 里的假标签都不会把切屏截断

签名规则：
  1. <section> 上有 data-arch="cover|toc|point|..." 时，直接用该值当骨架名，
     但仍然计算结构特征（--json 的 features 字段会保留）。
  2. 否则先剥掉 <style>、<script>、<aside class="notes"> 和 HTML 注释，再推断特征：
       table  <table>                     svg    <svg>
       image  <img> 或 .shot              flow   class 含 chain/flow/pipe/step，
                                                 或正文里有 ≥2 个 → / ↓ 箭头
       steps  class 含 step/ladder/timeline/toc
       gridN  .g2/.g3/.g4，或行内 grid-template-columns 为 2/3/4 栏
              （文档顺序里第一个可识别的 2–4 栏栅格；5 栏以上不归类）
       split  两栏结构：gridN=2、class 含 split、.row 或 .g-1-2 等
       list   <ul>/<ol> 或 .list         stat   .stat/.metrics/.ax-board/.ax-trio
       card   .card                       insight .insight/.takeaway
  3. 骨架名 = data-arch；否则把特征按固定顺序用「+」拼起来，如
     "grid3+card+insight"；一个特征都没有时是 "plain"。

统计与判定（默认建议级，不阻断构建）：
  总屏数、骨架种数、每种骨架出现次数与屏号
  · 相邻两屏同骨架       → 相邻重复（--no-adjacent 关闭）
  · 单骨架出现 > --max-repeat 次（默认 3）→ 报警
  · 骨架种数 < --min 种（默认 6）→ 报警
  · 全 deck 只有 1 种骨架 → 单独强提示
  覆盖 = 骨架种数 ÷ 屏数，只表示「每屏平均能摊到多少种结构」，不是验收分数。

输出：
  先一张「屏 / 标题 / 骨架」表，再一行摘要，最后列出 violations（每条带屏号和
  改法）。--json 输出机器可读结果（source/mode/total/kinds/coverage/distribution/
  slides/violations 等）。

退出码：
  0 = 输入正常（默认建议级；有 violation 也返回 0）
  1 = --strict 且存在 violation
  2 = 输入错误（缺 --src/--index、路径不存在、切不出任何一屏）

--self-test 会在 /tmp 下生成两套临时 deck（一套 8 屏 6 骨架、一套 6 屏全同骨架），
断言骨架种数、单调重复、坑位检测正确，跑完自动清理，不碰仓库里的文件。

限制：本工具只读 HTML，不解析外部 CSS（<style> 会被剥掉），所以自定义版式请
用 data-arch 或约定的类名（.grid/.g3/.card/.list/.stat/.insight 等）表达结构；
presenter notes 请使用 <aside class="notes">，否则备注里的箭头会被当成正文。
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import tempfile
import unicodedata
from functools import lru_cache
from html import unescape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 特征拼接顺序：先大结构（表格 / 图 / 流程 / 栅格），后组件（列表 / 数字 / 卡片 / 结论）
FEATURE_ORDER = (
    "table", "svg", "image", "flow", "steps",
    "grid4", "grid3", "grid2", "split",
    "list", "stat", "card", "insight",
)

TITLE_MAX = 42          # 表格里标题最多占多少显示宽度
SIGNATURE_MAX = 56      # 表格里骨架名最多占多少显示宽度

COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
STYLE_RE = re.compile(r"<style\b[^>]*>.*?</style\s*>", re.S | re.I)
SCRIPT_RE = re.compile(r"<script\b[^>]*>.*?</script\s*>", re.S | re.I)
BLOCK_TAG_RE = re.compile(r"<(aside|div)\b(?:[^>\"']|\"[^\"]*\"|'[^']*')*>", re.I)
CLASS_ATTR_RE = re.compile(r"\bclass\s*=\s*(?:\"([^\"]*)\"|'([^']*)')", re.I)
SECTION_TAG_RE = re.compile(r"<section\b(?:[^>\"']|\"[^\"]*\"|'[^']*')*>|</section\s*>", re.I)
HEADING_RE = re.compile(r"<(h1|h2|h3)\b[^>]*>(.*?)</\1\s*>", re.S | re.I)
TAG_RE = re.compile(r"<[^>]+>", re.S)

# 一次扫描里同时拿到 class 属性和行内 grid-template-columns，保持文档顺序
GRID_DECL_RE = re.compile(
    r"\bclass\s*=\s*(?:\"([^\"]*)\"|'([^']*)')"
    r"|grid-template-columns\s*:\s*([^;\"'}]+)",
    re.I,
)

FLOW_WORDS = ("chain", "flow", "pipe", "step")
STEP_WORDS = ("step", "ladder", "timeline", "toc")
STAT_CLASSES = {"stat", "metrics", "ax-board", "ax-trio"}
INSIGHT_CLASSES = {"insight", "takeaway"}
ROW_CLASSES = {"row", "g-1-2", "g-2-1", "g-5-7", "g-7-5"}


class AuditInputError(Exception):
    """输入有问题（路径不存在 / 不是 deck / 切不出屏），对应退出码 2。"""


# ------------------------------------------------------------------ 属性 / 清洗
@lru_cache(maxsize=None)
def _attr_re(name):
    return re.compile(
        r"\b" + re.escape(name) + r"\s*=\s*(?:\"([^\"]*)\"|'([^']*)'|([^\s>]+))",
        re.I,
    )


def get_attr(tag, name):
    """从一个开始标签里读属性值；没有或为空返回空字符串。"""
    m = _attr_re(name).search(tag or "")
    if not m:
        return ""
    raw = m.group(1) or m.group(2) or m.group(3) or ""
    return re.sub(r"\s+", " ", unescape(raw)).strip()


def class_tokens(html):
    """返回 HTML 里出现过的所有 class 小写词（用于判断 .card/.grid 等）。"""
    tokens = set()
    for m in CLASS_ATTR_RE.finditer(html or ""):
        raw = m.group(1) if m.group(1) is not None else m.group(2)
        tokens.update(t.lower() for t in raw.split())
    return tokens


def _strip_notes(html):
    """剥掉 presenter notes：<aside class="notes">（也兼容 <div class="notes">）。"""
    if "notes" not in html:
        return html
    pieces = []
    pos = 0
    for m in BLOCK_TAG_RE.finditer(html):
        if m.start() < pos:
            continue
        tag = m.group(1).lower()
        if "notes" not in class_tokens(m.group(0)):
            continue
        # 按同名标签深度找配对的闭合标签，避免 div 里嵌套 div 时提前截断
        close_re = re.compile(
            r"<" + tag + r"\b(?:[^>\"']|\"[^\"]*\"|'[^']*')*>|</" + tag + r"\s*>",
            re.I,
        )
        depth = 1
        end = len(html)
        for t in close_re.finditer(html, m.end()):
            if t.group(0).lower().startswith("</"):
                depth -= 1
                if depth == 0:
                    end = t.end()
                    break
            else:
                depth += 1
        pieces.append(html[pos:m.start()])
        pos = end
    pieces.append(html[pos:])
    return "".join(pieces)


def clean_html(raw):
    """剥掉不参与结构判断的内容：注释、<style>、<script>、presenter notes。"""
    html = COMMENT_RE.sub(" ", raw or "")
    html = STYLE_RE.sub(" ", html)
    html = SCRIPT_RE.sub(" ", html)
    html = _strip_notes(html)
    return html


def plain_text(html):
    """去标签、解实体、压空白，只留可见文字。"""
    return re.sub(r"\s+", " ", unescape(TAG_RE.sub(" ", html or ""))).strip()


# ------------------------------------------------------------------ 切屏
def extract_sections(html):
    """按标签深度切出顶层 <section class="slide">（或带 data-arch 的 section）。

    屏内嵌套的 <section> 会增加深度，只有回到 0 才结束当前屏，所以不会在第一个
    </section> 处截断。
    """
    spans = []
    start = -1
    depth = 0
    for m in SECTION_TAG_RE.finditer(html):
        tag = m.group(0)
        if tag.lower().startswith("</"):
            if start >= 0:
                depth -= 1
                if depth == 0:
                    spans.append(html[start:m.end()])
                    start = -1
            continue
        self_closing = tag.rstrip().endswith("/>")
        if start >= 0:
            if not self_closing:
                depth += 1
            continue
        if "slide" in class_tokens(tag) or get_attr(tag, "data-arch"):
            if self_closing:
                spans.append(html[m.start():m.end()])
            else:
                start, depth = m.start(), 1
    if start >= 0:  # 没闭合的最后一屏，尽量截到文末
        spans.append(html[start:])
    return spans


def _opening_tag(section):
    m = SECTION_TAG_RE.search(section)
    return m.group(0) if m else ""


def _heading_title(section):
    for m in HEADING_RE.finditer(section):
        text = plain_text(m.group(2))
        if text:
            return text
    return ""


# ------------------------------------------------------------------ 特征推断
def _count_columns(value):
    """数 grid-template-columns 的顶层栏数；数不出来返回 0。"""
    v = (value or "").strip().lower()
    if not v or "var(" in v or "auto-fit" in v or "auto-fill" in v:
        return 0
    m = re.match(r"repeat\(\s*(\d+)\s*,", v)
    if m:
        return int(m.group(1))
    parts = []
    depth = 0
    cur = ""
    for ch in v:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        if ch.isspace() and depth == 0:
            if cur:
                parts.append(cur)
                cur = ""
        else:
            cur += ch
    if cur:
        parts.append(cur)
    return len(parts)


def _first_grid_columns(html):
    """找文档顺序里第一个可归类的 2–4 栏栅格；.g2/.g3/.g4 也认。"""
    for m in GRID_DECL_RE.finditer(html):
        cls = m.group(1) if m.group(1) is not None else m.group(2)
        if cls is not None:
            for tok in cls.split():
                tok = tok.lower()
                if tok in ("g2", "g3", "g4"):
                    return int(tok[1])
            continue
        n = _count_columns(m.group(3) or "")
        if 2 <= n <= 4:
            return n
    return 0


def infer_features(html):
    """从已清洗的 HTML 里推断结构特征，按 FEATURE_ORDER 返回列表。"""
    toks = class_tokens(html)
    text = plain_text(html)
    feats = set()

    if re.search(r"<table\b", html, re.I):
        feats.add("table")
    if re.search(r"<svg\b", html, re.I):
        feats.add("svg")
    if re.search(r"<img\b", html, re.I) or any(
        t == "shot" or t.startswith("shot__") or t.startswith("shot--") for t in toks
    ):
        feats.add("image")
    if any(any(w in t for w in FLOW_WORDS) for t in toks) or (
        text.count("→") + text.count("↓") >= 2
    ):
        feats.add("flow")
    if any(any(w in t for w in STEP_WORDS) for t in toks):
        feats.add("steps")

    cols = _first_grid_columns(html)
    if cols:
        feats.add("grid%d" % cols)
    if (
        cols == 2
        or any("split" in t for t in toks)
        or any(t in ROW_CLASSES or t.startswith("row--") for t in toks)
    ):
        feats.add("split")

    if re.search(r"<(ul|ol)\b", html, re.I) or "list" in toks:
        feats.add("list")
    if toks & STAT_CLASSES:
        feats.add("stat")
    if "card" in toks:
        feats.add("card")
    if toks & INSIGHT_CLASSES:
        feats.add("insight")

    return [f for f in FEATURE_ORDER if f in feats]


def make_slide(section, file_label, fallback_title):
    """把一屏 HTML 变成一条待统计的记录（含 data-arch / 特征 / 骨架签名）。"""
    opening = _opening_tag(section)
    arch = get_attr(opening, "data-arch").lower()
    title = get_attr(opening, "data-title") or _heading_title(section) or fallback_title
    features = infer_features(section)
    signature = arch if arch else ("+".join(features) if features else "plain")
    return {
        "file": file_label,
        "title": title or "—",
        "arch": arch,
        "features": features,
        "signature": signature,
    }


# ------------------------------------------------------------------ 采集
def _read(path):
    return path.read_text(encoding="utf-8", errors="ignore")


def _natural_key(name):
    """让 2 排在 10 前面。"""
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", name)]


def _html_files(path):
    if path.is_file():
        if path.suffix.lower() not in (".html", ".htm"):
            raise AuditInputError("不是 .html 文件：%s" % path)
        return [path]
    files = [p for p in path.iterdir() if p.is_file() and p.suffix.lower() in (".html", ".htm")]
    return sorted(files, key=lambda p: _natural_key(p.name))


def collect_src(path):
    """源码形态：目录下每个 .html 一屏；文件里没有 <section> 时整个文件当一屏。"""
    if not path.exists():
        raise AuditInputError("路径不存在：%s" % path)
    files = _html_files(path)
    if not files:
        raise AuditInputError("目录下没有 .html 文件：%s" % path)

    slides = []
    for f in files:
        cleaned = clean_html(_read(f))
        sections = extract_sections(cleaned)
        if not sections:
            sections = [cleaned]
        for section in sections:
            slides.append(make_slide(section, f.name, f.stem))
    if not slides:
        raise AuditInputError("没有可分析的屏：%s" % path)
    return slides


def collect_index(path):
    """构建后的单文件：只认带 class="slide"（或 data-arch）的顶层 section。"""
    if not path.exists():
        raise AuditInputError("路径不存在：%s" % path)
    if path.is_dir():
        raise AuditInputError("--index 需要构建后的单文件，不是目录：%s" % path)
    cleaned = clean_html(_read(path))
    sections = extract_sections(cleaned)
    if not sections:
        raise AuditInputError(
            "没切出 <section class=\"slide\">：确认这是构建后的 deck 单文件（或先 node build.mjs）"
        )
    return [make_slide(section, path.name, "未命名") for section in sections]


# ------------------------------------------------------------------ 统计 / 判定
def _adjacent_runs(signatures):
    runs = []
    start = 0
    for i in range(1, len(signatures) + 1):
        if i == len(signatures) or signatures[i] != signatures[start]:
            if i - start > 1:
                runs.append((start, i - 1))
            start = i
    return runs


def _numbers_text(nums, limit=8):
    if not nums:
        return "—"
    shown = "、".join(str(n) for n in nums[:limit])
    text = "第 %s 屏" % shown
    if len(nums) > limit:
        text += "…（共 %d 屏）" % len(nums)
    return text


def build_report(slides, min_kinds=6, max_repeat=3, check_adjacent=True):
    """核心统计：不打印、不读文件，方便 --self-test 与外部复用。"""
    if not slides:
        raise AuditInputError("没有可分析的屏")
    slides = [dict(s, no=i) for i, s in enumerate(slides, 1)]
    total = len(slides)

    counts = {}
    first_seen = {}
    for s in slides:
        sig = s["signature"]
        counts[sig] = counts.get(sig, 0) + 1
        first_seen.setdefault(sig, s["no"])
    kinds = len(counts)
    order = sorted(counts, key=lambda sig: (-counts[sig], first_seen[sig]))
    distribution = [
        {
            "signature": sig,
            "count": counts[sig],
            "slides": [s["no"] for s in slides if s["signature"] == sig],
        }
        for sig in order
    ]
    max_signature = order[0]
    max_count = counts[max_signature]
    max_slides = [s["no"] for s in slides if s["signature"] == max_signature]
    coverage = round(kinds / total * 100, 1)

    signatures = [s["signature"] for s in slides]
    runs = _adjacent_runs(signatures) if check_adjacent else []
    adjacent_pairs = sum(end - begin for begin, end in runs)

    arch_tagged = sum(1 for s in slides if s["arch"])
    violations = []

    if kinds == 1:
        violations.append({
            "rule": "single_skeleton",
            "level": "强提示",
            "title": "单一骨架",
            "slides": list(range(1, total + 1)),
            "detail": "全 deck %d 屏只用了一种骨架 `%s`，没有结构变化" % (total, max_signature),
            "suggestion": "先定 4–6 种骨架轮换：封面 / 目录 / 单观点 / 三并列 / 流程 / 收尾，每屏只留一个焦点",
        })
    if min_kinds and kinds < min_kinds:
        violations.append({
            "rule": "few_kinds",
            "level": "建议",
            "title": "骨架种数不足",
            "slides": list(range(1, total + 1)),
            "detail": "骨架只有 %d 种，低于门限 %d 种（覆盖率 %s%%）" % (
                kinds, min_kinds, ("%.1f" % coverage).rstrip("0").rstrip(".")),
            "suggestion": "再补 %d 种结构差异明显的版式：表格页 / 流程页 / 两栏对照页 / 数据看板" % (
                max(1, min_kinds - kinds)),
        })
    if max_count > max_repeat:
        violations.append({
            "rule": "max_repeat",
            "level": "建议",
            "title": "单骨架重复过多",
            "slides": max_slides,
            "detail": "骨架 `%s` 出现 %d 次，%s，超过上限 %d 次" % (
                max_signature, max_count, _numbers_text(max_slides), max_repeat),
            "suggestion": "把其中 1–2 屏换成表格、流程或两栏对照，别让同一结构反复出现",
        })
    for begin, end in runs:
        sig = signatures[begin]
        count = end - begin + 1
        if count == 2:
            where = "第 %d、%d 屏" % (begin + 1, end + 1)
        else:
            where = "第 %d–%d 屏" % (begin + 1, end + 1)
        violations.append({
            "rule": "adjacent",
            "level": "建议",
            "title": "相邻重复",
            "slides": list(range(begin + 1, end + 2)),
            "detail": "%s连续 %d 屏同为 `%s`，相邻两屏没有换结构" % (where, count, sig),
            "suggestion": "把其中一屏换骨架，或在这两屏之间插一屏过渡 / 对照页",
        })

    return {
        "total": total,
        "kinds": kinds,
        "coverage": coverage,
        "distribution": distribution,
        "slides": slides,
        "adjacent_checked": check_adjacent,
        "adjacent_repeat": adjacent_pairs,
        "adjacent_runs": [
            {
                "signature": signatures[begin],
                "from": begin + 1,
                "to": end + 1,
                "slides": list(range(begin + 1, end + 2)),
            }
            for begin, end in runs
        ],
        "max_repeat": max_count,
        "max_repeat_signature": max_signature,
        "min_kinds": min_kinds,
        "max_repeat_allowed": max_repeat,
        "arch_tagged": arch_tagged,
        "inferred": total - arch_tagged,
        "violations": violations,
        "ok": not violations,
    }


def decide_exit(report, strict):
    """默认建议级退出 0；--strict 且有 violation 才退 1。"""
    return 1 if (strict and report["violations"]) else 0


# ------------------------------------------------------------------ 文本输出
def _display_width(text):
    return sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in text)


def _pad(text, width, align="left"):
    pad = max(0, width - _display_width(text))
    if align == "right":
        return " " * pad + text
    return text + " " * pad


def _clip(text, width):
    """按显示宽度截断，加省略号，避免中文表格错位。"""
    if _display_width(text) <= width:
        return text
    out = ""
    used = 0
    for ch in text:
        w = 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
        if used + w > width - 1:
            break
        out += ch
        used += w
    return out + "…"


def _fmt_pct(value):
    text = "%.1f" % value
    return text.rstrip("0").rstrip(".") + "%"


def format_report(report, strict=False):
    lines = []
    lines.append("# 版式骨架审计 · %s" % report["source"])
    lines.append("")

    rows = [
        (str(s["no"]), s["title"] or "—", s["signature"])
        for s in report["slides"]
    ]
    no_w = max(_display_width("屏"), max(_display_width(r[0]) for r in rows))
    title_w = max(_display_width("标题"), max(_display_width(_clip(r[1], TITLE_MAX)) for r in rows))
    sig_w = max(_display_width("骨架"), max(_display_width(_clip(r[2], SIGNATURE_MAX)) for r in rows))

    lines.append("  %s  %s  %s" % (_pad("屏", no_w, "right"), _pad("标题", title_w), "骨架"))
    lines.append("  %s  %s  %s" % ("─" * no_w, "─" * title_w, "─" * sig_w))
    for no, title, sig in rows:
        lines.append("  %s  %s  %s" % (
            _pad(no, no_w, "right"),
            _pad(_clip(title, TITLE_MAX), title_w),
            _clip(sig, SIGNATURE_MAX),
        ))

    adjacent = "—（已关闭）" if not report["adjacent_checked"] else str(report["adjacent_repeat"])
    lines.append("")
    lines.append(
        "摘要：骨架 %d 种 / %d 屏 · 相邻重复 %s · 最多重复 %d 次（%s） · 覆盖 %s"
        % (
            report["kinds"], report["total"], adjacent,
            report["max_repeat"], report["max_repeat_signature"],
            _fmt_pct(report["coverage"]),
        )
    )
    lines.append(
        "来源：data-arch %d 屏 · 特征推断 %d 屏 · 门限 min=%d / max-repeat=%d"
        % (
            report["arch_tagged"], report["inferred"],
            report["min_kinds"], report["max_repeat_allowed"],
        )
    )
    lines.append("")
    lines.append("骨架分布：")
    for item in report["distribution"]:
        lines.append("  %s ×%d  %s" % (
            _pad(_clip(item["signature"], SIGNATURE_MAX), sig_w),
            item["count"],
            _numbers_text(item["slides"]),
        ))
    lines.append("")

    if report["violations"]:
        hint = "（--strict 已开启，退出码 1）" if strict else "（默认建议级，退出码 0；加 --strict 则退出 1）"
        lines.append("发现 %d 条建议%s：" % (len(report["violations"]), hint))
        for v in report["violations"]:
            lines.append("  [%s] %s — %s" % (v["level"], v["title"], v["detail"]))
            lines.append("      建议：%s" % v["suggestion"])
    else:
        lines.append("✅ 没发现版式多样性问题（建议级；--strict 下同样退出 0）")

    return "\n".join(lines)


# ------------------------------------------------------------------ 自测
def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _check(cond, message):
    if not cond:
        raise AssertionError(message)


def _selftest_decks(base):
    """返回 (deck-a 的 8 个 section 文本, deck-a 目录, deck-b 目录)。"""
    # 1) data-arch 优先：签名是 cover，但特征仍应算出来（grid2/split/card）
    cover = (
        '<section class="slide" data-title="封面" data-arch="cover">'
        '<div class="grid" style="grid-template-columns: repeat(2, 1fr)">'
        '<div class="card">A</div><div class="card">B</div></div></section>'
    )
    # 2) 三并列 + 屏内嵌套 <section>：切屏必须按深度匹配，不许多切
    trio = (
        '<section class="slide" data-title="三并列">'
        '<div class="grid" style="grid-template-columns: repeat(3, 1fr)">'
        '<div class="card">A</div><div class="card">B</div><div class="card">C</div></div>'
        '<section class="aside"><p>屏内嵌套结构</p></section></section>'
    )
    # 3) 清单：<style>/注释/notes 里都放诱饵，清洗后不应影响特征
    list_slide = (
        '<section class="slide" data-title="清单">'
        '<style>.decoy { grid-template-columns: repeat(4, 1fr); }</style>'
        '<!-- 诱饵：<table><tr><td>假表格</td></tr></table> -->'
        '<ul><li>一</li><li>二</li></ul>'
        '<aside class="notes">备注里写箭头 → → 和 grid 也不该参与推断</aside></section>'
    )
    table = (
        '<section class="slide" data-title="对照表格">'
        '<table><tr><th>甲</th><td>1</td></tr></table></section>'
    )
    # 5) 无 data-title：标题回退到第一个 <h1>
    flow = (
        '<section class="slide">'
        '<h1>流程 · 标题回退</h1>'
        '<div class="flow"><span>输入</span><span>输出</span></div></section>'
    )
    board = (
        '<section class="slide" data-title="看板" data-arch="board">'
        '<div class="stat">42</div></section>'
    )
    sections = [cover, trio, list_slide, table, flow, board, list_slide, trio]

    deck_a = base / "deck-a"
    deck_a.mkdir(parents=True, exist_ok=True)
    for i, section in enumerate(sections, 1):
        _write(deck_a / ("%02d-slide.html" % i), section + "\n")

    # 6 屏全同骨架
    deck_b = base / "deck-b"
    deck_b.mkdir(parents=True, exist_ok=True)
    for i in range(1, 7):
        _write(
            deck_b / ("%02d-repeat.html" % i),
            '<section class="slide" data-title="重复 %d">'
            '<div class="grid" style="grid-template-columns: repeat(3, 1fr)">'
            '<div class="card">%d</div></div></section>\n' % (i, i),
        )

    return sections, deck_a, deck_b


def run_self_test():
    base_dir = "/tmp" if Path("/tmp").is_dir() else None
    tmp = Path(tempfile.mkdtemp(prefix="layout_audit_selftest_", dir=base_dir))
    ok = True
    print("layout_audit self-test")
    print("  临时目录：%s" % tmp)
    try:
        sections, deck_a, deck_b = _selftest_decks(tmp)

        # A. 干净 deck：8 屏 6 骨架，不应有任何 violation
        slides_a = collect_src(deck_a)
        report_a = build_report(slides_a, min_kinds=6, max_repeat=3, check_adjacent=True)
        _check(report_a["total"] == 8, "8 屏 deck 切出了 %d 屏" % report_a["total"])
        _check(report_a["kinds"] == 6, "8 屏 deck 应是 6 种骨架，实际 %d 种：%s" % (
            report_a["kinds"], [s["signature"] for s in report_a["slides"]]))
        _check(not report_a["violations"], "干净 deck 不应有 violation：%s" % report_a["violations"])
        _check(decide_exit(report_a, True) == 0, "干净 deck 加 --strict 也应退出 0")
        _check(slides_a[0]["signature"] == "cover", "data-arch 应优先于特征推断")
        _check("card" in slides_a[0]["features"], "data-arch 屏仍应计算特征")
        _check(report_a["slides"][4]["title"] == "流程 · 标题回退", "无 data-title 时应回退到 h1")
        print("  ✓ 干净 deck：8 屏 6 骨架，data-arch/特征/标题回退正确，0 violation，--strict 退出 0")

        # B. 构建后的单文件：嵌套 section 与 script 里的假标签都不许干扰切屏
        index_doc = (
            "<!doctype html><html><head>"
            "<style>.decoy { grid-template-columns: repeat(4, 1fr); }</style>"
            "<script>window.__decoy = '<section class=\"slide\" data-title=\"假屏\">' + '</section>';</script>"
            "</head><body><main><section class=\"region\">\n"
            + "\n".join(sections)
            + "\n</section></main></body></html>"
        )
        index_file = deck_a / "index.html"
        _write(index_file, index_doc)
        slides_i = collect_index(index_file)
        report_i = build_report(slides_i, min_kinds=6, max_repeat=3, check_adjacent=True)
        _check(report_i["total"] == 8, "构建单文件切出了 %d 屏" % report_i["total"])
        _check(
            [s["signature"] for s in slides_i] == [s["signature"] for s in slides_a],
            "构建单文件与 --src 的骨架签名不一致：%s vs %s" % (
                [s["signature"] for s in slides_i], [s["signature"] for s in slides_a]),
        )
        _check(report_i["kinds"] == report_a["kinds"], "构建单文件与 --src 的骨架种数不一致")
        print("  ✓ 构建单文件：嵌套 section / script 诱饵不干扰，切出 8 屏且骨架与 --src 一致")

        # C. 单调 deck：6 屏全同骨架
        report_b = build_report(collect_src(deck_b), min_kinds=6, max_repeat=3, check_adjacent=True)
        rules = {v["rule"] for v in report_b["violations"]}
        _check(report_b["total"] == 6, "单调 deck 屏数应为 6，实际 %d" % report_b["total"])
        _check(report_b["kinds"] == 1, "单调 deck 应只有 1 种骨架，实际 %d" % report_b["kinds"])
        _check("single_skeleton" in rules, "单调 deck 应命中 single_skeleton：%s" % rules)
        _check("few_kinds" in rules, "单调 deck 应命中 few_kinds：%s" % rules)
        _check("adjacent" in rules, "单调 deck 应命中相邻重复：%s" % rules)
        _check(report_b["max_repeat"] == 6, "单调 deck 单骨架最多重复应为 6")
        _check(report_b["adjacent_repeat"] == 5, "单调 deck 相邻重复对数应为 5")
        _check(decide_exit(report_b, True) == 1, "单调 deck 加 --strict 应退出 1")
        _check(decide_exit(report_b, False) == 0, "单调 deck 默认（建议级）应退出 0")
        print("  ✓ 单调 deck：识别 1 种骨架，命中单一骨架/种数不足/相邻重复，--strict 退出 1")

        # D. --no-adjacent：只关相邻检查，其它仍生效
        report_b2 = build_report(collect_src(deck_b), min_kinds=6, max_repeat=3, check_adjacent=False)
        rules2 = {v["rule"] for v in report_b2["violations"]}
        _check(report_b2["adjacent_repeat"] == 0, "--no-adjacent 时相邻重复应为 0")
        _check("adjacent" not in rules2, "--no-adjacent 后不应再有 adjacent violation")
        _check({"single_skeleton", "few_kinds"} <= rules2, "--no-adjacent 不应影响其它检查")
        print("  ✓ --no-adjacent：相邻重复检查关闭，其它 violation 不受影响")
    except AssertionError as exc:
        print("  ✗ %s" % exc)
        ok = False
    except Exception as exc:  # 自测自身出错也要给出可读信息
        print("  ✗ 自测异常：%s: %s" % (type(exc).__name__, exc))
        ok = False
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("  %s 临时目录已清理：%s" % ("✓" if ok else "✗", tmp))
    if ok:
        print("self-test 通过（4/4）")
        return 0
    print("self-test 失败")
    return 1


# ------------------------------------------------------------------ CLI
def _resolve(value):
    p = Path(value).expanduser()
    if p.is_absolute() or p.exists():
        return p
    alt = ROOT / p
    return alt if alt.exists() else p


def _display(path):
    try:
        return str(path.resolve().relative_to(ROOT))
    except (ValueError, OSError):
        return str(path)


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="layout_audit.py",
        description="用页面骨架签名检查一套 deck 的版式多样性（建议级设计质量门禁）",
        epilog=(
            "示例：\n"
            "  python3 tools/layout_audit.py --src src-sample/slides\n"
            "  python3 tools/layout_audit.py --index decks/sample-deck/index.html --json\n"
            "  python3 tools/layout_audit.py --self-test"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    group = ap.add_mutually_exclusive_group()
    group.add_argument("--src", metavar="目录", help="源码形态：目录下每个 .html 是一屏")
    group.add_argument("--index", metavar="文件", help="构建后的单文件 deck（按深度切 <section>）")
    ap.add_argument("--json", action="store_true", help="输出机器可读 JSON")
    ap.add_argument("--strict", action="store_true", help="有 violation 时退出 1（默认总是退出 0）")
    ap.add_argument("--min", dest="min_kinds", type=int, default=6, metavar="N",
                    help="骨架种数门限，低于则报警，默认 6")
    ap.add_argument("--max-repeat", dest="max_repeat", type=int, default=3, metavar="N",
                    help="单骨架最多重复次数，超过则报警，默认 3")
    ap.add_argument("--no-adjacent", action="store_true", help="关闭相邻同骨架检查")
    ap.add_argument("--self-test", action="store_true", help="在 /tmp 生成临时 deck 自测后清理")
    args = ap.parse_args(argv)

    if args.self_test:
        return run_self_test()
    if not args.src and not args.index:
        ap.print_usage(sys.stderr)
        print("错误：需要 --src <目录> 或 --index <文件>（或用 --self-test）", file=sys.stderr)
        return 2

    try:
        if args.src:
            path = _resolve(args.src)
            slides = collect_src(path)
            mode = "src"
        else:
            path = _resolve(args.index)
            slides = collect_index(path)
            mode = "index"
        report = {"source": _display(path), "mode": mode}
        report.update(build_report(
            slides,
            min_kinds=args.min_kinds,
            max_repeat=args.max_repeat,
            check_adjacent=not args.no_adjacent,
        ))
    except AuditInputError as exc:
        print("错误：%s" % exc, file=sys.stderr)
        return 2

    code = decide_exit(report, args.strict)
    report["strict"] = args.strict
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(format_report(report, strict=args.strict))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
