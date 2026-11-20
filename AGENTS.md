# AGENTS.md — 本仓库的写作与审查纪律

任何 agent（Codex / ZCode / DSH / Claude Code 等）在本仓库里**写或改内容**时，必须遵守下面这套纪律。
它对应一个可执行的能力包：`capabilities/causal-value-chain/`（DSH 技能名 `causal-value-chain`）。

## 1. 触发条件

出现以下任一情况，先跑一次审查，再动笔：

- 写/改任一屏幻灯片、汇报、复盘、方案（`src/slides/*.html`、`decks/*/deck.json` 的文案）
- 用户说"这屏怎么表达""没有说服力""太空""改成结论"
- 内容里出现对比表、倍数、人月、收益、效率一类的数字

```bash
python3 tools/frame.py audit "src/slides/*.html"          # 规则级问题（P0 必须修）
python3 tools/frame.py framework                          # 方法骨架，可拼进 prompt
python3 tools/frame.py lint "<要写的句子>"                 # 单句检查，有问题是退出码 1
```

## 2. 硬性规则

1. **数字三件套**：口径 · 基准 · 结论，缺一条不算写完。
2. **一把尺子**：人月 = 人数 × 月数；人月 ÷ 12 = 年；倍数必须写口径（人月/日历/费用）。
3. **表格必须有"所以"**：没有结论句的对照表不允许进正式页；能换成一个倍数或一条曲线就换。
4. **反事实**：出现倍数就要有"不这么做会怎样"（换算成年 / 倍 / 元）。
5. **结论可反驳**：不许"我觉得 / 应该是 / 大幅 / 显著 / 效率翻倍"（引号内被否定的说法除外）。
6. **图文因果链**：图注写"证明了什么"+"看这里"的锚点（具体数字/位置/颜色），不是"这是什么"。
7. **不编数字**：缺数据写 `【需补：<具体是哪个数>】`。

## 3. 交付格式（改完一屏）

```
结论：<一句能被反驳的话>
因果链：现状（成本）→ 机制（可复述的动作）→ 结果（同一把尺子）→ 反事实（相当于 X 年）
价值链：投入 X 人月 → 转化（能力）→ 产出（可交付物）→ 价值（省下的时间/可复用性）
口径与基准：<分子分母、和谁比、什么场景（模拟/实盘）>
图与锚点：<哪张图、看哪里、证明什么>
```

## 4. 改完必须验证

```bash
node build.mjs --src src-sample --deck sample-deck     # 或对应 deck
python3 tools/check_slides.py                # 版面：0 问题
python3 tools/design_audit.py --index decks/<slug>/index.html   # 视觉：0 问题
python3 tools/layout_audit.py --index decks/<slug>/index.html    # 版式：骨架不单调
python3 tools/frame.py audit "src/slides/*.html"   # 表达：P0 = 0
```

## 5. 设计质量门禁

任何封面、内容页、Q&A/收尾页、图表页改完，必须过视觉质量门禁。

```bash
python3 tools/design_audit.py --index decks/<slug>/index.html
python3 tools/design_audit.py --index decks/<slug>/index.html --ratio 4:3
```

硬性规则：

1. 信息文字对比度 ≥4.5:1；大字（≥24px 或 ≥18.66px 粗体）≥3:1。
2. 大字号低对比水印不算合格；Q&A、章节号、关键数字必须是实体字。
3. 单块高饱和强调色面积 ≤8%；>12% 视为问题；有意为之必须加 `data-design-allow` 并写理由。
4. 一页一个焦点；强调色是标点，不是背景板；层级优先用字号、字重、留白、细线。
5. 收尾页可以留白，但要有明确视觉锚点；不要用大色块硬填。
6. 页面骨架要换：一套 ≥10 屏至少 6 种骨架，相邻两屏不同骨架，同一骨架最多 3 次；
   先用 `capabilities/design-quality/LAYOUTS.md` 选型，再填内容，不要连续三屏「标题 + 卡片」。
7. 字号下限：解释性正文 18–20px；过渡句 / 脚注 / 口径 14.5–17.5px；标签 11.5–13.5px。
   13.5px 以下只做标签；不要用缩小正文字号来塞内容。

详细规则、修法和参考见 `docs/DESIGN.md`，能力包见 `capabilities/design-quality/SKILL.md`。

### 改完必须验证（补充视觉）

```bash
python3 tools/design_audit.py --index decks/<slug>/index.html --ratio 4:3
python3 tools/layout_audit.py --index decks/<slug>/index.html
```

## 6. PPTX 导出

页面导出的可编辑 PPTX，**不要同时使用 `slide.bkgd` 和 `slide.background`**；pptxgenjs 3.x 会让 `bkgd` 覆盖背景色，导致所有页变白、纸色/深色页失真。

导出后先检查：

```bash
python3 tools/check_pptx_bg.py 导出.pptx --expect F8F4EC
python3 tools/export_audit.py --index decks/<slug>/index.html
```

`export_audit.py` 是端到端门禁：无头导出一份真实 PPTX，逐页比对 DOM 背景、`<p:bg>` 和页数，任何不一致退出 1。

含 inline SVG 的页面（弧线、环形图、线稿）额外检查：不能出现黑色实心楔形、透明 SVG 周围的白底框。`docs/PPTX.md` 记录了 `fill:none` 与 `data:image/svg+xml` 两个已知陷阱。多行标题/结语还要检查导出后标题行数是否正确、末行是否压住下一块文字。

详见 `docs/PPTX.md`。
