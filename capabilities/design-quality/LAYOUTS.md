# 版式骨架库（LAYOUTS）

> 一句话：**视觉语言只有一套，页面骨架要有十二套。**
> 骨架解决「每页都长一样」，不解决「这页说了什么」——后者归写作门禁。

## 0. 为什么需要这一层

同一份 Word、同一句指令，生成出来的页面丰富度可能差一倍。差别通常不在配色或字体（它们由 `src/css/tokens.css` 固定），而在**模型能看到多少种「页面骨架」可以模仿**：

- 仓库自带的 `src-sample`：12 屏，约 5 种大结构；
- 作者本机的手写 deck：90 屏，约 30 种大结构，且 40–57% 的样式是每屏私有 CSS；
- 新用户 clone 后只能看到前者，于是默认收敛到「标题 + 三张卡 + 一列列表」。

这一层把「页面骨架」从隐性经验变成可复用资产：**12 个可直接抄的 HTML 骨架**（`archetypes/`），加选型规则与反单调检查。

### 外部参考（只取方法，不取模板皮肤）

- **断言—证据结构**：标题写完整断言，正文放证据。[presentation archetypes](https://github.com/Aperivue/medsci-skills/blob/main/skills/present-paper/references/presentation_archetypes.md) 总结了 Alley & Neeley 的实验支持，本库的 03/05/08 都按这个结构写。
- **极简版式六条**：不堆装饰、一个主色一个强调色、一页最多 3–4 个信息点、大留白、按内容类型选版式、数据页只放一个大数字。[完全原创 PPT 设计原则](https://github.com/GordenSun/GordenPPTSkill/blob/main/references/original-design-guide.md)
- **没有取用的**：主题色包、图标库、装饰边框、卡片套卡片、渐变与阴影堆叠。视觉语言已经由 tokens 统一，再引入皮肤只会破坏一致性。

## 1. 三层，不要混

| 层 | 载体 | 谁管 | 变更频率 |
|---|---|---|---|
| 视觉语言 | `src/css/tokens.css`、`base.css`、`docs/AUTHORING.md` | 全仓库一套 | 很低 |
| **页面骨架** | 本文件 + `archetypes/` + `base.css` 的 `.ax-*` | 12 个，可扩展 | 中 |
| 内容结论 | `tools/frame.py`、`capabilities/causal-value-chain/` | 每一屏 | 高 |

换骨架不等于换风格：12 个骨架全部使用同一套米色纸面、墨绿主色、赭石强调、衬线标题。

## 2. 十二个骨架（v1）

每个文件顶部都有注释：`骨架编号 · 名称｜适用｜容量`；`<section data-arch="...">` 供机器识别。页面里的数字与文案是**演示用占位**，必须全部替换。

| # | 骨架 | 文件 | 用在什么内容 | 容量上限 | 别这样用 |
|---|---|---|---|---|---|
| 01 | 封面 | [archetypes/01-cover.html](archetypes/01-cover.html) | 开篇、汇报、复盘 | 主标题 ≤ 2 行，标签 ≤ 3 | 封面堆三张卡、放目录 |
| 02 | 目录 | [archetypes/02-toc.html](archetypes/02-toc.html) | 4–6 个部分的总览 | 4–6 行 | 每行写小作文、加图标 |
| 03 | 单观点 | [archetypes/03-point.html](archetypes/03-point.html) | 一个必须被记住的断言 | 一句话 ≤ 40 字 | 变成两条并列观点 |
| 04 | 三并列 | [archetypes/04-trio.html](archetypes/04-trio.html) | 3 个动作 / 特征 / 原则 | 每列 ≤ 2 行，只强调 1 列 | 4 列硬塞、三列都强调 |
| 05 | 对照矩阵 | [archetypes/05-matrix.html](archetypes/05-matrix.html) | A/B 方案、前后对比 | 判据 ≤ 4 行，两列同口径 | 做成长表格、没有结论行 |
| 06 | 过程链 | [archetypes/06-chain.html](archetypes/06-chain.html) | 3–5 个连续环节 | 节点 ≤ 4，每节点 ≤ 2 行 | 分叉流程、并行支路 |
| 07 | 阶梯 | [archetypes/07-ladder.html](archetypes/07-ladder.html) | 成熟度、能力分级、递进 | 4–6 级 | 跳级、每级写一段 |
| 08 | 数据看板 | [archetypes/08-board.html](archetypes/08-board.html) | 3 个核心指标 + 口径 | 数字 ≤ 3，每个带口径与基准 | 堆 6 个数字、没有脚注 |
| 09 | 分层架构 | [archetypes/09-arch.html](archetypes/09-arch.html) | 系统分层、规则落点 | 3–4 层，每层 ≤ 4 个组件 | 画成流程图、层内再嵌套 |
| 10 | 闭环 | [archetypes/10-loop.html](archetypes/10-loop.html) | 复盘循环、运营节奏 | 3–4 步，回路线 1 句 | 画环形箭头、步骤超过 5 |
| 11 | 反例 / 正例 | [archetypes/11-contrast.html](archetypes/11-contrast.html) | 错误示范、prompt 前后对照 | 每侧 ≤ 4 行，结论 1 句 | 只放反例、两侧字号不同 |
| 12 | 收尾 | [archetypes/12-closing.html](archetypes/12-closing.html) | 一句话结论 + 下一步 | 一句话 ≤ 24 字，元信息 ≤ 3 条 | 写「谢谢聆听」、铺满色块 |

## 3. 选型：内容信号 → 骨架

先看这一屏**要让观众做什么**，再选骨架；不要先挑一个好看的。

| 内容里出现 | 用 |
|---|---|
| 「A 和 B」「之前 / 之后」「两种做法」 | 05 对照矩阵 |
| 「第一步…然后…最后」「流程 / 流水线 / 环节」 | 06 过程链 |
| 「初级 / 中级 / 高级」「成熟度 / 递进 / 分级」 | 07 阶梯 |
| 「三个指标」「降了多少」「数字 + 口径」 | 08 数据看板 |
| 「输入 / 处理 / 输出」「分层 / 规则放在哪」 | 09 分层架构 |
| 「循环 / 每轮 / 复盘 / 飞轮 / 反馈」 | 10 闭环 |
| 「常见错误 / 错误示范 / 这样写不对」 | 11 反例正例 |
| 「一句话结论 / 反直觉的判断」 | 03 单观点 |
| 「三条原则 / 三个动作 / 三个特征」 | 04 三并列 |
| 「五个部分 / 本期目录」 | 02 目录 |
| 都没有 | 先回 03 或 04，不要硬套第十二个 |

**先列清单，再动笔。** 一套 10–12 屏的 deck，先写出这样的 10–12 行（骨架名 + 这屏要证明什么），确认相邻不重复、种数够，再开始填内容：

```
01 cover
02 toc
03 point     省下的是返工，不是打字时间
04 trio      三个动作里只有一个起作用
05 matrix    人工重写 vs 辅助校对
06 chain     一次改稿的四个环节
07 ladder    四级能力
08 board     三组数字与口径
09 arch      规则集中在中间层
10 loop      每轮只改一个变量
11 contrast  同一段要求的两种写法
12 closing   把改稿从重写变成校对
```

## 4. 反单调硬指标（建议级，先别挂构建）

- 骨架种数：≥ 6 种 / 套（≥ 10 屏）；≤ 6 屏的短 deck ≥ 4 种（检查时传 `--min 4`）。
- 相邻两屏不得同骨架。
- 同一骨架全 deck 最多出现 3 次。
- 每 5 屏至少有 1 屏不是「卡片 + 网格」结构（用 03/05/06/07/09/10/11 之一）。
- 纯列表页不超过全 deck 的 1/5。
- 机器检查：

```bash
python3 tools/layout_audit.py --src src-<名字>/slides
python3 tools/layout_audit.py --index decks/<slug>/index.html
python3 tools/layout_audit.py --index decks/<slug>/index.html --strict   # 违规时退出 1
```

默认只提示、退出码 0；要进 CI 或构建门禁时加 `--strict`。**不要为了凑种数把内容拆碎**——指标是下限，不是目的。

### 4.1 内容少时怎么填满（不靠加卡片）

一屏正文可用高度约 **602px**（1600×900、单行标题）。内容组（主模块 + 结论 + 过渡句）应占版心 **70–85%**，
上下留白接近。按优先级：

1. **放大已有主元素**：大数字、条宽、阶梯高度、行高、行列间距——先放大，不要先加内容。
2. **模块内部上下对齐**：标签/序号在顶，结论或「产出」在底（`.ax-*` 用 `margin-top:auto` + 细线实现），中间留白成为结构。
3. **内容组整体垂直居中**：`.slide[data-arch] .body` 默认居中；如果底部还空 200px 以上，说明主模块不够大，而不是页边距没调匀。

不要：加无意义卡片、图标、色块来“填满”；把字号缩到 12px 以下凑密度；把结论句重复两遍。

## 5. 工作流：第一次生成就丰富

1. 读本文件，打开 `decks/archetypes/`（构建后）或 `src-archetypes/slides/`（源码）看 12 屏长什么样。
2. 按第 3 节列「内容 → 骨架」清单，先过第 4 节的反单调指标。
3. 复制骨架文件，替换**全部**文案；示例数字带「示例数据」标记的必须换掉。
4. 每屏只留一个焦点；超容量就拆屏，不要缩字号硬塞。
5. 跑四道检查：`node build.mjs`（写作 P0）、`check_slides.py`、`design_audit.py`（16:9 + 4:3）、`layout_audit.py`。
6. 人工复核：遮住标题，这页还能看出结论吗？不能就回到写作门禁，而不是换个骨架。

## 6. 默认动效（骨架已内置，不要另写 JS）

12 个骨架默认带三类动效，复制骨架即继承：

| 动效 | 写法 | 用在哪 |
|---|---|---|
| 区块入场 | `.reveal` + `style="--d:120ms"` | 标题、行、卡片、结论、过渡句 |
| 数字滚动 | `<span data-count="1.4" data-dec="1">1.4</span>`，单位放在 span 外 | 数据看板大数字 |
| 条形生长 | `.ax-ladder__bar.grow-x` + `style="--d:160ms"` | 阶梯 / 条形图 |

时序：标题 40ms → 主模块 60–380ms（阶梯 60–120ms）→ 结论 420–540ms → 过渡句 ≤ 560ms。
同一屏最后一拍不超过 900ms；数字滚动固定 1.15s，从 0 到目标值。

- 静态导出（`?export=1`）会自动把 `.reveal`、`.grow-x` 和计数器落到终态，截图/PPTX 不会拍到中间值。
- `prefers-reduced-motion` 会关闭 CSS 入场动画。
- 不要：手写 JS 动画、用 GIF、所有元素同时出现、同一屏混用超过 2 种入场方向。
- 计数器会替换 `data-count` 元素的全部文本，所以数字和单位要拆成两个子元素。

## 7. 预览与构建

```bash
# 骨架库本身（12 屏画廊）
node build.mjs --src src-archetypes --deck archetypes
python3 tools/serve_deck.py          # → http://127.0.0.1:8899/ 里的「版式原型库」

# 单跑检查
python3 tools/check_slides.py --index decks/archetypes/index.html
python3 tools/design_audit.py --index decks/archetypes/index.html
python3 tools/design_audit.py --index decks/archetypes/index.html --ratio 4:3
python3 tools/layout_audit.py --index decks/archetypes/index.html
```

- 正式源文件在 `capabilities/design-quality/archetypes/`；`src-archetypes/slides/` 是指向它们的符号链接，供 `build.mjs` 一屏一个文件地拼装。
- 安装后技能目录会复制 `archetypes/`，离开仓库也能照着写。
- `.ax-*` 样式在 `src/css/base.css` 末尾，4:3 有少量字号补偿；不要在每个骨架文件里另写一套。

## 8. 与写作门禁的关系

- 骨架只解决版式，不产生结论。构建仍会跑 `tools/frame.py audit`，P0（无基准倍数 / 表格无结论 / 量纲未统一）**照样阻断**。
- 一屏一个焦点；结论句、口径脚注、图注锚点仍按 `capabilities/causal-value-chain/` 的要求写。
- 没有结论的骨架只是排版；没有骨架的结论容易长得一样。两者是乘法，不是替代。

## 9. 扩展规则（加第 13 个骨架之前）

1. 结构签名必须与现有 12 个都不同：给新骨架一个唯一的 `data-arch` 值。
2. 在文件头写清「适用 / 容量 / 别这样用」，并补进第 2 节表。
3. 优先用 `base.css` 里的 `.ax-*` 引擎类；确需单屏 CSS 时，必须说明为什么不能共用。
4. 同时放进 `archetypes/` 与 `src-archetypes/slides/`（后者是符号链接），并跑四道检查。
5. 至少在 3 套真实 deck 里实际用过一次，确认容量上限没写错，再算稳定。
6. 在 `?dtheme=paper-white` 与 `?dtheme=ink-dark` 下各看一遍：条形、圆点、芯片这类图形要单独检查对比度，
   不能只检查文字；玄墨主题的 `.ax-*` 补偿写在 `base.css` 末尾，新骨架要自己补。

## 10. 已知边界

- 12 个是**下限**。真正的丰富来自组合（如 matrix + board 两屏一组）和内容本身，不是骨架数量。
- 同一骨架不同填法，质量差异很大；骨架不能替代审片。
- 极简不是空：留白要有锚点（大标题、大数字、一条细线），否则就是没做完。
- 示例文案仅用于演示结构与语气，交付前务必替换；示例数字已标注「示例数据」。
