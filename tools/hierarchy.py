#!/usr/bin/env python3
"""hierarchy.py — 观点层级审查器（纯标准库，可被任意 agent 通过 shell 调用）

一句话：一页只许有一个观点；每个模块都必须认领一句观点；没人认领的模块就是多余的。

用法：
  python3 tools/hierarchy.py outline "<glob|目录>"   每页：断言判定 + 模块清单（标签/字数/认领）+ 相似度
  python3 tools/hierarchy.py audit   "<glob|目录>" [--json]
                                                     H1–H10，P0/P1/P2；有 P0 时退出码 1
  python3 tools/hierarchy.py map     "<glob|目录>"     全册观点地图：章节 → 页 → 模块数/孤儿/重复，跨页重复对

退出码：0 通过（P0=0） · 1 有 P0 · 2 没找到文件
目标可以是 glob（"src-x/slides/*.html"）或目录（递归取 *.html）。一次跑一套 deck：
章节规则（H4/H8）按 data-rail 分组，混跑多套 deck 分组会串。

──────────────────────────── 抽取口径（纯 re + 手动配对，不用 DOM 库）
· 每屏 = <section class="slide">；取 data-title、data-rail、<p class="kicker">、<h1 class="title">。
· 只看 <div class="body"> 内部（按标签配对找到闭合，不用贪婪正则）；没有 body 的是封面/Q&A/收尾页。
· 模块容器：article / figure / table / blockquote / section，以及 class 含语义角色关键词
  item|step|card|pipe|prob|value|res|mrg__|flow 的 div。
· 模块标签：h3 > h4 > b/strong > figcaption > 首段 ≥2 字文本（截断 16 字）。
· 排除：.ptab / .practitioner / .foot / .notes / .take；.take 单独记为 claim 行，不算模块，
  但参与 H6/H7；没有 .take 时用 .insight 当结论句；style/script/svg 与标签都不算可见内容。

──── 与原始抽取口径的差异（都是在这三套 deck 上校准后加的，为了压误报）
· 包裹层下钻：命中容器里还套着 ≥2 个同类模块容器时，下钻一层。否则三张卡片的盒子会变成一个模块
  （标签取成第一张卡的名字）；原始口径「命中后不再下钻」在 03-features / 13-bp / 14-bp 上实测都错。
· 去掉了 bp1 / fin1 两个 div 关键词：它们是校准 deck 的页面命名空间（bp13__* / bp14__* / fin15__* /
  fin16__* 全页所有类名都带），按字面匹配会把整页包成一个模块，或把示意图零件（年度表、箭头、
  总表节点）算成 6–9 个模块。代价：fin16 的四条数字卡（div.fin16__stat）不再单独计模块；
  这类密页仍会被 H5 提示。
· flow：流水线容器（步骤用 span 写时整条流记 1 个模块，与 pipe 同类）。
· 列表（li）、纯 span 步骤、div 记录行（如 .rec9b__row）不算模块 —— 这是口径内的盲区，
  outline 会显示「模块 0/1」，这类页需要人看一眼。

相似度口径：
· 中文二元组 Dice（去标点、空白、数字、序号），英文按词（小写）；集合去重。
· 停用二元组：实践人 / 方案与成果 / 实践一…实践六 / 所以 / 因此 / 成果，
  再补一批功能词（我们/这个/一个/就是/不是/可以/已经…），避免「同一个/都在」造出假重复。
· 模块文本 < 20 字不参与重复判定（标签卡拿不出证据，比了只会误报）。

──────────────────────────── 规则与级别（严格执行；拿不准时降 P2）
H1 标题是名词短语 → P1
   ① 问句/话题式标题（为什么…/如何…/…吗/？）→ 话题不是断言；
   ② 黑名单词结尾（核心功能/使用说明/现在的成果/价值/背景/概述/介绍/问题/方案/成果）
      且无判断词（是/不是/要/才能/把/让/靠/从…到/拆成/换/收进）。
   例外：标题 > 12 字视为带谓语的长句，不判 —— 实测「六个实践，解决工作中面临的核心问题」
   会因「问题」结尾误报；无 <h1 class="title"> 的封面/收尾页不判。
H2 模块与「标题 + 结论句」二元组交集为空 → P2（孤儿候选，建议人工确认）
   例外 1：页面没有结论句（.take/.insight）时不判 —— 没有断言可认领，判了必误报（说明型 deck 即此）；
   例外 2：模块与同页其他模块有共同实词时，视为同一页的侧面，不判（三列卡常各说一个侧面）；
   例外 3：模块 < 12 字不判（短标签判不出孤儿）。
H3 同页两模块相似度 ≥ 0.60 → P0（必须合并）
H4 同一 data-rail 章节内、跨页两模块相似度 ≥ 0.55 → P1（同一观点讲了两遍）
   封面/收尾页（data-nofoot 或没有 h1.title）不参与：它们是导览，不是 L2。
H5 单页模块数 ≥ 5 → P2（需确认主次/是否分类说明；并列不等于重复，不要硬合并）
H6 标题是数值型断言（含 → / 倍 / % / 天 / 小时 / 屏 / 人），但页面无数字、无 <img>、无 <table> → P1
   例外：封面/收尾页不判（数字条是元信息，不是页面断言）。
H7 页面出现 ≥2 个成果型数字，但没有「口径/基准/同一套/同一把尺/相比/分母/按…计」→ P1
   成果型数字 = 带单位（天/小时/分钟/倍/%/格/元/亿/年/轮…）且至少一个是成果单位；
   序号 01/02、年份 2026、比例 16:9、引号里的原文、<pre>/<code> 命令行都不算。
   例外：封面/收尾页不判；说明型 deck 不判（使用说明/骨架库里的数字是操作参数，不是断言）。
H8 同一 data-rail 章节里没有任何一页 kicker 含「成果/结论」→ P2
   例外 1：章节里有一页明说「测试中 / 未对外发布 / 暂无结果 / 还没有结果」→ 不判
           （SKILL 原文：确实还没有结果就明说，不要用口号补）；
   例外 2：说明型 deck 不判（全册没有足够的 问题/方案/成果/结论/实践/复盘 语义）。
   「说明型 deck」判定：含汇报语义的 kicker 少于 2 屏、或不足全册 20% 时，H7/H8 跳过，其余规则照跑。
H9 同一章节内，上一页收口的那句话与本页标题「既无共同实词、标题也没有转折词」→ P2（承接断点候选）
   转折/追问词：但 / 不过 / 不够 / 还差 / 除了 / 然而 / 可是 / 问题 / 相反 / 反过来 /
   不止 / 不只 / 其实 / 所以 / 因此 / 于是 / 接下来 / 下一步 / 这才 / 否则 / 转向。
   例外：封面/收尾页不参与；上一页没有结论句或结论句太短（<24 字）不判；
         **上一页有 .bridge 过渡句的不判**（作者已经把接力写出来了，例如作品页的「下一个问题是…」）。
   只查词面与转折词，判断不了论证是否真的成立，所以只给 P2 候选，逐条人工确认。
H10 单页可见字数 > 520 → P2（细节过载：把不影响「相信」的解释下沉讲稿，页上只留主证据）
   参考值来自两套校准 deck：xlab 平均 273 字、learning 平均 352 字，最密的两页分别是 516 / 1187 字。

工具只做结构判断：主次、分类、是否值得讲，仍然要人读一遍（SKILL §6 的 12 问）。
"""
from __future__ import annotations

