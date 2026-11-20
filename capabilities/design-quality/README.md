# design-quality

视觉质量门禁能力包：对比度、强调色面积、低对比水印、层级与留白。

- 规则：`docs/DESIGN.md`
- 版式骨架：`LAYOUTS.md` + `archetypes/`（12 个可抄页面，画廊 `decks/archetypes/`）
- 检查：`python3 tools/design_audit.py --index decks/<slug>/index.html`
- 骨架多样性：`python3 tools/layout_audit.py --index decks/<slug>/index.html`
- 工作区约定：`AGENTS.md` 第 5 节
