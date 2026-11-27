# 制作规范（AUTHORING）— 写每一屏之前必须读

## 0. 一句话

这是一份 **1600×900 的学术编辑风个人汇报**：米色纸面、墨绿主色、赭石强调、衬线中文大标题。
不是"通用企业模板"，不要用大色块渐变、玻璃拟态、圆角胶囊按钮堆砌。留白要大，信息要稠密但有秩序。

## 1. 文件形态

```html
<section class="slide" id="s07" data-title="导航里显示的短标题" data-rail="物">
  <header class="head">
    <p class="kicker">02 / 物 · 01 REPLICATE</p>
    <h1 class="title">先完整复刻一个 <em>闭环</em></h1>
  </header>
  <div class="body">
    ……
  </div>
  <p class="bridge">闭环能跑之后，下一个问题：<strong>我能不能不只复刻，而是自己造？</strong></p>
</section>
<style>
  /* 只写 #s07 前缀的选择器 */
</style>
```

- 一个文件 = 一屏。**不要写 `<html>`/`<body>`/`<script>`**。
- `data-rail` 只能是 `量` / `物` / `法`。
- 页脚（`.foot`）由 `deck.js` 自动注入，**不要自己写页脚**。
- 只有一屏需要写 `<aside class="notes">这里写演讲者备注（2-4 句，口语化）</aside>`，放在 `section` 内部末尾。

## 2. 版心与高度预算（非常重要）

- 画布 1600×900，内容左右边距 96px → **内容宽 1408px**。
- `.slide` 是 flex 纵向：`head`（自动高） → `body`（flex:1） → `bridge`（自动） → `foot`（自动，约 42px）。
- **body 的可用高度约 595–605px**（单行大标题时）。两行标题再少 60px。
- 超出 `body` 会被裁切 → 写完必须用 `tools/check_slides.py` 自查（见第 8 节）。
- 图片统一用 `.shot` 包裹，给固定宽高（px），`object-fit: cover` 默认；需要完整显示界面时用 `.shot--contain`。

## 3. 排版层级

| 用途 | 类 | 说明 |
|---|---|---|
| 眉标 | `.kicker` | 英文/数字小字，自动带前导短线 |
| 主标题 | `.title` / `.title--xl` / `.title--light` | 衬线；`<em>` 会加墨绿高亮底色 |
| 副标题 | `.subtitle` | 衬线，38px |
| 导语 | `.lead` | 23px，无衬线 |
| 正文 | `.txt` / `.txt--sm` / `.txt--mut` | |
| 小标题 | `.h3`（26px，600） | 卡片内标题 |
| 微标签 | `.label` | 全大写等宽小字 |
| 强调 | `.hl`（墨绿）/ `.hl--terra`（赭石）/ `.hl--gold` | 行内加粗变色 |
| 洞察句 | `.insight` | 左侧 3px 竖线 + 衬线 27px；`.insight--terra` 换色 |
| 过渡句 | `.bridge` | 每屏都必须有，最后一屏除外；`<strong>` 会墨绿加粗 |
| 脚注 | `.note` | 12.5px 灰 |
| 数字 | `.stat` + `.stat__num` + `.stat__label` | 等宽数字；`.stat__num--xl` 118px |
| 标签 | `.tag` / `.tag--terra` / `.tag--gold` / `.tag--line` / `.tag--dark` | 胶囊小标 |
| 列表 | `.list` > `.list__item` > `.list__dot` + `.list__txt` | |
| 卡片 | `.card` / `.card--flat` / `.card--tint` / `.card--wash` / `.card--terra` / `.card--dark` / `.card--no-pad` | |
| 实拍图 | `.shot` > `img`，可加 `.shot__cap` 角标说明 | |

栅格：`.grid` + `.g2 .g3 .g4 .g5-7 .g7-5 .g1-2 .g2-1`，间距 26px；`.row` + `.grow` 做横向分栏。
等宽分隔指标行：`.metrics` > `.metric`（竖线自动分隔）。

