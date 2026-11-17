#!/usr/bin/env python3
"""
admin_site.py — /admin 后台的前端资产：管理页面、追踪脚本、门禁/下架页、缩略图占位

全部是纯模板 + 纯函数（filter_library_html），由 serve_deck.py 挂到路由上。
模板一律用 __TOKEN__ 占位 + .replace() 填充，不走 str.format（CSS/JS 花括号会炸）。
"""
from __future__ import annotations

import html
import re

# ============================================================ 追踪脚本（注入 deck / 展示台页面）
# 模型：每 1s 可见时钟累计（总活跃 + 各屏停留），每 15s 批量上报；
# slide 序号取自 deck 引擎写的 location.hash（#sN → 第 N 屏）。
_TRACKER = """<script>(function(){
if (window.__deckTracked) return; window.__deckTracked = 1;
var DECK = "__DECK__";
function slideNo(){ var m = /^#s?(\\d+)$/.exec(location.hash); return m ? (+m[1]-1) : 0; }
var visitor = (function(){ try {
  var k='deck_visitor', v=localStorage.getItem(k);
  if(!v){ v=(crypto.randomUUID?crypto.randomUUID():Date.now().toString(36)+Math.random().toString(36).slice(2)); localStorage.setItem(k,v); }
  return v; } catch(e){ return 'anon-'+Date.now().toString(36); } })();
var vid=null, cur=slideNo(), actMs=0, acc={}, entered={}, lastVis=Date.now(), N=document.querySelectorAll('.slide').length;
function post(body, beacon){
  body.deck=DECK;
  var s=JSON.stringify(body);
  if (beacon && navigator.sendBeacon) { try { navigator.sendBeacon('/api/track/end', new Blob([s],{type:'application/json'})); } catch(e){} }
  else fetch('/api/track/beat',{method:'POST',headers:{'Content-Type':'application/json'},body:s,keepalive:true}).catch(function(){});
}
function tick(){
  var now=Date.now();
  if (document.visibilityState==='visible'){
    var dt=now-lastVis; actMs+=dt; acc[cur]=(acc[cur]||0)+dt;
  }
  lastVis=now;
}
function flush(beacon, done){
  var a=actMs; actMs=0;
  var items=[]; for (var s in acc) items.push([+s, Math.round(acc[s]), entered[s]?1:0]);
  acc={}; entered={};
  if (vid==null || (a===0 && !items.length && !done)) return;
  post({v:vid, a:Math.round(a), n:N, items:items, done:done?1:0}, beacon);
}
setInterval(tick, 1000);
setInterval(function(){
  var s=slideNo();
  if (s!==cur){ cur=s; entered[s]=1; }
}, 600);
setInterval(function(){ tick(); flush(false,false); }, 15000);
document.addEventListener('visibilitychange', function(){
  lastVis=Date.now();
  if (document.visibilityState==='hidden'){ tick(); flush(false,false); }
});
window.addEventListener('pagehide', function(){ tick(); flush(true,true); });
fetch('/api/track/init',{method:'POST',headers:{'Content-Type':'application/json'},keepalive:true,
  body:JSON.stringify({deck:DECK, visitor:visitor, n:N, ref:document.referrer.slice(0,200)})})
.then(function(r){ return r.json(); })
.then(function(r){ if(r && r.ok){ vid=r.v; entered[cur]=1; flush(false,false); } })
.catch(function(){});
})();</script>"""


def tracker_script(deck: str) -> str:
    return _TRACKER.replace("__DECK__", deck)


