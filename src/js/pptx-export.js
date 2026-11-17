/*!
 * pptx-export.js — 把「1600×900 设计坐标」的 HTML 汇报 PPT 还原成原生、可编辑的 PowerPoint
 * ---------------------------------------------------------------------------------
 * 公开 API
 *   window.deckExportPptx(options?) -> Promise<report>   生成 .pptx 并触发下载
 *   window.deckExportPptx.lastReport                    上一次导出的报告
 *   任何 [data-export="pptx"] 元素点击自动触发
 *
 * 依赖：vendor/pptxgen.bundle.js（pptxgenjs 3.12.0，已落盘）。若页面未加载，本文件会自行注入。
 *
 * 换算：1600px 设计宽 = 13.3333in = 960pt，900px = 7.5in = 540pt
 *       => 1 设计 px = 0.6pt = 1/120 in
 *
 * 渲染规则（DOM -> 原生 PPT）
 *   · 文本叶子节点（不含块级子元素） -> 一个文本框；字体/字号/颜色/粗细/对齐/行距取自 computed style
 *   · <img> 与 CSS background-image   -> 图片；object-fit:cover 用 canvas 预裁剪，保持不拉伸
 *   · 纯色/圆角卡片底                  -> 圆角矩形（backgroundColor，跳过 transparent/渐变/blur）
 *   · .slide 背景色/渐变               -> slide.background
 *   · 跳过：blur/滤镜、纯装饰渐变、opacity<0.08、display:none、visibility:hidden
 *
 * 可配置：window.DECK_EXPORT_CONFIG = { fileName, slideSelector, scriptPath, fontMap, ... }
 */
