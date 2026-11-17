# 展示交互规范（所有 PPT 共用）

> 本站是多套 PPT 的展示台：首页是缩略图墙，点开任意一套进入放映。
> 为了避免"每套 PPT 操作都不一样"，所有 deck **共用同一份运行时源码**：
> `src/js/deck.js` + `src/css/deck.css`，由 `build.mjs --deck <slug>` **内联进每一套**，
> 同时在 `/_shared/` 留一份可读副本。
> 改交互只改这两个源文件 → 重跑 `node build.mjs --deck <slug>` 即全部生效。

---

## 一、页面结构（每套 deck 一致）

```
┌─────────────────────────────────────────────────────────┐
│ 品牌 ｜ 导轨（量/物/法…） ｜ 提示条            ← 顶部外壳 │
├─────────────────────────────────────────────────────────┤
│                                                         │
│                     舞台 stage（16:9）                   │
│                                                         │
├─────────────────────────────────────────────────────────┤
│ 01/19 标题 [进度条 18 段] ← → ⊞ 💬 放映 ⛶ ⤓  ← 底部外壳 │
└─────────────────────────────────────────────────────────┘
```

- **舞台**永远按 16:9 等比缩放居中（1600×900 设计坐标），不随窗口变形
- **顶部外壳**：左上是「‹ 展示台」返回入口（点击或按 `H` 回到首页），其右是品牌，中间是章节导轨，右侧是操作提示；窄窗口自动隐藏提示与导轨
- **底部外壳**：页码 / 当前屏标题 / 进度条 / 六个按钮
- 外壳在放映与影院模式下自动隐藏，鼠标移动到顶部/底部边缘时恢复

---

## 一·五、画幅自适应（16:9 / 4:3）

| 窗口比 | 自动画幅 | 效果 |
|---|---|---|
| ≈16:9（1.7–1.8） | 16:9 · 1600×900 | 标准版式 |
| ≈4:3（1.25–1.42 且短边 ≥720） | **4:3 · 1200×900** | 版式回流，上下不再留黑边 |
| 16:10 / 21:9 / 小窗口 | 16:9 | 等比缩放、留边，不变形 |

- **手动切换**：底部工具栏的「画幅」按钮（显示当前比例，如 `▭ 自动 16:9` / `▭ 4:3`，点击循环 自动 → 16:9 → 4:3 并记住选择）；也可按 `R`，或 URL `?ratio=4:3` / `?ratio=16:9`
- 填满/留边：`S` 键 或 `?fit=cover|contain`（cover 会裁掉外沿，慎用）
- 4:3 下对 7 屏做了逐屏校准（`deck.css` 里 `body.ratio-4x3 …` 的 zoom 值），
  保证 `python3 tools/check_slides.py --ratio 4:3` **0 问题**
- 导出（`?export=1`）固定 16:9，PDF / PPTX 不受画幅切换影响

## 二、键盘

| 键 | 行为 | 备注 |
|---|---|---|
| `→` `↓` `空格` `Enter` `PageDown` | 下一屏 / 展开下一步 | 有分步内容的屏先走分步 |
| `←` `↑` `PageUp` | 上一屏 / 收回一步 | |
| `Home` / `End` | 第一屏 / 最后一屏 | |
| `G` / `O` | 总览（缩略图墙）开关 | `Esc` 或点击卡片关闭 |
| `N` | 演讲备注抽屉开关 | 抽屉右上角 ✕ 也能关 |
| `F` | 全屏放映开关 | 不支持原生全屏时退化「影院模式」 |
| `Esc` | 逐层退出：总览 → 备注 → 全屏 → 影院 | 一次只退一层 |
| `H` | 返回 PPT 展示台首页 | 等同左上角「‹ 展示台」 |
| `S` | 切换填满 / 留边（`fit`） | 填满会裁掉外沿 |
| `R` | 切换画幅：自动 → 16:9 → 4:3 | 记住选择 |

**焦点约定**：按键在任何焦点位置都生效（不依赖 body 聚焦）；抽屉/总览打开时仍然生效。

---

## 三、鼠标与触控

| 操作 | 行为 |
|---|---|
| 点**左侧边缘**（约 13vw，最少 64px） | 上一屏 |
| 点**右侧边缘**（同上） | 下一屏 |
| 点**进度条任意一段** | 跳到该屏；命中高度 **28px**（视觉细条居中，热区占满） |
| 悬停进度条 | 细条变粗 + 浮出「06 · 屏标题」提示 |
| 左右滑动（触控） | 翻页 |
| 轻点屏幕（触控） | 在影院模式下唤回外壳 |

> 进度条热区不小于 24×24px；边缘点击带不遮挡舞台中央内容与任何按钮。

---

