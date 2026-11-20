---
name: design-quality
description: 幻灯片/页面视觉质量与版式骨架——对比度、强调色面积、低对比水印、层级、留白、网格、收尾页，以及 12 个可复用页面骨架的选择与多样性检查。用户说"看不清/太淡/太花/颜色不搭/大色块/排版空/每页不饱满/每页长得都一样/Q&A 看不出来"，或要设计/改一份 deck 时加载。
whenToUse: 写或改幻灯片、封面、Q&A、收尾页、图表页；用户反馈"不好看、不清晰、太空、太满、颜色太像、色块太重、重点不突出、每页一个样"；或需要先选页面骨架、做交付前视觉检查时。
---

# 设计质量门禁

> 一句话：**强调色是标点，不是背景；层级靠字号和留白，不靠色块。**

## 0. 先选骨架，再改颜色

一页怎么写之前，先定它属于哪种页面。完整清单、选型信号和反单调指标见 [LAYOUTS.md](LAYOUTS.md)；
12 个可抄的骨架在 `archetypes/`（画廊：`decks/archetypes/`）。

- 一套 ≥10 屏的 deck 至少 6 种骨架，相邻两屏不同骨架，同一骨架最多 3 次。
- 先列「内容 → 骨架」清单，再动笔；不要从「标题 + 三张卡」开始套。
- 骨架只解决版式；结论、证据、口径仍归 `tools/frame.py` 和写作能力包。
- 骨架默认带动效（`.reveal` / `data-count` / `.grow-x`）；不要另写 JS 动画。
- 字号下限：解释性正文 18–20px，标签 11.5–13.5px；13.5px 以下不做解释性文字。

```bash
node build.mjs --src src-archetypes --deck archetypes   # 先看 12 个骨架长什么样
python3 tools/layout_audit.py --src src-<名字>/slides   # 量骨架覆盖与重复
```

## 1. 先跑检查

```bash
python3 tools/design_audit.py --index decks/<slug>/index.html
python3 tools/design_audit.py --index decks/<slug>/index.html --ratio 4:3
```

它会逐屏检查：

- 正常文字对比度 ≥4.5:1；
- 大字对比度 ≥3:1；
- 大字号低对比水印；
- 单块高饱和强调色面积（>8% 警告，>12% 问题）。

骨架多样性与重复用 `python3 tools/layout_audit.py --index decks/<slug>/index.html` 检查。

详细规则与豁免方式见 `docs/DESIGN.md`。

## 2. 五条不可破的规则

1. **对比度**：信息文字 4.5:1，大字 3:1；不做低对比 Q&A/章节号水印。
2. **强调色面积**：单块高饱和色 ≤8%；大色块必须有 `data-design-allow` 和理由。
3. **一个焦点**：一页只让一个元素当主角；其它元素降字号、降对比、缩面积。
4. **留白是设计**：收尾页可以空，但要有明确锚点；不要用卡片/色块硬填。
5. **骨架要换**：相邻两屏不重复；连续三屏「标题 + 卡片」就是视觉上的复读。

## 3. 常用修法

- 浅色大字 → 深色实体字；不要用 opacity 淡出。
- 大色块 → 收成文字/细线/小标签。
- 金色小字 → 深金 `#7A5A1E`；金色只做线。
- 整页空 → 放大主图/主数字；内容少时让模块撑满版心（标签顶、结论底、上下留白接近），不要加卡填满。
- 整页挤 → 删解释，留结论+证据+锚点。
- 收尾页 → 一个大字 + 一条细线 + 一行说明；不要铺满。

## 4. 参考

WCAG 2.1 · Dieter Rams · Massimo Vignelli · 瑞士国际主义排版 · 60-30-10 配色法。

## 5. 交付前

```bash
node build.mjs --deck <slug>
python3 tools/check_slides.py --index decks/<slug>/index.html
python3 tools/design_audit.py --index decks/<slug>/index.html
python3 tools/layout_audit.py --index decks/<slug>/index.html
```