(function (global) {
  'use strict';

  /* ============================================================ 常量 */

  var DESIGN_W = 1600;
  var DESIGN_H = 900;
  var PX_TO_IN = 1 / 120;   // 1600 px -> 13.3333in
  var PX_TO_PT = 0.6;       // 1600 px -> 960pt

  /* 默认元数据从页面自身派生：<title> 首段、<meta name=author>、
     <meta name=export-filename>（可整体覆盖导出文件名）。也可用
     window.DECK_EXPORT_DEFAULTS = {...} 在 shell 里整体覆盖。 */
  function docMeta(name) {
    var m = document.querySelector('meta[name="' + name + '"]');
    return (m && m.content || '').trim();
  }
  function docTitle() {
    return (document.title || 'deck').split(/[—·\-–|]/)[0].trim() || 'deck';
  }
  var _docDefaults = {
    fileName: docMeta('export-filename') || docTitle() + '-可编辑.pptx',
    title: docTitle(),
    author: docMeta('author')
  };

  var DEFAULTS = Object.assign({}, _docDefaults, global.DECK_EXPORT_DEFAULTS || {}, {
    slideSelector: 'section.slide',
    scriptPath: null,             // 不填则自动探测
    skipSelector: '[data-pptx-skip], .no-export, .pptx-skip',
    // 本机没装 Inter / SF 系列，浏览器实际用系统回退渲染；
    // 这里映射到 macOS 自带、Windows 会回退到 Arial 的等价字体，避免 PowerPoint 各自猜。
    fontMap: {
      'Inter': 'Helvetica Neue',
      'SF Pro Display': 'Helvetica Neue',
      'SF Pro Text': 'Helvetica Neue',
      'SF Pro': 'Helvetica Neue',
      'SF Mono': 'Menlo',
      'ui-monospace': 'Menlo'
    },
    fallbackFont: 'Microsoft YaHei',
    minShapeArea: 600,            // 小于该面积(设计px²)的色块不导出
    minRuleLen: 16,               // 细线/分隔线最短长度
    thinRuleMax: 4,               // 细线最大厚度
    bigGradientAreaRatio: 0.4,    // 渐变面积 > 幻灯片 40% 时栅格化成图片层
    maxImageEdge: 2200,           // 导出图片最长边上限
    debug: false
  });

  var GENERIC_FONTS = {
    'system-ui': 1, 'sans-serif': 1, 'serif': 1, 'monospace': 1, 'cursive': 1, 'fantasy': 1,
    'ui-sans-serif': 1, 'ui-serif': 1, 'ui-monospace': 1, 'ui-rounded': 1,
    '-apple-system': 1, 'blinkmacsystemfont': 1, 'math': 1, 'emoji': 1,
    'inherit': 1, 'initial': 1, 'unset': 1, 'revert': 1
  };

  var REPLACED_TAGS = {
    IMG: 1, CANVAS: 1, VIDEO: 1, IFRAME: 1, OBJECT: 1, EMBED: 1, PICTURE: 1, SVG: 1
  };

  function cfg() {
    var out = {};
    for (var k in DEFAULTS) out[k] = DEFAULTS[k];
    var over = (global.DECK_EXPORT_CONFIG || {});
    for (var k2 in over) {
      if (over[k2] !== undefined && k2 !== 'fontMap') out[k2] = over[k2];
    }
    // fontMap 是「追加/覆盖」，不是整体替换：页面可以只补一条映射
    out.fontMap = {};
    for (var f in DEFAULTS.fontMap) out.fontMap[f] = DEFAULTS.fontMap[f];
    if (over.fontMap) {
      for (var f2 in over.fontMap) out.fontMap[f2] = over.fontMap[f2];
    }
    return out;
  }

  /* ============================================================ 小工具 */

  function wlog() {
    if (window.DECK_EXPORT_CONFIG && window.DECK_EXPORT_CONFIG.debug) {
      try { console.log.apply(console, ['[pptx-export]'].concat([].slice.call(arguments))); } catch (e) {}
    }
  }

  function num(v, dflt) {
    var n = parseFloat(v);
    return isFinite(n) ? n : (dflt || 0);
  }
  function r2(n) { return Math.round(n * 100) / 100; }
  function clamp(n, lo, hi) { return n < lo ? lo : (n > hi ? hi : n); }
  function inToPx(v) { return v / PX_TO_IN; }

  /* ---- 颜色 ---------------------------------------------------- */

  var _cvs = null, _ctx = null, _colorCache = Object.create(null);

  function cssColorToRGBA(str) {
    if (!_cvs) {
      _cvs = document.createElement('canvas');
      _cvs.width = 1; _cvs.height = 1;
      _ctx = _cvs.getContext('2d', { willReadFrequently: true });
    }
    _ctx.clearRect(0, 0, 1, 1);
    _ctx.fillStyle = '#000000';
    _ctx.fillStyle = str;
    if (!_ctx.fillStyle) return null;
    _ctx.fillRect(0, 0, 1, 1);
    var d = _ctx.getImageData(0, 0, 1, 1).data;
    return { r: d[0], g: d[1], b: d[2], a: d[3] / 255 };
  }

  function hex2(n) {
    var s = Math.max(0, Math.min(255, Math.round(n))).toString(16).toUpperCase();
    return s.length < 2 ? '0' + s : s;
  }

  function parseColor(str) {
    if (str === null || str === undefined) return null;
    var s = String(str).trim().toLowerCase();
    if (!s || s === 'transparent' || s === 'none' || s === 'currentcolor') return null;
    var fast = /^#([0-9a-f]{3,8})$/.exec(s);
    if (fast) {
      var h = fast[1];
      if (h.length === 3 || h.length === 4) h = h.replace(/./g, '$&$&');
      if (h.length === 6 || h.length === 8) {
        var a = h.length === 8 ? parseInt(h.slice(6, 8), 16) / 255 : 1;
        if (a < 0.004) return null;
        return { hex: h.slice(0, 6).toUpperCase(), a: a };
      }
    }
    if (_colorCache[s]) return _colorCache[s];
    var rgba = cssColorToRGBA(s);
    var out = null;
    if (rgba && rgba.a >= 0.004) out = { hex: hex2(rgba.r) + hex2(rgba.g) + hex2(rgba.b), a: rgba.a };
    _colorCache[s] = out;
    return out;
  }

  function rgbaToHex(c) { return hex2(c.r) + hex2(c.g) + hex2(c.b); }

  /* ---- 字体 ---------------------------------------------------- */

  function splitTopLevel(str, sep) {
    var out = [], depth = 0, cur = '', q = null;
    for (var i = 0; i < str.length; i++) {
      var ch = str[i];
      if (q) { if (ch === q) q = null; cur += ch; continue; }
      if (ch === '"' || ch === "'") { q = ch; cur += ch; continue; }
      if (ch === '(') depth++;
      if (ch === ')') depth--;
      if (ch === sep && depth === 0) { out.push(cur); cur = ''; continue; }
      cur += ch;
    }
    if (cur.trim()) out.push(cur);
    return out;
  }

  function firstFamily(list, c) {
    if (!list) return '';
    var parts = splitTopLevel(String(list), ',');
    for (var i = 0; i < parts.length; i++) {
      var p = parts[i].trim().replace(/^["']|["']$/g, '').trim();
      if (!p) continue;
      if (GENERIC_FONTS[p.toLowerCase()]) continue;
      return p;
    }
    return '';
  }

  function mapFont(family, c) {
    if (!family) return c.fallbackFont;
    var key = family.toLowerCase();
    for (var k in c.fontMap) {
      if (k.toLowerCase() === key) return c.fontMap[k];
    }
    return family;
  }

  /* ---- 尺寸 ---------------------------------------------------- */

  function cssPx(v) { return num(v, 0); }

  function contentBox(el, cs) {
    var r = el.getBoundingClientRect();
    var l = cssPx(cs.borderLeftWidth) + cssPx(cs.paddingLeft);
    var t = cssPx(cs.borderTopWidth) + cssPx(cs.paddingTop);
    var rr = cssPx(cs.borderRightWidth) + cssPx(cs.paddingRight);
    var b = cssPx(cs.borderBottomWidth) + cssPx(cs.paddingBottom);
    return {
      left: r.left + l,
      top: r.top + t,
      width: Math.max(0, r.width - l - rr),
      height: Math.max(0, r.height - t - b),
      borderBox: r
    };
  }

  var DISPLAY_INLINE = /^(inline|contents|ruby)/;
  var DISPLAY_BLOCKISH = /^(block|flex|grid|list-item|table|flow-root|run-in|-webkit-box)/;

  function isHidden(cs) {
    return cs.display === 'none' || cs.visibility === 'hidden' || cs.visibility === 'collapse';
  }

  function isReplaced(el) {
    return !!REPLACED_TAGS[el.tagName] || (el.tagName || '').toLowerCase() === 'svg';
  }

  function isTextBlock(el) {
    if (isReplaced(el)) return false;
    var text = el.textContent;
    if (!text || !text.trim()) return false;
    var kids = el.children;
    for (var i = 0; i < kids.length; i++) {
      var kid = kids[i];
      if (isReplaced(kid)) return false;
      var cs = getComputedStyle(kid);
      if (isHidden(cs)) continue;
      var d = cs.display;
      if (DISPLAY_INLINE.test(d)) continue;
      return false;
    }
    return true;
  }

  /* ---- 文本收集 ------------------------------------------------ */

  function applyTextTransform(text, tt) {
    if (!tt || tt === 'none') return text;
    if (tt === 'uppercase') return text.toUpperCase();
    if (tt === 'lowercase') return text.toLowerCase();
    if (tt === 'capitalize') {
      return text.replace(/(^|[\s\u3000\-/（(「“"'·])([a-z\u00e0-\u00ff])/g, function (m, p, c) {
        return p + c.toUpperCase();
      });
    }
    return text;
  }

  function runStyleOf(el, cs, c) {
    var colorHex = null, alpha = 1;
    var fillColor = cs.webkitTextFillColor;
    var bgClip = cs.webkitBackgroundClip || cs.backgroundClip || '';
    if (bgClip && /text/.test(bgClip) && /gradient/.test(cs.backgroundImage || '')) {
      var stops = parseGradientStops(cs.backgroundImage);
      if (stops && stops.length) { colorHex = stops[0].hex; alpha = 1; }
    }
    if (!colorHex) {
      var col = parseColor(cs.color) || parseColor(fillColor);
      if (col) { colorHex = col.hex; alpha = col.a; }
    }
    if (!colorHex) colorHex = '000000';
    if (alpha < 0.05) return null;

    var fsPx = cssPx(cs.fontSize) || 16;
    var weightRaw = cs.fontWeight;
    var weight = weightRaw === 'bold' ? 700 : (weightRaw === 'normal' ? 400 : (parseInt(weightRaw, 10) || 400));
    var ls = cssPx(cs.letterSpacing);
    var family = firstFamily(cs.fontFamily, c);

    return {
      fontFace: mapFont(family, c),
      fontSize: Math.max(1, r2(fsPx * PX_TO_PT)),
      color: colorHex,
      transparency: alpha < 0.98 ? Math.round((1 - alpha) * 100) : 0,
      bold: weight >= 600,
      italic: /italic|oblique/.test(cs.fontStyle),
      underline: /underline/.test((cs.textDecorationLine || cs.textDecoration || '')),
      strike: /line-through/.test((cs.textDecorationLine || cs.textDecoration || '')),
      charSpacing: Math.abs(ls) > 0.05 ? r2(ls * PX_TO_PT) : 0,
      _px: fsPx
    };
  }

  function collectRuns(root, c, warnings) {
    var raw = [];
    var whiteSpaceRoot = getComputedStyle(root).whiteSpace || 'normal';

    (function visit(el, preformatted) {
      var cs = getComputedStyle(el);
      var ws = cs.whiteSpace || 'normal';
      var pre = preformatted || /^pre/.test(ws);
      var tt = cs.textTransform;
      var node;
      for (node = el.firstChild; node; node = node.nextSibling) {
        if (node.nodeType === 3) {
          var t = node.nodeValue;
          if (!t) continue;
          raw.push({ text: t, el: el, cs: cs, pre: pre, tt: tt });
        } else if (node.nodeType === 1) {
          var tag = node.tagName;
          if (tag === 'BR') { raw.push({ br: true }); continue; }
          var ccs = getComputedStyle(node);
          if (isHidden(ccs)) continue;
          if (isReplaced(node)) continue;
          visit(node, pre);
        }
      }
    })(root, /^pre/.test(whiteSpaceRoot));

    // 归一化：折叠空白 / text-transform / <br> -> \n
    var runs = [];
    for (var i = 0; i < raw.length; i++) {
      var item = raw[i];
      if (item.br) {
        if (runs.length) runs[runs.length - 1].text += '\n';
        continue;
      }
      var text = item.text;
      if (!item.pre) text = text.replace(/[\t\n\r ]+/g, ' ');
      else text = text.replace(/\r\n?/g, '\n');
      text = applyTextTransform(text, item.tt);
      if (!text) continue;
      var style = runStyleOf(item.el, item.cs, c);
      if (!style) continue;
      var prev = runs[runs.length - 1];
      if (prev && prev.styleKey === styleKey(style)) {
        prev.text += text;
      } else {
        runs.push({ text: text, style: style, styleKey: styleKey(style) });
      }
    }

    // 去掉首尾空白
    if (runs.length) {
      runs[0].text = runs[0].text.replace(/^[\s\u00a0]+/, '');
      runs[runs.length - 1].text = runs[runs.length - 1].text.replace(/[\s\u00a0]+$/, '');
    }
    runs = runs.filter(function (r) { return r.text.length > 0; });
    return runs;
  }

  function styleKey(s) {
    return [s.fontFace, s.fontSize, s.color, s.transparency, s.bold, s.italic, s.underline,
      s.strike, s.charSpacing].join('|');
  }

  function mapAlign(cs) {
    var a = (cs.textAlign || 'left').toLowerCase();
    if (a === 'start' || a === 'left' || a === 'justify-all') {
      return cs.direction === 'rtl' && a === 'start' ? 'right' : 'left';
    }
    if (a === 'end') return cs.direction === 'rtl' ? 'left' : 'right';
    if (a === 'center' || a === 'centre') return 'center';
    if (a === 'right') return 'right';
    if (a === 'justify') return 'justify';
    return 'left';
  }

  function lineSpacingPt(cs, c) {
    var lh = cs.lineHeight;
    if (!lh || lh === 'normal') return 0;
    var px = parseFloat(lh);
    if (!isFinite(px) || px <= 0) return 0;
    return r2(px * PX_TO_PT);
  }

  /* ---- 渐变解析 ------------------------------------------------ */

  function parseGradientStops(bgImage) {
    if (!bgImage || !/gradient/i.test(bgImage)) return null;
    var layers = splitTopLevel(bgImage, ',');
    for (var i = 0; i < layers.length; i++) {
      var layer = layers[i].trim();
      if (!/gradient\(/i.test(layer)) continue;
      var open = layer.indexOf('(');
      var body = layer.slice(open + 1, layer.lastIndexOf(')'));
      var parts = splitTopLevel(body, ',');
      var stops = [];
      for (var j = 0; j < parts.length; j++) {
        var p = parts[j].trim();
        var m = /^(.*?)\s+(-?[\d.]+)%$/.exec(p);
        var colStr = m ? m[1] : p;
        var pos = m ? parseFloat(m[2]) : null;
        var col = parseColor(colStr);
        if (!col) continue;
        stops.push({ hex: col.hex, rgba: col, pos: pos });
      }
      if (stops.length) return stops;
    }
    return null;
  }

  function averageGradientColor(bgImage) {
    var stops = parseGradientStops(bgImage);
    if (!stops || !stops.length) return null;
    var r = 0, g = 0, b = 0, a = 0;
    for (var i = 0; i < stops.length; i++) {
      r += parseInt(stops[i].hex.slice(0, 2), 16);
      g += parseInt(stops[i].hex.slice(2, 4), 16);
      b += parseInt(stops[i].hex.slice(4, 6), 16);
      a += stops[i].rgba.a;
    }
    var n = stops.length;
    return { hex: hex2(r / n) + hex2(g / n) + hex2(b / n), a: a / n };
  }

  function gradientAngleDeg(prefix, w, h) {
    var s = (prefix || '').trim().toLowerCase();
    if (!s) return 180; // 默认 to bottom
    var m = /^(-?[\d.]+)(deg|grad|rad|turn)$/.exec(s);
    if (m) {
      var v = parseFloat(m[1]);
      if (m[2] === 'grad') return v * 0.9;
      if (m[2] === 'rad') return v * 180 / Math.PI;
      if (m[2] === 'turn') return v * 360;
      return v;
    }
    if (/^to\s/.test(s)) {
      var dirs = s.slice(3).trim().split(/\s+/);
      var vert = dirs.indexOf('top') >= 0 ? 'top' : (dirs.indexOf('bottom') >= 0 ? 'bottom' : '');
      var horz = dirs.indexOf('right') >= 0 ? 'right' : (dirs.indexOf('left') >= 0 ? 'left' : '');
      if (vert === 'top' && horz) {
        var ang = Math.atan2(horz === 'right' ? w : -w, h) * 180 / Math.PI;
        return 90 - ang;
      }
      if (vert === 'bottom' && horz) {
        var ang2 = Math.atan2(horz === 'right' ? w : -w, -h) * 180 / Math.PI;
        return 90 - ang2;
      }
      if (vert === 'top') return 0;
      if (vert === 'bottom') return 180;
      if (horz === 'right') return 90;
      if (horz === 'left') return 270;
    }
    return 180;
  }

  /**
   * 把 linear-gradient 栅格化成 canvas（用于 slide 背景 / 大面积蒙版层）。
   * @returns {string|null} data URL（image/png）
   */
  function rasterizeGradient(bgImage, cssW, cssH, maxEdge) {
    if (!bgImage || !/linear-gradient/i.test(bgImage)) return null;
    var layers = splitTopLevel(bgImage, ',');
    var outW = Math.max(2, Math.min(Math.round(cssW), maxEdge || 800));
    var outH = Math.max(2, Math.round(outW * cssH / Math.max(1, cssW)));
    var cv = document.createElement('canvas');
    cv.width = outW; cv.height = outH;
    var ctx = cv.getContext('2d');
    var drew = false;

    // CSS 中排在后面的层在底层，先画
    for (var i = layers.length - 1; i >= 0; i--) {
      var layer = layers[i].trim();
      var m = /^linear-gradient\((.*)\)$/i.exec(layer);
      if (!m) continue;
      var parts = splitTopLevel(m[1], ',');
      var angle = gradientAngleDeg(parts[0].replace(/^(linear-gradient)\(?/i, ''), outW, outH);
      var isAngle = /^(-?[\d.]+(deg|grad|rad|turn)|to\s)/i.test(parts[0].trim());
      var stopParts = isAngle ? parts.slice(1) : parts;
      var stops = [];
      for (var j = 0; j < stopParts.length; j++) {
        var sp = stopParts[j].trim();
        var mm = /^(.*?)\s+(-?[\d.]+)%$/.exec(sp);
        var colStr = mm ? mm[1] : sp;
        var pos = mm ? parseFloat(mm[2]) : null;
        var rgba = cssColorToRGBA(colStr);
        if (!rgba) continue;
        stops.push({ rgba: rgba, pos: pos });
      }
      if (!stops.length) continue;
      // 补齐缺省位置
      if (stops[0].pos === null) stops[0].pos = 0;
      if (stops[stops.length - 1].pos === null) stops[stops.length - 1].pos = 100;
      for (var k = 0; k < stops.length; k++) {
        if (stops[k].pos !== null) continue;
        var prev = k - 1, next = k;
        while (next < stops.length && stops[next].pos === null) next++;
        var p0 = stops[prev].pos, p1 = stops[next] ? stops[next].pos : 100;
        var steps = next - prev;
        stops[k].pos = p0 + (p1 - p0) * ((k - prev) / steps);
      }
      // 角度 -> 线段端点（CSS: 0deg = to top，顺时针）
      var rad = angle * Math.PI / 180;
      var dirX = Math.sin(rad), dirY = -Math.cos(rad);
      var len = Math.abs(outW * dirX) + Math.abs(outH * dirY);
      var cx = outW / 2, cy = outH / 2;
      var x0 = cx - dirX * len / 2, y0 = cy - dirY * len / 2;
      var x1 = cx + dirX * len / 2, y1 = cy + dirY * len / 2;
      var g = ctx.createLinearGradient(x0, y0, x1, y1);
      for (var s2 = 0; s2 < stops.length; s2++) {
        var c2 = stops[s2].rgba;
        g.addColorStop(clamp(stops[s2].pos / 100, 0, 1),
          'rgba(' + c2.r + ',' + c2.g + ',' + c2.b + ',' + c2.a + ')');
      }
      ctx.fillStyle = g;
      ctx.fillRect(0, 0, outW, outH);
      drew = true;
    }
    return drew ? cv.toDataURL('image/png') : null;
  }

  /* ---- 图片处理 ------------------------------------------------ */

  var _imgInfoCache = new Map();

  function absoluteUrl(url) {
    if (!url) return '';
    if (/^(data:|blob:)/i.test(url)) return url;
    try { return new URL(url, document.baseURI).href; } catch (e) { return url; }
  }

  function extractBgUrls(bgImage) {
    if (!bgImage || bgImage === 'none') return [];
    var out = [];
    var re = /url\((['"]?)([^'")]+)\1\)/g, m;
    while ((m = re.exec(bgImage))) out.push(m[2]);
    return out;
  }

  function loadHTMLImage(url) {
    return new Promise(function (resolve, reject) {
      var key = url;
      if (_imgInfoCache.has(key)) {
        var cached = _imgInfoCache.get(key);
        if (cached instanceof Error) return reject(cached);
        return resolve(cached);
      }
      var img = new Image();
      // file:// 下设 crossOrigin 会让请求直接失败（origin 'null' 不被允许），
      // 只在 http(s) 下开启；file:// 的 canvas 污染另外兜住。
      if (/^https?:/i.test(url)) img.crossOrigin = 'anonymous';
      var done = false;
      var timer = setTimeout(function () {
        if (done) return;
        done = true;
        _imgInfoCache.set(key, new Error('image timeout: ' + url));
        reject(new Error('image timeout: ' + url));
      }, 6000);
      img.onload = function () {
        if (done) return;
        done = true; clearTimeout(timer);
        _imgInfoCache.set(key, img);
        resolve(img);
      };
      img.onerror = function () {
        if (done) return;
        // 去掉 crossOrigin 再试一次（同源/无 CORS 头的情况仍可绘制，只是可能污染 canvas）
        var img2 = new Image();
        img2.onload = function () {
          done = true; clearTimeout(timer);
          _imgInfoCache.set(key, img2);
          resolve(img2);
        };
        img2.onerror = function () {
          done = true; clearTimeout(timer);
          var err = new Error('image load failed: ' + url);
          _imgInfoCache.set(key, err);
          reject(err);
        };
        img2.src = url;
      };
      img.src = url;
    });
  }

  function parseObjectPosition(str, freeW, freeH) {
    // 返回 {px, py}，0..1
    var s = (str || '50% 50%').trim().split(/\s+/);
    if (s.length === 1) s = [s[0], '50%'];
    function axis(v, free) {
      v = String(v).trim().toLowerCase();
      if (v === 'center') return 0.5;
      if (v === 'left' || v === 'top') return 0;
      if (v === 'right' || v === 'bottom') return 1;
      if (/%$/.test(v)) return clamp(parseFloat(v) / 100, 0, 1);
      if (/px$/.test(v) && free > 0) return clamp(parseFloat(v) / free, 0, 1);
      return 0.5;
    }
    return { px: axis(s[0], freeW), py: axis(s[1], freeH) };
  }

  /**
   * 生成可直接塞进 pptx 的图片 payload。
   * @returns {Promise<{data:string, w:number, h:number}|null>}  w/h 是图片像素比（用于 pptx 定位，可选）
   */
  function prepareImage(url, boxW, boxH, fit, objPos, roundPx, c) {
    var abs = absoluteUrl(url);
    return loadHTMLImage(abs).then(function (img) {
      var nw = img.naturalWidth || img.width;
      var nh = img.naturalHeight || img.height;
      if (!nw || !nh) return null;

      fit = (fit || 'fill').toLowerCase();
      var sx = 0, sy = 0, sw = nw, sh = nh;

      if (fit === 'cover') {
        var scale = Math.max(boxW / nw, boxH / nh);
        sw = Math.min(nw, boxW / scale);
        sh = Math.min(nh, boxH / scale);
        var pos = parseObjectPosition(objPos, nw - sw, nh - sh);
        sx = (nw - sw) * pos.px;
        sy = (nh - sh) * pos.py;
      } else if (fit === 'contain' || fit === 'scale-down' || fit === 'none') {
        sx = 0; sy = 0; sw = nw; sh = nh;
      } // fill: 整图拉伸

      var maxEdge = c.maxImageEdge;
      var outScale = Math.min(1, maxEdge / Math.max(sw, sh));
      var ow = Math.max(1, Math.round(sw * outScale));
      var oh = Math.max(1, Math.round(sh * outScale));

      var cv = document.createElement('canvas');
      cv.width = ow; cv.height = oh;
      var ctx = cv.getContext('2d');
      var rounded = roundPx && roundPx > 3;
      if (rounded) {
        var r = Math.min(roundPx * outScale, Math.min(ow, oh) / 2);
        roundRectPath(ctx, 0, 0, ow, oh, r);
        ctx.clip();
      }
      var useJpeg = !rounded && ow * oh > 120000 && !/\.(png|gif|svg|webp)(\?|#|$)/i.test(abs);
      if (useJpeg) { ctx.fillStyle = '#ffffff'; ctx.fillRect(0, 0, ow, oh); }
      ctx.drawImage(img, sx, sy, sw, sh, 0, 0, ow, oh);

      var data;
      try {
        data = cv.toDataURL(useJpeg ? 'image/jpeg' : 'image/png', useJpeg ? 0.92 : undefined);
      } catch (e) {
        // canvas 被污染 —— 典型场景：用户双击用 file:// 打开页面，
        // 浏览器禁止读取本地图片像素。此时宁可不放图，也不能塞坏数据。
        _blockedImages++;
        return null;
      }
      if (!data || data.indexOf('base64,') < 0) { _blockedImages++; return null; }
      return { data: data.replace(/^data:/, ''), w: ow, h: oh };
    }).catch(function (err) {
      wlog('image failed', url, err && err.message);
      return null;
    });
  }

  function roundRectPath(ctx, x, y, w, h, r) {
    r = Math.max(0, Math.min(r, Math.min(w, h) / 2));
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.arcTo(x + w, y, x + w, y + h, r);
    ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r);
    ctx.arcTo(x, y, x + w, y, r);
    ctx.closePath();
  }

  /* ============================================================ 舞台缩放 = 1 */

  function withScale1(c, fn) {
    var deck = global.__deck;
    if (deck && typeof deck.withScale1 === 'function') {
      return Promise.resolve().then(function () {
        return deck.withScale1(fn);
      }).catch(function (err) {
        wlog('__deck.withScale1 failed, fallback to manual', err);
        return manualWithScale1(c, fn);
      });
    }
    return manualWithScale1(c, fn);
  }

  function manualWithScale1(c, fn) {
    var restore = forceScale1(c);
    var out;
    try { out = fn(); } catch (e) { restore(); throw e; }
    if (out && typeof out.then === 'function') {
      return out.then(function (v) { restore(); return v; },
        function (e) { restore(); throw e; });
    }
    restore();
    return out;
  }

  function forceScale1(c) {
    var saved = [];
    var seen = new Set();
    var slides = document.querySelectorAll(c.slideSelector);
    var first = slides[0];
    var node = first;
    while (node && node.nodeType === 1) {
      if (!seen.has(node)) {
        seen.add(node);
        var cs = getComputedStyle(node);
        if ((cs.transform && cs.transform !== 'none') || (cs.zoom && cs.zoom !== '1' && cs.zoom !== 'normal')) {
          saved.push({ el: node, style: node.getAttribute('style'), hadAttr: node.hasAttribute('style') });
          node.style.setProperty('transform', 'none', 'important');
          node.style.setProperty('zoom', '1', 'important');
          node.style.setProperty('transition', 'none', 'important');
        }
      }
      node = node.parentElement;
    }
    // 常见舞台选择器兜底（即使不含 .slide 祖先链）
    ['.stage', '.deck-stage', '.deck-viewport', '#stage'].forEach(function (sel) {
      var els = document.querySelectorAll(sel);
      for (var i = 0; i < els.length; i++) {
        var el = els[i];
        if (seen.has(el)) continue;
        var cs = getComputedStyle(el);
        if (cs.transform && cs.transform !== 'none') {
          seen.add(el);
          saved.push({ el: el, style: el.getAttribute('style'), hadAttr: el.hasAttribute('style') });
          el.style.setProperty('transform', 'none', 'important');
          el.style.setProperty('transition', 'none', 'important');
        }
      }
    });
    return function restore() {
      for (var i = saved.length - 1; i >= 0; i--) {
        var s = saved[i];
        if (s.style === null) s.el.removeAttribute('style');
        else s.el.setAttribute('style', s.style);
      }
    };
  }

  /* ============================================================ 测量 */

  function forceRendered(el) {
    var saved = null;
    var cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden') {
      saved = el.getAttribute('style');
      el.style.setProperty('display', 'block', 'important');
      el.style.setProperty('visibility', 'visible', 'important');
      el.style.setProperty('opacity', '1', 'important');
      void el.offsetHeight;
    }
    return function restore() {
      if (saved === null && getComputedStyle(el).display !== 'none') return;
      if (saved === null) el.removeAttribute('style');
      else el.setAttribute('style', saved);
    };
  }

  function collectSlides(c) {
    return [].slice.call(document.querySelectorAll(c.slideSelector));
  }

  async function measureDeck(slideEls, c) {
    var models = [];
    for (var i = 0; i < slideEls.length; i++) {
      models.push(await measureSlide(slideEls[i], i, c));
    }
    return models;
  }

  async function measureSlide(slideEl, index, c) {
    var warnings = [];
    var restoreVisible = forceRendered(slideEl);
    var rect = slideEl.getBoundingClientRect();
    if (rect.width < 8 || rect.height < 8) {
      restoreVisible();
      warnings.push('slide#' + index + ' 尺寸为 0，已跳过');
      return { index: index, title: '', background: null, items: [], warnings: warnings };
    }
    var kx = DESIGN_W / rect.width;
    var ky = DESIGN_H / rect.height;
    if (Math.abs(kx - 1) > 0.002) {
      wlog('slide#' + index + ' 舞台缩放未还原（宽 ' + rect.width + '），已按比例归一化 kx=' + kx.toFixed(3));
    }

    var ctx = {
      slideEl: slideEl,
      rect: rect,
      kx: kx,
      ky: ky,
      c: c,
      index: index,
      warnings: warnings,
      items: [],
      depth: 0
    };

    var background = await resolveSlideBackground(slideEl, ctx);

    var kids = slideEl.children;
    for (var i = 0; i < kids.length; i++) {
      await walk(kids[i], ctx, 1);
    }
    restoreVisible();

    return {
      index: index,
      title: slideEl.getAttribute('data-title') || slideEl.id || ('Slide ' + (index + 1)),
      background: background,
      items: ctx.items,
      warnings: warnings
    };
  }

  function toDesign(r, ctx, useContentBox) {
    return {
      x: r2((r.left - ctx.rect.left) * ctx.kx),
      y: r2((r.top - ctx.rect.top) * ctx.ky),
      w: r2(r.width * ctx.kx),
      h: r2(r.height * ctx.ky)
    };
  }

  function slideBackgroundColor(slideEl) {
    var cs = getComputedStyle(slideEl);
    var col = parseColor(cs.backgroundColor);
    return col;
  }

  async function resolveSlideBackground(slideEl, ctx) {
    var cs = getComputedStyle(slideEl);
    var bgImage = cs.backgroundImage;
    var out = { color: null, data: null };

    if (bgImage && bgImage !== 'none' && /gradient/i.test(bgImage)) {
      var url = rasterizeGradient(bgImage, DESIGN_W / 2, DESIGN_H / 2, 800);
      if (url) { out.data = url.replace(/^data:/, ''); return out; }
      var avg = averageGradientColor(bgImage);
      if (avg) out.color = avg.hex;
      return out;
    }
    var urls = extractBgUrls(bgImage);
    if (urls.length) {
      var payload = await prepareImage(urls[0], DESIGN_W, DESIGN_H, 'cover', cs.backgroundPosition, 0, ctx.c);
      if (payload && payload.data) { out.data = payload.data; return out; }
    }
    var col = parseColor(cs.backgroundColor);
    if (col) { out.color = col.hex; if (col.a < 0.995) out.alpha = col.a; return out; }

    // 幻灯片自身没有背景：沿用祖先（.deck/.stage/body）的底色，
    // 否则整页会变成白底，和浏览器里看到的纸色不一致。
    var inherited = inheritedBackdrop(slideEl, ctx);
    if (inherited) out.color = inherited.hex;
    return out;
  }

  function inheritedBackdrop(el, ctx) {
    var node = el.parentElement;
    var guard = 0;
    while (node && guard++ < 24) {
      var cs = getComputedStyle(node);
      if (cs.backgroundImage && cs.backgroundImage !== 'none' && /gradient|url/.test(cs.backgroundImage)) {
        return null; // 祖先是有图/渐变的复杂背景，不猜
      }
      var col = parseColor(cs.backgroundColor);
      if (col && col.a >= 0.5) return col;
      node = node.parentElement;
    }
    var bodyCol = parseColor(getComputedStyle(document.body).backgroundColor);
    if (bodyCol && bodyCol.a >= 0.5) return bodyCol;
    var htmlCol = parseColor(getComputedStyle(document.documentElement).backgroundColor);
    return htmlCol && htmlCol.a >= 0.5 ? htmlCol : null;
  }

  /* ---- 走查 ---------------------------------------------------- */

  async function walk(el, ctx, depth) {
    if (depth > 48) return;
    var c = ctx.c;
    if (el.nodeType !== 1) return;

    if (el.hasAttribute && el.hasAttribute('data-pptx-skip')) return;
    if (c.skipSelector && el.matches && el.matches(c.skipSelector)) return;

    var cs = getComputedStyle(el);
    if (isHidden(cs)) return;
    var opacity = parseFloat(cs.opacity);
    if (isFinite(opacity) && opacity < 0.08) return;

    var rect = el.getBoundingClientRect();
    if (rect.width <= 0.5 && rect.height <= 0.5) return;

    // 完全在幻灯片外
    var sr = ctx.rect;
    if (rect.right <= sr.left + 0.5 || rect.left >= sr.right - 0.5 ||
        rect.bottom <= sr.top + 0.5 || rect.top >= sr.bottom - 0.5) {
      return;
    }

    // 1) 背景色 / 边框 -> 形状
    emitBackgroundShape(el, cs, ctx, rect);

    // 1.5) ::before / ::after 纯色装饰（下划线、小短线…）
    emitPseudoElement(el, cs, ctx, '::before');
    emitPseudoElement(el, cs, ctx, '::after');

    // 2) background-image -> 图片
    await emitBackgroundImage(el, cs, ctx, rect);

    // 3) 图片/替元素
    if (el.tagName === 'IMG') {
      await emitImgElement(el, cs, ctx, rect);
      return;
    }
    if (isReplaced(el)) {
      if (el.tagName === 'SVG' || el.tagName === 'svg') await emitInlineSvg(el, ctx, rect);
      return;
    }

    // 4) 文本块
    if (isTextBlock(el)) {
      await emitTextBlock(el, cs, ctx, rect);
      return;
    }

    // 5) 递归子元素
    var kids = el.children;
    for (var i = 0; i < kids.length; i++) {
      await walk(kids[i], ctx, depth + 1);
    }

    // 6) 混合内容：flex/inline 容器里的「裸文本」匿名盒
    emitDirectTextNodes(el, cs, ctx);
  }

  /**
   * 元素里直接挂着的文本节点（flex 容器里会变成「匿名 flex item」）。
   * 关键：一个容器里可能有 **多段** 裸文本（被 <strong> 等元素隔开），
   * 每段是独立的匿名盒，必须各自定位，否则会挤到一起压住中间的元素。
   */
  function emitDirectTextNodes(el, cs, ctx) {
    var groups = [];
    var cur = [];
    for (var n = el.firstChild; n; n = n.nextSibling) {
      if (n.nodeType === 3) {
        if (n.nodeValue && n.nodeValue.trim()) cur.push(n);
        else if (cur.length) cur.push(n);      // 组内空白保留
      } else if (n.nodeType === 1) {
        if (cur.length) { groups.push(cur); cur = []; }
      }
    }
    if (cur.length) groups.push(cur);
    if (!groups.length) return;

    var style = runStyleOf(el, cs, ctx.c);
    if (!style) return;

    for (var g = 0; g < groups.length; g++) {
      var nodes = groups[g];
      var raw = '';
      var rect = null;
      for (var i = 0; i < nodes.length; i++) {
        var r = null;
        try {
          var range = document.createRange();
          range.selectNodeContents(nodes[i]);
          r = range.getBoundingClientRect();
        } catch (e) { r = null; }
        if (r && r.width > 0.5 && r.height > 0.5) {
          if (rect === null) {
            rect = { left: r.left, top: r.top, right: r.right, bottom: r.bottom };
          } else {
            rect.left = Math.min(rect.left, r.left);
            rect.top = Math.min(rect.top, r.top);
            rect.right = Math.max(rect.right, r.right);
            rect.bottom = Math.max(rect.bottom, r.bottom);
          }
        }
        raw += nodes[i].nodeValue;
      }
      var txt = raw.replace(/[\t\n\r ]+/g, ' ');
      if (!txt.trim() || !rect) continue;
      var box = {
        left: rect.left,
        top: rect.top,
        right: rect.right,
        bottom: rect.bottom,
        width: rect.right - rect.left,
        height: rect.bottom - rect.top
      };
      emitTextItem(el, cs, ctx, box, {
        runs: [{ text: txt, style: style, styleKey: styleKey(style) }],
        forceLeft: true,
        forceNoWrap: true
      });
    }
  }

  /**
   * 伪元素装饰（只处理纯色 background-color 的简单情况）
   *  - position:absolute -> 用 left/right/top/bottom + 实际 width/height 反推
   *  - flex item        -> ::before 贴内容左、::after 贴内容右，垂直按 align-items
   */
  function emitPseudoElement(el, cs, ctx, which) {
    var ps;
    try { ps = getComputedStyle(el, which); } catch (e) { return; }
    if (!ps) return;
    var content = ps.content;
    if (!content || content === 'none' || content === 'normal') return;
    if (ps.display === 'none' || ps.visibility === 'hidden') return;
    var op = parseFloat(ps.opacity);
    if (isFinite(op) && op < 0.05) return;

    var bg = parseColor(ps.backgroundColor);
    if (!bg || bg.a < 0.05) return;          // 渐变/图片伪元素跳过（如纸张网点纹理）
    var w = cssPx(ps.width), h = cssPx(ps.height);
    if (w < 0.5 || h < 0.5) return;

    var r = el.getBoundingClientRect();
    var bl = cssPx(cs.borderLeftWidth), bt = cssPx(cs.borderTopWidth);
    var brw = cssPx(cs.borderRightWidth), bbw = cssPx(cs.borderBottomWidth);
    var padLeft = r.left + bl, padTop = r.top + bt;
    var padRight = r.right - brw, padBottom = r.bottom - bbw;

    var x = null, y = null;
    var pos = ps.position;
    if (pos === 'absolute' || pos === 'fixed') {
      var L = ps.left, R = ps.right, T = ps.top, B = ps.bottom;
      if (L !== 'auto') x = padLeft + cssPx(L);
      else if (R !== 'auto') x = padRight - cssPx(R) - w;
      if (T !== 'auto') y = padTop + cssPx(T);
      else if (B !== 'auto') y = padBottom - cssPx(B) - h;
      if (x === null) x = padLeft + cssPx(cs.paddingLeft);
      if (y === null) y = padTop + cssPx(cs.paddingTop);
    } else {
      var cLeft = padLeft + cssPx(cs.paddingLeft);
      var cTop = padTop + cssPx(cs.paddingTop);
      var cW = (padRight - padLeft) - cssPx(cs.paddingLeft) - cssPx(cs.paddingRight);
      var cH = (padBottom - padTop) - cssPx(cs.paddingTop) - cssPx(cs.paddingBottom);
      var isFlex = /flex/.test(cs.display);
      if (!isFlex) return;                    // 其它流内伪元素位置不可靠，跳过
      x = (which === '::before') ? cLeft : cLeft + cW - w;
      if (/center/.test(cs.alignItems)) y = cTop + (cH - h) / 2;
      else if (/end|flex-end/.test(cs.alignItems)) y = cTop + cH - h;
      else y = cTop;
    }

    var boxRect = {
      left: x, top: y, width: w, height: h, right: x + w, bottom: y + h
    };
    var box = toDesign(boxRect, ctx);
    if (box.w < 0.5 || box.h < 0.5) return;
    var radius = Math.max(
      cssPx(ps.borderTopLeftRadius), cssPx(ps.borderTopRightRadius),
      cssPx(ps.borderBottomRightRadius), cssPx(ps.borderBottomLeftRadius)
    );
    ctx.items.push({
      kind: 'shape',
      shape: radius >= 1 ? 'roundRect' : 'rect',
      box: box,
      fill: bg.hex,
      fillAlpha: bg.a,
      rectRadius: Math.min(radius, Math.min(box.w, box.h) / 2) * PX_TO_IN,
      line: null,
      name: which.replace('::', 'pseudo-')
    });
  }

  function effectiveBackdrop(el, ctx) {
    var node = el.parentElement;
    var guard = 0;
    while (node && guard++ < 40) {
      if (node === ctx.slideEl) {
        var sb = slideBackgroundColor(node);
        return sb ? sb : null;
      }
      var cs = getComputedStyle(node);
      if (cs.backgroundImage && cs.backgroundImage !== 'none') return null;
      var col = parseColor(cs.backgroundColor);
      if (col && col.a >= 0.98) return col;
      node = node.parentElement;
    }
    return null;
  }

  function hasDecorativeFilter(cs) {
    var f = cs.filter || 'none';
    return /blur|drop-shadow|brightness|contrast|saturate|hue-rotate/i.test(f);
  }

  function emitBackgroundShape(el, cs, ctx, rect) {
    if (el === ctx.slideEl) return;
    if (hasDecorativeFilter(cs)) return;

    var bgColor = parseColor(cs.backgroundColor);
    if (!bgColor || bgColor.a < 0.04) return;
    if (cs.backgroundImage && cs.backgroundImage !== 'none') return; // 交给图片/渐变逻辑

    var box = toDesign(rect, ctx);
    if (box.w < 0.5 || box.h < 0.5) return;

    var radii = [
      cssPx(cs.borderTopLeftRadius), cssPx(cs.borderTopRightRadius),
      cssPx(cs.borderBottomRightRadius), cssPx(cs.borderBottomLeftRadius)
    ];
    var radius = Math.max.apply(null, radii);

    var isThin = (box.w <= box.h && box.w <= ctx.c.thinRuleMax && box.h >= ctx.c.minRuleLen) ||
      (box.h <= box.w && box.h <= ctx.c.thinRuleMax && box.w >= ctx.c.minRuleLen);
    var area = box.w * box.h;
    // 小圆点（图例/圆点标记）即使面积小也要保留
    var isDot = radius >= Math.min(box.w, box.h) / 2 - 0.6 &&
      Math.min(box.w, box.h) >= 2.5 && area >= 12;
    if (!isThin && !isDot && area < ctx.c.minShapeArea) return;

    // 与父级背景同色 + 无圆角无边框 -> 视觉冗余，跳过
    var borderW = cssPx(cs.borderTopWidth);
    var hasBorder = borderW > 0.4 && /solid|dashed|dotted|double/.test(cs.borderTopStyle);
    if (!isThin && !isDot && radius < 1 && !hasBorder && bgColor.a > 0.98) {
      var back = effectiveBackdrop(el, ctx);
      if (back && back.hex === bgColor.hex) return;
    }

    var shape = 'rect';
    var rectRadius = 0;
    if (!isThin && radius >= Math.min(box.w, box.h) / 2 - 0.6 && Math.abs(box.w - box.h) <= Math.min(box.w, box.h) * 0.08) {
      shape = 'ellipse';
    } else if (!isThin && radius >= 1) {
      shape = 'roundRect';
      rectRadius = Math.min(radius, Math.min(box.w, box.h) / 2) * PX_TO_IN;
    }

    var item = {
      kind: 'shape',
      shape: shape,
      box: box,
      fill: bgColor.hex,
      fillAlpha: bgColor.a,
      rectRadius: rectRadius,
      line: null,
      name: (el.className && typeof el.className === 'string' ? el.className.split(/\s+/)[0] : el.tagName)
    };
    if (hasBorder) {
      var bc = parseColor(cs.borderTopColor) || { hex: '000000', a: 1 };
      item.line = { color: bc.hex, width: r2(borderW * PX_TO_PT), alpha: bc.a };
    }
    ctx.items.push(item);
  }

  async function emitBackgroundImage(el, cs, ctx, rect) {
    var bg = cs.backgroundImage;
    if (!bg || bg === 'none') return;
    if (el === ctx.slideEl) return;
    if (hasDecorativeFilter(cs)) return;

    var box = toDesign(rect, ctx);
    if (box.w < 4 || box.h < 4) return;

    var hasGradient = /gradient/i.test(bg);
    var urls = extractBgUrls(bg);

    if (urls.length) {
      var fit = cs.backgroundSize === 'cover' ? 'cover'
        : (cs.backgroundSize === 'contain' ? 'contain' : 'cover');
      // 多个 url 层：取第一层（最上层）
      var payload = await prepareImage(urls[0], box.w, box.h, fit, cs.backgroundPosition,
        cornerRadiusOf(cs), ctx.c);
      if (payload) {
        ctx.items.push({
          kind: 'image',
          box: box,
          data: payload.data,
          url: urls[0],
          name: 'bg-image'
        });
      }
      return;
    }

    if (hasGradient) {
      var areaRatio = (box.w * box.h) / (DESIGN_W * DESIGN_H);
      if (areaRatio >= ctx.c.bigGradientAreaRatio) {
        // 大面积蒙版层：栅格化，保证深色叠加/渐变遮罩的观感
        var url = rasterizeGradient(bg, box.w, box.h, Math.min(ctx.c.maxImageEdge, Math.round(box.w)));
        if (url) {
          ctx.items.push({ kind: 'image', box: box, data: url.replace(/^data:/, ''), name: 'gradient-overlay' });
          return;
        }
      }
      // 小面积装饰渐变：跳过（按约定）
      return;
    }
  }

  function cornerRadiusOf(cs) {
    return Math.max(
      cssPx(cs.borderTopLeftRadius), cssPx(cs.borderTopRightRadius),
      cssPx(cs.borderBottomRightRadius), cssPx(cs.borderBottomLeftRadius)
    );
  }

  function nearestClipRadius(el) {
    // 往上找 1~2 层 overflow:hidden + border-radius 的容器（图片圆角裁切）
    var node = el.parentElement, hops = 0;
    while (node && hops < 3) {
      if (node.hasAttribute && node.hasAttribute('data-pptx-skip')) break;
      var cs = getComputedStyle(node);
      if (/hidden|clip/.test(cs.overflow + ' ' + cs.overflowX)) {
        var r = cornerRadiusOf(cs);
        if (r > 3) return r;
      }
      node = node.parentElement;
      hops++;
    }
    return 0;
  }

  async function emitImgElement(el, cs, ctx, rect) {
    if (hasDecorativeFilter(cs)) return;
    var box = toDesign(rect, ctx);
    if (box.w < 2 || box.h < 2) return;

    var src = el.currentSrc || el.getAttribute('src') || '';
    if (!src) return;
    var fit = (cs.objectFit || 'fill').toLowerCase();
    var payload = await prepareImage(src, box.w, box.h, fit, cs.objectPosition,
      nearestClipRadius(el), ctx.c);
    if (!payload) {
      ctx.warnings.push('图片无法内嵌（跨域 / file:// 安全限制）：' + src);
      return;
    }
    var target = box;
    if (fit === 'contain' || fit === 'scale-down') {
      var nat = payload.w / Math.max(1, payload.h);
      var bnat = box.w / Math.max(1, box.h);
      if (nat > bnat) {
        var h = box.w / nat;
        target = { x: box.x, y: box.y + (box.h - h) / 2, w: box.w, h: h };
      } else {
        var w = box.h * nat;
        target = { x: box.x + (box.w - w) / 2, y: box.y, w: w, h: box.h };
      }
    }
    ctx.items.push({ kind: 'image', box: target, data: payload.data, url: src, name: 'img' });
  }

  var SVG_INLINE_PROPS = [
    'fill', 'fill-opacity', 'fill-rule', 'stroke', 'stroke-width', 'stroke-opacity',
    'stroke-dasharray', 'stroke-dashoffset', 'stroke-linecap', 'stroke-linejoin',
    'opacity', 'paint-order', 'transform', 'transform-origin', 'visibility',
    'font-family', 'font-size', 'font-weight', 'font-style', 'letter-spacing',
    'text-anchor', 'dominant-baseline', 'stop-color', 'stop-opacity', 'clip-path'
  ];

  function pairNodes(origRoot, cloneRoot) {
    var pairs = [];
    (function rec(o, c) {
      if (!o || !c) return;
      pairs.push([o, c]);
      var oc = o.children, cc = c.children;
      var n = Math.min(oc.length, cc.length);
      for (var i = 0; i < n; i++) rec(oc[i], cc[i]);
    })(origRoot, cloneRoot);
    return pairs;
  }

  /** 把外部 CSS 的计算样式内联进克隆的 SVG（data URL 里拿不到外部样式表） */
  function inlineSvgComputedStyles(origRoot, cloneRoot) {
    var pairs = pairNodes(origRoot, cloneRoot);
    for (var i = 0; i < pairs.length; i++) {
      var o = pairs[i][0], cl = pairs[i][1];
      if (!o || o.nodeType !== 1) continue;
      var cs;
      try { cs = getComputedStyle(o); } catch (e) { continue; }
      var decl = '';
      for (var p = 0; p < SVG_INLINE_PROPS.length; p++) {
        var prop = SVG_INLINE_PROPS[p];
        var v = cs.getPropertyValue(prop);
        if (v && v !== 'none' && v !== 'normal') decl += prop + ':' + v + ';';
      }
      var prev = cl.getAttribute('style');
      cl.setAttribute('style', decl + (prev || ''));
    }
  }

  /** SVG <text> -> 可编辑文本框（需求：A 路径尽量保留可编辑性） */
  function emitSvgTextItems(svgEl, ctx) {
    var list = svgEl.querySelectorAll('text');
    for (var i = 0; i < list.length; i++) {
      var el = list[i];
      var cs;
      try { cs = getComputedStyle(el); } catch (e) { continue; }
      if (isHidden(cs)) continue;
      var content = (el.textContent || '').replace(/[\t\n\r ]+/g, ' ').trim();
      if (!content) continue;

      // <tspan> 若各占一行（y 不同）则分行
      var tspans = el.querySelectorAll('tspan');
      if (tspans.length > 1) {
        var ys = [], lines = [];
        for (var k = 0; k < tspans.length; k++) {
          var tk = tspans[k];
          var y = tk.getAttribute('y') || tk.getAttribute('dy') || '';
          var tkText = (tk.textContent || '').trim();
          if (!tkText) continue;
          if (ys.indexOf(y) < 0 || y === '') { ys.push(y); lines.push([tkText]); }
          else lines[ys.indexOf(y)].push(tkText);
        }
        if (lines.length > 1) content = lines.map(function (l) { return l.join(' '); }).join('\n');
      }

      var r = el.getBoundingClientRect();
      if (!r.width || !r.height) continue;
      var fs = cssPx(cs.fontSize) || 16;
      var anchor = (cs.textAnchor || 'start').toLowerCase();
      var fill = parseColor(cs.fill) || { hex: '000000', a: 1 };
      var family = firstFamily(cs.fontFamily, ctx.c);
      var weight = cs.fontWeight === 'bold' ? 700 : (parseInt(cs.fontWeight, 10) || 400);
      var padY = fs * 0.16;

      var box = {
        x: r2((r.left - ctx.rect.left) * ctx.kx - 2),
        y: r2((r.top - ctx.rect.top) * ctx.ky - padY),
        w: r2(r.width * ctx.kx + 4),
        h: r2(r.height * ctx.ky + padY * 2)
      };
      if (box.w < 0.5 || box.h < 0.5) continue;

      var opts = {
        fontFace: mapFont(family, ctx.c),
        fontSize: Math.max(1, r2(fs * PX_TO_PT)),
        color: fill.hex,
        bold: weight >= 600,
        italic: /italic|oblique/.test(cs.fontStyle)
      };
      if (fill.a < 0.98) opts.transparency = Math.round((1 - fill.a) * 100);

      ctx.items.push({
        kind: 'text',
        box: box,
        runs: [{ text: content, options: opts }],
        align: anchor === 'middle' ? 'center' : (anchor === 'end' ? 'right' : 'left'),
        wrap: false,
        lineSpacing: r2(fs * 1.2 * PX_TO_PT),
        fontFace: opts.fontFace,
        fontSize: opts.fontSize,
        color: opts.color,
        name: 'svg-text'
      });
    }
  }

  async function emitInlineSvg(svgEl, ctx, rect) {
    var box = toDesign(rect, ctx);
    if (box.w < 2 || box.h < 2) return;
    var hasText = svgEl.querySelector && svgEl.querySelector('text');
    try {
      var clone = svgEl.cloneNode(true);
      inlineSvgComputedStyles(svgEl, clone);
      if (!clone.getAttribute('xmlns')) clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
      // 文本单独作为可编辑文本框输出，栅格化时去掉，避免重影
      var ts = clone.querySelectorAll('text');
      for (var i = 0; i < ts.length; i++) {
        if (ts[i].parentNode) ts[i].parentNode.removeChild(ts[i]);
      }
      var xml = new XMLSerializer().serializeToString(clone);
      var url = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(xml);
      var payload = await prepareImage(url, box.w, box.h, 'contain', '50% 50%', 0, ctx.c);
      if (payload) {
        ctx.items.push({ kind: 'image', box: box, data: payload.data, name: 'svg' });
      }
    } catch (e) {
      ctx.warnings.push('内联 SVG 无法栅格化：' + (e && e.message));
    }
    if (hasText) emitSvgTextItems(svgEl, ctx);
  }

  function emitInlineDecorations(root, ctx) {
    // 文本块内带背景色的内联子元素（高亮片）+ 它们的伪元素（下划线等）
    var kids = root.querySelectorAll('*');
    for (var i = 0; i < kids.length; i++) {
      var k = kids[i];
      var cs = getComputedStyle(k);
      if (isHidden(cs)) continue;
      emitPseudoElement(k, cs, ctx, '::before');
      emitPseudoElement(k, cs, ctx, '::after');
      var bgc = parseColor(cs.backgroundColor);
      if (!bgc || bgc.a < 0.05) continue;
      if (isReplaced(k)) continue;
      var r = k.getBoundingClientRect();
      if (r.width < 2 || r.height < 2) continue;
      var box = toDesign(r, ctx);
      var radius = cornerRadiusOf(cs);
      ctx.items.push({
        kind: 'shape',
        shape: radius >= 1 ? 'roundRect' : 'rect',
        box: box,
        fill: bgc.hex,
        fillAlpha: bgc.a,
        rectRadius: Math.min(radius, Math.min(box.w, box.h) / 2) * PX_TO_IN,
        line: null,
        name: 'inline-bg'
      });
    }
  }

  async function emitTextBlock(el, cs, ctx, rect) {
    emitInlineDecorations(el, ctx);
    var box = contentBox(el, cs);
    emitTextItem(el, cs, ctx, box, { allowInlineKids: true });
  }

  function emitTextItem(el, cs, ctx, boxRect, opts) {
    opts = opts || {};
    var c = ctx.c;
    var runs = opts.runs || collectRuns(el, c, ctx.warnings);
    if (!runs.length) return;
    var text = runs.map(function (r) { return r.text; }).join('');
    if (!text.replace(/[\s\u00a0]/g, '')) return;

    var box = toDesign(boxRect, ctx);
    if (box.w < 1 || box.h < 1) return;

    var align = opts.forceLeft ? 'left' : mapAlign(cs);
    var lh = lineSpacingPt(cs, c);
    var fsPx = runs[0].style._px || 16;
    // 单行盒子禁止换行：PowerPoint 字体度量与浏览器略有差异，
    // 允许换行会把「466.4」这种贴着文本框宽度的内容折成两行。
    var linePx = lh ? lh / PX_TO_PT : fsPx * 1.25;
    var singleLine = text.indexOf('\n') < 0 && box.h <= linePx * 1.5;
    var noWrap = !!opts.forceNoWrap || singleLine;

    var pptxRuns = [];
    for (var i = 0; i < runs.length; i++) {
      var s = runs[i].style;
      var o = {
        fontFace: s.fontFace,
        fontSize: s.fontSize,
        color: s.color,
        bold: s.bold,
        italic: s.italic,
        underline: s.underline ? { style: 'sng' } : false,
        strike: s.strike ? 'sngStrike' : undefined
      };
      if (s.charSpacing) o.charSpacing = s.charSpacing;
      if (s.transparency) o.transparency = s.transparency;
      pptxRuns.push({ text: runs[i].text, options: o });
    }

    ctx.items.push({
      kind: 'text',
      box: box,
      runs: pptxRuns,
      align: align,
      wrap: !noWrap,
      lineSpacing: lh || undefined,
      fontFace: runs[0].style.fontFace,
      fontSize: runs[0].style.fontSize,
      color: runs[0].style.color,
      name: 'text:' + (el.className && typeof el.className === 'string' ? el.className.split(/\s+/)[0] : el.tagName)
    });
  }

  /* ============================================================ 生成 PPTX */

  function buildPptx(models, c, PptxGenJS) {
    var pptx = new PptxGenJS();
    var LAYOUT = 'DECK_16x9_1600x900';
    pptx.defineLayout({ name: LAYOUT, width: DESIGN_W * PX_TO_IN, height: DESIGN_H * PX_TO_IN });
    pptx.layout = LAYOUT;
    pptx.title = c.title;
    pptx.author = c.author;
    pptx.subject = c.title;
    pptx.company = 'AI learning report';

    var SHAPE = pptx.ShapeType || {};
    var report = [];

    for (var i = 0; i < models.length; i++) {
      var m = models[i];
      var slide = pptx.addSlide();
      slide.bkgd = 'FFFFFF';
      if (m.background) {
        if (m.background.data) {
          slide.background = { data: m.background.data };
        } else if (m.background.color) {
          slide.background = { color: m.background.color };
        }
      }
      var stats = { index: m.index, title: m.title, texts: 0, images: 0, shapes: 0, chars: 0 };

      for (var j = 0; j < m.items.length; j++) {
        var it = m.items[j];
        if (it.kind === 'text') {
          var opts = {
            x: it.box.x * PX_TO_IN,
            y: it.box.y * PX_TO_IN,
            w: Math.max(0.02, it.box.w * PX_TO_IN),
            h: Math.max(0.02, it.box.h * PX_TO_IN),
            align: it.align,
            valign: 'top',
            inset: 0,
            margin: 0,
            wrap: it.wrap !== false,
            fit: 'none',
            fontFace: it.fontFace,
            fontSize: it.fontSize,
            color: it.color
          };
          if (it.lineSpacing) opts.lineSpacing = it.lineSpacing;
          try {
            slide.addText(it.runs, opts);
            stats.texts++;
            for (var r = 0; r < it.runs.length; r++) stats.chars += it.runs[r].text.length;
          } catch (e) {
            m.warnings.push('文本写入失败：' + e.message);
          }
        } else if (it.kind === 'image') {
          var imgOpts = {
            data: it.data,
            x: it.box.x * PX_TO_IN,
            y: it.box.y * PX_TO_IN,
            w: Math.max(0.02, it.box.w * PX_TO_IN),
            h: Math.max(0.02, it.box.h * PX_TO_IN)
          };
          try {
            slide.addImage(imgOpts);
            stats.images++;
          } catch (e) {
            m.warnings.push('图片写入失败：' + e.message);
          }
        } else if (it.kind === 'shape') {
          var shapeName = it.shape === 'ellipse' ? (SHAPE.ellipse || 'ellipse')
            : (it.shape === 'roundRect' ? (SHAPE.roundRect || 'roundRect') : (SHAPE.rect || 'rect'));
          var shapeOpts = {
            x: it.box.x * PX_TO_IN,
            y: it.box.y * PX_TO_IN,
            w: Math.max(0.02, it.box.w * PX_TO_IN),
            h: Math.max(0.02, it.box.h * PX_TO_IN)
          };
          if (it.fill) {
            shapeOpts.fill = it.fillAlpha < 0.995
              ? { color: it.fill, transparency: Math.round((1 - it.fillAlpha) * 100) }
              : { color: it.fill };
          } else {
            shapeOpts.fill = { color: 'FFFFFF', transparency: 100 };
          }
          if (it.line) {
            shapeOpts.line = it.line.alpha < 0.995
              ? { color: it.line.color, width: Math.max(0.25, it.line.width), transparency: Math.round((1 - it.line.alpha) * 100) }
              : { color: it.line.color, width: Math.max(0.25, it.line.width) };
          } else {
            shapeOpts.line = { color: 'FFFFFF', width: 0 };
          }
          if (it.shape === 'roundRect' && it.rectRadius) shapeOpts.rectRadius = it.rectRadius;
          try {
            slide.addShape(shapeName, shapeOpts);
            stats.shapes++;
          } catch (e) {
            m.warnings.push('形状写入失败：' + e.message);
          }
        }
      }
      report.push(stats);
    }

    return { pptx: pptx, report: report };
  }

  /* ============================================================ 依赖加载 */

  function loadScript(src) {
    return new Promise(function (resolve, reject) {
      var s = document.createElement('script');
      s.src = src;
      s.async = false;
      s.onload = function () { resolve(src); };
      s.onerror = function () { reject(new Error('无法加载 ' + src)); };
      document.head.appendChild(s);
    });
  }

  function scriptBaseDir() {
    var scripts = document.getElementsByTagName('script');
    for (var i = scripts.length - 1; i >= 0; i--) {
      var src = scripts[i].src || '';
      if (/pptx-export\.js(\?|#|$)/.test(src)) {
        return src.replace(/[^/]*(\?.*)?(#.*)?$/, '');
      }
    }
    return null;
  }

  async function ensurePptxGenJS(c) {
    if (global.PptxGenJS) return global.PptxGenJS;
    var candidates = [];
    if (c.scriptPath) candidates.push(c.scriptPath);
    var base = scriptBaseDir();
    var paths = ['vendor/pptxgen.bundle.js', '../vendor/pptxgen.bundle.js', '../../vendor/pptxgen.bundle.js'];
    if (base) {
      for (var i = 0; i < paths.length; i++) candidates.push(base + paths[i]);
    }
    candidates.push('vendor/pptxgen.bundle.js');
    candidates.push('/vendor/pptxgen.bundle.js');

    var lastErr = null;
    for (var k = 0; k < candidates.length; k++) {
      var url = candidates[k];
      var norm = absoluteUrl(url);
      if (ensurePptxGenJS._tried && ensurePptxGenJS._tried[norm]) continue;
      (ensurePptxGenJS._tried = ensurePptxGenJS._tried || {})[norm] = 1;
      try {
        await loadScript(url);
        if (global.PptxGenJS) return global.PptxGenJS;
      } catch (e) {
        lastErr = e;
      }
    }
    throw new Error('未能加载 PptxGenJS（请确认 ' + (base || './') + 'vendor/pptxgen.bundle.js 存在）。' +
      (lastErr ? ' 最后一次错误：' + lastErr.message : ''));
  }

  /* ============================================================ 主流程 */

  var running = false;

  var _FORCE_CSS_ID = '__pptx_export_force_css';
  var _blockedImages = 0;

  function raf2() {
    return new Promise(function (resolve) {
      if (typeof requestAnimationFrame !== 'function') return setTimeout(resolve, 16);
      requestAnimationFrame(function () {
        requestAnimationFrame(function () { resolve(); });
      });
    });
  }

  /**
   * 进入「导出模式」：让每一屏都处于**可测量、可截图**的最终静态状态。
   *
   * 为什么必须做：`.slide` 的基态是 `opacity:0; visibility:hidden`，而且
   * 各元素的入场动画（.reveal / .stagger > * / .frag / [data-anim-hidden]）
   * 只在「当前激活屏」上跑过，非激活屏的元素还停在 `opacity:0`
   * —— 逐屏遍历时它们会被当成不可见元素整个跳过，导致 2..N 页全空。
   *
   * 做法：加 deck 约定的 `body.exporting`（deck.css 里已写好全部终态），
   * 再叠一层自带兜底 CSS（换一个项目、没有 .exporting 样式时也能用）。
   * 返回 restore()。
   */
  function enterExportMode() {
    var body = document.body;
    var hadExporting = body.classList.contains('exporting');
    body.classList.add('exporting');
    body.classList.add('pptx-exporting');

    var styleEl = document.getElementById(_FORCE_CSS_ID);
    if (!styleEl) {
      styleEl = document.createElement('style');
      styleEl.id = _FORCE_CSS_ID;
      styleEl.textContent = [
        'body.pptx-exporting .reveal,',
        'body.pptx-exporting .stagger > *,',
        'body.pptx-exporting .frag,',
        'body.pptx-exporting [data-anim-hidden],',
        'body.pptx-exporting .ring-dot {',
        '  opacity:1 !important; visibility:visible !important;',
        '  transform:none !important; filter:none !important;',
        '}',
        'body.pptx-exporting section.slide {',
        '  opacity:1 !important; visibility:visible !important; transform:none !important;',
        '}',
        'body.pptx-exporting *, body.pptx-exporting *::before, body.pptx-exporting *::after {',
        '  transition:none !important; animation-duration:0s !important;',
        '  animation-delay:0s !important; animation-iteration-count:1 !important;',
        '}'
      ].join('\n');
      document.head.appendChild(styleEl);
    }

    return function restoreExportMode() {
      var el = document.getElementById(_FORCE_CSS_ID);
      if (el && el.parentNode) el.parentNode.removeChild(el);
      body.classList.remove('pptx-exporting');
      if (!hadExporting) body.classList.remove('exporting');
    };
  }

  /**
   * 导出结果提示（非阻塞 toast）。
   * file:// 打开时浏览器禁止读本地图片像素，只能导出文字/色块，
   * 必须明确告诉用户，而不是静默产出一份缺图的文件。
   */
  function showNotice(title, lines) {
    try {
      var old = document.getElementById('__pptx_export_notice');
      if (old && old.parentNode) old.parentNode.removeChild(old);

      var box = document.createElement('div');
      box.id = '__pptx_export_notice';
      box.setAttribute('role', 'alert');
      box.style.cssText = [
        'position:fixed', 'right:24px', 'bottom:24px', 'z-index:2147483647',
        'max-width:460px', 'padding:16px 18px', 'border-radius:14px',
        'background:#1C1917', 'color:#FAFAF9',
        'font:14px/1.65 "PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif',
        'box-shadow:0 18px 48px rgba(0,0,0,.38)', 'border:1px solid rgba(255,255,255,.14)'
      ].join(';');

      var h = document.createElement('div');
      h.style.cssText = 'font-weight:700;font-size:15px;margin-bottom:8px;color:#FBBF24';
      h.textContent = title;
      box.appendChild(h);

      for (var i = 0; i < lines.length; i++) {
        var p = document.createElement('p');
        p.style.cssText = 'margin:0 0 6px;color:#D6D3D1';
        p.textContent = lines[i];
        box.appendChild(p);
      }

      var close = document.createElement('button');
      close.type = 'button';
      close.textContent = '知道了';
      close.style.cssText = [
        'margin-top:8px', 'padding:6px 14px', 'border-radius:999px', 'cursor:pointer',
        'border:1px solid rgba(255,255,255,.28)', 'background:transparent',
        'color:#FAFAF9', 'font:inherit', 'font-size:13px'
      ].join(';');
      close.addEventListener('click', function () {
        if (box.parentNode) box.parentNode.removeChild(box);
      });
      box.appendChild(close);

      document.body.appendChild(box);
      setTimeout(function () {
        if (box.parentNode) box.parentNode.removeChild(box);
      }, 6000);
    } catch (e) { /* 提示失败不影响导出 */ }
  }

  function setStatus(status, detail) {
    document.body.setAttribute('data-pptx-export', status);
    try {
      document.dispatchEvent(new CustomEvent('pptx:status', {
        detail: { status: status, detail: detail || null }
      }));
    } catch (e) { /* CustomEvent 不可用时忽略 */ }
  }

  async function deckExportPptx(options) {
    var opts = options || {};
    var c = cfg();
    if (opts.fileName) c.fileName = opts.fileName;
    if (opts.slideSelector) c.slideSelector = opts.slideSelector;

    if (running && !opts.allowConcurrent) {
      throw new Error('导出已在进行中');
    }
    running = true;
    var t0 = (global.performance ? performance.now() : Date.now());
    setStatus('running');

    try {
      var PptxGenJS = await ensurePptxGenJS(c);
      var slideEls = collectSlides(c);
      if (!slideEls.length) throw new Error('页面里没有找到 ' + c.slideSelector);
      setStatus('measuring', { total: slideEls.length });

      _blockedImages = 0;
      var restoreExportMode = enterExportMode();
      var models;
      try {
        await raf2();   // 等导出模式样式生效（两帧足够让布局稳定）
        models = await withScale1(c, function () { return measureDeck(slideEls, c); });
      } finally {
        restoreExportMode();
      }

      var built = buildPptx(models, c, PptxGenJS);
      var warnings = [];
      for (var i = 0; i < models.length; i++) {
        if (models[i].warnings && models[i].warnings.length) {
          warnings = warnings.concat(models[i].warnings);
        }
      }
      if (_blockedImages > 0) {
        warnings.push(_blockedImages + ' 张图片因浏览器安全限制无法内嵌（canvas 被污染）');
      }

      var report = {
        fileName: c.fileName,
        slides: built.report,
        slideCount: models.length,
        texts: built.report.reduce(function (a, s) { return a + s.texts; }, 0),
        images: built.report.reduce(function (a, s) { return a + s.images; }, 0),
        shapes: built.report.reduce(function (a, s) { return a + s.shapes; }, 0),
        chars: built.report.reduce(function (a, s) { return a + s.chars; }, 0),
        warnings: warnings,
        widthIn: DESIGN_W * PX_TO_IN,
        heightIn: DESIGN_H * PX_TO_IN,
        ms: Math.round((global.performance ? performance.now() : Date.now()) - t0)
      };

      if (opts.dryRun) {
        running = false;
        setStatus('dryrun');
        deckExportPptx.lastReport = report;
        return report;
      }

      setStatus('writing');
      var tWrite = (global.performance ? performance.now() : Date.now());
      await built.pptx.writeFile({ fileName: c.fileName });
      report.writeMs = Math.round((global.performance ? performance.now() : Date.now()) - tWrite);
      report.ms = Math.round((global.performance ? performance.now() : Date.now()) - t0);
      running = false;
      setStatus('done');
      deckExportPptx.lastReport = report;
      if (_blockedImages > 0 && !opts.silentNotice) {
        showNotice('本次导出省略了 ' + _blockedImages + ' 张图片', [
          '本地文件（file://）打开时，浏览器不允许读取图片像素，' +
          '只能导出文字和色块。',
          '要完整导出：运行 python3 tools/serve.py --port 8765，' +
          '再从 http://127.0.0.1:8765/index.html?export=1 打开后点导出。',
          '或者用 python3 tools/make_pptx.py 直接生成整页图片版（所见即所得）。'
        ]);
      }
      try {
        document.dispatchEvent(new CustomEvent('pptx:done', { detail: report }));
      } catch (e) {}
      return report;
    } catch (err) {
      running = false;
      setStatus('error', { message: err && err.message });
      try {
        document.dispatchEvent(new CustomEvent('pptx:error', { detail: { error: String(err && err.message || err) } }));
      } catch (e) {}
      throw err;
    }
  }

  /* ---- 事件绑定 ------------------------------------------------- */

  function bindClicks() {
    document.addEventListener('click', function (ev) {
      var target = ev.target;
      var btn = target && target.closest ? target.closest('[data-export="pptx"]') : null;
      if (!btn) return;
      ev.preventDefault();
      if (btn.getAttribute('data-pptx-busy') === '1') return;
      btn.setAttribute('data-pptx-busy', '1');
      var prevText = btn.textContent;
      btn.textContent = '正在导出…';
      deckExportPptx().catch(function (err) {
        /* eslint-disable no-console */
        console.error('[pptx-export]', err);
        try { global.alert('导出 PPT 失败：' + (err && err.message || err)); } catch (e) {}
      }).then(function () {
        btn.removeAttribute('data-pptx-busy');
        btn.textContent = prevText;
      });
    }, true);
  }

  /* ---- 导出 ---------------------------------------------------- */

  global.deckExportPptx = deckExportPptx;
  global.deckExportPptx.withScale1 = function (fn) { return withScale1(cfg(), fn); };
  global.deckExportPptx.config = cfg;
  global.deckExportPptx.version = '1.0.0';

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bindClicks);
  } else {
    bindClicks();
  }

  wlog('ready', DEFAULTS.fileName);
})(typeof window !== 'undefined' ? window : this);