# ============================================================ library.html 服务端实时过滤
def filter_library_html(text: str, access: dict) -> str:
    """下架的卡片从展示台移除、加密的卡片加 🔒 标签、页脚挂管理入口。"""
    disabled = [s for s, c in access.items() if c and c.get("enabled") is False]
    locked = [s for s, c in access.items() if c and c.get("password_hash")]

    removed = 0
    for slug in disabled:
        pat = re.compile(r'<a class="card" href="/decks/%s/"[\s\S]*?</a>\s*' % re.escape(slug))
        text, n = pat.subn("", text)
        removed += n
    if removed:
        text = re.sub(r'(<div class="stat"><b>)(\d+)(</b><span>套</span>)',
                      lambda m: f"{m.group(1)}{max(0, int(m.group(2)) - removed)}{m.group(3)}",
                      text, count=1)

    for slug in locked:
        m = re.search(r'<a class="card" href="/decks/%s/"[\s\S]*?</a>' % re.escape(slug), text)
        if not m:
            continue
        block = m.group(0)
        if '<div class="tags">' in block:
            nb = block.replace('<div class="tags">',
                               '<div class="tags"><span class="tag">🔒 需密码</span>', 1)
        else:
            nb = block.replace('      </div>\n    </a>',
                               '        <div class="tags"><span class="tag">🔒 需密码</span></div>\n'
                               '      </div>\n    </a>', 1)
        if nb != block:
            text = text[:m.start()] + nb + text[m.end():]

    if 'href="/admin"' not in text:
        text = text.replace("</footer>",
                            '<span><a href="/admin" style="color:inherit;text-decoration:none">管理后台</a></span></footer>',
                            1)
    return text


# ============================================================ 共用样式（library 同一套纸墨配色）
_BASE_CSS = """
  :root { --paper:#F7F3EA; --paper-2:#FCFAF4; --ink:#14201B; --ink-2:#33453D; --ink-3:#5F6E66;
    --ink-4:#8A968F; --green:#1E5B47; --green-2:#2E7D62; --red:#A4472F; --line:rgba(20,32,27,.12);
    --serif:"Songti SC","Source Han Serif SC","Noto Serif SC",serif;
    --sans:"PingFang SC","Hiragino Sans GB","Microsoft YaHei",system-ui,sans-serif;
    --mono:ui-monospace,"SF Mono",Menlo,monospace; }
  * { box-sizing:border-box; }
  [hidden] { display:none !important; }
  body { margin:0; min-height:100vh; background:var(--paper); color:var(--ink);
    font-family:var(--sans); -webkit-font-smoothing:antialiased; }
  a { color:var(--green); }
"""

