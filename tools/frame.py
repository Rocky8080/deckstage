#!/usr/bin/env python3
"""frame.py — 因果链 / 价值链审查器（可被 Codex、ZCode、DSH 等任意 agent 通过 shell 调用）

用法：
  python3 tools/frame.py framework            打印方法骨架（可直接拼进 prompt）
  python3 tools/frame.py checklist            打印 10 问自检清单
  python3 tools/frame.py audit <路径|glob>     审查幻灯片/文档，输出问题表（--json 输出机器可读）
  python3 tools/frame.py lint <文本文件|字符串> 检查一句话/一段话里的禁用表达
"""
from __future__ import annotations

import argparse
import glob
import json
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------- 规则定义
BANNED = [
    (r"大幅(提升|提高|增长|改善)", "无数字的'大幅'"),
    (r"显著(提升|提高|增长|改善)", "无数字的'显著'"),
    (r"极大(提升|提高|改善)", "无数字的'极大'"),
    (r"(效率|速度)(翻倍|倍增)", "无基准的'翻倍'"),
    (r"业内(领先|第一|最好)", "无出处的排名断言"),
    (r"我觉得|应该是|大概吧", "无法反驳的措辞"),
]

MULTIPLE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:倍|×)")
BASELINE = re.compile(r"(相比|对比|基准|口径|vs|VS|相对|同一|同期|相当于|人月|传统做法|原来|聚宽)")
COUNTERFACTUAL = re.compile(r"(如果|否则|相当于|折合|需要约?\s*\d|不这么做)")
CONCLUSION = re.compile(r"(所以|因此|结论|意味着|说明|这才是|证明|核心判断|一句话|主张|换来|变成)")
ANCHOR = re.compile(r"(看(图|这|那|左|右|上|到)?|图中|图为首|图为|左上|右下|这一行|那一块|见右栏|注意|指那里)")
PERSON_MONTH = re.compile(r"(人月|人\s*[×x*]\s*月|人数\s*[×x*]|\d+\s*人\s*[×x*]\s*\d+)")
IMAGES = re.compile(r"<img[^>]*alt=\"([^\"]*)\"")
TABLE = re.compile(r"<table|class=\"[^\"]*cmp[^\"]*\"")
TEXT = re.compile(r">([^<>]{2,})<")


def framework_text() -> str:
    return """因果链（Why it works）—— 五段，缺一段就只是原料
  1 现状   原本怎么做、成本多少（人月 / 时间 / 费用）
  2 机制   我做对了哪一件事（必须能被复述的一句话）
  3 结果   用同一把尺子量出的数字
  4 反事实 不这么做会怎样（换算成年 / 倍 / 钱）
  5 结论   一句话，能被复述、能被反驳

价值链（What it is worth）—— 四段
  投入 → 转化 → 产出 → 价值
  (人月/时间/费用) (能力/系统) (可交付物) (省下的未来时间 / 可复用性)

数字三件套：口径 · 基准 · 结论
  假设例：同一批月报沿用同一审核标准，人工汇总 4 人 × 6 个月 = 24 人月，
          自动汇总 2 人 × 6 个月 = 12 人月。
  反事实：沿用人工汇总需多投入 12 人月，相当于多用 2 人工作 6 个月。
  结论：自动汇总使这批月报的投入从 24 人月降至 12 人月。

图文因果链：断言 → 指认锚点（看这里）→ 可自证的结论
  图注必须写“这张图证明了什么”，并指出该看哪一处（数字/位置/颜色）

五条禁则
  1 不写没有比较对象的倍数  2 不混量纲  3 表格没有“所以”就不该出现
  4 结论不许“我觉得”      5 估算当场标口径
"""


def checklist_text() -> str:
    return """每屏 10 问
 1 这一屏想让人记住的一句话是什么？它出现在页面上了吗？
 2 每个数字都有口径吗？
 3 每个数字都有基准（和谁比）吗？
 4 有没有把不同量纲并列（人/月/次/页）？
 5 有没有换算成统一货币（人月、倍、天）？
 6 有没有反事实（不这么做会怎样）？
 7 结论句能否被反驳？不能就重写
 8 这个表格真的需要吗？能不能换成一个倍数或一条曲线？
 9 删掉这屏，论证会断吗？不会断说明它只是素材
 10 图文：遮住文字图能证明什么？遮住图句子还成立吗？
"""


def strip_tags(html: str) -> str:
    html = re.sub(r"<style[\s\S]*?</style>", " ", html)
    html = re.sub(r"<script[\s\S]*?</script>", " ", html)
    return " ".join(TEXT.findall(html))


QUOTED = re.compile(r"[「『“\"][^」』”\"]{0,80}[」』”\"]")


