# vendor/

第三方运行时依赖，**已锁定版本并落盘**（离线可用，不依赖 CDN）。

## pptxgen.bundle.js

| 项目 | 值 |
|---|---|
| 包名 | `pptxgenjs` |
| 版本 | **3.12.0**（锁定） |
| 文件 | `dist/pptxgen.bundle.js`（浏览器 IIFE bundle，含 JSZip 依赖） |
| 来源 URL | https://cdn.jsdelivr.net/npm/pptxgenjs@3.12.0/dist/pptxgen.bundle.js |
| 备用来源 | https://unpkg.com/pptxgenjs@3.12.0/dist/pptxgen.bundle.js |
| License | MIT（Copyright (c) Brent Ely） |
| 大小 | 477,529 bytes |
| SHA-256 | `cd078ca9e91c6f9e061ee0a3c310d6ff157c3a71b1dea7f40fd53818017266ff` |
| 校验方式 | `shasum -a 256 vendor/pptxgen.bundle.js` |
| 下载于 | 2026-11-16 |

### 重新下载 / 校验

```bash
cd ppt-deck
curl -fsSL -o vendor/pptxgen.bundle.js \
  https://cdn.jsdelivr.net/npm/pptxgenjs@3.12.0/dist/pptxgen.bundle.js
shasum -a 256 vendor/pptxgen.bundle.js
# 期望：cd078ca9e91c6f9e061ee0a3c310d6ff157c3a71b1dea7f40fd53818017266ff
```

### 用法

`src/js/pptx-export.js` 优先使用页面里已经加载的 `window.PptxGenJS`；如果页面没有引入，
它会自己动态注入 `<script src="vendor/pptxgen.bundle.js">`（路径可由
`window.DECK_EXPORT_CONFIG.scriptPath` 覆盖）。因此 index.html 只要引入
`src/js/pptx-export.js` 即可，vendor 文件不必额外声明（当然显式引入更快）。

### 注意

- 该 bundle 会把 `JSZip` 挂到 `window.JSZip`（`pptxgen.bundle.js` 自带 JSZip 3.x）。
- 只使用 v3.12.0 的公开 API：`PptxGenJS#addSlide/addText/addImage/addShape/writeFile`、
  `defineLayout`、`ShapeType`。
- 升级版本时请同步更新本文件的版本号与 SHA-256，并重跑
  `tools/export_editable.py` + `tools/verify_pptx.py` 回归。
