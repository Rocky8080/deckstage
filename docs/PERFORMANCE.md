# 性能：deck 首屏为什么快，怎么保持

一套 16 屏的 deck，线上首屏只下载 **HTML 本身**（brotli 后约 83 KB）；图片、导出代码都不进首屏。
本文记录三个机制、实测数字、保持清单，以及怎么重新测。

## 一、当前基准（16 屏 deck · 线上部署）

| 阶段 | FCP | LCP | DCL | 首屏传输 |
|---|---|---|---|---|
| 优化前（导出包内联 + 图片全量 + 未压缩） | 2352 ms | 8108 ms | 7558 ms | 1461 KB |
| ① 导出包按需 + 图片 2× 压缩 | 1620 | 3936 | 3346 | 544 KB |
| ② 按屏懒加载（当前） | **1060–1632** | **2424–2996** | **1870–2439** | **1 KB** |

同一台机器、同一条隧道取样 3 次；本地 4× CPU + Slow 4G 降速下：LCP 1316 ms、DCL 757 ms、load 774 ms、首屏图片 **0 张**。
翻到有图的屏才拉那一张（1520px 截图 ≈0.5 s 就绪，此前 11 张抢带宽要 4.7 s）。

## 二、三个机制

### 1. PPTX 导出包不进首屏（收益最大）

`vendor/pptxgen.bundle.js`（468 KB）只在点「导出 PPTX」时用。`build.mjs` 不再把它内联进 deck 的 HTML，
改由 `src/js/pptx-export.js` 的 `ensurePptxGenJS()` 在第一次导出时注入 `/vendor/pptxgen.bundle.js`
（边缘缓存命中后，第二次起 0 请求）。根构建里两个导出脚本改为 `defer`。

构建带回归护栏：一旦导出包又被内联进首屏，`node build.mjs --deck <slug>` 直接失败。

### 2. 图片按 2× 显示尺寸压成 Web 版

`build.mjs` 的 deck 构建会**优先使用** `assets/web/<deck>/<名字>.jpg`：存在就用它，否则回落到 `assets/<deck>/<原图>`。
所以压缩图不需要改任何 deck 源码，放对位置即可：

```bash
# 例：把一张 760px 宽显示的截图压到 2×（1520px）+ q82
python3 -c "
from PIL import Image
im = Image.open('assets/mydeck/shot.png').convert('RGB')
im.thumbnail((1520, 1520), Image.LANCZOS)
im.save('assets/web/mydeck/shot.jpg', 'JPEG', quality=82, optimize=True, progressive=True)"
```

注意：**扁平色截图（表格、UI 截屏）保持 PNG 往往比转 JPEG 更小**——转之前比一下两者大小。

### 3. 按屏懒加载（复用引擎已有机制）

`.slide { position: absolute; inset: 0 }` 把 16 屏叠在同一位置，所以 `loading="lazy"` **不生效**
（实测 11 张图仍在同一时刻发起）。引擎自带的 `deck.js#hydrateImages(from, to)` 只加载当前屏 ±2 屏、
导出时补满全册，但它原本只认 `<img data-src>`（PPTX 导入的 deck 就是这个写法）。

`build.mjs` 现在把首屏之外的普通 `<img src>` 换成 1×1 占位 + `data-src`（只换 src，`alt` / `class` / `style` 保留），
于是所有 deck 都走同一条懒加载路径。配套两处：

- `src/js/pptx-export.js` 取图时优先读 `data-src`——导出时图片即使还没水合也能正确内嵌；
- `tools/check_slides.py`、`tools/make_pptx.py` 在测量/导出前调用 `window.__deckHydrate(0, 999)`。

`--inline`（离线单文件版）不启用懒加载：单文件本来就要自带全部图片。

## 三、保持清单（写新 deck / 加图片时）

1. 截图先按 **2× 显示宽度** 压一版放 `assets/web/<deck>/`，再比一次原图大小。
2. 不要为了「单文件」把大脚本塞回首屏——导出包按需加载是故意的，构建护栏会拦。
3. 图片放 `<div class="shot">` 这类**定尺寸容器**里（`object-fit: cover`），占位图不会引起布局跳动。
4. 首屏（第 1 屏）可以有图；从第 2 屏起图片会自动懒加载。
5. 改完照常跑门禁：`check_slides.py` / `design_audit.py`，再 `export_audit.py` 验一次导出图完整。

## 四、怎么重新测

```bash
# 1) 起一个本地服务（本地测记得开 gzip，否则会被放大成 3 倍传输）
python3 tools/serve.py --port 8901

# 2) 量首屏：FCP / LCP / DCL / 长任务 / 传输字节
python3 tools/perf_probe.py http://127.0.0.1:8901/decks/xlab-ai-practice/index.html

# 3) 模拟弱网弱 CPU（4× CPU + 1.6 Mbps / 150 ms RTT）
python3 tools/perf_probe.py http://127.0.0.1:8901/decks/xlab-ai-practice/index.html --cpu 4 --net slow4g

# 4) 只看 HTML + JS 的成本（屏蔽图片）
python3 tools/perf_probe.py <url> --cpu 4 --net slow4g --block-images
```

线上测量把 URL 换成你的部署地址（`/decks/<slug>/index.html`）即可；注意隧道走的是本机上行，
带宽抖动会主导结果（本机实测约 1.5 Mbps），所以**判断优化是否生效以上面的降速场景与首屏传输字节为准**。

## 五、已知天花板

- 首屏现在已经只剩 HTML：16 屏 ≈83 KB、33 屏 ≈63 KB（brotli）。再往下只能拆 deck 或做按屏 HTML 分片。
- 真正的瓶颈是出口带宽与隧道 RTT（本机上行约 1.5 Mbps，TTFB 1–3.5 s）。
- 图片已经是 2× q82；若要再省 30% 可转 WebP（需要改构建的扩展名映射），收益主要落在「翻到图页」那 0.5 s。