# ============================================================ 密码门禁页
_GATE = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>需密码访问 · __TITLE__</title>
<style>__BASE__
  .wrap { min-height:100vh; display:flex; align-items:center; justify-content:center; padding:24px; }
  .card { width:min(420px,100%); background:var(--paper-2); border:1px solid var(--line);
    border-radius:16px; padding:44px 40px 36px; text-align:center;
    box-shadow:0 20px 50px rgba(20,32,27,.10); }
  .lock { font-size:40px; line-height:1; }
  h1 { font-family:var(--serif); font-size:24px; margin:18px 0 8px; font-weight:600; letter-spacing:.02em; }
  .sub { color:var(--ink-3); font-size:13.5px; line-height:1.7; margin:0 0 6px; }
  .hint { color:var(--ink-4); font-size:12px; font-family:var(--mono); margin:0 0 22px; white-space:pre-wrap; min-height:14px; }
  input[type=password] { width:100%; padding:12px 14px; border:1px solid var(--line); border-radius:10px;
    background:#fff; font:15px/1 var(--sans); letter-spacing:.2em; text-align:center; outline:none; }
  input[type=password]:focus { border-color:var(--green); box-shadow:0 0 0 3px rgba(30,91,71,.15); }
  button { width:100%; margin-top:12px; padding:12px; border:0; border-radius:10px; cursor:pointer;
    background:var(--green); color:var(--paper); font:600 14px/1 var(--sans); letter-spacing:.06em; }
  button:hover { background:var(--green-2); }
  .err { color:var(--red); font-size:12.5px; min-height:18px; margin:12px 0 0; }
  .back { display:inline-block; margin-top:14px; font-size:12px; color:var(--ink-4);
    font-family:var(--mono); letter-spacing:.06em; text-decoration:none; }
</style></head><body><div class="wrap"><div class="card">
  <div class="lock">🔒</div>
  <h1>__TITLE__</h1>
  <p class="sub">这套幻灯片受密码保护，请输入访问密码。</p>
  <p class="hint">__HINT__</p>
  <input type="password" id="pw" placeholder="••••••••" autofocus autocomplete="off">
  <button id="go">解锁</button>
  <p class="err" id="err">__ERR__</p>
  <a class="back" href="/">← 返回展示台</a>
</div></div>
<script>
(function () {
  function go() {
    var pw = document.getElementById('pw').value;
    if (!pw) return;
    fetch('/api/access', { method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ deck: '__SLUG__', password: pw }) })
    .then(function (r) { return r.json(); })
    .then(function (r) {
      if (r && r.ok) location.replace(r.redirect || location.href);
      else document.getElementById('err').textContent = (r && r.error) || '密码不对，再试试';
    }).catch(function () { document.getElementById('err').textContent = '网络错误'; });
  }
  document.getElementById('go').addEventListener('click', go);
  document.getElementById('pw').addEventListener('keydown', function (e) { if (e.key === 'Enter') go(); });
})();
</script></body></html>"""


def gate_page(slug: str, title: str, hint: str, err: str = "") -> str:
    return (_GATE.replace("__BASE__", _BASE_CSS)
                 .replace("__TITLE__", html.escape(title))
                 .replace("__HINT__", html.escape(hint))
                 .replace("__ERR__", html.escape(err))
                 .replace("__SLUG__", html.escape(slug, quote=True)))


# ============================================================ 下架页（HTTP 404）
_DISABLED = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>内容不可用</title>
<style>__BASE__
  .wrap { min-height:100vh; display:flex; align-items:center; justify-content:center; padding:24px; }
  .card { width:min(420px,100%); background:var(--paper-2); border:1px solid var(--line);
    border-radius:16px; padding:44px 40px 36px; text-align:center; box-shadow:0 20px 50px rgba(20,32,27,.10); }
  .lock { font-size:38px; }
  h1 { font-family:var(--serif); font-size:22px; margin:16px 0 8px; font-weight:600; }
  p { color:var(--ink-3); font-size:13.5px; line-height:1.7; margin:0; }
  a.back { display:inline-block; margin-top:18px; font-size:12px; color:var(--ink-4);
    font-family:var(--mono); letter-spacing:.06em; text-decoration:none; }
</style></head><body><div class="wrap"><div class="card">
  <div class="lock">🗂️</div>
  <h1>内容暂未公开</h1>
  <p>「__TITLE__」已被管理者下架，暂时无法访问。</p>
  <a class="back" href="/">← 返回展示台</a>
</div></div></body></html>"""


def disabled_page(title: str) -> str:
    return _DISABLED.replace("__BASE__", _BASE_CSS).replace("__TITLE__", html.escape(title))


# ============================================================ 加密 deck 的缩略图占位（SVG）
_LOCKED_THUMB = """<svg xmlns="http://www.w3.org/2000/svg" width="800" height="450" viewBox="0 0 800 450">
<rect width="800" height="450" fill="#E8E2D4"/>
<text x="400" y="215" font-size="56" text-anchor="middle">🔒</text>
<text x="400" y="285" font-family="PingFang SC, sans-serif" font-size="20" fill="#5F6E66"
  text-anchor="middle" letter-spacing="4">需密码访问</text>
</svg>"""


def locked_thumb() -> bytes:
    return _LOCKED_THUMB.encode("utf-8")