## 四、URL 约定

| 形式 | 含义 |
|---|---|
| `/decks/<slug>/` | 打开某一套 PPT |
| `#sNN` | 深链到第 NN 屏（`#s4` = 第 4 屏），翻页时地址栏同步 |
| `?present=1` | 打开即进放映（影院模式） |
| `?export=1` | 静态导出模式：所有屏同时可见、无动画，供截图 / 打印 / 转 PDF |
| `/` | 展示台首页（缩略图墙）；若带 `#sNN` 会自动跳到最近打开的那套 |

---

## 五、组件

| 组件 | 规范 |
|---|---|
| **进度条** | 每屏一段；已看=浅绿、当前=亮绿、未看=灰；悬停显示标题 |
| **总览** | 网格列出全部屏（序号 + 标题 + 导轨标签），点击跳转，`Esc` 关闭 |
| **备注抽屉** | 从底部弹出，**抬在工具栏之上**（`bottom: 52px`），限高 46vh 可滚动；右上角 ✕、`N`、`Esc` 三种关闭方式 |
| **放映** | 优先浏览器 Fullscreen API；被拒（iframe / iOS）则退化影院模式：隐藏外壳、铺满窗口 |
| **提示条** | 首次进入显示「← → 或点两侧翻页 · 空格逐步展开 · G 总览 · N 备注 · F 全屏放映」，翻页后淡出 |

---

## 六、单套 deck 的制作约定

每套 PPT 是 `decks/<slug>/` 一个目录：

```
decks/<slug>/
    index.html   ← build.mjs --deck <slug> 生成（不要手改）
    deck.json    ← 元数据：title / subtitle / author / date / tags / order
    thumb.jpg    ← 首页缩略图，build_library.py 自动拍
```

**每屏文件**放在 `src/slides/NN-name.html`，必须满足：

- 根节点 `<section class="slide" id="sNN" data-title="屏标题" data-rail="量|物|法">`
- `data-title` 会出现在进度条提示、总览卡片、页脚与浏览器标题里
- 演讲备注写在 `<aside class="notes">…</aside>`，不进画面
- 屏幕字号下限：正文 ≥ 13.5px；13px 以下只允许「序号 / 单位 / 轴标签 / 徽标」
- 数值涨跌按 A 股口径：涨红 `var(--up)`、跌绿 `var(--down-2)`
- 套用主题变量（`tokens.css`），不要写死颜色

---

## 六·五、导入已有 PPTX（渲染保真）

外部 PPTX 转进来时，**不要重排版式**——用真实渲染器把每页渲染成图，视觉 1:1：

```bash
# 依赖：LibreOffice（brew install --cask libreoffice）
python3 tools/xlab_render_deck.py     # pptx → pdf → 逐页 1600×900 JPEG → src-xlab/slides/
node build.mjs --deck tsinghua-xlab --src src-xlab
```

- 渲染管线：`soffice --headless --convert-to pdf` → PyMuPDF 逐页出图（1600×900）
- 每屏 = 渲染图（`data-src` 懒加载）+ `<aside class="notes">` 原文（讲稿面板可检索/复制）
- 背景、SmartArt、图表、母版元素全部保留（这些用 python-pptx 读不出来）
- 画幅：`object-fit: contain`，4:3 下保持原页完整、不裁切（补字层同步缩放对齐）
- **补字层**：LibreOffice 会漏画部分文字（如 P5 的项目名单、P8 的生态标签、括号等标点）。
  生成时逐行取 PDF 文字 bbox，裁该区域算像素方差，方差≈0 说明没画出来 → 按 bbox 生成绝对定位的 HTML 文字，
  颜色/字号/字体取自 PDF span。字号取「PDF 声明字号」与「实际行高」的较小值
- **字号还原**：PDF 里记录的字号对「自动缩放」文本框不准（记录的是未缩放值）。
  改用「文本框宽度 ÷ 字符数」反推真实字号（中文 1 字≈1 字号宽，西文≈0.52），与 PPT 观感一致
- **不做重排/放大**：补字保持原稿字号与位置（保真优先），页面上的里程碑标签等不会被压住；
  只有明显超宽时才做 ≤30% 的横向收窄，防止压到相邻列

> 注：早期用 python-pptx 按几何重建（`xlab_import.py`）已废弃——它拿不到渐变背景与 SmartArt，必然与原稿有差距。

## 七、新增一套 PPT（四步）

