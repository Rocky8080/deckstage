#!/usr/bin/env python3
"""plan.py — 施工图（plan.json）校验：先定观点与骨架，再写页面

「写之前先填两行：这页回答上一页的哪个问题？看完对方会问什么？」——施工图把这两行
连同全册主张（L0）、每页断言、骨架选择、模块认领写成 <src>/plan.json，在写 HTML 之前
就能校验结构。规则与 capabilities/point-hierarchy、design-quality/LAYOUTS.md 同源。

用法：
  python3 tools/plan.py audit src-sample/slides          # 自动找 ../plan.json
  python3 tools/plan.py audit src-sample/slides --plan <路径> --json

plan.json 形态：
  {
    "l0": "一句话全册主张（能被反驳）",
    "slides": [
      {"file": "01-cover.html", "arch": "cover",
       "claim": "这页的断言（与页面 h1 一致）",
       "answers": "—（封面）",          // 回答上一页留下的哪个问题；首屏可写 —
       "asks": "这套系统怎么装？",       // 看完这页对方会问什么
       "modules": [{"role": "主", "supports": "完整用法", "evidence": "本页即成品"}]}
    ]
  }

检查（P0 阻断构建；P1 建议）：
  P0 plan_slide_mismatch   plan 与 slides/*.html 文件集不一致（缺 / 多 / 顺序外文件）
  P0 arch_unknown          data-arch 不在骨架注册表
  P0 claim_missing         断言缺失或过短（< 6 个可见字符）
  P0 modules_bad           模块缺失 / 超过 3 个 / 没有「主」/ 有多个「主」
  P1 claim_generic         断言是名词短语（概述 / 背景 / 核心功能 一类）
  P1 title_drift           断言与页面 h1/data-title 对不上（两侧互不包含）
  P1 answers_missing       第 2 屏起没有写「承接上一页哪个问题」
  P1 asks_missing          没有写「看完对方会问什么」
  P1 evidence_missing      「主」模块没有写证据
  P1 adjacent_arch         相邻两屏同骨架
  P1 few_arch              骨架种数不足（≥10 屏 6 种 / 短 deck 4 种）
  P1 arch_repeat           同一骨架超过 3 次

退出码：0 = 通过（P1 只提示）；1 = 有 P0；2 = 输入错误。
plan.json 不存在 → 视为该 deck 未用施工图流程，输出提示并退出 0（不阻断旧 deck）。
"""
from __future__ import annotations

import _platform  # noqa: F401  — Windows GBK 管道下的 stdout UTF-8 兜底（见 _platform.py）
import argparse
import json
import re
import sys
from html import unescape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 骨架注册表：capabilities/design-quality/LAYOUTS.md 的 12 骨架 + 图示型扩展
KNOWN_ARCHS = (
    "cover", "toc", "point", "trio", "matrix", "chain", "ladder", "board",
    "arch", "loop", "contrast", "closing",
    "bars", "bridge", "quadrant", "timeline", "versus",
)

GENERIC_TITLE_WORDS = (
    "概述", "背景", "核心功能", "简介", "介绍", "总结", "小结", "内容",
    "价值", "方案", "成果", "亮点", "其它", "其他", "附录", "问答", "QA",
)

SECTION_TAG_RE = re.compile(r"<section\b[^>]*>", re.I)
H1_RE = re.compile(r"<h1\b[^>]*>(.*?)</h1\s*>", re.S | re.I)
TAG_RE = re.compile(r"<[^>]+>", re.S)
ATTR_RE_TEMPLATE = r"\b{name}\s*=\s*(?:\"([^\"]*)\"|'([^']*)'|([^\s>]+))"
NATURAL_SPLIT = re.compile(r"(\d+)")


class PlanInputError(Exception):
    """输入有问题（目录不存在 / 没有页面），对应退出码 2。"""


def _natural_key(name):
    return [int(t) if t.isdigit() else t.lower() for t in NATURAL_SPLIT.split(name)]


def get_attr(tag, name):
    m = re.search(ATTR_RE_TEMPLATE.format(name=re.escape(name)), tag or "", re.I)
    if not m:
        return ""
    return re.sub(r"\s+", " ", unescape(m.group(1) or m.group(2) or m.group(3) or "")).strip()


def plain_text(html):
    return re.sub(r"\s+", " ", unescape(TAG_RE.sub(" ", html or ""))).strip()


def _norm(text):
    """比较用：去空白与常见标点。"""
    return re.sub(r"[\s，。：:；;、·—\-–|/《》“”\"'（）()]+", "", text or "")


