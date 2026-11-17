# PPTX 导入 pipeline（自动转换）

> 一条命令把外部 PPTX 转成展示台 deck。两个 x-lab deck（`tsinghua-xlab` / `xlab-2026-10`）
> 导入时手工迭代出来的全部能力，都已沉淀进这条流水线：`tools/import_pptx.py`。
> **网页操作入口**：展示台右上角「＋ 导入 PPTX」（见下文「Web UI」）。

## Web UI（展示台集成）

本地跑着 `serve_deck.py` 时，展示台右上角会出现「＋ 导入 PPTX」，进入四步向导
（`import.html`）：**拖入文件 → 体检确认 → 表单 → 进度与结果**。

- 体检在上传后立即自动进行：页数 / 画幅 / 语言判定 / 字体清单 / 表格·组合统计
- slug 与标题按文件名自动带出；slug 撞名会实时提示并要求显式勾选「覆盖」
- 转换全程显示六阶段 stepper + pipeline 原始日志（SSE 实时流），可中途取消
- 完成后给首页预览、补字数与用时；按钮：打开 deck / 入库刷新展示台 / 调参重导

**安全约定**：`/api/*` 只接受 `Host: 127.0.0.1 / localhost` 的直连请求；
经 cloudflared 隧道来的公网请求（Host 是站点域名）一律 403 —— 导入功能永远不会暴露到公网。
file:// 或公网打开展示台时点按钮会提示如何本地启用。

API 一览（均走 Host 守卫）：
`GET /api/ping`（特性探测）· `POST /api/inventory`（上传+体检）· `GET /api/slug-exists` ·
`POST /api/import`（SSE）· `POST /api/cancel` · `POST /api/publish`（SSE，跑 build_library）。
上传暂存在 `build/import/_uploads/`（超一天自动清理）。

## 命令行用法

```bash
python3 tools/import_pptx.py 源.pptx --slug my-deck [元数据/旋钮...]
```

## 流水线六步

| 步 | 做什么 | 怎么做 |
|---|---|---|
| [0/6] 体检 | 字体清单 / 画幅 / 页数 / 表格·组合·自动缩放统计；语言按正文 CJK/Latin 比例判定 | 只读 zip，不改文件。`--dry-run` 到此为止 |
| [1/6] 字体规整 | **默认保留原字体**（LibreOffice 原生回退已验证可用）；可选统一改写 / 单点映射 / 装入下载字体 | `--rewrite-fonts` / `--map A=B` / `--install-font` |
| [2/6] 版式预修 | 验证配方：短行禁折(≤8/≤16字) → 表格缩字 ×0.9 → **全局缩字 ×0.95** | 复用 `tools/pptx_*.py`；prefit/track/groupfit 为实验手段，显式开启 |
| [3/6] 渲染 | soffice → PDF（按修改时间缓存）→ 逐页 1600×900 JPEG | LibreOffice headless |
| [4/6] 补字层 | PDF 里没画出来 / 缺字方块的文字，按 PDF 坐标补成 HTML 覆盖层 | 复用 `pptx_import.py` 的 tofu 检测 |
| [5/6] 组装 | `tools/templates/import/` 模板 → `src-<slug>/`（shell + deck.css + slides + deck.json）→ `node build.mjs --deck` | 4:3 画幅自动适配（运行时 `body.ratio-4x3`） |
| [6/6] 报告 | `build/import/<slug>/report.json`（字体映射 / 各轮补字数 / 产物路径） | |

## 配方从哪来（为什么默认不改字体）

两个 x-lab deck 手工迭代十余轮后成功的最终产物（`m3.pptx`）被解剖验证：
**保留原字体 + nowrap（wrap none 42→180）+ 全局缩字 ×0.95 + 表格 ×0.9**，
中文交给 LibreOffice 原生回退（PingFang / Hiragino）。prefit（写 fontScale）与
track（收紧字距）在迭代中被淘汰——它们解决折行的同时引入了新的漏画。
这套配方就是 pipeline 的默认值。

实验手段仍保留，供个别源文件需要时显式开启：

```bash
--prefit                 # 实测每段宽度，超框写 normAutofit（需 Arial Unicode 度量）
--track -40              # 超框段落收紧字距
--group-k 0.9            # 组合内短文本缩字
--rewrite-fonts          # 全部字体统一改写：拉丁→Arial Unicode MS / 中文→Hiragino Sans GB
```

想更贴近原稿观感（或原稿用了特殊字体导致漏画）时，下载字体装入系统直用：

```bash
# 例：下载微软雅黑 ttf 后
python3 tools/import_pptx.py 源.pptx --slug my-deck \
    --install-font "Microsoft YaHei=/path/msyh.ttf"
# 若 LibreOffice 正在运行，新字体要等它退出后再渲染才生效
```

## 常用旋钮

| 场景 | 参数 |
|---|---|
| 只看体检结果 | `--dry-run` |
| 覆盖已调过的同名 deck | `--force`（否则拒绝执行，防误删） |
| 中英混合稿判错语言 | `--lang zh` / `--lang en` |
| 某个字体指定特殊目标 | `--map "仓耳渔阳体=PingFang SC"` |
| 顶部导轨精确分章 | `--rail-map "About:1-6 Programs:7-13 Tournaments:14-19 Global:20-33"`（默认按标题关键词粗分） |
| 导轨显示中文标签 | `--rail-labels "About=关于,Programs=教育项目,..."` |
| 缩字力度 | `--shrink 0.92`（全局）/ `--table-k 0.85`（表格） |
| 补字太多时自动加码重渲 | `--rounds 3`（缩字逐轮 ×0.97，取补字最少的一轮） |
| 折行问题顽固 | 追加 `--prefit` 或 `--track -40` 实验手段 |
| 不跑 build.mjs | `--skip-build` |
| 确认效果后入库 | `--publish`（重拍全部缩略图 + 刷新 decks.json / library.html） |

## 元数据参数

`--title --subtitle --author --date --version --tags a,b --order N --accent #RRGGBB`
`--brand`（左上角品牌名，默认 title）`--brand-sub`（副题，默认 date）`--overview-foot`（总览页脚）

## 推荐流程

```bash
# 1) 起本地服务（一次性）
python3 tools/serve_deck.py                # 127.0.0.1:8899，展示台右上角即有「＋ 导入 PPTX」

# 2) 浏览器里完成四步向导；或走命令行：
python3 tools/import_pptx.py 源.pptx --slug my-deck --dry-run   # 体检
python3 tools/import_pptx.py 源.pptx --slug my-deck --title "…"  # 导入
python3 tools/build_library.py --force                          # 入库
```

产物四处：`assets/<slug>/`（逐页 JPEG）、`src-<slug>/`（可改的源）、`decks/<slug>/`（成品 + deck.json）、
`build/import/<slug>/`（中间产物 + 报告）。导入的 deck 每屏 = 整页图 + 补字覆盖层，
文字可检索复制（讲稿面板 / N 键），但**改字要回到源 PPTX 重新导入**——这与手工编辑的
`src/`（纯 HTML deck）不同，见 [AUTHORING.md](AUTHORING.md)。