import _platform  # noqa: F401  — Windows GBK 管道下的 stdout UTF-8 兜底（见 _platform.py）
import argparse
import glob
import html as html_lib
import json
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------- 阈值 / 关键词
MIN_DUP_CHARS = 20          # 模块文本少于 20 字不参与重复判定
SAME_PAGE_DUP = 0.60        # H3
CROSS_PAGE_DUP = 0.55       # H4
MANY_MODULES = 5            # H5
H2_MIN_CHARS = 12           # 少于 12 字的模块太短，判不了孤儿
SHORT_TITLE_MAX = 12        # H1：超过这个长度的标题视为长句，不判名词短语
BRIDGE_MIN_CLAIM = 24       # H9：上一页收口的句子少于 24 字不判（太短，无从接）
DENSE_CHARS = 520           # H10：单页可见字数上限（参考值，超出只提示不阻断）
TURN_RE = re.compile(
    r"(但|不过|不够|还差|还缺|还少|除了|然而|可是|问题|相反|反过来|不止|不只|"
    r"其实|所以|因此|于是|接下来|下一步|这才|否则|转向|再往)"
)

MODULE_TAGS = {"article", "figure", "table", "blockquote", "section"}
MODULE_CLASS_KEYWORDS = ("item", "step", "card", "pipe", "prob", "value",
                         "res", "mrg__", "flow")
# 说明：原始口径还含 bp1 / fin1，但它们是校准 deck 的“页面命名空间”（bp13__* / fin15__* 全页所有
# 类名都带），按字面匹配会把整页和示意图零件都算成模块；校准后去掉，详见 --help。
EXCLUDE_TOKENS = {"ptab", "practitioner", "foot", "notes", "take"}
CLAIM_TOKENS = ("take", "takeaway", "insight")

TITLE_BLACKLIST = ("核心功能", "使用说明", "现在的成果", "价值", "背景",
                   "概述", "介绍", "问题", "方案", "成果")
JUDGE_RE = re.compile(r"(不是|是|要|才能|把|让|靠|从[^，。；]{0,8}到|拆成|换|收进)")
# 数值型断言：数字 + 单位（阿拉伯数字或中文数字），或 → / % / 倍。
# 不单看「天/人/屏」字：实测「日常 · 三种节奏」会因「常」里的「天」误报。
NUMERIC_TITLE_RE = re.compile(
    r"(→|%|\d|[0-9]+\s*(?:天|小时|分钟|屏|人|倍|格|元|亿)|"
    r"[一二三四五六七八九十百千万两几半]\s*(?:天|小时|分钟|屏|人|倍|格|元|亿)|倍)")
QUESTION_TITLE_RE = re.compile(r"^(为什么|为何|如何|怎么|怎样|什么是|是什么|是否|有哪些)|[吗呢？?]\s*$")
# 口径词：页面出现即认为作者交代过口径（「口径不一」也算谈到了口径）。
# 不数「口径」的各种否定形态，是为了不把“作者已经在讨论口径”的页判成“没有口径”。
CALIBER_RE = re.compile(r"(口径|基准|同一套|同一把尺|相比|对比|分母|按[^，。；]{0,8}计)")
NO_RESULT_RE = re.compile(r"(还没有结果|暂无结果|尚无结果|未对外发布|尚未发布|测试中|试运行中|未上线|仍在内测|没有结果)")
REPORT_KICKER_RE = re.compile(r"(问题|方案|成果|结论|实践|复盘|problem|solution|result|conclusion|takeaway)", re.I)

CLAIM_NUM_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(%|倍|人|天|小时|分钟|秒|毫秒|格|套|屏|个|次|条|笔|张|"
    r"年|月|周|轮|项|页|行|处|元|亿|万元|步)"
)
OUTCOME_UNITS = {"天", "小时", "分钟", "秒", "毫秒", "倍", "%", "格", "元", "亿", "万元", "年", "周", "轮"}

QUOTED_RE = re.compile(r"[「『“\"][^」』”\"]{0,200}[」』”\"]")
RATIO_RE = re.compile(r"\d+\s*[:：×xX]\s*\d+")
YEAR_RE = re.compile(r"(?<!\d)(?:19|20)\d{2}(?!\d)")
ORDINAL_RE = re.compile(r"(?<![\d.])0[1-9](?![\d.])")

STOP_PHRASES = [
    # SKILL §4 点名的停用词
    "实践人", "方案与成果", "实践一", "实践二", "实践三", "实践四", "实践五", "实践六",
    "所以", "因此", "成果",
    # 功能词：不承载观点，留着只会让任何两段中文都像
    "我们", "你们", "这个", "那个", "一个", "一次", "这些", "那些", "什么", "怎么",
    "已经", "可以", "没有", "就是", "如果", "但是", "而且", "其中", "通过", "进行",
    "以及", "还有", "不是", "这样", "那样", "这里", "那里", "现在", "之后", "之前",
    "同时", "并且", "因为", "只是", "还是", "需要", "应该", "能够", "一眼", "每",
]
STOP_BIGRAMS = set()
for _phrase in STOP_PHRASES:
    for _i in range(len(_phrase) - 1):
        STOP_BIGRAMS.add(_phrase[_i:_i + 2])