```bash
# 1. 写内容：新建一套源目录（如 src-<slug>/），放 shell.html + slides/ + deck.css
#    - 主题 token / base / 运行时统一走 src/css、src/js（由 --src 指定内容源）
#    - deck.css 可选：这一套专属的版式与动画
# 2. 构建到目录并同步共享运行时
node build.mjs --deck <slug> --src src-<slug>   # → decks/<slug>/index.html

# 3. 写元数据
cat > decks/<slug>/deck.json <<'JSON'
{ "title": "标题", "subtitle": "副标题", "author": "作者", "date": "2026-11-17",
  "tags": ["个人汇报"], "order": 2 }
JSON

# 4. 生成缩略图 + 首页（会自动扫描 decks/）
python3 tools/build_library.py
```

刷新首页即可看到新卡片。

---

## 八、自检清单（改完必跑）

```bash
python3 tools/check_slides.py            # 文字溢出 / 叠字 / 图片缺失 / 字号对比
python3 tools/test_deck.py               # 22 条交互断言（键盘、总览、备注、进度条、深链）
python3 tools/build_library.py           # 首页与缩略图重新生成
```

- 指定某一套 deck 检查：`python3 tools/check_slides.py --index decks/<slug>/index.html [--ratio 4:3]`
- 图片懒加载：幻灯片里用 `<img data-src="...">`，运行时只加载当前屏 ±2 的图片（导出模式一次全载）
- 截图预览：`python3 tools/check_slides.py --shots` → `/tmp/qa/sNN.png`
- 排版回归：任何改动后 `check_slides` 必须 **0 问题**

### 中文字体（重要）

LibreOffice 只认它自己字体目录里的字体，**不读 macOS 系统字体**。默认情况下中文会被画成 □。

一次性处理（装完 LibreOffice 后做一次即可，升级后需重做）：

```bash
LO_FONTS="/Applications/LibreOffice.app/Contents/Resources/fonts/truetype"
cp "/System/Library/Fonts/Supplemental/Arial Unicode.ttf" "$LO_FONTS/"
cp "/System/Library/Fonts/Hiragino Sans GB.ttc" "$LO_FONTS/"
```

装好后中文即可原生渲染：没有再补字、没有擦除痕迹、基线与西文自然对齐。

**补字层**只处理真正没画出来的文字（PDF 里有记录、像素区无墨迹）：
- 位置用 PDF 的真实基线（`origin.y`），浏览器端再用 canvas 实测字体度量，扣半行距与墨迹下沉后定位
- 若检测到「边框有墨、中心空白」的方块字，才擦除并补写（`looks_like_tofu`）

### 字体替换导致的折行（重要）

LibreOffice 用回退字体排中文时，字宽与 PowerPoint 的微软雅黑略有差异，会出现原稿一行、这里多折一行的情况
（如卡片标题「付智 · 共绩科技」被拆成「付智 · 共绩科 / 技」）。

处理：渲染前把所有字号按比例缩一点（只改 `sz` 属性，不动 XML 结构），留出换行余量。

```bash
python3 tools/pptx_shrink.py /tmp/x.pptx /tmp/x_s.pptx 0.93   # 中文版用 0.93
python3 tools/pptx_import.py --pptx /tmp/x.pptx --slug <slug> --src <src> --pdf <缩字号后转出的 pdf>
```

- 0.96 仍有个别孤立换行，**0.93 效果最好**（中文版 33 屏已验证）
- 英文版不需要（Liberation Sans 与 Arial 度量兼容，折行与原稿一致）

### 关键：装入原稿使用的字体（微软雅黑）

LibreOffice 只认自己的字体目录。装了微软雅黑后，中文版**字形与原稿完全一致**，排版也基本对齐。

```bash
LO_FONTS="/Applications/LibreOffice.app/Contents/Resources/fonts/truetype"
# 微软雅黑（本机 Camoufox 缓存里有，也可从 Windows/Office 拷贝）
cp ~/Library/Caches/camoufox/Camoufox.app/Contents/Resources/fonts/msyh{,bd,l}.ttc "$LO_FONTS/"
```

中文版的完整渲染链（顺序不能变）：

```bash
python3 tools/pptx_shrink.py      原.pptx  s1.pptx 0.95   # 全局字号留换行余量
python3 tools/pptx_groupfit.py    s1.pptx  s2.pptx 0.90   # 组合内卡片标题再缩一点
python3 tools/pptx_nowrap_short.py s2.pptx s3.pptx 8      # 短文本/数字禁止换行
soffice --headless --convert-to pdf → tools/pptx_import.py
```

英文版直接用原文件渲染即可（英文用 Arial/Calibri，LibreOffice 有度量兼容的替换字体）。

### 不要再“擦方块”

装上微软雅黑后，中文已能原生渲染。早期为绕过缺字而做的「抹掉方块 + 补字」逻辑会**误删真实中文**，
已在 `tools/pptx_import.py` 中移除：现在只补“像素区确实没有墨迹”的文字，已绘制的一律跳过。