def _shared_run(a, b, min_len=4):
    """两串文本之间最长公共子串长度（小写、去标点后）；用于 title_drift 判定。"""
    a, b = _norm(a).lower(), _norm(b).lower()
    best = 0
    for i in range(len(a)):
        for j in range(len(b)):
            k = 0
            while i + k < len(a) and j + k < len(b) and a[i + k] == b[j + k]:
                k += 1
            best = max(best, k)
    return best


def load_plan(plan_path):
    try:
        data = json.loads(plan_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PlanInputError(f"plan.json 不是合法 JSON：{exc}")
    if not isinstance(data.get("slides"), list) or not data["slides"]:
        raise PlanInputError("plan.json 缺少 slides 数组（或为空）")
    return data


def audit(slides_dir: Path, plan_path: Path | None):
    if not slides_dir.exists() or not slides_dir.is_dir():
        raise PlanInputError(f"页面目录不存在：{slides_dir}")
    html_files = sorted(
        [p for p in slides_dir.iterdir() if p.is_file() and p.suffix.lower() == ".html"],
        key=lambda p: _natural_key(p.name),
    )
    # 纯 <style> 补丁文件（没有 <section>）不算一屏
    page_files = []
    for p in html_files:
        if re.search(r"<section\b", p.read_text(encoding="utf-8", errors="ignore"), re.I):
            page_files.append(p)
    if not page_files:
        raise PlanInputError(f"目录下没有可分析的页面：{slides_dir}")

    if plan_path is None or not plan_path.exists():
        return {
            "source": str(slides_dir), "plan": None,
            "total": {"P0": 0, "P1": 0, "P2": 0},
            "slides": [], "arch_map": {}, "kinds": 0,
            "note": "未找到 plan.json：该 deck 未走施工图流程（可选；新 deck 建议先写施工图）",
        }

    plan = load_plan(plan_path)
    entries = {e.get("file"): e for e in plan["slides"] if isinstance(e, dict)}
    plan_files = [e.get("file") for e in plan["slides"] if isinstance(e, dict)]
    html_names = [p.name for p in page_files]

    issues_by_file = {name: [] for name in html_names}

    def add(name, sev, rule, detail):
        issues_by_file.setdefault(name, []).append({"sev": sev, "rule": rule, "detail": detail})

    # ---- 文件集一致性（P0） ----
    for name in plan_files:
        if name not in html_names:
            add(name or "(空)", "P0", "plan_slide_mismatch", f"plan 里有 {name}，但目录下没有这个页面文件")
    for name in html_names:
        if name not in entries:
            add(name, "P0", "plan_slide_mismatch", f"目录下有 {name}，但 plan 里没有它的条目（先补施工图再写页面）")

    # ---- 逐页检查 ----
    arch_seq = []
    for idx, path in enumerate(page_files, 1):
        name = path.name
        e = entries.get(name)
        if not e:
            continue
        raw = path.read_text(encoding="utf-8", errors="ignore")
        opening = SECTION_TAG_RE.search(raw)
        opening = opening.group(0) if opening else ""

        arch = str(e.get("arch") or "").strip().lower()
        arch_seq.append((name, arch))
        if arch and arch not in KNOWN_ARCHS:
            add(name, "P0", "arch_unknown",
                f"骨架 `{arch}` 不在注册表：{' / '.join(KNOWN_ARCHS)}")
        elif arch:
            html_arch = get_attr(opening, "data-arch").lower()
            if html_arch and html_arch != arch:
                add(name, "P0", "arch_unknown",
                    f"页面写了 data-arch={html_arch}，施工图写的是 {arch}；两边要一致")

        claim = str(e.get("claim") or "").strip()
        if len(plain_text(claim)) < 6:
            add(name, "P0", "claim_missing", f"断言缺失或过短（< 6 字）：{claim or '（空）'}")
        elif any(w in claim for w in GENERIC_TITLE_WORDS):
            add(name, "P1", "claim_generic", f"断言像名词短语（{claim}）——标题要是一句能被反驳的话")

        h1m = H1_RE.search(raw)
        h1 = plain_text(h1m.group(1)) if h1m else ""
        dt = get_attr(opening, "data-title")
        page_title = h1 or dt
        if claim and page_title and _shared_run(claim, page_title) < 4:
            add(name, "P1", "title_drift",
                f"断言（{claim}）与页面标题（{page_title}）对不上：改标题或改施工图，保持同源")

        if idx >= 2 and not str(e.get("answers") or "").strip():
            add(name, "P1", "answers_missing", "没写「承接上一页哪个问题」——这页开头要接得住上一页")
        if not str(e.get("asks") or "").strip():
            add(name, "P1", "asks_missing", "没写「看完对方会问什么」——下一页要回答它")

        modules = e.get("modules")
        if not isinstance(modules, list) or not modules:
            add(name, "P0", "modules_bad", "modules 缺失或为空——每个模块都要认领标题里的哪个词")
        else:
            if len(modules) > 3:
                add(name, "P0", "modules_bad", f"模块 {len(modules)} 个，超过 3 个上限——合并或移页")
            roles = [str(m.get("role") or "").strip() for m in modules if isinstance(m, dict)]
            mains = [r for r in roles if r == "主"]
            if not mains:
                add(name, "P0", "modules_bad", "没有标记「主」模块——支撑同一句的模块只许一个主")
            elif len(mains) > 1:
                add(name, "P0", "modules_bad", f"标了 {len(mains)} 个「主」——只许一个")
            for m in modules:
                if isinstance(m, dict) and m.get("role") == "主" and not str(m.get("evidence") or "").strip():
                    add(name, "P1", "evidence_missing", f"主模块（{m.get('supports') or '未命名'}）没写证据")

    # ---- 全册骨架节奏（P1） ----
    known_seq = [(n, a) for n, a in arch_seq if a]
    for i in range(1, len(known_seq)):
        if known_seq[i][1] == known_seq[i - 1][1]:
            add(known_seq[i][0], "P1", "adjacent_arch",
                f"相邻两屏同为 `{known_seq[i][1]}`——施工图阶段就该换开")
    counts = {}
    for _, a in known_seq:
        counts[a] = counts.get(a, 0) + 1
    kinds = len(counts)
    total = len(page_files)
    min_kinds = 6 if total >= 10 else 4
    if kinds and kinds < min_kinds:
        first = known_seq[0][0]
        add(first, "P1", "few_arch", f"骨架只有 {kinds} 种，低于 {min_kinds} 种（{total} 屏）")
    for a, c in sorted(counts.items(), key=lambda kv: -kv[1]):
        if c > 3:
            victim = next(n for n, x in known_seq if x == a)
            add(victim, "P1", "arch_repeat", f"骨架 `{a}` 出现 {c} 次，超过 3 次上限")

    slides_out = []
    arch_map = {}
    for name in html_names:
        e = entries.get(name) or {}
        arch = str(e.get("arch") or "").strip().lower()
        if arch in KNOWN_ARCHS:
            arch_map[name] = arch
        slides_out.append({
            "file": name,
            "arch": arch or None,
            "claim": e.get("claim"),
            "answers": e.get("answers"),
            "asks": e.get("asks"),
            "modules": e.get("modules"),
            "issues": issues_by_file.get(name, []),
        })

    total_counts = {"P0": 0, "P1": 0, "P2": 0}
    for s in slides_out:
        for i in s["issues"]:
            total_counts[i["sev"]] = total_counts.get(i["sev"], 0) + 1

    return {
        "source": str(slides_dir),
        "plan": str(plan_path),
        "l0": plan.get("l0") or "",
        "total": total_counts,
        "slides": slides_out,
        "arch_map": arch_map,
        "kinds": kinds,
    }


def format_report(rep):
    lines = []
    lines.append("# 施工图校验 · %s" % rep["source"])
    lines.append("")
    if rep.get("plan") is None:
        lines.append("  %s" % rep.get("note", "未找到 plan.json"))
        return "\n".join(lines)
    if rep.get("l0"):
        lines.append("  L0 全册主张：%s" % rep["l0"])
    lines.append("  骨架：%d 种 / 施工图 %d 屏" % (rep.get("kinds", 0), len(rep["slides"])))
    lines.append("")
    for s in rep["slides"]:
        head = "  %-22s %s  %s" % (
            s["file"], (s["arch"] or "—").ljust(8), (s["claim"] or "—")[:36])
        lines.append(head)
        for i in s["issues"]:
            lines.append("      [%s] %s — %s" % (i["sev"], i["rule"], i["detail"]))
    if not any(s["issues"] for s in rep["slides"]):
        lines.append("  ✅ 施工图与页面一致，节奏与认领检查全部通过")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="plan.py", description="施工图（plan.json）校验")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_audit = sub.add_parser("audit", help="校验施工图与页面的一致性")
    p_audit.add_argument("target", help="slides 目录（plan.json 在其上级目录）")
    p_audit.add_argument("--plan", help="plan.json 路径（默认 <target>/../plan.json）")
    p_audit.add_argument("--json", action="store_true", help="机器可读输出")
    args = ap.parse_args(argv)

    slides_dir = Path(args.target)
    if not slides_dir.is_absolute() and not slides_dir.exists():
        alt = ROOT / slides_dir
        slides_dir = alt if alt.exists() else slides_dir
    plan_path = Path(args.plan) if args.plan else slides_dir.parent / "plan.json"

    try:
        rep = audit(slides_dir, plan_path)
    except PlanInputError as exc:
        print("错误：%s" % exc, file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(rep, ensure_ascii=False, indent=2))
    else:
        print(format_report(rep))
    return 1 if rep["total"]["P0"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
