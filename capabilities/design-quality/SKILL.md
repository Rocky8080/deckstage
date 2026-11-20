---
name: design-quality
description: 幻灯片/页面视觉质量审查与修正——对比度、强调色面积、低对比水印、层级、留白、网格和收尾页。用户说"看不清/太淡/太花/颜色不搭/大色块/排版空/每页不饱满/Q&A 看不出来"，或要设计/改一份 deck 时加载。
whenToUse: 写或改幻灯片、封面、Q&A、收尾页、图表页；用户反馈"不好看、不清晰、太空、太满、颜色太像、色块太重、重点不突出"；或需要在交付前做视觉质量检查。
---

# 设计质量门禁

> 一句话：**强调色是标点，不是背景；层级靠字号和留白，不靠色块。**

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

详细规则与豁免方式见 `docs/DESIGN.md`。

## 2. 四条不可破的规则

1. **对比度**：信息文字 4.5:1，大字 3:1；不做低对比 Q&A/章节号水印。
2. **强调色面积**：单块高饱和色 ≤8%；大色块必须有 `data-design-allow` 和理由。
3. **一个焦点**：一页只让一个元素当主角；其它元素降字号、降对比、缩面积。
4. **留白是设计**：收尾页可以空，但要有明确锚点；不要用卡片/色块硬填。

## 3. 常用修法

- 浅色大字 → 深色实体字；不要用 opacity 淡出。
- 大色块 → 收成文字/细线/小标签。
- 金色小字 → 深金 `#7A5A1E`；金色只做线。
- 整页空 → 放大主图/主数字；整页挤 → 删解释，留结论+证据+锚点。
- 收尾页 → 一个大字 + 一条细线 + 一行说明；不要铺满。

## 4. 参考

WCAG 2.1 · Dieter Rams · Massimo Vignelli · 瑞士国际主义排版 · 60-30-10 配色法。

## 5. 交付前

```bash
node build.mjs --deck <slug>
python3 tools/check_slides.py --index decks/<slug>/index.html
python3 tools/design_audit.py --index decks/<slug>/index.html
```