# H2 用轻停用词：判断词（不是/要/让…）要留着，否则「标题 + 结论句」里的断言词会被削掉
STOP_PHRASES_MIN = ["实践人", "方案与成果", "实践一", "实践二", "实践三",
                    "实践四", "实践五", "实践六", "所以", "因此", "成果"]
STOP_BIGRAMS_MIN = set()
for _phrase in STOP_PHRASES_MIN:
    for _i in range(len(_phrase) - 1):
        STOP_BIGRAMS_MIN.add(_phrase[_i:_i + 2])

# 英文功能词/技术词：留着会让“同一个 HTML 文件”这类句子在任意两屏都相似
STOP_WORDS_EN = {"the", "and", "for", "with", "this", "that", "from", "into", "your",
                 "you", "are", "can", "not", "but", "all", "use", "used", "one", "two",
                 "page", "pages", "http", "https", "www", "html", "css", "js", "div"}

VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link",
             "meta", "param", "source", "track", "wbr"}

TAG_RE = re.compile(
    r"<!--[\s\S]*?-->"
    r"|</\s*([a-zA-Z][\w:-]*)\s*>"
    r"|<([a-zA-Z][\w:-]*)((?:\"[^\"]*\"|'[^']*'|[^>\"'])*)>"
)
SECTION_RE = re.compile(r"<section\b((?:\"[^\"]*\"|'[^']*'|[^>\"'])*)>", re.I)
CJK_RE = re.compile(r"[\u4e00-\u9fff]+")
LATIN_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9_.\-]*")
ATTR_RE = re.compile(r"([:\w-]+)\s*=\s*\"([^\"]*)\"|([:\w-]+)\s*=\s*'([^']*)'")
CLASS_RE = re.compile(r"\bclass\s*=\s*\"([^\"]*)\"")


# ---------------------------------------------------------------- 最小 HTML 树
class El:
    __slots__ = ("tag", "cls", "children")

    def __init__(self, tag: str, cls: set[str]):
        self.tag = tag
        self.cls = cls
        self.children: list = []


def parse_class(attrs: str) -> set[str]:
    m = CLASS_RE.search(attrs or "")
    if not m:
        m = re.search(r"\bclass\s*=\s*'([^']*)'", attrs or "")
    if not m:
        return set()
    return {t for t in m.group(1).split() if t}


def parse_attrs(attrs: str) -> dict[str, str]:
    out = {}
    for m in ATTR_RE.finditer(attrs or ""):
        if m.group(1):
            out[m.group(1).lower()] = html_lib.unescape(m.group(2))
        elif m.group(3):
            out[m.group(3).lower()] = html_lib.unescape(m.group(4))
    return out


def build_tree(fragment: str) -> El:
    """栈式配对扫描；HTML 不完整（少闭合标签）时把残余压到当前节点，不抛异常。"""
    root = El("#root", set())
    stack = [root]
    pos = 0
    for m in TAG_RE.finditer(fragment):
        if m.start() > pos:
            stack[-1].children.append(fragment[pos:m.start()])
        pos = m.end()
        if m.group(1):                      # 闭合标签：向上找最近的同名开标签
            tag = m.group(1).lower()
            for i in range(len(stack) - 1, 0, -1):
                if stack[i].tag == tag:
                    del stack[i:]
                    break
            continue
        if not m.group(2):                  # 注释
            continue
        tag = m.group(2).lower()
        attrs = m.group(3) or ""
        el = El(tag, parse_class(attrs))
        stack[-1].children.append(el)
        if tag in VOID_TAGS or attrs.rstrip().endswith("/"):
            continue
        stack.append(el)
    if pos < len(fragment):
        stack[-1].children.append(fragment[pos:])
    return root


def clean_fragment(fragment: str) -> str:
    """去掉注释 / style / script / svg：它们不是可见文案。"""
    fragment = re.sub(r"<!--[\s\S]*?-->", " ", fragment)
    fragment = re.sub(r"<script\b[\s\S]*?</script\s*>", " ", fragment, flags=re.I)
    fragment = re.sub(r"<style\b[\s\S]*?</style\s*>", " ", fragment, flags=re.I)
    fragment = re.sub(r"<svg\b[\s\S]*?</svg\s*>", " ", fragment, flags=re.I)
    return fragment


def _excluded(cls: set[str]) -> bool:
    for tok in cls:
        for pat in EXCLUDE_TOKENS:
            if tok == pat or tok.startswith(pat + "__") or tok.startswith(pat + "--") \
                    or tok.endswith("__" + pat) or tok.endswith("--" + pat):
                return True
    return False


def _is_claim(cls: set[str]) -> bool:
    return any(tok in CLAIM_TOKENS or tok.startswith("take--") or tok.startswith("take__")
               for tok in cls)


def text_of(el: El, *, keep_claim: bool = False,
            skip_tags: frozenset[str] = frozenset()) -> str:
    parts: list[str] = []

    def walk(node: El) -> None:
        for child in node.children:
            if isinstance(child, str):
                parts.append(html_lib.unescape(child))
                continue
            if child.tag in ("style", "script", "svg") or child.tag in skip_tags:
                continue
            if _excluded(child.cls) and not (keep_claim and _is_claim(child.cls)):
                continue
            walk(child)

    walk(el)
    return re.sub(r"[\s\u00a0]+", " ", " ".join(parts)).strip()


def find_all(node: El, pred) -> list[El]:
    out: list[El] = []

    def walk(n: El) -> None:
        for child in n.children:
            if isinstance(child, El):
                if pred(child):
                    out.append(child)
                walk(child)

    walk(node)
    return out


def find_first(node: El, pred):
    for child in node.children:
        if isinstance(child, El):
            if pred(child):
                return child
            found = find_first(child, pred)
            if found is not None:
                return found
    return None


def has_tag(node: El, tag: str) -> bool:
    return any(el.tag == tag for el in find_all(node, lambda e: e.tag == tag))


