# 设计质量门禁（DESIGN）

交付幻灯片前，分别检查版面、表达和视觉质量。

- `check_slides.py` 检查溢出、截断、重叠、图片加载和控制台报错。
- `frame.py` 检查口径、基准、结论和图文因果链。
- `design_audit.py` 检查文字对比度、强调色块面积和低对比水印。
- `theme_contrast.py` 逐套检查预设主题（`C` 键切换）下的文字对比度。
- `layout_audit.py` 检查页面骨架种数、相邻重复与单骨架复用（建议级，`--strict` 可阻断）。

## 1. 先跑命令

在仓库根目录构建示例，并启动展示台。视觉检查需要 Playwright 和 Chrome。

```bash
node build.mjs --src src-sample --deck sample-deck
python3 tools/serve_deck.py
```

服务运行在 `127.0.0.1:8899`。在另一个终端运行以下命令，检查两种画幅。

```bash
python3 tools/design_audit.py --index decks/sample-deck/index.html
python3 tools/design_audit.py --index decks/sample-deck/index.html --ratio 4:3
python3 tools/theme_contrast.py --index decks/sample-deck/index.html --warn-only
```

- `contrast-low` 表示普通文字对比度低于 4.5:1。
- `contrast-low-large` 表示大字对比度低于 3:1。
- `contrast-watermark` 提示低对比的大字号装饰字，例如浅色 Q&A 或章节号水印。
- `accent-block` 标记占该页至少 8% 的高饱和色块。超过 12% 记为 P1。

有发现时命令返回非零。可加 `--only s01,s02` 检查指定页，或用 `--warn-only` 查看报告并继续。带背景图的文字需在实际画面中检查对比度。

`theme_contrast.py` 会逐屏、逐文字节点把六套预设主题注入页面再计算对比度；默认配色仍由 `design_audit.py` 检查。加 `--theme navy` 只看一套，`--json` 输出机器可读结果，`--warn-only` 只报告不阻断。

## 2. 硬规则

### 2.1 对比度

- 正常文字：**≥ 4.5:1**
- 大字（≥24px，或 ≥18.66px 且粗体）：**≥ 3:1**
- 承载信息的大字**不能**用低对比水印；Q&A、章节号、关键数字尤其不能。
- 纯装饰元素可以用低对比，但必须满足“去掉它信息不丢失”，并且不要做成页面的唯一焦点。

### 2.2 强调色面积

- 纸色/背景 60%、墨色 30%、强调色 10%。
- 单块高饱和强调色面积 **≥ 8% 警告，> 12% 记为 P1**。
- 大色块不是不能用，但要有明确理由，并在元素上标注 `data-design-allow`；内容页优先用文字、细线、留白建立层级，而不是铺一整块品牌色。
- 例如，在 1600 × 900 的画布上，430 × 500 的高饱和面板约占整页 15%，超过 P1 阈值。可将强调色收进标题和细线，再用检查器确认面积。

### 2.3 一个焦点

一页只允许一个视觉焦点。焦点可以是：

- 一张关键图；
- 一个数字；
- 一个大标题/大字；
- 一条流程图。

其它元素要退后：更小的字号、更低的对比、更细的线。不要“标题大、图大、色块也大”。

### 2.4 层级与留白

- 用**字号阶梯**（如 96 / 48 / 28 / 18 / 13）和**字重**建立层级；
- 用**留白**分组，不要把每个区域都填满；
- 收尾页（Q&A/谢谢）可以留白，但必须有一个明确的视觉锚点；不要把“空”误当成“留白”。
- 内容少时**放大已有模块**（大数字、条宽、行高、行列间距），或让模块内部上下对齐（标签顶、结论底），
  内容组占到版心 70–85%、上下留白接近；不要用新卡片/图标/色块去填满。

### 2.5 网格与对齐

- 左右两栏、页边距、基线要对齐；
- 一张页最多一套主网格；细线统一 1px；
- 图、标题、正文共享同一条左边线或同一中心线。

### 2.6 版式骨架

- 一套 ≥10 屏的 deck 至少 **6 种骨架**，相邻两屏不同骨架，同一骨架最多 3 次。
- 不要连续三屏「标题 + 三张卡」；每隔几屏换一次结构（对照 / 过程链 / 阶梯 / 数据 / 闭环）。
- 选型信号与 17 个可抄骨架见 `capabilities/design-quality/LAYOUTS.md`；检查用 `layout_audit.py`。

### 2.7 颜色纪律

- 品牌色只做“标点”，不做“背景板”；
- 不在低对比纸底上叠同明度的淡色大字；
- 重要文字用实体色，不用 `opacity` 把字“淡出”；
- 颜色数量控制在 3 个主色以内（纸、墨、一个强调色），金色只做线/小标签。

## 3. 怎么修

| 症状 | 优先修法 |
|---|---|
| 浅色大字看不清 | 改深色实体字，或换到深底浅字；不要继续加 opacity |
| 强调色块太大 | 把色块收成文字/细线/小标签；或加 `data-design-allow` 并写理由 |
| 整页空 | 先放大主图/主数字，再考虑加一条结论；不要靠加卡片填满 |
| 整页挤 | 删掉解释性文字，保留“结论 + 证据 + 锚点” |
| 金色小字太淡 | 文字用深金（如 `#7A5A1E`），金色只留给线和小面积装饰 |
| 装饰字与内容抢焦点 | 降低装饰字对比/缩小，或删掉；让内容成为唯一焦点 |

## 4. 允许豁免

在**有意为之且不影响信息**的元素上加：

```html
<div class="cover-decoration" data-design-allow="封面装饰">…</div>
```

规则：

1. 豁免只用于装饰，不用于承载信息；
2. 豁免元素不能是页面唯一的信息来源；
3. 一页最多一个豁免块；
4. 在提交说明里写一句为什么。

## 5. 参考

- WCAG 2.1：正文 4.5:1，大字号 3:1
- Dieter Rams：Less but better
- Massimo Vignelli：编辑设计与网格
- 瑞士国际主义排版：字号阶梯、对齐、留白
- 60-30-10 配色法：背景/文字/强调色的面积比

## 6. 每次改完

```bash
node build.mjs --src src-sample --deck sample-deck
python3 tools/check_slides.py --index decks/sample-deck/index.html
python3 tools/check_slides.py --index decks/sample-deck/index.html --ratio 4:3
python3 tools/design_audit.py --index decks/sample-deck/index.html
python3 tools/design_audit.py --index decks/sample-deck/index.html --ratio 4:3
python3 tools/layout_audit.py --index decks/sample-deck/index.html
python3 tools/frame.py audit "src-sample/slides/*.html"
```

检查自己的 deck 时，将 `src-sample` 和 `sample-deck` 换成实际源码目录和 slug。
