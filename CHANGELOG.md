# 更新日志 / Changelog

格式参照 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循
[语义化版本](https://semver.org/lang/zh-CN/)。deck 引擎与工具链整体作为版本单元，
deck 内容（`decks/<slug>/`）不在版本范围内。

## [1.8.1] - 2026-11-28

### 新增

- **「补充说明进备注」固化为系统能力**（口径、基准、折算、估算细节、题外解释一律进当页备注
  `aside.notes`，放映页只留主证据；唯一例外是一句话级的 `.source` 槽位）：
  - `frame.py` 新增「口径上屏」（P1）：页面正文出现口径/折算/基准类补充说明即提示移入备注
    （`.source` 一句话级豁免、insight/takeaway/bridge 结论槽位排除）；
    新增「备注倍数无基准」（P2）：备注是讲稿，口述倍数同样要带基准词。
  - `frame.py` 扫描范围修正：aside.notes 是讲稿不是页面——先剥离再查页面级规则，
    备注内倍数单独降为 P2（此前备注文本会参与页面级 P0 判定）。
  - `design_audit.py` 新增 `fine-print-overload` 提示（**warn 级，不计入退出码**）：
    小字号（<15.5px）长段落（≥50 字）且含口径/折算/基准类信号词 → 建议移入备注；`.source` 豁免。
  - 能力包同步：causal-value-chain 新增「补充说明进备注」纪律（SKILL + 用户级 AGENTS 规则块），
    point-hierarchy H10 修法明确「下沉到当页备注」，design-quality 补充说明不上屏，
    工作区 AGENTS.md 硬性规则第 8 条。
- 规则口径与 hierarchy 对齐：封面/收尾页（data-nofoot）不参与「缺结论」；
  「反事实」标签计入反事实信号；空 alt 图（头像 / 图标）不要求指认锚点。

### 修复

- sample-deck s09 桥接句压到页脚（text-overlap ×3，v1.8.0 看板重排时引入；
  此前 check_slides 只跑过根实例，未覆盖 sample）——收正文间距与看板字号。
- sample-deck s09 的 `.source` 超一句话，被新规则拦下后按纪律收敛为一行，细节下沉备注；
  ai-learning-report s06 口径脚注同样下沉备注。

### 验证

- frame：sample P0 0 · P1 7（说明型页「缺结论」，既有建议项）；ai-learning-report P0 0 · P1 0 · P2 1。
- design_audit 双 deck 0 问题 0 提示（16:9）；theme_contrast 六主题 0；check_slides 双 deck 0；
  layout_audit self-test 5/5。

## [1.8.0] - 2026-11-28

### 新增

- **施工图流程（`plan.json` + `tools/plan.py`）**：先定全册主张（L0）、每页断言、骨架与模块认领，再写页面。
  `<src>/plan.json` 存在时构建自动校验（P0 阻断：文件集不一致 / 骨架不在注册表 / 断言缺失 / 模块缺「主」），
  并按施工图给缺 `data-arch` 的页面注入骨架；没有施工图的旧 deck 不受影响。`--no-plan` 可应急跳过。
  示例 deck 已带施工图（`src-sample/plan.json`）。
- **5 个图示型骨架（12 → 17）**：基准柱状图（`bars`，焦点柱 + 虚线基准线）、因果链桥（`bridge`，
  现状 → 机制 → 结果 → 反事实四格）、2×2 象限（`quadrant`）、时间轴（`timeline`）、痛点 → 对策（`versus`）。
  全部 DIV/CSS 实现（无 SVG，导出 PPTX 不栅格化），模板在 `capabilities/design-quality/archetypes/`，
  画廊 deck 同步扩到 17 屏。
- **口径槽位 `.source`**：带数字的页在结论区前写口径行（分子分母 / 时间窗 / 基准）；
  `frame.py` 口径规则与 hierarchy H7 优先认这里的「口径」字样。
- **token 角色别名**：`--accent-text`（文字用强调色）、`--chart-focal` / `--chart-neutral`（图表焦点 / 退后）、
  `--on-accent`（强调色实心块上的文字），指向既有主题变量、随主题整套翻转。

### 修复

- **版式反单调规则补实现**（`layout_audit.py`）：LAYOUTS.md 写了两条但脚本从未检查——
  新增结构族统计（`grid3+card` 与 `grid4+list+card` 归并成同一「卡片 + 网格」族，族超过 3 屏报
  `family_repeat`）、连续 ≥5 屏卡片墙（`card_grid_run`）、纯列表页超 1/5（`pure_list_ratio`）；
  自测扩到 5 组。
- **对比度门禁闭环**：`design_audit.py` 不再跳过 12px 以下文字（新增 `font-too-small`，字号下限 11.5px），
  并把 `pre` / `code` 纳入检查（此前代码块完全不受检）；纸色回退值与 token 对齐（`#F7F3EA`）。
  由此暴露并修复：默认 `--ink-3/--ink-4` 加深一档（着色卡底上也 ≥4.5:1）、六套预设主题的 `--ink-4`
  逐主题校准（此前 41 处不达标）、深色页低透明度文字（.34–.5 → .6）、示例 deck 内 4 处 11px 文字与
  深色卡 `kv__k` 颜色。`theme_contrast.py` 对两套 deck 全主题 0 问题。
- **引擎残留清理**：导出 PPTX 的 `company` 不再写死「AI learning report」（改读 `data-brand`）；
  页脚 / 标题兜底改用 `DeckStage`；总览标题「全部 N 屏」由运行时写入实际屏数（此前写死 6）。
- 文档口径统一：预设主题「七套 / 六套」统一为「默认 + 六套预设」；骨架数量 12 → 17 全量更新。

### 变更

- 示例 deck 按施工图重排：10/12 屏使用骨架库（cover / chain ×2 / arch / toc / contrast / board / closing），
  07 / 11 保留卡片网格并如实计入结构族统计；`layout_audit` 骨架 10 种 / 结构族 10 种 / 相邻重复 0。
- `archetypes` 画廊 deck 重新上架（此前后台下架）。

### 平台

- **Windows 支持**（macOS 行为不变——所有解析都是「原值优先，找不到才走新分支」）：
  - 新增 `tools/_platform.py`：Python 解释器探测（`python3` → `python` → `py -3`）、LibreOffice 定位
    （环境变量 `SOFFICE` → PATH → 各平台默认路径）、Playwright 启动 Chrome → Edge → 自带 chromium 回退、
    stdout 强制 UTF-8（GBK 管道下 Python 打印 emoji 会 `UnicodeEncodeError`）。
  - `build.mjs` 四处子进程改用探测到的解释器：Windows 上此前会因找不到 `python3` 而**静默跳过全部门禁**
    （frame / hierarchy / plan fail-open + 缩略图不生成），现在门禁在 Windows 同样生效。
  - PPTX 导出字体映射按导出端平台分支：Windows → `Segoe UI / Consolas`（此前 mac 专属字体名在
    Windows PowerPoint 里全部缺失，会任意替代导致版式漂移）。
  - `install.ps1` Windows 安装器；`frame` 全局命令在 Windows 装为 `%USERPROFILE%\.local\bin\frame.bat`
    （符号链接在 Windows 需要开发者模式，改为复制 + 包装器）。
  - 导入管线跨平台：LibreOffice 路径 / 预修度量字体 / 用户字体目录 / 依赖自愈的解释器候选逐项平台化；
    `preview_pptx.py` 的替身字体候选表补 Windows 系统字体（msyh / simsun / consola / arial）。

### 验证

- 两套 deck：`design_audit` 16:9 / 4:3 全 0、`theme_contrast` 六主题全 0、`frame` / `hierarchy` / `plan` P0 全 0、
  `export_audit` 12/12 页背景一致、`check_slides` 根实例 33 屏 0 问题、`layout_audit --self-test` 5/5。

## [1.7.1] - 2026-11-27

### 性能

- **deck 首屏不再内联 PPTX 导出包**（`vendor/pptxgen.bundle.js`，468 KB）：改由 `src/js/pptx-export.js` 的
  `ensurePptxGenJS()` 在第一次点「导出 PPTX」时按需注入 `/vendor/pptxgen.bundle.js`（边缘缓存已命中，第二次起 0 请求）。
  单套 deck 的 HTML 763 KB → 297 KB（线上 brotli 244 KB → 83 KB）。
  实测（4× CPU + Slow 4G）：DCL 4756 → 822 ms、LCP 5324 → 1380 ms、load 8540 → 3434 ms。
- 根构建（`node build.mjs`）把两个导出脚本改成 `defer`，不再阻塞首屏。
- 新增回归护栏：deck 构建若检测到导出包又被内联进首屏，直接失败。

### 资源

- 部门 deck 的 6 张截图生成 2× 显示尺寸的 Web 压缩版（`assets/web/xlab-ai-practice/`，构建自动优先使用）：
  图片总量 1460 KB → 543 KB，最慢一张 8.1 s → 3.5 s；线上首屏传输 1461 KB → 544 KB。
- 线上实测（同一台机器、同一条隧道）：FCP 2352 → 1620 ms、LCP 8108 → 3936 ms、DCL 7558 → 3346 ms。

### 上线

- 8 套 deck 全部重建、`library.html` 重新生成。
  `xlab-2026-10` 原本卡在写作门禁 P0（讲稿里「1 年内估值增长 15 倍」缺口径），本次补成
  「口径：2022-06 种子轮投后 → 2023-06 preA 轮投后，12 个月」后重建通过，636 KB → 188 KB。
- 线上验收：8 套 deck 均 200（`archetypes` 为后台下架状态，404 属预期）、可翻页 / 总览 / 备注；
  导出按钮触发按需拉取导出包；两套 deck 的端到端导出各 16 / 33 页，媒体文件齐全。

### 按屏懒加载图片（复用引擎已有机制，不另写一套）

- 引擎本来就支持按屏懒加载：`deck.js` 的 `hydrateImages(from, to)` 只加载当前屏 ±2 屏，导出时补满全册，
  但此前**只对 `<img data-src>` 生效**（PPTX 导入的 deck 是这个写法），普通 `<img src>` 的 deck 仍然首屏全量拉图；
  而 `.slide { position:absolute; inset:0 }` 把 16 屏叠在同一位置，`loading="lazy"` 无效（实测 11 张图仍在同一时刻发起）。
- 本次只在构建期把首屏之外的普通 `<img src>` 换成 1×1 占位 + `data-src`（`build.mjs`，只换 src，
  alt / class / style 保留；`--inline` 单文件版不启用），即可直接复用引擎原机制。
- 配套：PPTX 导出取图增加 `data-src` 兜底（`pptx-export.js`）；`check_slides.py` / `make_pptx.py`
  在测量前调用 `window.__deckHydrate(0, 999)`，QA 截图与测量不受懒加载影响。
- 效果：首屏图片请求 11 张 / 544 KB → **0 张**；翻到有图的屏才拉 ~143 KB（≈0.5 s，此前首屏抢带宽要 4.7 s）。
  线上三次取样：FCP 1060–1632 ms、LCP 2424–2996 ms、DCL 1870–2439 ms、首屏传输 **1 KB**。

## [1.7.0] - 2026-11-25

### 新增

- **观点层级能力包** `capabilities/point-hierarchy/`：审查「这页到底在说什么、每块内容凭什么留在这儿」——
  一页一断言、模块认领制、同页 / 跨页重复合并、并列分类与主次、章节结论页；含 `SKILL.md`
  （方法 + H1–H10 规则 + 自检 12 问）、用户级 / 工作区规则块与审查提示词。
- **`tools/hierarchy.py`**：`outline` / `audit` / `map` 三个子命令——每页断言与模块清单、
  H1–H10 问题（P0/P1/P2，`--json` 机器可读）与全册观点地图。
- **页间接力与展示程度两条规则**：`H9 承接断点`（同一章节内，上一页结论句与下一页标题既无共同实词、
  标题也无转折词 → P2）与 `H10 细节过载`（单页可见字数 > 520 → P2）。`tools/hierarchy.py` 已实现并校准：
  H9 对写了 `.bridge` 过渡句的页面豁免、收尾页不判；H10 阈值取自两套校准 deck 校准时的单页可见字数（平均 273 / 352 字）。
  `SKILL.md` 对应两节：**§2.5 页间接力**（承接 / 转折 / 过渡句三种合法接法，以及「把一章标题连读」的断链判定）
  与 **§2.6 展示程度**（论据 ≤3 块、每块 1 句解释 + 1 证据、可见字数 ≤520、实现细节下沉讲稿）。
- **构建门禁**：`node build.mjs` 在表达检查之外跑同一套结构检查，P0 直接失败，P1/P2 只计数提示；
  应急跳过：`--no-hierarchy`（不推荐）。

### 改进

- `tools/install_capability.py` 增加第三套能力：观点层级技能与用户级「观点层级纪律」随
  `./install.sh` 一起装进本机已检测到的客户端；工作区约定现在会并入写作与结构两个规则块。
  `--check` 按能力分别列出技能与规则块状态，并校验 `build.mjs` 同时含表达门禁与结构门禁，文案改为三套能力。
- 仓库根 `AGENTS.md` 新增「观点层级」一节（触发条件 + 硬性规则 + 工具命令），原设计质量、
  PPTX 导出两节顺延为第 6、7 节；「改完必须验证」补 `hierarchy.py audit`。
- 用户级与工作区规则块补三条：「接得住上一页」「一页别放太多」「写之前先填两行」。
- `install.sh` 说明改为写作、结构与设计三套能力，完成提示补结构检查命令。

### 修复

- 根构建（不带 `--deck`）现在与 `--deck` 构建一样并入 `<src>/deck.css`（deck 级样式）；
  此前根构建会漏掉它，写在 deck 级样式里的类（如 `.take` / `.bridge`）在根 `index.html` 上不生效。

### 文档

- 新增 `capabilities/point-hierarchy/README.md`、两份 `README-AGENTS-*.md` 与 `prompts/audit-deck.md`；
  README 补能力表一行、工具清单与「结构能力包」小节；`docs/AUTHORING.md` 补「结构门禁」一节。

### 说明

- H9 / H10 的触发来源是一次真实事故：新加的一页只讲「系统怎么运转」，没有回答「为什么上一页那个答案不够」，
  且把实现细节塞满整页。原规则（重复 / 孤儿 / 名词标题）在这两个维度上都是盲区——
  **只查「多说了什么」，不查「少说了哪一步」**。

## [1.6.0] - 2026-11-21

### 新增

- **技能装进本机所有 AI 客户端**：`install_capability.py` 现在把「因果链 / 价值链」与
  「设计质量」两套技能装进本机已检测到的客户端 —— DSH（`~/.dsh/skills`）、Codex
  （`~/.codex/skills`）、ZCode（`~/.zcode/skills`）、WorkBuddy（`~/.workbuddy/skills`）、
  Claude Code（`~/.claude/skills`），并把用户级写作规则并入各自的 `AGENTS.md` / `CLAUDE.md`。
  `--agents` 指定客户端（`all` / `auto` / `dsh,codex,zcode,workbuddy,claude`），
  `--list-agents` 查看检测结果；WorkBuddy 支持官方 `WORKBUDDY_DIR` 数据目录。
- 每个装好的技能目录写入 `.deckstage.json`（来源 / 内容摘要 / 时间）：`--check` 按客户端
  列出缺什么、哪个是旧版本；`--uninstall` 只删本系统装的技能与规则块，不动用户自己同名的技能。

### 改进

- `install.sh` 一步装全：依赖 → 技能与规则（所有已检测客户端）→ 按客户端自检；以后装了
  新客户端重跑一次即补装。
- `README-AGENTS-user.md` 用户级约定标题改为客户端中立（不再写「所有 DSH 会话自动加载」）；
  README 与两个能力包文档补充「装哪些客户端 / 怎么生效 / 怎么撤销」。

## [1.5.1] - 2026-11-21

### 新增

- `tools/theme_contrast.py`：逐套预设配色（素白 / 藏青 / 暖赭 / 紫藤 / 青瓷 / 玄墨）按
  WCAG 阈值检查每屏文字对比度，支持 `--theme`、`--json`、`--warn-only`；默认配色仍由
  `design_audit.py` 检查。

### 改进

- 校准多套预设主题的 `--ink-4` / `--gold` / `--terra` / `--green-2` 等色值，改善 11–15px
  小字与强调标签在部分主题下的对比度；现有 deck 的残留问题可用新工具逐主题定位。
- `extract_notes.py` 跳过纯样式片段（如 `src/slides/99-readability.html`），只按含
  `<section>` 的页面统计屏数与讲稿字数。

### 文档

- README 与 `docs/DESIGN.md` 补充预设主题对比度检查的命令与适用范围。

## [1.5.0] - 2026-11-21

### 新增

- **管理后台「首页排序」**：在 `/admin/` 拖动卡片或点 ↑↓ 调整展示台顺序，调整后首页与
  `/decks.json` 立即生效，不需要重新 build；「恢复默认顺序」回到各 deck `deck.json` 的
  `order` / 标题排序。顺序保存在 `data/library.json`（0600，gitignore），不改 `deck.json`；
  新导入的 deck 默认落在末尾，下架内容保留位置，重新上架后回到原处。
- **展示台首页列数切换**：右上角新增「2 列 / 3 列 / 4 列」按钮，默认 2 列；选择记在
  `localStorage`，刷新后保留。窄窗口自动降级（4→3→2 列），手机单列并隐藏按钮；4 列时
  卡片标题与内边距同步收紧。调整列数不需要重新构建。
- 新增 `POST /api/admin/library/order`（`{slugs:[...]}` / `{reset:true}`）；后台内容管理
  同步显示每套 deck 的首页位置。
- 新增 `tools/test_admin_order.py`、`tools/test_admin_ui.py`、`tools/test_library_columns.py`
  自测（临时站点，不碰本机 `data/`；UI 自测覆盖 ↑↓、拖动、恢复默认与 2/3/4 列切换）。

### 修复

- 后台「恢复默认顺序」后，即使静态 `library.html` 还是上次按自定义顺序构建的，首页也会
  立即回到默认顺序（服务端始终按当前顺序重算，而不是只在有手工顺序时重排）。
- `/decks.json` 改为 `no-cache`，避免浏览器缓存住旧的顺序或下架状态。

### 文档

- `docs/ADMIN.md` 补充首页排序的规则、API 与数据文件；README 同步能力清单与自测命令。

## [1.4.1] - 2026-11-20

### 修复

- 提升骨架主体说明字号：过程链 / 闭环 / 数据看板 / 分层架构 / 反例正例的说明统一到 18px，过渡句 17.5px，口径脚注 15px；避免在 1440 宽窗口下正文只剩 14px 左右。
- 阶梯标签 17→18px、架构说明 15→18px、反例说明 15→18px；看板口径脚注 12.5→15px。
- 同步更新 `AUTHORING.md` / `DECK_SPEC.md` / `LAYOUTS.md` / `AGENTS.md`：解释性正文 18–20px，辅助说明 14.5–17.5px，13.5px 以下只做标签。
- 重新构建 12 屏画廊、示例 deck 与封面拼图。

## [1.4.0] - 2026-11-20

### 新增

- **版式骨架库**：`capabilities/design-quality/archetypes/` 提供 12 个可直接抄的页面骨架（封面 / 目录 / 单观点 / 三并列 / 对照矩阵 / 过程链 / 阶梯 / 数据看板 / 分层架构 / 闭环 / 反例正例 / 收尾），每个都带适用信号、容量上限和反例；选型规则与反单调指标见 `capabilities/design-quality/LAYOUTS.md`。
- **12 屏骨架画廊**：新增 `src-archetypes/` 与 `src/css/base.css` 的 `.ax-*` 引擎样式；`node build.mjs --src src-archetypes --deck archetypes` 可预览。
- **默认动效**：骨架默认带区块 `.reveal` 阶梯入场、数据看板数字从 0 滚动、阶梯条从左生长；静态导出自动落终态，时序与限制见 `LAYOUTS.md` 第 6 节。
- **`tools/layout_audit.py`**：按页面骨架签名统计骨架种数、相邻重复与单骨架复用；默认建议级，`--strict` 可在 CI 中阻断。
- **「素白」主题与七套配色**：新增纯白纸面 + 墨绿主色 + 赭石强调的素白方案；七套预设统一加约 3–8% 的多色环境光（绿 / 赭 / 蓝 / 青），第一眼仍是单一底色；地址加 `?dtheme=paper-white` / `?dtheme=ink-dark` 可直接打开指定配色。
- **安装链路**：`install.sh` 同时安装写作与设计两个 DSH 技能；`install_capability.py --check` 校验 `design-quality` 的 `SKILL.md` 与 `LAYOUTS.md`。

### 改进

- `AGENTS.md`、`docs/AUTHORING.md`、README 增加「先选骨架、再填内容」的生成流程：一套 ≥10 屏至少 6 种骨架，相邻两屏不同骨架，同一骨架最多 3 次。
- `LAYOUTS.md` 补充内容少时撑满版心的做法、默认动效约定，以及新增骨架必须在 `paper-white` / `ink-dark` 两套主题下检查图形对比度。
- 示例 deck 的主题页改为七套 + 自定义卡；`05-overview`、主题说明与截图口径同步为七套；重新构建示例 deck，带上新增引擎样式。
- `docs/DECK_SPEC.md` 补充 `?dtheme=` 约定、素白配色表与玄墨环境光说明。

### 修复

- 玄墨主题的阶梯条、矩阵圆点、架构芯片和小标签对比度不足；条形改为填充 + 完整描边，条形填充对纸面约 2.5:1、左缘亮边约 9.9:1。
- 玄墨底色从 `#14171B` 抬到 `#1B211F`，外壳抬到 `#121917`，避免“死黑”。
- 青瓷主色从 `#3E8577` 加深到 `#35766A`，12px 标签对比度从 3.95:1 提升到 4.83:1。

## [1.3.0] - 2026-11-20

### 新增

- 管理后台可为展示台首页或单套 deck 复制链接、生成二维码并下载竖版分享卡片。链接使用当前站点，可在生成卡片前编辑。详见 [管理后台](docs/ADMIN.md)。
- 展示台首页可独立设访问密码，单套 deck 继续使用各自的门禁。访客分析按浏览器访客 ID 聚合访问次数、停留、浏览内容及 IP，可展开查看单次访问记录。
- 新增写作审查命令 `frame` 和一键安装脚本。构建时默认运行表达检查，检测到 P0 即停止，P1、P2 提示后继续。详见 [写作能力包](capabilities/causal-value-chain/README.md)。
- 新增 16:9 和 4:3 视觉检查，检查文字对比度、低对比大字和强调色面积。新增 PPTX 导出检查，实际下载文件并比对纯色背景和页数。详见 [设计检查](docs/DESIGN.md)和 [PPTX 导出](docs/PPTX.md)。
- 静态视频支持 HTTP 单段字节范围请求，浏览器可按需加载和拖动进度。

### 改进与修复

- 用 `node build.mjs --deck <slug>` 构建后尝试重拍该套缩略图并刷新展示台。缩略图地址随文件更新时间变化，浏览器可加载新版封面。
- 可编辑 PPTX 保留网页的纸色与深色背景，透明内联 SVG 按 PNG 导出，多行文本逐行写为可编辑文本框。
- 提高亮色和深色主题中的橙棕与金色标签对比度，修正示例的 4:3 版面溢出。README 增加展示台、放映和深色主题实拍图。

## [1.2.0] - 2026-11-17

### 新增：deck 配色主题（六套预设一键切换）

- `serve_deck.py` 向 deck 页注入 `tools/deck_themes.py`：默认 / 藏青 / 暖赭 / 紫藤 /
  青瓷 / 玄墨（深色）六套预设，放映中按 `C` 循环或右下角 🎨 浮窗点选，
  顶部 toast 提示当前方案；按 deck 存 `localStorage` 记忆。
- 实现：全部 deck 共用 `tokens.css` 变量契约，预设 = 同名变量成套覆盖
  （`html[data-dtheme=…]`），不改 deck 文件、旧 deck 自动支持；
  `?export=1`（缩略图采集）不注入，缩略图保持原配色。
- 边界：写死颜色与整页渲染图（导入 deck 的逐页 PNG）不受主题影响；
  玄墨主题保持 `--dark*` 深面板不变浅，保证面板内浅色文字可读。

### 重写：sample-deck 变为系统使用说明

- `src-sample/` 由 6 屏「引擎自我介绍」扩写为 12 屏使用手册，按「重要 → 细节」排序：
  封面 → **安装**（一句话安装：把仓库地址发给 AI 客户端，克隆 + 装依赖 + 起服务
  全自动，附等效手动命令）→ **AI 代工最佳实践**（三窗格图示：Word 素材 →
  拖入 WorkBuddy 一句话 → 生成 deck，配提示词示例与三步要点）→ 快速开始 →
  系统总览 → 放映操作 → 配色主题 → 创作规范 → PPTX 导入 → 导出与质检 →
  管理后台 → 结尾文档索引（含 GitHub 仓库链接），
  `deck.json` 标题同步改为「DeckStage · 使用说明」。

### 修复

- `base.css`：`.card--dark` 补 `.kv__k` / `.kv__v` 浅色变体——此前深色卡片内的
  key-value 正文沿用 `--ink` 深色，深底上几乎不可读（老 deck 同样受益）。

## [1.1.0] - 2026-11-17

### 新增：`/admin` 管理后台

`serve_deck.py` 内置管理面，无需重新 build、开关即时生效（详见 [docs/ADMIN.md](docs/ADMIN.md)）：

- **访问追踪**：展示台与全部 deck 的 HTML 由服务端注入追踪脚本 —— 页面可见时间逐秒累计
  （后台标签页不计）、15 秒批量心跳、翻页经 `location.hash` 归属到每一屏、`sendBeacon` 收尾；
  访客侧只存 `localStorage` 随机 UUID，不采集任何个人身份信息。
- **管理面板 `/admin/`**：概览卡（累计访问 / 独立访客 / 总观看时长 / 今日 / 近 7 天）、
  内容管理表（状态 / 访问数 / 时长 / 最近访问）、逐屏热度（进入次数 + 平均/总停留热度条）、
  最近 100 条访问记录（时间 / 内容 / 时长 / 看到第几屏 / 访客 / IP / 客户端 / 来源），
  30 秒自动刷新；支持改管理密码与清空统计。
- **deck 门禁**：单套 deck 可设访问密码（PBKDF2 哈希存储 + HMAC 签名 Cookie 30 天免重输，
  可配门禁页提示语）与上下架 —— 下架后 `decks/<slug>/` 整目录 404，
  `library.html` 与 `decks.json` 服务端每请求实时过滤并即时生效；加密 deck 的缩略图
  换为占位图，内容不出网。
- **安全边界**：`/api/track/*`、`/api/access`、`/api/admin/*` 公网可达但分别有
  登录限流（10 分钟 8 次）与追踪 init 限流；导入 API 的本机 `Host` 守卫保持不变。
  运行时数据全部落在 `data/`（gitignore）：`admin.json`（密码哈希 + Cookie 签名密钥，
  0600）、`access.json`（门禁配置）、`tracking.db`（SQLite WAL）。

### 其他

- 首次启动打印一次初始管理密码；`--admin-password` 可随时重置，
  `DECK_ADMIN_PASSWORD` 环境变量可用于首次初始化。
- `.gitignore` 增补 `/data/`。

## [1.0.0] - 2026-11-17

引擎与内容分离基线：

- HTML 幻灯片引擎（`src/css` tokens/base/deck + `src/js` deck.js 放映引擎、
  pptx-export.js 页面内导出），`build.mjs` 单文件拼装。
- 展示台：`library.html` 缩略图墙、`#s12` 深链、全屏放映 / 备注 / 画幅切换。
- PPTX 导入：`import_pptx.py` 六阶段 pipeline（体检 → 字体 → 版式预修 → LibreOffice
  渲染 → 补字层 → 组装）+ `pptx_*.py` 预修工具链 + `import.html` 四步向导（SSE 进度，
  仅限本机）。
- 质检：`check_slides.py` 溢出/截断/重叠体检、`test_deck.py` 放映交互自测。
- 匿名示例 deck（`sample-deck`）与文档（AUTHORING / DECK_SPEC / IMPORT）。

[1.8.1]: https://github.com/Rocky8080/deckstage/compare/v1.8.0...v1.8.1
[1.8.0]: https://github.com/Rocky8080/deckstage/compare/v1.7.1...v1.8.0
[1.7.1]: https://github.com/Rocky8080/deckstage/compare/v1.7.0...v1.7.1
[1.7.0]: https://github.com/Rocky8080/deckstage/compare/85691d1...v1.7.0
[1.6.0]: https://github.com/Rocky8080/deckstage/compare/v1.5.1...85691d1
[1.5.1]: https://github.com/Rocky8080/deckstage/compare/v1.5.0...v1.5.1
[1.5.0]: https://github.com/Rocky8080/deckstage/compare/v1.4.1...v1.5.0
[1.4.1]: https://github.com/Rocky8080/deckstage/compare/v1.4.0...v1.4.1
[1.4.0]: https://github.com/Rocky8080/deckstage/compare/v1.3.0...v1.4.0
[1.3.0]: https://github.com/Rocky8080/deckstage/compare/v1.2.0...v1.3.0
[1.2.0]: https://github.com/Rocky8080/deckstage/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/Rocky8080/deckstage/compare/dce5a61...v1.1.0
[1.0.0]: https://github.com/Rocky8080/deckstage/commit/dce5a61