# ---------------------------------------------------------------- 文本 / 相似度
def normalize(text: str) -> str:
    return re.sub(r"[\s\u00a0]+", " ", html_lib.unescape(text)).strip()


def char_count(text: str) -> int:
    return len(re.sub(r"\s", "", text))


def tokens(text: str, stop: set[str] | None = None) -> set[str]:
    stop = STOP_BIGRAMS if stop is None else stop
    out: set[str] = set()
    for run in CJK_RE.findall(text):
        for i in range(len(run) - 1):
            bg = run[i:i + 2]
            if bg not in stop:
                out.add(bg)
    for word in LATIN_RE.findall(text.lower()):
        if len(word) > 1 and word not in STOP_WORDS_EN:
            out.add(word)
    return out


def dice(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return 2.0 * len(a & b) / (len(a) + len(b))


def truncate(text: str, limit: int = 16) -> str:
    text = normalize(text)
    return text if len(text) <= limit else text[:limit] + "…"


# ---------------------------------------------------------------- 一屏的抽取
def module_label(el: El, full_text: str) -> str:
    for tag in ("h3", "h4"):
        hit = find_first(el, lambda e, t=tag: e.tag == t and text_of(e))
        if hit is not None:
            return truncate(text_of(hit))
    hit = find_first(el, lambda e: e.tag in ("b", "strong") and text_of(e))
    if hit is not None:
        return truncate(text_of(hit))
    hit = find_first(el, lambda e: e.tag == "figcaption" and text_of(e))
    if hit is not None:
        return truncate(text_of(hit))
    hit = find_first(el, lambda e: e.tag == "p" and char_count(text_of(e)) >= 2)
    if hit is not None:
        return truncate(text_of(hit))
    for chunk in re.split(r"[。；;！!？?\n]", full_text):
        if char_count(chunk) >= 2:
            return truncate(chunk)
    return "(未命名)"


def keyword_hits(el: El) -> set[str]:
    return {k for k in MODULE_CLASS_KEYWORDS
            if any(k in tok for tok in el.cls)}


def count_nested_modules(el: El) -> int:
    return len([e for e in find_all(el, is_module_container) if not _excluded(e.cls)])


def is_module_container(el: El) -> bool:
    if el.tag in MODULE_TAGS:
        return True
    if el.tag != "div":
        return False
    return bool(keyword_hits(el))


def pick_modules(node: El, out: list[El]) -> None:
    for child in node.children:
        if not isinstance(child, El):
            continue
        if _excluded(child.cls):
            continue
        if is_module_container(child):
            # 包裹层：里面还套着 ≥2 个模块容器时下钻，避免把“三张卡片的盒子”算成一个模块
            is_wrapper = child.tag in ("div", "section") and count_nested_modules(child) >= 2
            if is_wrapper:
                pick_modules(child, out)
            else:
                out.append(child)
            continue
        pick_modules(child, out)


def extract_slide(fragment: str, section_attrs: str, filename: str) -> dict:
    attrs = parse_attrs(section_attrs)
    data_title = normalize(attrs.get("data-title", ""))
    rail = normalize(attrs.get("data-rail", ""))

    cleaned = clean_fragment(fragment)
    root = build_tree(cleaned)

    kicker_el = find_first(root, lambda e: "kicker" in e.cls)
    kicker = text_of(kicker_el) if kicker_el is not None else ""
    title_el = find_first(root, lambda e: e.tag == "h1" and "title" in e.cls)
    title = text_of(title_el) if title_el is not None else ""

    body_el = find_first(root, lambda e: e.tag == "div" and "body" in e.cls)
    modules: list[dict] = []
    claim = ""
    bridge = ""
    page_text = ""
    prose_text = ""
    has_img = has_table = False
    has_body = body_el is not None

    if body_el is not None:
        picked: list[El] = []
        pick_modules(body_el, picked)
        for el in picked:
            full = text_of(el)
            modules.append({
                "label": module_label(el, full),
                "text": full,
                "chars": char_count(full),
                "tag": el.tag,
            })
        for e in find_all(root, lambda e: any("bridge" in c for c in e.cls)):
            bridge = text_of(e)
            break
        take_texts = [text_of(e) for e in find_all(
            body_el, lambda e: "take" in e.cls or any(t.startswith("take--") for t in e.cls))]
        if not take_texts:
            take_texts = [text_of(e) for e in find_all(body_el, lambda e: "insight" in e.cls)]
        claim = normalize(" ".join(t for t in take_texts if t))
        page_text = text_of(body_el, keep_claim=True)
        prose_text = text_of(body_el, keep_claim=True, skip_tags=frozenset({"pre", "code"}))
        has_img = has_tag(body_el, "img")
        has_table = has_tag(body_el, "table")

    return {
        "file": filename,
        "name": data_title or Path(filename).stem,
        "rail": rail,
        "kicker": kicker,
        "title": title,
        "nofoot": bool(re.search(r"\bdata-nofoot\b", section_attrs)),
        "has_body": has_body,
        "modules": modules,
        "claim": claim,
        "bridge": bridge,
        "page_text": page_text,
        "prose_text": prose_text,
        "has_img": has_img,
        "has_table": has_table,
    }


def load_slides(target: str) -> tuple[list[dict], list[str], list[str]]:
    """返回 (slides, 跳过提示, 命中文件)。文件缺失/HTML 不完整只提示，不崩。"""
    path = Path(target)
    if path.is_dir():
        files = sorted([*path.rglob("*.html"), *path.rglob("*.htm")])
    elif any(c in target for c in "*?["):
        files = sorted(f for f in glob.glob(target, recursive=True) if Path(f).is_file())
    elif path.is_file():
        files = [str(path)]
    else:
        files = []
    files = [str(f) for f in files]
    if not files:
        return [], [], []

    slides: list[dict] = []
    notes: list[str] = []
    used: list[str] = []
    seen: set[str] = set()
    for f in files:
        if f in seen:
            continue
        seen.add(f)
        try:
            text = Path(f).read_text(encoding="utf-8", errors="ignore")
        except OSError as exc:
            notes.append(f"跳过（读不了）：{f} —— {exc}")
            continue
        text = re.sub(r"<!--[\s\S]*?-->", " ", text)   # 注释掉的一屏不算一屏
        marks = [m for m in SECTION_RE.finditer(text) if "slide" in parse_class(m.group(1) or "")]
        if not marks:
            notes.append(f"跳过（没有 <section class=\"slide\">）：{f}")
            continue
        used.append(f)
        for i, m in enumerate(marks):
            end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
            slides.append(extract_slide(text[m.end():end], m.group(1) or "", f))
    return slides, notes, used


# ---------------------------------------------------------------- 规则 H1–H10
def h1_issue(slide: dict) -> dict | None:
    title = slide["title"]
    if not title:
        return None
    if QUESTION_TITLE_RE.search(title):
        return {
            "sev": "P1", "rule": "H1", "name": "标题不是断言",
            "detail": f"标题「{title}」是问句/话题，不是一句能被反驳的话",
        }
    body = title.rstrip(" 　.。!！?？·|｜:：")
    if len(body) > SHORT_TITLE_MAX:
        return None
    suffix = next((w for w in TITLE_BLACKLIST if body.endswith(w)), None)
    if suffix is None:
        return None
    if JUDGE_RE.search(title):
        return None
    return {
        "sev": "P1", "rule": "H1", "name": "标题不是断言",
        "detail": f"标题「{title}」以名词「{suffix}」结尾且无判断词，是名词短语不是观点",
    }


def assertion_tokens(slide: dict) -> set[str]:
    return tokens(f"{slide['title']} {slide['claim']}", STOP_BIGRAMS_MIN)


def h2_flags(slide: dict) -> list[str]:
    """每个模块的认领状态：✔ 直接认领 / ~ 靠同页侧面 / ✗ 孤儿候选 / · 太短不判 / — 无断言可认。"""
    mods = slide["modules"]
    base = assertion_tokens(slide)
    if not base or not slide["claim"]:
        # 没有结论句就没有可认领的断言（封面/目录/说明型页面），判了必误报
        return ["—"] * len(mods)
    mod_tokens = [tokens(m["text"], STOP_BIGRAMS_MIN) for m in mods]
    flags: list[str] = []
    for idx, m in enumerate(mods):
        tok = mod_tokens[idx]
        if not tok:
            flags.append("—")
            continue
        if tok & base:
            flags.append("✔")
            continue
        others: set[str] = set()
        for j, other in enumerate(mod_tokens):
            if j != idx:
                others |= other
        if tok & others:            # 和同页别的模块有共同实词 → 是同一页的侧面，不是孤儿
            flags.append("~ 侧面")
        elif m["chars"] < H2_MIN_CHARS:
            flags.append("· 太短不判")
        else:
            flags.append("✗ 孤儿候选")
    return flags


def h2_issues(slide: dict) -> list[dict]:
    flags = h2_flags(slide)
    return [
        {
            "sev": "P2", "rule": "H2", "name": "孤儿模块候选",
            "detail": f"模块「{m['label']}」（{m['chars']} 字）与标题+结论句无共同实词，建议人工确认去留",
        }
        for m, flag in zip(slide["modules"], flags) if flag.startswith("✗")
    ]


def comparable(module: dict) -> bool:
    return module["chars"] >= MIN_DUP_CHARS


def h3_issues(slide: dict) -> list[dict]:
    mods = [m for m in slide["modules"] if comparable(m)]
    if len(mods) < 2:
        return []
    toks = [tokens(m["text"]) for m in mods]
    out = []
    for i in range(len(mods)):
        for j in range(i + 1, len(mods)):
            sim = dice(toks[i], toks[j])
            if sim >= SAME_PAGE_DUP:
                out.append({
                    "sev": "P0", "rule": "H3", "name": "同页模块重复",
                    "detail": f"「{mods[i]['label']}」与「{mods[j]['label']}」相似度 {sim:.2f}"
                              f"（≥{SAME_PAGE_DUP:.2f}）：说的是同一件事，合并或降级为一句",
                })
    return out


def is_landmark(slide: dict) -> bool:
    """封面 / 收尾页：不承载 L2，只做导览，不参与跨页重复与 H6/H7。"""
    return bool(slide["nofoot"] or not slide["title"])


def h4_pairs(slides: list[dict]) -> list[tuple[int, dict, int, dict, float]]:
    by_rail: dict[str, list[int]] = {}
    for idx, s in enumerate(slides):
        if s["rail"] and not is_landmark(s):
            by_rail.setdefault(s["rail"], []).append(idx)
    pairs = []
    for indices in by_rail.values():
        for a_pos in range(len(indices)):
            for b_pos in range(a_pos + 1, len(indices)):
                ia, ib = indices[a_pos], indices[b_pos]
                ma = [m for m in slides[ia]["modules"] if comparable(m)]
                mb = [m for m in slides[ib]["modules"] if comparable(m)]
                if not ma or not mb:
                    continue
                toks_a = [tokens(m["text"]) for m in ma]
                toks_b = [tokens(m["text"]) for m in mb]
                for i, ta in enumerate(toks_a):
                    for j, tb in enumerate(toks_b):
                        sim = dice(ta, tb)
                        if sim >= CROSS_PAGE_DUP:
                            pairs.append((ia, ma[i], ib, mb[j], sim))
    return pairs


def h5_issues(slide: dict) -> list[dict]:
    n = len(slide["modules"])
    if n < MANY_MODULES:
        return []
    return [{
        "sev": "P2", "rule": "H5", "name": "并列无主次",
        "detail": f"本屏 {n} 个模块（≥{MANY_MODULES}）：先确认主次，或说明这是不是分类并列"
                  f"（不同侧面要加分类标签，不要硬合并）",
    }]


def h6_issue(slide: dict) -> dict | None:
    title = slide["title"]
    if not title or not slide["has_body"]:
        return None
    mark = NUMERIC_TITLE_RE.search(YEAR_RE.sub(" ", title))   # 「2026 年」是时间范围，不是断言
    if not mark:
        return None
    if slide["has_img"] or slide["has_table"] or re.search(r"\d", slide["page_text"]):
        return None
    return {
        "sev": "P1", "rule": "H6", "name": "断言无证据",
        "detail": f"标题是数值型断言（含「{mark.group(1)}」），但页面既无数字也无图/表/记录",
    }


def claim_numbers(text: str) -> list[str]:
    text = QUOTED_RE.sub(" ", text)
    text = RATIO_RE.sub(" ", text)
    text = YEAR_RE.sub(" ", text)
    text = ORDINAL_RE.sub(" ", text)
    return [f"{m.group(1)} {m.group(2)}" for m in CLAIM_NUM_RE.finditer(text)]


def h7_issue(slide: dict) -> dict | None:
    if not slide["has_body"] or is_landmark(slide):
        return None
    nums = claim_numbers(slide["prose_text"])
    if len(nums) < 2:
        return None
    if not any(n.split()[-1] in OUTCOME_UNITS for n in nums):
        return None
    if CALIBER_RE.search(slide["page_text"]):
        return None
    counts: dict[str, int] = {}
    for num in nums:
        counts[num] = counts.get(num, 0) + 1
    shown = "、".join(f"{n}×{c}" if c > 1 else n for n, c in list(counts.items())[:4])
    if len(counts) > 4:
        shown += "…"
    return {
        "sev": "P1", "rule": "H7", "name": "数字无口径",
        "detail": f"页面有 {len(nums)} 处成果型数字（{shown}），但没有「口径/基准/同一套/相比/分母」"
                  f"——和谁比、分母是什么、什么时间窗",
    }


def h8_issues(slides: list[dict]) -> list[dict]:
    by_rail: dict[str, list[int]] = {}
    for idx, s in enumerate(slides):
        if s["rail"] and not is_landmark(s):
            by_rail.setdefault(s["rail"], []).append(idx)
    out = []
    for rail, indices in by_rail.items():
        if any("成果" in slides[i]["kicker"] or "结论" in slides[i]["kicker"] for i in indices):
            continue
        if any(NO_RESULT_RE.search(slides[i]["page_text"] + " " + slides[i]["claim"])
               for i in indices):
            continue    # 章节里已经明说“还没有结果 / 测试中”，按 SKILL 允许，不补口号
        last = indices[-1]
        out.append({
            "idx": last, "sev": "P2", "rule": "H8", "name": "章节缺结论页",
            "detail": f"章节「{rail}」共 {len(indices)} 屏，没有任何一页 kicker 含「成果/结论」"
                      f"——确实还没有结果就明说，不要用口号补",
        })
    return out


def h9_issues(slides: list[dict]) -> list[dict]:
    """承接断点候选：同一章节内，上一页收口的那句话与下一页标题是否接得上。

    这是 SKILL §2.5「页间接力」的机器部分。只查词面与转折词，判断不了论证是否真的成立；
    上一页写了 .bridge 过渡句的（作者已把接力写出来）不判，所以这条只给 P2 候选。
    """
    out: list[dict] = []
    by_rail: dict[str, list[int]] = {}
    for idx, s in enumerate(slides):
        if s["rail"] and not is_landmark(s):
            by_rail.setdefault(s["rail"], []).append(idx)
    for rail, indices in by_rail.items():
        for pos in range(len(indices) - 1):
            a = slides[indices[pos]]
            b = slides[indices[pos + 1]]
            if not b["title"] or a.get("bridge"):
                continue
            if not re.match(r"\s*\d+\s*/", b["kicker"] or ""):
                continue          # 封面 / Q&A 不承接业务页
            if indices[pos + 1] == len(slides) - 1 and len(slides) > 3:
                continue          # 全册最后一屏是收尾页，不需要承接（三屏以内的小样除外）
            tail = (a["claim"] or "").strip()
            if not tail and a["modules"]:
                tail = a["modules"][-1]["label"]
            if char_count(tail) < BRIDGE_MIN_CLAIM:
                continue
            prev_text = " ".join([a["title"], tail, a["modules"][-1]["text"] if a["modules"] else ""])
            first = b["modules"][0] if b["modules"] else None
            next_text = b["title"] + " " + (first["text"] if first else "")
            if tokens(prev_text) & tokens(next_text):
                continue
            if TURN_RE.search(b["title"]):
                continue
            out.append({
                "idx": indices[pos + 1], "sev": "P2", "rule": "H9", "name": "承接断点候选",
                "detail": f"上一页收在「{truncate(tail, 22)}」，本页标题「{b['title']}」"
                          f"既无共同实词、也没有转折词 —— 确认这页是否换了话题；若只是没写接力，"
                          f"在上一页加一句追问或在标题里加转折词",
            })
    return out


def h10_issue(slide: dict) -> dict | None:
    """细节过载：单页可见字数超过参考上限。"""
    if not slide["has_body"]:
        return None
    n = char_count(slide["page_text"])
    if n <= DENSE_CHARS:
        return None
    return {
        "sev": "P2", "rule": "H10", "name": "细节过载",
        "detail": f"本屏可见 {n} 字（参考上限 {DENSE_CHARS}）："
                  f"把不影响「相信」的解释下沉到讲稿，页上只留主证据与一句结论",
    }


def is_report_deck(slides: list[dict]) -> bool:
    """汇报/复盘型 deck：≥2 屏、且 ≥20% 的 kicker 含 问题/方案/成果/结论/实践/复盘。

    说明型 deck（使用说明、骨架库、原型库）里没有“问题→方案→成果”的章节叙事，
    模块是功能枚举、数字是操作参数，H7/H8 判了只会误报。
    """
    hits = sum(1 for s in slides if s["kicker"] and REPORT_KICKER_RE.search(s["kicker"]))
    return hits >= 2 and hits * 5 >= len(slides)


def analyze(slides: list[dict]) -> list[dict]:
    """返回逐屏 issue 列表：[{idx, sev, rule, name, detail}]"""
    out: list[dict] = []
    report = is_report_deck(slides)
    for idx, slide in enumerate(slides):
        for fn in (h1_issue, h6_issue, h10_issue):
            issue = fn(slide)
            if issue:
                out.append({"idx": idx, **issue})
        if report:
            issue = h7_issue(slide)
            if issue:
                out.append({"idx": idx, **issue})
        for fn in (h2_issues, h3_issues, h5_issues):
            for issue in fn(slide):
                out.append({"idx": idx, **issue})
    for ia, ma, ib, mb, sim in h4_pairs(slides):
        out.append({
            "idx": ib, "sev": "P1", "rule": "H4", "name": "跨页模块重复",
            "detail": f"「{ma['label']}」({Path(slides[ia]['file']).name}) 与 "
                      f"「{mb['label']}」({Path(slides[ib]['file']).name}) 相似度 {sim:.2f}"
                      f"（同章节「{slides[ib]['rail']}」，≥{CROSS_PAGE_DUP:.2f}）：同一观点讲了两遍",
        })
    if report:
        out.extend(h8_issues(slides))
    out.extend(h9_issues(slides))
    return out


# ---------------------------------------------------------------- 输出
SEV_ORDER = {"P0": 0, "P1": 1, "P2": 2}


def group_issues(issues: list[dict], slides: list[dict]) -> dict[int, list[dict]]:
    grouped: dict[int, list[dict]] = {}
    for issue in issues:
        grouped.setdefault(issue["idx"], []).append(issue)
    for idx in grouped:
        grouped[idx].sort(key=lambda it: (SEV_ORDER[it["sev"]], it["rule"]))
    return grouped


def print_skip_notes(notes: list[str]) -> None:
    for note in notes:
        print(f"提示：{note}", file=sys.stderr)


def cmd_outline(target: str) -> int:
    slides, notes, used = load_slides(target)
    print_skip_notes(notes)
    if not slides:
        print(f"没有找到幻灯片：{target}", file=sys.stderr)
        return 2
    print(f"# 观点层级 · {len(slides)} 屏 · {len(used)} 个文件")
    if notes:
        print(f"> 跳过 {len(notes)} 个文件（见 stderr）。")
    print()
    for slide in slides:
        chapter = f"[{slide['rail']}] " if slide["rail"] else ""
        print(f"## {chapter}{Path(slide['file']).name} · {slide['name']}")
        if slide["kicker"]:
            print(f"kicker：{slide['kicker']}")
        h1 = h1_issue(slide)
        if slide["title"]:
            verdict = h1["detail"] if h1 else "✔ 不是名词短语（未命中黑名单）"
            print(f"标题断言：{slide['title']}")
            print(f"断言判定：{verdict}")
        elif slide["has_body"]:
            print("标题断言：—（本屏没有 <h1 class=\"title\">，如标题用其他样式承载，需人工确认）")
        else:
            print("标题断言：—（封面 / Q&A / 收尾页，不判 H1）")
        mods = slide["modules"]
        if mods:
            print(f"模块（{len(mods)}）：")
            flags = h2_flags(slide)
            for i, m in enumerate(mods):
                print(f"  {i + 1} {m['label']} · {m['chars']} 字 · 认领 {flags[i]}")
            pairs = []
            for i in range(len(mods)):
                for j in range(i + 1, len(mods)):
                    if mods[i]["chars"] < MIN_DUP_CHARS or mods[j]["chars"] < MIN_DUP_CHARS:
                        continue
                    sim = dice(tokens(mods[i]["text"]), tokens(mods[j]["text"]))
                    pairs.append((sim, i, j))
            pairs.sort(reverse=True)
            hot = [p for p in pairs if p[0] >= 0.20]
            if hot:
                text = " · ".join(f"{i + 1}×{j + 1} {sim:.2f}" for sim, i, j in hot[:6])
                print(f"相似度（≥0.20 才显示）：{text}")
        else:
            print("模块（0）：—（列表 / 纯图 / 整段自绘版式，不计模块；需人工看）")
        if mods and not slide["claim"]:
            print("  （本屏没有结论句，H2 认领不判；模块只做清单）")
        print(f"结论句：{slide['claim']}" if slide["claim"] else "结论句：—（没有 .take/.insight）")
        print()
    return 0


def cmd_audit(target: str, as_json: bool) -> int:
    slides, notes, used = load_slides(target)
    print_skip_notes(notes)
    if not slides:
        print(f"没有找到幻灯片：{target}", file=sys.stderr)
        return 2
    issues = analyze(slides)
    grouped = group_issues(issues, slides)
    total = {"P0": 0, "P1": 0, "P2": 0}
    rule_count: dict[str, int] = {}
    for issue in issues:
        total[issue["sev"]] += 1
        rule_count[issue["rule"]] = rule_count.get(issue["rule"], 0) + 1

    if as_json:
        payload = {
            "total": total,
            "files": len(used),
            "slideCount": len(slides),
            "reportDeck": is_report_deck(slides),
            "skipped": notes,
            "slides": [
                {
                    "file": slides[idx]["file"],
                    "slide": slides[idx]["name"],
                    "rail": slides[idx]["rail"],
                    "title": slides[idx]["title"],
                    "modules": len(slides[idx]["modules"]),
                    "issues": [
                        {"sev": it["sev"], "rule": it["rule"],
                         "name": it["name"], "detail": it["detail"]}
                        for it in items
                    ],
                }
                for idx, items in grouped.items()
            ],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=1))
        return 1 if total["P0"] else 0

    print(f"# 观点层级审查 · {len(used)} 个文件 / {len(slides)} 屏\n")
    if not is_report_deck(slides):
        print("> 说明型 deck（含 问题/方案/成果/结论 语义的 kicker 不足 2 屏或不足 20%）："
              "H7/H8 跳过 —— 数字是操作参数、模块是功能枚举，不做断言判定。\n")
    if total["P0"] + total["P1"] + total["P2"] == 0:
        print("✅ 没发现规则级问题（仍需人工过一遍 SKILL §6 的 12 问）\n")
        return 0
    print(f"问题合计：P0 {total['P0']} · P1 {total['P1']} · P2 {total['P2']}\n")
    print("规则分布：" + " · ".join(f"{k} {v}" for k, v in sorted(rule_count.items())) + "\n")
    if total["P0"]:
        print("> P0 必须修：同页两个模块说的是同一件事。先合并，再谈主次。\n")
    if total["P0"] + total["P1"] == 0:
        print("> P2 只是候选（孤儿模块 / 并列无主次 / 章节缺结论页 / 承接断点 / 细节过载），逐条确认后按需处理。\n")
    for idx in sorted(grouped):
        slide = slides[idx]
        print(f"## {slide['name']}  ({Path(slide['file']).name})")
        if slide["rail"]:
            print(f"   章节 {slide['rail']} · {len(slide['modules'])} 个模块")
        for it in grouped[idx]:
            print(f"  [{it['sev']}] {it['rule']} {it['name']} — {it['detail']}")
        print()
    return 1 if total["P0"] else 0


