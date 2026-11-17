# 更新日志 / Changelog

格式参照 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循
[语义化版本](https://semver.org/lang/zh-CN/)。deck 引擎与工具链整体作为版本单元，
deck 内容（`decks/<slug>/`）不在版本范围内。

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

[1.2.0]: https://github.com/Rocky8080/deckstage/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/Rocky8080/deckstage/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/Rocky8080/deckstage/releases/tag/v1.0.0
