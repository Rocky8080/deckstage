#!/usr/bin/env node
/* ============================================================
   build.mjs — 把 src/slides/*.html 拼装成单文件 index.html
   · 每屏文件可携带 <style>（提取到 head，按屏顺序）
   · 每屏文件可携带 <script>（提取到 body 末尾）
   · 其余标记按文件名顺序放进 .slides
   用法： node build.mjs
   ============================================================ */
import { readFileSync, writeFileSync, readdirSync, existsSync, mkdirSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = dirname(fileURLToPath(import.meta.url));
const srcIdx = process.argv.indexOf('--src');
const SRC = join(ROOT, srcIdx > -1 ? process.argv[srcIdx + 1] : 'src');
const THEME = join(ROOT, 'src/css');   // 主题 token / base 永远共用主树的

const read = (p) => readFileSync(p, 'utf8');

/* ---------- 1. 样式 ---------- */
const cssFiles = ['tokens.css', 'base.css', 'deck.css']
  .map(f => join(THEME, f));

/* ---------- 2. 各屏文件 ---------- */
const slideDir = join(SRC, 'slides');
const files = readdirSync(slideDir).filter(f => f.endsWith('.html')).sort();

const slideStyles = [];
const slideScripts = [];
const slideMarkup = [];

for (const f of files) {
  const raw = read(join(slideDir, f));
  let rest = raw;

  // 提取 <style> 块
  rest = rest.replace(/<style[^>]*>([\s\S]*?)<\/style>/gi, (_, css) => {
    slideStyles.push(`/* ---- ${f} ---- */\n${css.trim()}`);
    return '';
  });
  // 提取 <script> 块
  rest = rest.replace(/<script[^>]*>([\s\S]*?)<\/script>/gi, (_, js) => {
    slideScripts.push(`/* ---- ${f} ---- */\n${js.trim()}`);
    return '';
  });

  const trimmed = rest.trim();
  if (!trimmed) continue;

  // 给没有 id 的 section 补一个
  const idMatch = /<section[^>]*\bid="([^"]+)"/.exec(trimmed);
  if (!idMatch) {
    const n = files.indexOf(f) + 1;
    slideMarkup.push(trimmed.replace('<section', `<section id="s${String(n).padStart(2, '0')}"`));
    console.warn(`[build] ${f} 缺少 id，已自动补为 s${String(n).padStart(2, '0')}`);
  } else {
    slideMarkup.push(trimmed);
  }
}

/* ---------- 3. 组装 ---------- */
const styles = [
  ...cssFiles.map(p => `/* ===== ${p.split('/src/').pop()} ===== */\n${read(p)}`),
  '/* ===== 各屏专属样式 ===== */',
  ...slideStyles,
].join('\n\n');

const scripts = slideScripts.length
  ? `\n<script>\n${slideScripts.join('\n\n')}\n</script>\n`
  : '';

const shell = read(join(SRC, 'shell.html'))
  .replace('/*@STYLES*/', () => styles)
  .replace('<!--@SLIDES-->', () => slideMarkup.join('\n\n'))
  .replace('<!--@SCRIPTS-->', () => scripts);

writeFileSync(join(ROOT, 'index.html'), shell, 'utf8');

/* ---------- 3b. 可选：自包含单文件（图片全部转 base64 data URI） ---------- */
if (process.argv.includes('--inline')) {
  const MIME = { jpg: 'image/jpeg', jpeg: 'image/jpeg', png: 'image/png', webp: 'image/webp', svg: 'image/svg+xml' };
  let imgs = 0, scripts = 0, missing = [];

  // 1) 图片 -> data URI
  let standalone = shell.replace(/src="(assets\/[^"]+)"/g, (m, rel) => {
    try {
      const buf = readFileSync(join(ROOT, rel));
      const ext = rel.split('.').pop().toLowerCase();
      imgs++;
      return `src="data:${MIME[ext] || 'application/octet-stream'};base64,${buf.toString('base64')}"`;
    } catch { missing.push(rel); return m; }
  });

  // 2) 脚本 -> 内联（pptxgen 这类大包也一起内联，做到真正单文件）
  standalone = standalone.replace(/<script src="([^"]+)"><\/script>/g, (m, rel) => {
    try {
      const js = readFileSync(join(ROOT, rel), 'utf8').replace(/<\/script>/gi, '<\\/script>');
      scripts++;
      return `<script>\n/* inlined: ${rel} */\n${js}\n</script>`;
    } catch { missing.push(rel); return m; }
  });

  const outIdx = process.argv.indexOf('--out');
  const out = join(ROOT, outIdx > -1 ? process.argv[outIdx + 1] : 'deck-standalone.html');
  writeFileSync(out, standalone, 'utf8');
  console.log(`[build] ${out}  ${(standalone.length / 1024 / 1024).toFixed(2)} MB   ` +
              `内联图片 ${imgs} 张 · 内联脚本 ${scripts} 个` +
              (missing.length ? `  ⚠ 缺: ${missing.join(', ')}` : ''));
}