def audit_slide(text: str, title: str) -> list[dict]:
    issues = []
    plain = strip_tags(text)
    # 引号内的文字是被讨论/被否定的对象，不参与禁用表达检查
    plain_for_banned = QUOTED.sub(" ", plain)
    for pat, label in BANNED:
        if re.search(pat, plain_for_banned):
            issues.append({"sev": "P1", "rule": "禁用表达", "detail": label})

    # 倍数缺基准
    for m in MULTIPLE.finditer(plain):
        seg = plain[max(0, m.start() - 60): m.end() + 60]
        if not BASELINE.search(seg):
            issues.append({"sev": "P0", "rule": "无基准倍数",
                           "detail": f"『{m.group(0)}』周边 60 字内无对比口径"})

    # 有倍数但无反事实
    if MULTIPLE.search(plain) and not COUNTERFACTUAL.search(plain):
        issues.append({"sev": "P1", "rule": "缺反事实",
                       "detail": "出现倍数，但没有换算成“相当于/需要 X 年/否则…”"})

    # 表格无结论
    if TABLE.search(text) and not CONCLUSION.search(plain) and 'class="insight' not in text:
        issues.append({"sev": "P0", "rule": "表格无结论",
                       "detail": "有表格/对照，但全屏没有“所以/意味着/说明”"})

    # 人月口径混用
    if re.search(r"\d+\s*人", plain) and re.search(r"\d+\s*个?月", plain) and not PERSON_MONTH.search(plain):
        issues.append({"sev": "P0", "rule": "量纲未统一",
                       "detail": "同屏出现“N 人”和“N 个月”，但没有折成人月"})

    # 图像无锚点
    imgs = IMAGES.findall(text)
    if imgs:
        if not ANCHOR.search(plain):
            issues.append({"sev": "P1", "rule": "图无指认锚点",
                           "detail": f"{len(imgs)} 张图，正文没有“看图中/左上/这一行”之类的指引"})
        if not re.search(r"(证明|说明|核对|可复算|看)", " ".join(imgs) + plain):
            issues.append({"sev": "P2", "rule": "图注描述式",
                           "detail": "图注可能在描述“是什么”，而不是“证明了什么”"})

    # 结论句（页面里的 .insight 元素视为已有结论位）
    has_insight = 'class="insight' in text or 'class="takeaway' in text
    if len(plain) > 80 and not has_insight and not CONCLUSION.search(plain):
        issues.append({"sev": "P1", "rule": "缺结论", "detail": "整屏没有结论性措辞"})

    return issues


def do_audit(target: str, as_json: bool) -> int:
    files = sorted(glob.glob(target, recursive=True)) if any(c in target for c in "*?[") else [target]
    files = [f for f in files if Path(f).is_file()]
    if not files:
        print(f"没有找到：{target}", file=sys.stderr)
        return 2

    report, total = [], {"P0": 0, "P1": 0, "P2": 0}
    for f in files:
        html = Path(f).read_text(encoding="utf-8", errors="ignore")
        # 一屏一屏切：按 <section class="slide" ...> 起始位置切（幻灯片内部可能还有嵌套 <section>）
        marks = list(re.finditer(r'<section[^>]*class="slide[^"]*"[^>]*>', html))
        slides = []
        for i, m in enumerate(marks):
            end = marks[i + 1].start() if i + 1 < len(marks) else len(html)
            body = html[m.end():end]
            t = re.search(r'data-title="([^"]*)"', m.group(0))
            slides.append((t.group(1) if t else Path(f).stem, body))
        if not slides:
            slides = [(Path(f).stem, html)]
        for title, body in slides:
            issues = audit_slide(body, title)
            for it in issues:
                total[it["sev"]] += 1
            if issues:
                report.append({"file": f, "slide": title, "issues": issues})

    if as_json:
        print(json.dumps({"total": total, "slides": report}, ensure_ascii=False, indent=1))
        return 1 if total["P0"] else 0

    print(f"# 因果链 / 价值链审查 · {len(files)} 个文件\n")
    if total["P1"] + total["P2"] > 20:
        print("> 提示：图片型幻灯片（每屏只有一张渲染图）会让“图无锚点/缺结论”规则大量命中，")
        print("> 这类 deck 应把审查重点放在讲稿与文案层（可先导出文字再审）。\n")
    print(f"问题合计：P0 {total['P0']} · P1 {total['P1']} · P2 {total['P2']}\n")
    for r in report:
        print(f"## {r['slide']}  ({Path(r['file']).name})")
        for it in r["issues"]:
            print(f"  [{it['sev']}] {it['rule']} — {it['detail']}")
        print()
    if not report:
        print("✅ 没发现规则级问题（仍需人工过一遍 10 问清单）")
    return 1 if total["P0"] else 0


def do_lint(target: str) -> int:
    p = Path(target)
    text = p.read_text(encoding="utf-8", errors="ignore") if p.is_file() else target
    plain = strip_tags(text) if "<" in text else text
    plain_for_banned = QUOTED.sub(" ", plain)
    bad = 0
    for pat, label in BANNED:
        for m in re.finditer(pat, plain_for_banned):
            print(f"[P1] 禁用表达：{label} —— 『{m.group(0)}』")
            bad += 1
    for m in MULTIPLE.finditer(plain):
        seg = plain[max(0, m.start() - 60): m.end() + 60]
        if not BASELINE.search(seg):
            print(f"[P0] 无基准倍数：『{m.group(0)}』需要写清和谁比、什么口径")
            bad += 1
    print("✅ 通过" if not bad else f"共 {bad} 处问题")
    return 1 if bad else 0


def main() -> int:
    ap = argparse.ArgumentParser(description="因果链/价值链框架与审查")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("framework")
    sub.add_parser("checklist")
    a = sub.add_parser("audit"); a.add_argument("target"); a.add_argument("--json", action="store_true")
    l = sub.add_parser("lint"); l.add_argument("target")
    args = ap.parse_args()

    if args.cmd == "framework":
        print(framework_text()); return 0
    if args.cmd == "checklist":
        print(checklist_text()); return 0
    if args.cmd == "audit":
        return do_audit(args.target, args.json)
    if args.cmd == "lint":
        return do_lint(args.target)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