字号下限（2026-11 修订）：**解释性正文 18–20px**；辅助说明（过渡句、脚注、口径）14.5–17.5px；标签 11.5–13.5px。13.5px 以下只允许序号 / 单位 / 轴标签 / 徽标，不承载解释。

## 4. 动效规则

- 元素想入场就加 `.reveal`，用内联 `style="--d:180ms"` 控制延迟。**同一屏延迟阶梯 90–120ms，从 60ms 起，不超过 900ms**。
- 变体：`.reveal--fade`（只淡入）、`.reveal--left` / `--right`（横向滑入）、`.reveal--scale`、`.reveal--blur`（大标题用，慢一点 1.05s）。
- 容器内子项逐个入场：父级加 `.stagger`，子项各自写 `--d`。
- SVG 描边绘制：给 `<path>` 加 `pathLength="1"` 和 class `draw` + `style="--d:300ms"`。
- 数字滚动：`<span class="stat__num num" data-count="466.4" data-dec="1">0</span>`（会自动从 0 滚到目标值）。
- 逐步揭示（讲演时按空格一条条出）：给元素加 `.frag`。——同一屏最多 4 个 `.frag`。
- 版式原型库默认已带三类动效：标题/区块 `.reveal`、数字 `data-count`、条形 `.grow-x`；复制骨架即继承。
  数字滚动的单位要放在 `data-count` 的 `<span>` **外面**，否则会被计数替换掉。
- 不要写 JS 动画、不要用 GIF。
- 尊重 `prefers-reduced-motion`（base.css 已处理，只要用上面的类即可）。

## 5. 视觉纪律

- **小字只用于标签，不用于解释**（2026-11 修订）：屏面 13px 以下只允许放「单位 / 序号 / 轴标签 / 徽标」这类标签；口径、推导、来源、旁白一律写进 `<aside class="notes">` 由讲者口述。判断标准：这行字删掉，观众是否还看得懂核心结论？看得懂就删。
- **数值的涨跌必须红涨绿跌**（A 股口径）：涨/正收益用 `var(--up)`（#C0392B），跌/负收益用 `var(--down-2)`（#1E5B47）；类别色、品牌绿不参与涨跌语义。
- 颜色只用变量：`--paper / --ink / --green / --terra / --gold / --line / --dark`，**不要写除变量外的十六进制**（除非是 SVG 里需要 `currentColor` 反而更好）。
- 圆角只用 8 / 14 / 20 三档。阴影用 `--sh-card` / `--sh-shot`。
- 一屏最多一个"视觉主角"（大图 / 大数字 / 大图）。其余是支撑。
- 深色屏（`.slide--dark`）最多连续出现一屏，用作节奏变化。
- 图标一律用内联 SVG（1.4–1.6px stroke，`currentColor`），**禁止 emoji、禁止用字符当图标**。
- 中文标点用全角，句中不要连续感叹号；数字与中文之间不强行加空格（保持原文案）。

## 6. 图片素材

见 `assets/MANIFEST.md`。约定命名：
- `assets/img/trae.jpg` Trae 用量看板（深色）
- `assets/img/codex.jpg` Codex 看板（浅色）
- `assets/img/glm.jpg` GLM 看板（浅色，宽扁）
- `assets/img/quant-arch.jpg` 量化闭环架构图（深色）
- `assets/img/github-jq.jpg` GitHub 仓库
- `assets/img/jq-site.jpg` jq 策略工作台
- `assets/img/kelly-site.jpg` kelly 选股工作台
- `assets/img/books-site.jpg` books 阅读平台
- `assets/img/startup24.jpg` 24 步法 PPT 首页
- `assets/img/rsi-site.jpg` RSI / PaperResearch
- `assets/covers/book1-life.jpg` 一生之间 · `book2-math.jpg` 数学发展图谱 · `book3-harness.jpg` Harness Engineering · `book4-startup24.jpg` AI 创业 24 步法
- `assets/shots/arxiv-abs.png` arXiv 实拍

