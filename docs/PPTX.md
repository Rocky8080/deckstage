# PPTX 导出与验收

在放映页工具栏点击「导出 PPTX」可下载可编辑的 `.pptx`。文字和可转换的形状在 PowerPoint 中保留为可编辑对象。需要以整页截图保留浏览器画面时，运行 `python3 tools/make_pptx.py` 从构建生成的根目录 `index.html` 制作图片版。

## 检查页数和纯色背景

在仓库根目录构建公开示例并启动服务。检查器需要 Playwright 和 Chrome。

```bash
node build.mjs --src src-sample --deck sample-deck
python3 tools/serve_deck.py
```

服务运行在 `127.0.0.1:8899`。在另一个终端执行以下命令。

```bash
python3 tools/export_audit.py --index decks/sample-deck/index.html --out /tmp/sample-deck.pptx
```

检查器会从浏览器实际导出 PPTX，比较 HTML 与 PPTX 的页数，并逐页比较幻灯片的计算背景色和 PPTX 中的 `<p:bg>`。页数不符、无法比较背景或颜色不符时返回非零。纯色背景适合自动比对。图片和渐变背景需要在 PowerPoint 中打开核对。

`--out` 可选，用于保留导出的文件。已有 PPTX 时，可以直接检查每一页的纯色背景。将 `--expect` 换成该 deck 的预期色值，混用多种纯色时可用 `--allow` 追加允许值。

```bash
python3 tools/check_pptx_bg.py /tmp/sample-deck.pptx --expect F7F3EA
```

## 排查常见导出问题

### 纸色或深色页面变白

在 PptxGenJS 3.x 中，旧字段 `slide.bkgd` 会覆盖 `slide.background`。在 [PPTX 导出器](../src/js/pptx-export.js) 中统一用 `slide.background` 设置纯色或图片背景。

```js
slide.background = { color: 'F7F3EA' };
```

如果纯色背景已匹配，仍可在实际交付用的 PowerPoint 或 WPS 中对照网页，检查阅读器渲染和显示器色彩设置。

### SVG 出现黑色楔形或白框

- 复制内联 SVG 时保留计算样式中的 `fill:none` 和 `stroke:none`。丢掉 `fill:none` 后，缺省黑色填充会把弧线变成黑色楔形。
- 识别 `data:image/svg+xml` 并栅格化为保留透明通道的 PNG。将其按 JPEG 处理会在图形周边铺白色。
- 将页面定位样式放在 SVG 外层容器上，避免 SVG 在导出时偏离自身画布。
- 打开生成的 PPTX，检查图形填充、线条和透明边缘。

### 多行标题压住下方内容

PptxGenJS 3.x 可能在换行与行内颜色变化相邻的位置多插入一个段落。导出器为多行文本逐行生成文本框。打开生成的文件，核对标题的行数、颜色和末行位置，并确认末行底部在下一块内容上方。
