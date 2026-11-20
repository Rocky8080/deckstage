# 更新日志 / Changelog

格式参照 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循
[语义化版本](https://semver.org/lang/zh-CN/)。deck 引擎与工具链整体作为版本单元，
deck 内容（`decks/<slug>/`）不在版本范围内。

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

[1.5.1]: https://github.com/Rocky8080/deckstage/compare/v1.5.0...v1.5.1
[1.5.0]: https://github.com/Rocky8080/deckstage/compare/v1.4.1...v1.5.0
[1.4.1]: https://github.com/Rocky8080/deckstage/compare/v1.4.0...v1.4.1
[1.4.0]: https://github.com/Rocky8080/deckstage/compare/v1.3.0...v1.4.0
[1.3.0]: https://github.com/Rocky8080/deckstage/compare/v1.2.0...v1.3.0
[1.2.0]: https://github.com/Rocky8080/deckstage/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/Rocky8080/deckstage/compare/dce5a61...v1.1.0
[1.0.0]: https://github.com/Rocky8080/deckstage/commit/dce5a61