def cmd_map(target: str) -> int:
    slides, notes, used = load_slides(target)
    print_skip_notes(notes)
    if not slides:
        print(f"没有找到幻灯片：{target}", file=sys.stderr)
        return 2

    issues = analyze(slides)
    grouped = group_issues(issues, slides)
    h4 = h4_pairs(slides)

    # 章节分组：保持全册顺序
    chapters: list[tuple[str, list[int]]] = []
    index_of: dict[str, int] = {}
    loose: list[int] = []
    for idx, s in enumerate(slides):
        if not s["rail"]:
            loose.append(idx)
            continue
        if s["rail"] not in index_of:
            index_of[s["rail"]] = len(chapters)
            chapters.append((s["rail"], []))
        chapters[index_of[s["rail"]]][1].append(idx)

    total_modules = sum(len(s["modules"]) for s in slides)
    orphan_count = sum(1 for it in issues if it["rule"] == "H2")
    dup_count = sum(1 for it in issues if it["rule"] == "H3")
    cross_dup = len(h4)
    report_gate = is_report_deck(slides)
    with_result = [rail for rail, idxs in chapters
                   if any("成果" in slides[i]["kicker"] or "结论" in slides[i]["kicker"]
                          for i in idxs)]
    no_result_declared = [rail for rail, idxs in chapters
                          if rail not in with_result
                          and any(NO_RESULT_RE.search(slides[i]["page_text"] + " " + slides[i]["claim"])
                                  for i in idxs)]
    missing_result = [rail for rail, _ in chapters
                      if rail not in with_result and rail not in no_result_declared]

    print(f"# 全册观点地图 · {len(slides)} 屏 · {len(chapters)} 个章节\n")
    print("L0 全册主张：—（工具不猜全册论点；需要一句能被反驳的话，写在目录页上）\n")

    for rail, idxs in chapters:
        print(f"## L1 章节：{rail} —— {len(idxs)} 屏")
        for idx in idxs:
            s = slides[idx]
            orphans = [it for it in grouped.get(idx, []) if it["rule"] == "H2"]
            dups = [it for it in grouped.get(idx, []) if it["rule"] == "H3"]
            mark = "  ← 承担结论" if ("成果" in s["kicker"] or "结论" in s["kicker"]) else ""
            print(f"  L2 第 {idx + 1} 页 [{s['name']}] 断言：{s['title'] or s['name']}")
            print(f"     {('kicker：' + s['kicker'] + ' · ') if s['kicker'] else ''}"
                  f"模块 {len(s['modules'])} · 孤儿 {len(orphans)} · 同页重复 {len(dups)}{mark}")
            for m in s["modules"]:
                tags = []
                if any(m["label"] in it["detail"] for it in orphans):
                    tags.append("孤儿候选")
                if any(m["label"] in it["detail"] for it in dups):
                    tags.append("疑似重复")
                print(f"       L3 · {m['label']}（{m['chars']} 字）"
                      f"{' → ' + ' / '.join(tags) if tags else ''}")
        print()

    if h4:
        print("## 跨页重复对（同章节，相似度 ≥0.55）")
        for ia, ma, ib, mb, sim in sorted(h4, key=lambda p: -p[4]):
            print(f"  · {slides[ia]['name']}「{ma['label']}」 × {slides[ib]['name']}「{mb['label']}」"
                  f" —— {sim:.2f}（章节 {slides[ia]['rail']}）")
        print()

    if loose:
        print("## 未分章的屏（封面 / 目录 / Q&A / 收尾，不参与章节判断）")
        for idx in loose:
            print(f"  · 第 {idx + 1} 页 [{slides[idx]['name']}] 模块 {len(slides[idx]['modules'])}")
        print()

    print("## 三问")
    if chapters:
        print(f"  1 观点数（章节）{len(chapters)} vs 屏数 {len(slides)} —— "
              f"平均 {len(slides) / len(chapters):.1f} 屏一个观点")
    else:
        print("  1 本册没有 data-rail 分章 —— 先给每屏标章节，才能算观点数")
    if total_modules:
        share = (orphan_count + dup_count) / total_modules * 100
        print(f"  2 孤儿 {orphan_count} + 同页重复 {dup_count} = {orphan_count + dup_count}，"
              f"占模块总数 {total_modules} 的 {share:.1f}%（目标 <15%；跨页重复对另计 {cross_dup} 对）")
    else:
        print("  2 孤儿 0 + 同页重复 0 —— 本册没有可识别的模块容器，需人工看")
    if report_gate:
        line = f"  3 有结论页的章节：{len(with_result)}/{len(chapters)}"
        if no_result_declared:
            line += f"；{'、'.join(no_result_declared)} 明说暂无结果（按 SKILL 允许，不补口号）"
        if missing_result:
            line += f"；缺结论页：{'、'.join(missing_result)}（确实还没有结果就明说，别补口号）"
        print(line)
    else:
        print("  3 说明型 deck（kicker 无 问题/方案/成果/结论 语义）：H8 不判，章节是否要结论页由人定")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        prog="hierarchy.py",
        description="观点层级审查：一页一个断言，每个模块认领一句，重复与孤儿先找出来。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("────────────────────────────", 1)[-1] if "────" in __doc__ else None,
    )
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, help_text in (
        ("outline", "每页断言判定 + 模块清单（标签/字数/是否认领标题）+ 相似度"),
        ("audit", "H1–H10，P0/P1/P2；有 P0 时退出码 1"),
        ("map", "全册观点地图：章节 → 页 → 模块数/孤儿/重复，跨页重复对"),
    ):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("target", help="glob（src-x/slides/*.html）或目录")
        if name == "audit":
            p.add_argument("--json", action="store_true", help="机器可读输出（total + slides）")
    args = ap.parse_args()

    if args.cmd == "outline":
        return cmd_outline(args.target)
    if args.cmd == "audit":
        return cmd_audit(args.target, args.json)
    if args.cmd == "map":
        return cmd_map(args.target)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