# ============================================================ /admin 管理页面
_ADMIN = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>管理后台 · PPT 展示台</title>
<style>__BASE__
  .wrap { max-width:1280px; margin:0 auto; padding:48px 40px 72px; }
  header.top { display:flex; align-items:flex-end; justify-content:space-between; gap:24px; flex-wrap:wrap; }
  .brand { font-family:var(--mono); font-size:11px; letter-spacing:.22em; color:var(--green); margin:0 0 12px; }
  h1 { font-family:var(--serif); font-size:38px; line-height:1.1; margin:0; font-weight:600; }
  h2 { font-family:var(--serif); font-size:21px; margin:44px 0 14px; font-weight:600; }
  .tools { display:flex; gap:10px; flex-wrap:wrap; }
  .btn { padding:8px 16px; border-radius:999px; border:1px solid var(--line); background:var(--paper-2);
    color:var(--ink-2); font:500 12.5px/1 var(--sans); cursor:pointer; letter-spacing:.03em;
    transition:transform .15s, box-shadow .15s, background .15s; }
  .btn:hover { transform:translateY(-1px); box-shadow:0 6px 14px rgba(20,32,27,.10); }
  .btn.pri { background:var(--green); border-color:var(--green); color:var(--paper); }
  .btn.warn { color:var(--red); border-color:rgba(164,71,47,.4); }
  .rule { height:1px; background:var(--line); margin:28px 0 26px; }

  /* 登录 */
  #login { min-height:60vh; display:flex; align-items:center; justify-content:center; }
  .loginCard { width:min(380px,100%); background:var(--paper-2); border:1px solid var(--line);
    border-radius:16px; padding:40px 36px 32px; text-align:center; box-shadow:0 20px 50px rgba(20,32,27,.10); }
  .loginCard .lock { font-size:36px; }
  .loginCard h1 { font-size:24px; margin:14px 0 20px; }
  #pw { width:100%; padding:12px 14px; border:1px solid var(--line); border-radius:10px; background:#fff;
    font:15px/1 var(--sans); letter-spacing:.2em; text-align:center; outline:none; }
  #pw:focus { border-color:var(--green); box-shadow:0 0 0 3px rgba(30,91,71,.15); }
  #loginBtn { width:100%; margin-top:12px; padding:12px; }
  #loginErr { color:var(--red); font-size:12.5px; min-height:18px; margin:12px 0 0; }

  /* 概览 */
  .stats { display:grid; grid-template-columns:repeat(auto-fit, minmax(150px, 1fr)); gap:14px; }
  .stat { background:var(--paper-2); border:1px solid var(--line); border-radius:12px; padding:18px 20px; }
  .stat b { display:block; font-family:var(--mono); font-size:28px; font-weight:600; letter-spacing:-.02em; }
  .stat span { font-size:11px; letter-spacing:.1em; color:var(--ink-4); }

  /* 表格 */
  table { width:100%; border-collapse:collapse; background:var(--paper-2);
    border:1px solid var(--line); border-radius:12px; overflow:hidden; font-size:13px; }
  th { text-align:left; font:600 11px/1.4 var(--sans); letter-spacing:.08em; color:var(--ink-4);
    padding:12px 14px; border-bottom:1px solid var(--line); background:rgba(30,91,71,.05); white-space:nowrap; }
  td { padding:11px 14px; border-bottom:1px solid var(--line); vertical-align:middle; }
  tr:last-child td { border-bottom:0; }
  td.num, th.num { font-family:var(--mono); font-size:12px; text-align:right; white-space:nowrap; }
  .slug { font-family:var(--mono); font-size:11px; color:var(--ink-4); }
  .muted { color:var(--ink-4); }
  .pill { display:inline-block; padding:3px 10px; border-radius:999px; font-size:11px; letter-spacing:.05em; }
  .pill.on { background:rgba(30,91,71,.12); color:var(--green); }
  .pill.off { background:rgba(164,71,47,.12); color:var(--red); }
  .pill.lock { background:rgba(30,91,71,.08); color:var(--green); margin-left:6px; }
  .rowbtns { display:flex; gap:6px; flex-wrap:wrap; }
  .mini { padding:5px 11px; border-radius:999px; border:1px solid var(--line); background:#fff;
    font:500 11.5px/1 var(--sans); cursor:pointer; color:var(--ink-2); }
  .mini:hover { border-color:var(--green); color:var(--green); }
  .mini.danger:hover { border-color:var(--red); color:var(--red); }
  tr.editor td { background:rgba(30,91,71,.04); }
  tr.editor input { padding:8px 10px; border:1px solid var(--line); border-radius:8px; font:13px/1 var(--sans);
    background:#fff; outline:none; width:100%; }
  tr.editor input:focus { border-color:var(--green); }
  .editgrid { display:grid; grid-template-columns:1fr 1.6fr auto auto; gap:8px; align-items:center; }

  /* 屏热度条 */
  .heat { position:relative; background:rgba(30,91,71,.08); border-radius:4px; height:16px; min-width:60px; }
  .heat i { position:absolute; inset:0 auto 0 0; background:var(--green-2); border-radius:4px; opacity:.85; }

  .empty { padding:40px 0; color:var(--ink-3); font-size:14px; text-align:center; }
  .selrow { display:flex; align-items:center; gap:10px; margin:0 0 12px; font-size:13px; color:var(--ink-3); }
  .selrow select { padding:7px 10px; border:1px solid var(--line); border-radius:8px; background:#fff;
    font:13px/1 var(--sans); outline:none; }
  .foot { margin-top:52px; padding-top:18px; border-top:1px solid var(--line); font-family:var(--mono);
    font-size:11px; letter-spacing:.08em; color:var(--ink-4); }
  @media (max-width: 720px) { .wrap { padding:30px 16px 56px; } h1 { font-size:28px; }
    .editgrid { grid-template-columns:1fr; } }
</style></head><body>
<div class="wrap">
  <header class="top">
    <div>
      <p class="brand">DECK STAGE · ADMIN</p>
      <h1>管理后台</h1>
    </div>
    <div class="tools" id="topTools" hidden>
      <button class="btn" id="refreshBtn">↻ 刷新</button>
      <button class="btn" id="passwdBtn">改管理密码</button>
      <button class="btn warn" id="clearBtn">清空统计</button>
      <button class="btn warn" id="logoutBtn">登出</button>
    </div>
  </header>
  <div class="rule"></div>

  <section id="login">
    <div class="loginCard">
      <div class="lock">🔐</div>
      <h1>管理员登录</h1>
      <input type="password" id="pw" placeholder="管理密码" autofocus autocomplete="current-password">
      <button class="btn pri" id="loginBtn">进入</button>
      <p id="loginErr"></p>
    </div>
  </section>

  <main id="panel" hidden>
    <div class="stats" id="ovw"></div>

    <h2>内容管理</h2>
    <div id="deckBox"></div>

    <h2>逐屏热度</h2>
    <div class="selrow"><label for="deckSel">选择内容</label>
      <select id="deckSel"></select><span class="muted" id="slideNote"></span></div>
    <div id="slideBox"></div>

    <h2>访问记录 <span class="muted" style="font-size:12px;font-family:var(--mono)">最近 100 条</span></h2>
    <div id="visitBox"></div>

    <p class="foot">数据存于 data/tracking.db · 心跳 15s · 时长按页面可见时间累计 · 面板每 30s 自动刷新</p>
  </main>
</div>

<script>
(function () {
  'use strict';
  function $(s) { return document.querySelector(s); }
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
    return { '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;' }[c]; }); }
  function api(p, o) {
    return fetch(p, Object.assign({ cache:'no-store', headers:{'Content-Type':'application/json'} }, o || {}))
      .then(function (r) { return r.json().catch(function () { return { ok:false, error:'HTTP ' + r.status }; }); });
  }
  function fmtDur(s) {
    s = Math.round(s || 0);
    if (s < 60) return s + '秒';
    if (s < 3600) return Math.floor(s/60) + '分' + String(s%60).padStart(2,'0') + '秒';
    return Math.floor(s/3600) + ':' + String(Math.floor(s%3600/60)).padStart(2,'0') + ':' + String(s%60).padStart(2,'0');
  }
  function fmtT(ts) { if (!ts) return '—';
    var d = new Date(ts * 1000);
    function p(n) { return String(n).padStart(2, '0'); }
    return p(d.getMonth()+1) + '-' + p(d.getDate()) + ' ' + p(d.getHours()) + ':' + p(d.getMinutes()) + ':' + p(d.getSeconds()); }
  function ago(ts) { if (!ts) return '—'; var s = Math.max(0, (Date.now() - ts*1000) / 1000);
    if (s < 60) return '刚刚'; if (s < 3600) return Math.floor(s/60) + ' 分钟前';
    if (s < 86400) return Math.floor(s/3600) + ' 小时前'; return Math.floor(s/86400) + ' 天前'; }
  function uaShort(u) {
    var b = /Edg\\//.test(u) ? 'Edge' : /OPR\\//.test(u) ? 'Opera' : /Firefox\\//.test(u) ? 'Firefox'
      : /Chrome\\//.test(u) ? 'Chrome' : /Safari\\//.test(u) ? 'Safari' : '其他';
    return b + (/Mobi/.test(u) ? '·移动' : '');
  }
  var TITLES = { __library: '展示台首页' };
  var DECKS = [];

  /* ---------- 登录 ---------- */
  function tryLogin() {
    var pw = $('#pw').value;
    if (!pw) return;
    api('/api/admin/login', { method:'POST', body: JSON.stringify({ password: pw }) }).then(function (r) {
      if (r && r.ok) boot();
      else $('#loginErr').textContent = (r && r.error) || '密码不对';
    }).catch(function () { $('#loginErr').textContent = '网络错误'; });
  }
  $('#loginBtn').addEventListener('click', tryLogin);
  $('#pw').addEventListener('keydown', function (e) { if (e.key === 'Enter') tryLogin(); });

  /* ---------- 数据加载与渲染 ---------- */
  function boot() {
    $('#login').hidden = true; $('#panel').hidden = false; $('#topTools').hidden = false;
    refresh();
    setInterval(function () { if (document.visibilityState === 'visible' && !$('#panel').hidden) refresh(); }, 30000);
  }
  function refresh() {
    api('/api/admin/overview').then(function (r) { if (r && r.ok) renderOvw(r.stats); });
    api('/api/admin/decks').then(function (r) { if (r && r.ok) { DECKS = r.decks; renderDecks(r.decks); renderDeckSel(r.decks); } });
    api('/api/admin/visits?limit=100').then(function (r) { if (r && r.ok) renderVisits(r.visits); });
    loadSlides();
  }
  function renderOvw(s) {
    $('#ovw').innerHTML =
      '<div class="stat"><b>' + s.total + '</b><span>累计访问</span></div>' +
      '<div class="stat"><b>' + s.visitors + '</b><span>独立访客</span></div>' +
      '<div class="stat"><b>' + fmtDur(s.active) + '</b><span>总观看时长</span></div>' +
      '<div class="stat"><b>' + s.today + '</b><span>今日访问</span></div>' +
      '<div class="stat"><b>' + s.week + '</b><span>近 7 天</span></div>';
  }
  function renderDecks(list) {
    if (!list.length) { $('#deckBox').innerHTML = '<p class="empty">decks/ 里还没有幻灯片。</p>'; return; }
    var rows = list.map(function (d) {
      var pills = '<span class="pill ' + (d.enabled ? 'on">公开' : 'off">已下架') + '</span>' +
        (d.locked ? '<span class="pill lock">🔒 密码</span>' : '');
      var st = d.stats || {};
      return '<tr data-slug="' + esc(d.slug) + '">' +
        '<td><b>' + esc(d.title) + '</b><br><span class="slug">' + esc(d.slug) + ' · ' + d.n_slides + ' 屏</span></td>' +
        '<td>' + pills + (d.hint ? '<br><span class="muted slug">提示：' + esc(d.hint) + '</span>' : '') + '</td>' +
        '<td class="num">' + (st.visits || 0) + '</td>' +
        '<td class="num">' + fmtDur(st.active || 0) + '</td>' +
        '<td class="num">' + ago(st.last || 0) + '</td>' +
        '<td><div class="rowbtns">' +
          '<button class="mini act-en">' + (d.enabled ? '下架' : '上架') + '</button>' +
          '<button class="mini act-pw">' + (d.locked ? '改密码' : '设密码') + '</button>' +
          (d.locked ? '<button class="mini danger act-rm">移除密码</button>' : '') +
        '</div></td></tr>';
    }).join('');
    $('#deckBox').innerHTML = '<table><thead><tr><th>内容</th><th>状态</th><th class="num">访问</th>' +
      '<th class="num">总时长</th><th class="num">最近</th><th>操作</th></tr></thead><tbody>' + rows + '</tbody></table>';
  }
  function deckClicks(e) {
    var btn = e.target.closest('button'); if (!btn) return;
    var tr = e.target.closest('tr[data-slug]'); if (!tr) return;
    var slug = tr.getAttribute('data-slug');
    if (btn.classList.contains('act-en')) {
      api('/api/admin/deck', { method:'POST', body: JSON.stringify({ slug: slug, enabled: btn.textContent === '下架' ? false : true }) })
        .then(function (r) { if (!r.ok) alert(r.error || '操作失败'); refresh(); });
    } else if (btn.classList.contains('act-rm')) {
      api('/api/admin/deck', { method:'POST', body: JSON.stringify({ slug: slug, password: null }) })
        .then(function (r) { if (!r.ok) alert(r.error || '操作失败'); refresh(); });
    } else if (btn.classList.contains('act-pw')) {
      var d = DECKS.filter(function (x) { return x.slug === slug; })[0] || {};
      var editor = document.getElementById('editor-' + slug);
      if (editor) { editor.remove(); return; }
      var etr = document.createElement('tr');
      etr.className = 'editor'; etr.id = 'editor-' + slug;
      etr.setAttribute('data-slug', slug);   // 让保存/取消也能被事件委托定位到
      etr.innerHTML = '<td colspan="6"><div class="editgrid">' +
        '<input type="text" id="hin-' + esc(slug) + '" placeholder="门禁页提示语（可选）" value="' + esc(d.hint || '') + '">' +
        '<input type="text" id="pw-' + esc(slug) + '" placeholder="新访问密码（留空 = 只改提示语）" autocomplete="off">' +
        '<button class="mini act-save">保存</button><button class="mini act-cancel">取消</button></div></td>';
      tr.after(etr);
    } else if (btn.classList.contains('act-save')) {
      var body = { slug: slug, hint: document.getElementById('hin-' + slug).value };
      var pw = document.getElementById('pw-' + slug).value;
      if (pw !== '') body.password = pw;
      api('/api/admin/deck', { method:'POST', body: JSON.stringify(body) })
        .then(function (r) { if (!r.ok) alert(r.error || '保存失败'); refresh(); });
    } else if (btn.classList.contains('act-cancel')) {
      document.getElementById('editor-' + slug).remove();
    }
  }
  $('#deckBox').addEventListener('click', deckClicks);
  function renderDeckSel(list) {
    var opts = '<option value="__library">展示台首页</option>' + list.map(function (d) {
      return '<option value="' + esc(d.slug) + '">' + esc(d.title) + '</option>'; }).join('');
    var sel = $('#deckSel');
    var cur = sel.value;
    sel.innerHTML = opts;
    if (cur && [].some.call(sel.options, function (o) { return o.value === cur; })) sel.value = cur;
  }
  function loadSlides() {
    var deck = $('#deckSel').value || '__library';
    api('/api/admin/slides?deck=' + encodeURIComponent(deck)).then(function (r) {
      if (!r || !r.ok) return;
      var rows = r.rows || [];
      if (!rows.length) { $('#slideBox').innerHTML = '<p class="empty">还没有逐屏数据。</p>'; $('#slideNote').textContent = ''; return; }
      var maxD = Math.max.apply(null, rows.map(function (x) { return x.dwell; })) || 1;
      var totalViews = rows.reduce(function (a, x) { return a + x.views; }, 0);
      $('#slideNote').textContent = '共 ' + totalViews + ' 次进屏';
      $('#slideBox').innerHTML = '<table><thead><tr><th class="num">屏</th><th class="num">进入</th>' +
        '<th class="num">平均停留</th><th class="num">总停留</th><th>热度</th></tr></thead><tbody>' +
        rows.map(function (x) {
          return '<tr><td class="num">' + (x.slide + 1) + '</td><td class="num">' + x.views + '</td>' +
            '<td class="num">' + fmtDur(x.avg) + '</td><td class="num">' + fmtDur(x.dwell) + '</td>' +
            '<td><div class="heat"><i style="width:' + Math.round(x.dwell / maxD * 100) + '%"></i></div></td></tr>';
        }).join('') + '</tbody></table>';
    });
  }
  $('#deckSel').addEventListener('change', loadSlides);

  function renderVisits(list) {
    if (!list.length) { $('#visitBox').innerHTML = '<p class="empty">还没有访问记录。</p>'; return; }
    $('#visitBox').innerHTML = '<table><thead><tr><th>时间</th><th>内容</th><th class="num">时长</th>' +
      '<th class="num">看到</th><th>访客</th><th>IP</th><th>客户端</th><th>来源</th></tr></thead><tbody>' +
      list.map(function (v) {
        var prog = v.n_slides ? (Math.min(v.max_slide + 1, v.n_slides) + '/' + v.n_slides + ' 屏') : '—';
        return '<tr><td class="num">' + fmtT(v.started) + '</td>' +
          '<td>' + esc(TITLES[v.deck] || v.deck) + '</td>' +
          '<td class="num">' + fmtDur(v.active) + '</td>' +
          '<td class="num">' + prog + '</td>' +
          '<td class="slug">' + esc(String(v.visitor).slice(0, 8)) + '</td>' +
          '<td class="slug">' + esc(v.ip || '—') + '</td>' +
          '<td>' + uaShort(v.ua || '') + '</td>' +
          '<td class="slug">' + esc(v.referrer ? v.referrer.replace(/^https?:\\/\\/[^/]+/, '') : '直接打开') + '</td></tr>';
      }).join('') + '</tbody></table>';
  }

  /* ---------- 顶部操作 ---------- */
  $('#refreshBtn').addEventListener('click', refresh);
  $('#logoutBtn').addEventListener('click', function () {
    api('/api/admin/logout', { method:'POST' }).then(function () { location.reload(); });
  });
  $('#passwdBtn').addEventListener('click', function () {
    var o = prompt('当前管理密码：'); if (o == null) return;
    var n = prompt('新管理密码（至少 6 位）：'); if (n == null) return;
    if (n.length < 6) { alert('新密码至少 6 位'); return; }
    api('/api/admin/password', { method:'POST', body: JSON.stringify({ old: o, new: n }) })
      .then(function (r) { alert(r.ok ? '✅ 已更新' : (r.error || '失败')); });
  });
  $('#clearBtn').addEventListener('click', function () {
    if (!confirm('确定清空全部访问统计？此操作不可恢复。')) return;
    api('/api/admin/stats/clear', { method:'POST' }).then(function () { refresh(); });
  });

  /* ---------- 启动 ---------- */
  api('/api/admin/session').then(function (r) {
    if (r && r.authed) boot();
  });
})();
</script></body></html>"""


def admin_page() -> str:
    return _ADMIN.replace("__BASE__", _BASE_CSS)