/* ---------- 5. 可选：Web 轻量版（图片走 assets/web/ + 脚本内联，减少请求数） ---------- */
if (process.argv.includes('--web')) {
  let web = shell.replace(/src="(assets\/[^"]+)\.(?:jpg|png)"/g, (_m, base) => {
    const rel = `assets/web/${base.replace('assets/', '')}.jpg`;
    return existsSync(join(ROOT, rel)) ? `src="${rel}"` : _m;   // 没有压缩版就保留原图
  });
  let scripts = 0;
  web = web.replace(/<script src="([^"]+)"><\/script>/g, (_m, rel) => {
    try {
      const js = readFileSync(join(ROOT, rel), 'utf8').replace(/<\/script>/gi, '<\\/script>');
      scripts++;
      return `<script>\n/* inlined: ${rel} */\n${js}\n</script>`;
    } catch { return _m; }
  });
  writeFileSync(join(ROOT, 'index-web.html'), web, 'utf8');
  console.log(`[build] index-web.html  ${(Buffer.byteLength(web)/1024).toFixed(0)} KB  ` +
              `图片→assets/web/ · 内联脚本 ${scripts} 个`);
}

/* ---------- 6. 可选：多套 PPT 展示工具 —— 输出到 decks/<slug>/ ---------- */
{
  const i = process.argv.indexOf('--deck');
  if (i > -1) {
    const slug = process.argv[i + 1];
    if (!slug) { console.error('[build] --deck 需要一个 slug，例如 --deck 我的汇报'); process.exit(1); }
    const outDir = join(ROOT, 'decks', slug);
    mkdirSync(outDir, { recursive: true });

    // (1) 组装时不带 deck.css（与所有 deck 共享），只保留主题与各屏样式
    const deckCssPath = join(SRC, 'deck.css');
    const themeStyles = [
      ...['tokens.css', 'base.css'].map(f => read(join(THEME, f))),
      ...(existsSync(deckCssPath) ? [`/* ===== ${srcIdx > -1 ? process.argv[srcIdx + 1] : 'src'}/deck.css ===== */\n` + read(deckCssPath)] : []),
      '/* ===== 各屏专属样式 ===== */',
      ...slideStyles,
    ].join('\n\n');

    let html = read(join(SRC, 'shell.html'))
      .replace('/*@STYLES*/', () => themeStyles)
      .replace('<!--@SLIDES-->', () => slideMarkup.join('\n\n'))
      .replace('<!--@SCRIPTS-->', () => scripts)
      .replace('<link rel="stylesheet" href="/_shared/deck.css">', '');

    // (2) 共享运行时内联进每套 deck（单一来源 src/js/deck.js + src/css/deck.css，
    //     构建时内联 → 公网少两个请求；隧道对 text/css 的边缘缓存偶发极慢，内联最稳）
    const sharedCss = read(join(THEME, 'deck.css'));
    const sharedJs = read(join(ROOT, 'src/js/deck.js')).replace(/<\/script>/gi, '<\\/script>');
    html = html.replace('</head>',
      `  <style>\n/* ===== _shared/deck.css（构建内联，改 src/css/deck.css 后重跑 build） ===== */\n${sharedCss}\n  </style>\n</head>`);
    html = html.replace('<script src="src/js/deck.js"></script>', `<script>\n/* ===== _shared/deck.js（构建内联） ===== */\n${sharedJs}\n</script>`);

    // (3) 图片：优先 Web 压缩版，全部改成站点绝对路径
    html = html.replace(/src="(assets\/[^"]+)\.(?:jpg|png)"/g, (_m, base) => {
      const rel = `assets/web/${base.replace('assets/', '')}.jpg`;
      return existsSync(join(ROOT, rel)) ? `src="/${rel}"` : _m.replace('src="assets/', 'src="/assets/');
    });
    html = html.replace(/src="assets\//g, 'src="/assets/');
    html = html.replace(/href="assets\//g, 'href="/assets/');
    html = html.replace(/data-src="assets\//g, 'data-src="/assets/');

    // (4) 其余脚本照旧内联（pptx 导出等）
    html = html.replace(/<script src="([^"]+)"><\/script>/g, (_m, rel) => {
      try {
        const js = readFileSync(join(ROOT, rel), 'utf8').replace(/<\/script>/gi, '<\\/script>');
        return `<script>\n/* inlined: ${rel} */\n${js}\n</script>`;
      } catch { return _m; }
    });

    writeFileSync(join(outDir, 'index.html'), html, 'utf8');
    console.log(`[build] decks/${slug}/index.html  ${(Buffer.byteLength(html)/1024).toFixed(0)} KB  共享运行时 /_shared/`);
  }
}

/* ---------- 7. 把交互运行时同步到 _shared/（所有 deck 共用一份） ---------- */
{
  const shared = join(ROOT, '_shared');
  mkdirSync(shared, { recursive: true });
  const pairs = [['src/js/deck.js', 'deck.js'], ['src/css/deck.css', 'deck.css']];
  for (const [from, to] of pairs) {
    const body = read(join(ROOT, from));
    writeFileSync(join(shared, to), body, 'utf8');
  }
  console.log(`[_shared] deck.js + deck.css 已同步`);
}
