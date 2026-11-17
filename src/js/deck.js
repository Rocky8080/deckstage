/* ============================================================
   deck.js — 演示模式引擎
   · 舞台等比缩放       · 键盘/触摸/进度条导航
   · 逐步揭示(.frag)    · 数字滚动计数
   · 章节导轨(量/物/法) · 总览 / 备注 / 全屏
   · window.__deck 供导出工具调用
   ============================================================ */
(() => {
  'use strict';

  const DESIGN_W = 1600;
  const DESIGN_H = 900;
  const RAIL_NAMES = { '量': '量', '物': '物', '法': '法' };

  const deckEl = document.querySelector('.deck');
  const stageEl = document.querySelector('.stage');
  const slidesEl = document.querySelector('.slides');
  const slides = Array.from(document.querySelectorAll('.slide'));
  const total = slides.length;

  let idx = 0;
  let scale = 1;
  let fragIndex = 0;
  let notesOpen = false;
  /* 投影适配：contain = 等比缩放留边（不丢内容）；cover = 填满屏幕并按比例裁掉外沿 */
  /* 画幅：16:9 = 1600×900；4:3 = 1200×900（版式按同一套栅格回流） */
  const RATIOS = { '16:9': 1600, '4:3': 1200 };
  let ratioMode = 'auto';          // auto | 16:9 | 4:3
  let designW = RATIOS['16:9'];
  let fitMode = 'contain';
  try {
    const params = new URLSearchParams(location.search);
    const q = params.get('fit');
    if (q === 'cover' || q === 'contain') fitMode = q;
    else if (localStorage.getItem('deck-fit') === 'cover') fitMode = 'cover';
    const saved = localStorage.getItem('deck-ratio');
    if (saved === '4:3' || saved === '16:9') ratioMode = saved;
    const qr = params.get('ratio');
    if (qr === '4:3' || qr === '43') ratioMode = '4:3';
    if (qr === '16:9' || qr === '169') ratioMode = '16:9';
  } catch (e) { /* 隐私模式忽略 */ }

  /* 窗口比 < 1.5（4:3 投影 / 竖屏笔记本）→ 自动切 4:3 画幅 */
  function resolveRatio() {
    if (ratioMode !== 'auto') return ratioMode;
    const r = window.innerWidth / Math.max(1, window.innerHeight);
    // 只有接近 4:3（1.25–1.42，典型投影 1024×768 / 1400×1050）才切 4:3；
    // 其余（16:9 / 16:10 / 21:9 / 窄窗口）保持 16:9，避免小窗口意外改版式
    return (r >= 1.25 && r <= 1.42 && Math.min(window.innerWidth, window.innerHeight) >= 720) ? '4:3' : '16:9';
  }

  function applyRatio() {
    const ratio = resolveRatio();
    designW = RATIOS[ratio];
    stageEl.style.width = designW + 'px';
    document.documentElement.style.setProperty('--design-w', designW + 'px');
    document.body.classList.toggle('ratio-4x3', ratio === '4:3');
    document.body.classList.toggle('ratio-16x9', ratio === '16:9');
    if (window.__deck) window.__deck.ratio = ratio;
    const btn = document.querySelector('.chrome__ratio-btn');
    if (btn) {
      btn.classList.toggle('is-auto', ratioMode === 'auto');
      const label = btn.querySelector('.chrome__ratio');
      if (label) label.textContent = (ratioMode === 'auto' ? '自动 ' : '') + ratio;
      btn.title = `切换画幅：自动 / 16:9 / 4:3（R）· 当前 ${ratioMode === 'auto' ? '自动 ' : '固定 '}${ratio}`;
    }
    return ratio;
  }

  function cycleRatio() {
    const order = ['auto', '16:9', '4:3'];
    ratioMode = order[(order.indexOf(ratioMode) + 1) % order.length];
    try { localStorage.setItem('deck-ratio', ratioMode === 'auto' ? '' : ratioMode); } catch (e) { /* 忽略 */ }
    const ratio = applyRatio();
    fit();
    toast(ratioMode === 'auto'
      ? `画幅自动（当前按 ${ratio} 排版 · 窗口比 ${(window.innerWidth/window.innerHeight).toFixed(2)}:1）`
      : `画幅固定 ${ratio} · 窗口比 ${(window.innerWidth/window.innerHeight).toFixed(2)}:1`);
  }
  let overviewOpen = false;

  /* ---------------------------------------------- 左右点击翻页 */
  function buildTapZones() {
    const mk = (side) => {
      const z = document.createElement('button');
      z.type = 'button';
      z.className = `tapzone tapzone--${side}`;
      z.setAttribute('aria-label', side === 'prev' ? '上一屏' : '下一屏');
      z.innerHTML = side === 'prev'
        ? '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M15 5 8 12l7 7"/></svg>'
        : '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 5l7 7-7 7"/></svg>';
      /* 透明手势面：不进 Tab 顺序、点击也不抢焦点。
         否则鼠标点过右侧翻页带后，只要再按一下键盘，Chrome 就会给这个
         190×900 的按钮画上默认焦点框（放映时右侧一个大蓝框）。 */
      z.tabIndex = -1;
      z.addEventListener('mousedown', (e) => e.preventDefault());
      z.addEventListener('click', () => (side === 'next' ? next() : prev()));
      document.body.appendChild(z);
    };
    mk('prev'); mk('next');
    document.body.classList.add('has-tapzones');
  }

  /* ---------------------------------------------- 鼠标视差 */
  let paFrame = null;
  function initParallax() {
    document.addEventListener('mousemove', (e) => {
      if (paFrame) return;
      paFrame = requestAnimationFrame(() => {
        paFrame = null;
        const x = (e.clientX / Math.max(1, window.innerWidth) - 0.5) * 2;
        const y = (e.clientY / Math.max(1, window.innerHeight) - 0.5) * 2;
        stageEl.style.setProperty('--mx', x.toFixed(3));
        stageEl.style.setProperty('--my', y.toFixed(3));
      });
    }, { passive: true });
  }

  /* ---------------------------------------------- 章节切换扫光 */
  let sweepTimer = null;
  function chapterSweep() {
    deckEl.classList.remove('is-sweep');
    void deckEl.offsetWidth;
    deckEl.classList.add('is-sweep');
    clearTimeout(sweepTimer);
    sweepTimer = setTimeout(() => deckEl.classList.remove('is-sweep'), 1000);
  }

  /* ---------------------------------------------- 尺寸 */
  function fit() {
    // 给外框 chrome 留出空间：全屏放映时收紧，普通浏览时留足
    const fs = nativeFS() || cinema;
    const padX = cinema ? 0 : (window.innerWidth < 900 ? 20 : (fs ? 30 : 72));
    const padY = cinema ? 0 : (window.innerHeight < 620 ? 24 : (fs ? 30 : 100));
    const w = window.innerWidth - padX;
    const h = window.innerHeight - padY;
    scale = fitMode === 'cover'
      ? Math.max(w / designW, h / DESIGN_H)    // 填满：可能裁掉外沿
      : Math.min(w / designW, h / DESIGN_H);   // 留边：保证内容完整
    scale = Math.max(scale, 0.12);
    stageEl.style.setProperty('--scale', scale.toFixed(4));
    document.body.classList.toggle('is-cover', fitMode === 'cover');
    window.__deck.scale = scale;
    window.__deck.fitMode = fitMode;
  }

  let toastTimer = null;
  function toast(text) {
    let el = document.querySelector('.deck-toast');
    if (!el) {
      el = document.createElement('div');
      el.className = 'deck-toast';
      document.body.appendChild(el);
    }
    el.textContent = text;
    el.classList.add('is-on');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => el.classList.remove('is-on'), 1600);
  }

  function toggleFit() {
    fitMode = fitMode === 'cover' ? 'contain' : 'cover';
    try { localStorage.setItem('deck-fit', fitMode); } catch (e) { /* 忽略 */ }
    fit();
    const ratio = (window.innerWidth / window.innerHeight).toFixed(2);
    toast(fitMode === 'cover'
      ? `填满屏幕（可能裁掉外沿）· 当前窗口比 ${ratio}:1`
      : `等比留边（内容完整）· 当前窗口比 ${ratio}:1`);
  }

  /* ---------------------------------------------- 图片懒加载
     幻灯片里用 <img data-src="..."> 时，只加载当前屏与前后各 2 屏的图片；
     首屏加载完成后按需补，切屏时再补邻居。大 deck（上百张图）因此不会一次拖满。 */
  const lazyLoaded = new WeakSet();
  function hydrateImages(from, to) {
    const lo = Math.max(0, from), hi = Math.min(total - 1, to);
    for (let i = lo; i <= hi; i++) {
      const slide = slides[i];
      if (!slide) continue;
      slide.querySelectorAll('img[data-src]').forEach(img => {
        if (lazyLoaded.has(img)) return;
        lazyLoaded.add(img);
        img.src = img.dataset.src;
        img.removeAttribute('data-src');
      });
    }
  }
  window.__deckHydrate = hydrateImages;

  /* 补字层自适应：把每行文字横向缩放到它在原稿里的宽度，避免字体变宽压到别的列 */
  /* 补字层基线对齐：用 canvas 量出文字的实际高度，把字形底边压到 PDF 基线上 */
  const measureCtx = (() => {
    try { return document.createElement('canvas').getContext('2d'); } catch (e) { return null; }
  })();
  function alignBaselines(root) {
    (root || document).querySelectorAll('.xl3__t[data-bl]').forEach(el => {
      const bl = parseFloat(el.dataset.bl);
      if (!bl || !measureCtx) return;
      const cs = getComputedStyle(el);
      measureCtx.font = cs.fontWeight + ' ' + cs.fontSize + ' ' + cs.fontFamily;
      const m = measureCtx.measureText(el.textContent || '');
      const fs = parseFloat(cs.fontSize);
      const asc = m.fontBoundingBoxAscent || fs * 0.88;
      const desc = m.fontBoundingBoxDescent || fs * 0.12;
      const lh = parseFloat(cs.lineHeight) || fs;
      // 行盒会把字形下推半个行距，定位时要扣掉，才能让基线落在 PDF 基线上
      const halfLeading = (lh - (asc + desc)) / 2;
      // 汉字墨迹底边会略低于基线（约 0.05–0.1em），对齐时扣掉，才能与西文同基线
      const inkDescent = m.actualBoundingBoxDescent || 0;
      el.style.top = (bl - asc - halfLeading - inkDescent).toFixed(1) + 'px';
    });
  }
  window.__deckAlignBaselines = alignBaselines;

  function fitOverlays(root) {
    (root || document).querySelectorAll('.xl3__t[data-w]').forEach(el => {
      const want = parseFloat(el.dataset.w);
      const base = parseFloat(el.dataset.fs);
      if (!want || !base) return;
      el.style.fontSize = base + 'px';        // 先还原，再测量
      const nat = el.scrollWidth;
      if (!nat) return;
      // 同页统一字号：不再缩放；过长的行由文本块换行处理
      void want; void nat;
    });
  }
  window.__deckFitOverlays = fitOverlays;

  /* ---------------------------------------------- 页脚注入 */
  function injectFooters() {
    slides.forEach((slide, i) => {
      if (slide.querySelector(':scope > .foot')) return;
      if (slide.hasAttribute('data-nofoot')) return;
      const rail = slide.dataset.rail || '';
      const title = slide.dataset.title || '';
      const foot = document.createElement('div');
      foot.className = 'foot';
      const custom = slide.dataset.foot;
      foot.innerHTML = custom
        ? `<span>${custom}</span>`
        : `<span>${rail ? rail + ' · ' : ''}${title}</span><span class="foot__marks">
             <span>${document.body.dataset.brand || 'AI 改变学习方式'}</span><span class="foot__dot"></span>
             <span class="num">${String(i + 1).padStart(2, '0')} / ${total}</span></span>`;
      slide.appendChild(foot);
    });
  }

  /* ---------------------------------------------- 进度条 + 总览 */
  function buildChrome() {
    const bar = document.querySelector('.chrome__progress');
    if (bar) {
      bar.innerHTML = slides.map((s, i) =>
        `<i data-goto="${i}" data-tip="${String(i + 1).padStart(2, '0')} · ${s.dataset.title || ''}" title="${i + 1}. ${s.dataset.title || ''}" role="tab" aria-label="第 ${i + 1} 屏：${s.dataset.title || ''}"></i>`).join('');
      bar.addEventListener('click', (e) => {
        const t = e.target.closest('[data-goto]');
        if (t) go(+t.dataset.goto);
      });
    }

    const grid = document.querySelector('.overview__grid');
    if (grid) {
      grid.innerHTML = slides.map((s, i) => `
        <button class="ov-card" data-goto="${i}">
          <span class="ov-card__no">${String(i + 1).padStart(2, '0')}</span>
          <span class="ov-card__title">${s.dataset.title || ''}</span>
          <span class="ov-card__rail">${s.dataset.rail || ''}</span>
        </button>`).join('');
      grid.addEventListener('click', (e) => {
        const t = e.target.closest('[data-goto]');
        if (t) { go(+t.dataset.goto); toggleOverview(false); }
      });
    }

    document.querySelectorAll('[data-rail-jump]').forEach(btn => {
      btn.addEventListener('click', () => {
        const rail = btn.dataset.railJump;
        const target = slides.findIndex(s => (s.dataset.rail || '') === rail);
        if (target >= 0) go(target);
      });
    });
  }

  /* ---------------------------------------------- 数字滚动 */
  function finalizeCounters(root) {
    (root || document).querySelectorAll('[data-count]').forEach(el => {
      const v = parseFloat(el.dataset.count);
      const d = parseInt(el.dataset.dec || '0', 10);
      el.textContent = (el.dataset.prefix || '') +
        v.toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d }) +
        (el.dataset.suffix || '');
    });
  }
  function animateCounters(slide) {
    slide.querySelectorAll('[data-count]').forEach(el => {
      const target = parseFloat(el.dataset.count);
      const decimals = parseInt(el.dataset.dec || '0', 10);
      const suffix = el.dataset.suffix || '';
      const prefix = el.dataset.prefix || '';
      const dur = 1150;
      const t0 = performance.now();
      const from = 0;
      const fmt = (v) => v.toLocaleString('en-US', {
        minimumFractionDigits: decimals, maximumFractionDigits: decimals
      });
      function tick(t) {
        const p = Math.min(1, (t - t0) / dur);
        const e = 1 - Math.pow(1 - p, 3);
        el.textContent = prefix + fmt(from + (target - from) * e) + suffix;
        if (p < 1) requestAnimationFrame(tick);
        else el.textContent = prefix + fmt(target) + suffix;
      }
      requestAnimationFrame(tick);
    });
  }

  /* ---------------------------------------------- 逐步揭示 */
  function frags(slide) { return Array.from(slide.querySelectorAll('.frag')); }
  function resetFrags(slide) {
    frags(slide).forEach(f => f.classList.remove('is-shown'));
    fragIndex = 0;
  }
  function nextFrag() {
    const list = frags(slides[idx]);
    if (fragIndex < list.length) {
      list[fragIndex].classList.add('is-shown');
      fragIndex++;
      return true;
    }
    return false;
  }
  function allFragsShown() {
    const list = frags(slides[idx]);
    return list.length === 0 || fragIndex >= list.length;
  }

  /* ---------------------------------------------- 导航 */
  function render() {
    slides.forEach((s, i) => {
      s.classList.toggle('is-active', i === idx);
      s.classList.toggle('is-prev', i < idx);
      s.setAttribute('aria-hidden', i === idx ? 'false' : 'true');
    });
    const cur = slides[idx];

    const count = document.querySelector('.chrome__count');
    if (count) count.innerHTML = `<b>${String(idx + 1).padStart(2, '0')}</b>/ ${String(total).padStart(2, '0')}`;

    const titleEl = document.querySelector('.chrome__title');
    if (titleEl) titleEl.textContent = cur.dataset.title || '';

    document.querySelectorAll('.chrome__progress i').forEach((el, i) => {
      el.classList.toggle('is-active', i === idx);
      el.classList.toggle('is-done', i < idx);
    });

    document.querySelectorAll('.chrome__rail button').forEach(btn => {
      btn.classList.toggle('is-active', btn.dataset.railJump === (cur.dataset.rail || ''));
    });

    const stageBar = document.querySelector('.stage__bar > i');
    if (stageBar) stageBar.style.width = ((idx + 1) / total * 100).toFixed(2) + '%';

    document.querySelectorAll('.ov-card').forEach((c, i) => c.classList.toggle('is-active', i === idx));

    hydrateImages(idx - 2, idx + 2);
    alignBaselines(slides[idx]);
    fitOverlays(slides[idx]);
    const drawer = document.querySelector('.notebar__body');
    if (drawer) {
      const note = cur.querySelector('.notes');
      drawer.innerHTML = note ? note.innerHTML : '<span style="opacity:.45">这一屏没有备注。</span>';
    }

    const hash = '#s' + (idx + 1);
    if (location.hash !== hash) history.replaceState(null, '', hash);

    animateCounters(cur);
    document.title = `${String(idx + 1).padStart(2, '0')} · ${cur.dataset.title || 'AI 改变学习方式'}`;
  }

  function go(n, opts = {}) {
    if (n < 0 || n >= total) return;
    const prev = slides[idx];
    const fromRail = prev ? (prev.dataset.rail || '') : '';
    const toRail = slides[n].dataset.rail || '';
    stageEl.style.setProperty('--dir', n >= idx ? '1' : '-1');
    if (fromRail && toRail && fromRail !== toRail) chapterSweep();
    if (prev && prev !== slides[n]) prev.classList.remove('is-active');
    idx = n;
    resetFrags(slides[idx]);
    render();
    if (!opts.silent) hideHint();
  }
  function next() {
    if (nextFrag()) return;
    if (idx < total - 1) go(idx + 1);
  }
  function prev() {
    const list = frags(slides[idx]);
    if (fragIndex > 0) {
      fragIndex--;
      list[fragIndex].classList.remove('is-shown');
      return;
    }
    if (idx > 0) go(idx - 1);
  }

  /* ---------------------------------------------- 总览 / 备注 / 全屏 */
  function toggleOverview(force) {
    const ov = document.querySelector('.overview');
    if (!ov) return;
    overviewOpen = force === undefined ? !overviewOpen : force;
    ov.classList.toggle('is-open', overviewOpen);
    document.body.classList.toggle('is-overview', overviewOpen);
  }
  function toggleNotes(force) {
    const nb = document.querySelector('.notebar');
    const btn = document.querySelector('[data-act="notes"]');
    if (!nb) return;
    notesOpen = force === undefined ? !notesOpen : force;
    nb.classList.toggle('is-open', notesOpen);
    if (btn) btn.classList.toggle('is-on', notesOpen);
  }
  /* 全屏：优先原生 Fullscreen API，不可用/被拒时退化为「影院模式」（隐藏外壳、铺满窗口） */
  let cinema = false;
  let chromeTimer = null;

  function nativeFS() {
    return !!(document.fullscreenElement || document.webkitFullscreenElement || document.msFullscreenElement);
  }

  function setCinema(on) {
    cinema = on;
    document.body.classList.toggle('is-cinema', on);
    document.body.classList.toggle('chrome-hidden', on);
    fit();
  }

  function autoHideChrome() {
    if (!cinema) return;
    clearTimeout(chromeTimer);
    chromeTimer = setTimeout(() => document.body.classList.add('chrome-hidden'), 2600);
  }

  async function toggleFullscreen() {
    if (nativeFS()) {
      const exit = document.exitFullscreen || document.webkitExitFullscreen || document.msExitFullscreen;
      if (exit) await exit.call(document);
      return;
    }
    if (cinema) { setCinema(false); return; }
    const el = document.documentElement;
    const req = el.requestFullscreen || el.webkitRequestFullscreen || el.msRequestFullscreen;
    if (req) {
      try {
        await req.call(el);
        if (nativeFS()) return;     // 真进了全屏 → 交给 fullscreenchange 处理 fit
        await new Promise(r => setTimeout(r, 120));
        if (nativeFS()) return;
      } catch (e) { /* 被策略拒绝（iOS / 受限 iframe）→ 退化 */ }
    }
    setCinema(true);                // iPhone / iframe / 无 API：影院模式
  }

  /* ---------------------------------------------- 提示 */
  let hintTimer = null;
  function showHint() {
    const hint = document.querySelector('.chrome__hint');
    if (!hint) return;
    hint.classList.add('is-shown');
    clearTimeout(hintTimer);
    hintTimer = setTimeout(hideHint, 5200);
  }
  function hideHint() {
    const hint = document.querySelector('.chrome__hint');
    if (hint) hint.classList.remove('is-shown');
  }

  /* ---------------------------------------------- 键盘 */
  function onKey(e) {
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    switch (e.key) {
      case 'ArrowRight': case 'ArrowDown': case 'PageDown': case 'Enter':
        e.preventDefault(); next(); break;
      case ' ':
        e.preventDefault(); next(); break;
      case 'ArrowLeft': case 'ArrowUp': case 'PageUp':
        e.preventDefault(); prev(); break;
      case 'Home': e.preventDefault(); go(0); break;
      case 'End': e.preventDefault(); go(total - 1); break;
      case 'g': case 'G': case 'o': case 'O': toggleOverview(); break;
      case 'n': case 'N': toggleNotes(); break;
      case 'f': case 'F': toggleFullscreen(); break;
      case 's': case 'S': toggleFit(); break;
      case 'r': case 'R': cycleRatio(); break;
      case 'h': case 'H': location.href = '/' + location.search.replace(/^\?/, '').replace(/present=1&?/, ''); break;
      case 'Escape':
        if (overviewOpen) toggleOverview(false);
        else if (notesOpen) toggleNotes(false);
        else if (nativeFS()) toggleFullscreen();
        else if (cinema) setCinema(false);
        break;
      default: break;
    }
  }

  /* ---------------------------------------------- 触摸 */
  let touchX = 0, touchY = 0, touchT = 0;
  function onTouchStart(e) {
    const t = e.changedTouches[0];
    touchX = t.clientX; touchY = t.clientY; touchT = Date.now();
  }
  function onTouchEnd(e) {
    const t = e.changedTouches[0];
    const dx = t.clientX - touchX, dy = t.clientY - touchY;
    if (Date.now() - touchT > 700) return;
    if (Math.abs(dx) > 60 && Math.abs(dx) > Math.abs(dy)) {
      dx < 0 ? next() : prev();
      return;
    }
    // 触摸设备没有鼠标移入：单击唤回外壳（影院模式下的退出口）
    if (cinema) {
      document.body.classList.remove('chrome-hidden');
      autoHideChrome();
    }
  }

  /* ---------------------------------------------- 对外接口（导出工具用） */
  const api = {
    get total() { return total; },
    get index() { return idx; },
    scale: 1,
    go: (n) => go(n, { silent: true }),
    next, prev,
    /** 把舞台缩放临时还原为 1，执行 fn 后恢复（导出测量必须用） */
    async withScale1(fn) {
      const prevScale = stageEl.style.getPropertyValue('--scale');
      stageEl.style.setProperty('--scale', '1');
      stageEl.style.transition = 'none';
      await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
      try { return await fn(); }
      finally {
        stageEl.style.setProperty('--scale', prevScale || scale);
        stageEl.style.transition = '';
      }
    },
    slides,
    onReady: null
  };

  /* ---------------------------------------------- 初始化 */
  function init() {
    if (!total) { console.warn('[deck] 没有找到 .slide'); return; }
    injectFooters();
    buildChrome();
    buildTapZones();
    initParallax();
    // 首帧不要淡入，避免工具截图/用户第一眼看到半透明画面
    slidesEl.classList.add('is-booting');
    // 导出模式固定 16:9（PDF / PPTX 走 1600×900）
    const exporting = /[?&]export=1/.test(location.search);
    if (exporting && !/[?&]ratio=/.test(location.search)) { ratioMode = '16:9'; }
    applyRatio();
    fit();
    hydrateImages(0, exporting ? total - 1 : 2);
    alignBaselines(document);
    fitOverlays(document);
    window.addEventListener('resize', () => { applyRatio(); fit(); alignBaselines(document); fitOverlays(document); });
    document.addEventListener('fullscreenchange', () => { applyRatio(); fit(); });

    // 初始页码：优先 URL hash
    const m = /^#s?(\d+)$/.exec(location.hash);
    idx = m ? Math.min(total - 1, Math.max(0, parseInt(m[1], 10) - 1)) : 0;
    resetFrags(slides[idx]);
    render();

    window.addEventListener('keydown', onKey);
    // 手改地址栏 hash 也能跳屏（replaceState 不会触发 hashchange，不会打架）
    window.addEventListener('hashchange', () => {
      const m = /^#s?(\d+)$/.exec(location.hash);
      if (!m) return;
      const n = parseInt(m[1], 10) - 1;
      if (n >= 0 && n < total && n !== idx) go(n, { silent: true });
    });
    stageEl.addEventListener('touchstart', onTouchStart, { passive: true });
    stageEl.addEventListener('touchend', onTouchEnd, { passive: true });

    // ?present=1 / #present → 直接进入放映（影院模式，不需要手势）
    if (/[?&]present=1/.test(location.search)) setCinema(true);

    document.addEventListener('mousemove', () => {
      if (!cinema) return;
      document.body.classList.remove('chrome-hidden');
      autoHideChrome();
    });
    document.addEventListener('fullscreenchange', () => {
      if (nativeFS()) document.body.classList.add('is-presenting');
      else document.body.classList.remove('is-presenting');
      applyRatio();
      fit();
    });

    // 导出模式：所有屏同时可见，数字直接落终值
    if (/[?&]export=1/.test(location.search)) {
      document.body.classList.add('exporting');
      finalizeCounters(document);
    }

    // 工具栏动作
    document.querySelectorAll('[data-act]').forEach(btn => {
      btn.addEventListener('click', () => {
        const a = btn.dataset.act;
        if (a === 'next') next();
        else if (a === 'prev') prev();
        else if (a === 'overview') toggleOverview();
        else if (a === 'notes') toggleNotes();
        else if (a === 'fullscreen' || a === 'present') toggleFullscreen();
        else if (a === 'ratio') cycleRatio();
        else if (a === 'fit') toggleFit();
        else if (a === 'export') {
          if (window.deckExportPptx) window.deckExportPptx();
          else alert('导出模块尚未加载（src/js/pptx-export.js）。');
        }
      });
    });

    document.querySelectorAll('[data-close]').forEach(el => {
      el.addEventListener('click', () => toggleOverview(false));
    });

    requestAnimationFrame(() => requestAnimationFrame(() => {
      slidesEl.classList.remove('is-booting');
    }));

    // 打印 / 另存 PDF 前把所有计数器落值（非当前屏不会走 animateCounters）
    window.addEventListener('beforeprint', () => finalizeCounters(document));

    showHint();
    if (typeof api.onReady === 'function') api.onReady();
    document.documentElement.classList.add('deck-ready');
    window.dispatchEvent(new CustomEvent('deck:ready', { detail: { total } }));
  }

  window.__deck = api;
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