图片必须给 `alt`。file:// 直接打开也能显示（同目录相对路径）。

### 图片与首屏性能

- **压缩版放 `assets/web/<deck>/<名字>.jpg`**：`build.mjs` 在拼 deck 时会优先用它（没有才回落到原图），
  不需要改任何 deck 源码。按 **2× 显示宽度 + q82** 压即可；扁平色截图（表格、UI 截屏）先比一下 PNG / JPEG 哪个更小。
- **从第 2 屏起的图片会自动懒加载**：构建期把 `<img src>` 换成 1×1 占位 + `data-src`，翻到该屏才补 `src`；
  首屏（第 1 屏）保持直连。因此图片请放在 `object-fit: cover` 的定尺寸容器（如 `.shot`）里，避免占位期布局跳动。
- PPTX 导出会自动补全懒加载的图片（导出取图优先读 `data-src`），不需要额外处理。
- 细节与实测见 [PERFORMANCE.md](PERFORMANCE.md)。

## 7. 文案纪律

- `docs/SLIDE_SPEC.md` 里的文案**逐字使用**，不要改写、不要加自己的判断句、不要删减。
- 允许做的是：分段、加 `<em>`/`.hl`/`<strong>` 强调、拆成卡片/列表/图表。
- 如果发现某句实在放不下，**压缩排版而不是删文案**；确实必须改字，先告诉我（lead）。

## 8. 自检（每个屏文件写完都要跑）

```bash
cd <仓库根目录>
node build.mjs                     # 拼装 index.html
python3 tools/check_slides.py      # 检查溢出/重叠/图片加载，输出问题清单
python3 tools/check_slides.py --shots   # 同时截图到 /tmp/qa/，可以 read_image 看一眼
```

检查器会列出：超出画布的元素、body 溢出、图片 404、控制台报错。**必须清零再交付。**

## 9. 版式骨架库（推荐首次使用先看）

仓库自带 **17 个页面骨架**，源文件在 `capabilities/design-quality/archetypes/`，画廊 deck 用下面的命令构建：

```bash
node build.mjs --src src-archetypes --deck archetypes
python3 tools/layout_audit.py --index decks/archetypes/index.html
```

- 选型信号、容量上限、反单调指标：`capabilities/design-quality/LAYOUTS.md`
- 引擎样式：`src/css/base.css` 末尾的 `.ax-*`；骨架页用 `<section ... data-arch="cover|toc|...">` 标记
- 硬指标：一套 ≥10 屏至少 6 种骨架，相邻两屏不同骨架，同一骨架最多 3 次
- 骨架里的文案和数字是演示占位，必须替换；骨架只管版式，结论 / 口径仍走写作门禁


## 写作门禁（自动生效）

`node build.mjs` / `node build.mjs --deck <slug>` 在构建前会调用
`tools/frame.py audit`：

- **P0**（无基准倍数 / 表格无结论 / 量纲未统一）→ 构建失败，不会产出 index.html
- **P1/P2** → 只打印提示
- 应急跳过：`--no-frame`（不推荐）

新写一屏请从 `capabilities/causal-value-chain/slide-template.html` 复制，骨架已带
「口径 · 基准 · 结论」注释、结论位 `.insight`、图注"看这里"三件套。

写作方法和作者模板见 [因果链 / 价值链能力包](../capabilities/causal-value-chain/README.md)。
出片前的对比度与强调色面积检查见 [设计质量检查](DESIGN.md)，可编辑导出的验证步骤见 [PPTX 导出](PPTX.md)。

## 结构门禁（自动生效）

写作门禁之后，构建还会调用 `tools/hierarchy.py audit`：

- **P0**（同页两个模块说的是同一件事）→ 构建失败
- **P1/P2** → 只计数提示，不阻断；明细运行 `python3 tools/hierarchy.py audit "src/slides/*.html"` 查看
- 应急跳过：`--no-hierarchy`（不推荐）

一页一断言、模块认领、页间接力等规则见 [观点层级能力包](../capabilities/point-hierarchy/README.md)。
