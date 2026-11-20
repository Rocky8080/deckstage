#!/usr/bin/env python3
"""
deck_themes.py — 原生 deck 的预设配色方案 + 运行时切换（由 serve_deck.py 注入）

前提：全部 deck 共用 src/css/tokens.css 的变量契约（--paper/--ink/--green*/--terra*/
--gold*/--up/--down/--dark*）。预设 = 同名变量的成套覆盖，`html[data-dtheme=…]`
特异度高于 deck 内嵌的 `:root`，不改 deck 文件即可整套换色。

切换：放映中按 `C` 循环，或右下角调色板浮窗点选；按 deck 存 localStorage。
`?export=1`（缩略图采集）不注入，缩略图始终用 deck 原配色。
"""

# 变量分组与值全部按 tokens.css 语义推导；tint/wash/soft 是浅色底块，
# 深色主题（ink-dark）下给深底、--dark*（页内深面板）反转成浅面板。
THEMES = [
    {"id": None, "name": "默认", "note": "deck 原配色", "vars": {}},

    {"id": "paper-white", "name": "素白", "note": "纯白纸面 + 墨绿主色",
     "vars": {
         "--paper": "#FFFFFF", "--paper-2": "#FCFCFA", "--paper-3": "#F4F4F0",
         "--ink": "#14171A", "--ink-2": "#353C3A", "--ink-3": "#5B6561",
         "--ink-4": "#6E7873", "--line": "#E2E3DD", "--line-soft": "#EFF0EB",
         "--green": "#16533F", "--green-2": "#226B52", "--green-3": "#4C8B74",
         "--green-tint": "#E7EFEA", "--green-wash": "#F2F6F3",
         "--terra": "#A8481F", "--terra-2": "#C25C32", "--terra-tint": "#F8E8E0",
         "--gold": "#8B6B22", "--gold-tint": "#F5EFDC",
         "--up": "#B3261E", "--up-2": "#D04A3F", "--up-soft": "#F7E2DE",
         "--down": "#1F6B53", "--down-2": "#16533F", "--down-soft": "#E2EFE9",
         "--dark": "#0E1512", "--dark-2": "#18211D", "--dark-3": "#222D28",
         "--dark-line": "#33423A",
         "--ambient-1": "rgba(22, 83, 63, .035)",
         "--ambient-2": "rgba(168, 72, 31, .024)",
         "--ambient-3": "rgba(37, 99, 235, .018)",
         "--ambient-4": "transparent"}},

    {"id": "navy", "name": "藏青", "note": "冷调纸面 + 靛蓝主色",
     "vars": {
         "--paper": "#F3F5F9", "--paper-2": "#FBFCFE", "--paper-3": "#E8EDF4",
         "--ink": "#111A2B", "--ink-2": "#2E3D55", "--ink-3": "#4C5E7A",
         "--ink-4": "#76839B", "--line": "#D3DAE5", "--line-soft": "#E1E7EF",
         "--green": "#1D4E89", "--green-2": "#2F6BAD", "--green-3": "#729FD1",
         "--green-tint": "#E1EAF5", "--green-wash": "#EAF1F8",
         "--terra": "#A83A55", "--terra-2": "#C25871", "--terra-tint": "#F6E0E6",
         "--gold": "#A08339", "--gold-tint": "#F1EAD5",
         "--up": "#C0392B", "--up-2": "#D9574A", "--up-soft": "#F5E0DC",
         "--down": "#2F6BAD", "--down-2": "#1D4E89", "--down-soft": "#E0EAF6",
         "--dark": "#0F1728", "--dark-2": "#16203A", "--dark-3": "#1E2A46",
         "--dark-line": "#2C3A58",
         "--ambient-1": "rgba(29, 78, 137, .06)",
         "--ambient-2": "rgba(168, 58, 85, .032)",
         "--ambient-3": "rgba(44, 120, 160, .028)",
         "--ambient-4": "transparent"}},

    {"id": "terra", "name": "暖赭", "note": "暖纸面 + 赭陶主色",
     "vars": {
         "--paper": "#F8F2EA", "--paper-2": "#FEFBF6", "--paper-3": "#F0E6DA",
         "--ink": "#231A12", "--ink-2": "#46392B", "--ink-3": "#655643",
         "--ink-4": "#8B7D6B", "--line": "#DFD2C0", "--line-soft": "#EAE0D2",
         "--green": "#A65232", "--green-2": "#BF6B45", "--green-3": "#D89270",
         "--green-tint": "#F3E2D6", "--green-wash": "#F8EBE1",
         "--terra": "#96351C", "--terra-2": "#B04F30", "--terra-tint": "#F6DFD4",
         "--gold": "#A9863C", "--gold-tint": "#F3EAD5",
         "--up": "#C0392B", "--up-2": "#D9574A", "--up-soft": "#F5E0DC",
         "--down": "#BF6B45", "--down-2": "#A65232", "--down-soft": "#F3E2D6",
         "--dark": "#1C130C", "--dark-2": "#2A1D13", "--dark-3": "#38271A",
         "--dark-line": "#4A3624",
         "--ambient-1": "rgba(166, 82, 50, .06)",
         "--ambient-2": "rgba(169, 134, 60, .038)",
         "--ambient-3": "rgba(29, 78, 137, .02)",
         "--ambient-4": "transparent"}},

    {"id": "violet", "name": "紫藤", "note": "冷紫纸面 + 绛紫主色",
     "vars": {
         "--paper": "#F5F3F8", "--paper-2": "#FCFAFE", "--paper-3": "#EAE6F1",
         "--ink": "#1B1528", "--ink-2": "#383050", "--ink-3": "#544B70",
         "--ink-4": "#7C7490", "--line": "#D9D3E4", "--line-soft": "#E5E0EE",
         "--green": "#5B4A8A", "--green-2": "#72619F", "--green-3": "#9C8FC4",
         "--green-tint": "#E8E3F4", "--green-wash": "#EFEAF8",
         "--terra": "#AE3A66", "--terra-2": "#C75C86", "--terra-tint": "#F6E0EB",
         "--gold": "#A08339", "--gold-tint": "#F1EAD5",
         "--up": "#C0392B", "--up-2": "#D9574A", "--up-soft": "#F5E0DC",
         "--down": "#72619F", "--down-2": "#5B4A8A", "--down-soft": "#E8E3F4",
         "--dark": "#171226", "--dark-2": "#221B36", "--dark-3": "#2D2446",
         "--dark-line": "#3E3359",
         "--ambient-1": "rgba(91, 74, 138, .06)",
         "--ambient-2": "rgba(174, 58, 102, .032)",
         "--ambient-3": "rgba(29, 78, 137, .022)",
         "--ambient-4": "transparent"}},

    {"id": "celadon", "name": "青瓷", "note": "灰绿纸面 + 青瓷主色",
     "vars": {
         "--paper": "#F1F5F2", "--paper-2": "#FAFCFA", "--paper-3": "#E2EBE5",
         "--ink": "#13221C", "--ink-2": "#2F443B", "--ink-3": "#4E635A",
         "--ink-4": "#74857D", "--line": "#CFDDD5", "--line-soft": "#DFE9E3",
         "--green": "#35766A", "--green-2": "#438C7E", "--green-3": "#8CC2B2",
         "--green-tint": "#DEECE6", "--green-wash": "#E8F1EC",
         "--terra": "#C05A42", "--terra-2": "#D4755D", "--terra-tint": "#F7E1DA",
         "--gold": "#A9863C", "--gold-tint": "#F3EAD5",
         "--up": "#C0392B", "--up-2": "#D9574A", "--up-soft": "#F5E0DC",
         "--down": "#35766A", "--down-2": "#2F6B60", "--down-soft": "#DEECE6",
         "--dark": "#10201B", "--dark-2": "#182B25", "--dark-3": "#20362E",
         "--dark-line": "#2E453B",
         "--ambient-1": "rgba(53, 118, 106, .06)",
         "--ambient-2": "rgba(192, 90, 66, .03)",
         "--ambient-3": "rgba(29, 78, 137, .02)",
         "--ambient-4": "transparent"}},

    {"id": "ink-dark", "name": "玄墨", "note": "抬起的炭黑 · 墨绿冷光",
     "vars": {
         "--paper": "#1B211F", "--paper-2": "#222926", "--paper-3": "#2A322E",
         "--ink": "#ECE8DF", "--ink-2": "#CBC6BB", "--ink-3": "#A39D91",
         "--ink-4": "#8C867D", "--line": "#3C443F", "--line-soft": "#313834",
         "--green": "#5BB08D", "--green-2": "#70C4A1", "--green-3": "#9AD6BA",
         "--green-tint": "#26342D", "--green-wash": "#202C26",
         "--terra": "#D87047", "--terra-2": "#E58860", "--terra-tint": "#38281F",
         "--gold": "#CDAB5F", "--gold-tint": "#342C1D",
         "--up": "#E4594A", "--up-2": "#EE7466", "--up-soft": "#3D2420",
         "--down": "#5BB08D", "--down-2": "#70C4A1", "--down-soft": "#1F2C26",
         "--dark": "#101513", "--dark-2": "#161C19", "--dark-3": "#1D2521",
         "--dark-line": "#2D3732",
         "--ambient-1": "rgba(91, 176, 141, .08)",
         "--ambient-2": "rgba(216, 112, 71, .055)",
         "--ambient-3": "rgba(80, 140, 190, .05)",
         "--ambient-4": "rgba(90, 180, 190, .04)"}},
]

ORDER = [t["id"] for t in THEMES]
NAMES = {t["id"]: t["name"] for t in THEMES}
NOTES = {t["id"]: t["note"] for t in THEMES}


def theme_style_block() -> str:
    rules = []
    for t in THEMES:
        if not t["id"]:
            continue
        body = "\n".join(f"  {k}:{v};" for k, v in t["vars"].items())
        rules.append(f'html[data-dtheme="{t["id"]}"]{{\n{body}\n}}')
    return "<style id=\"deck-themes\">\n" + "\n".join(rules) + "\n</style>"


def _js_data() -> dict:
    order = ",".join("null" if i is None else f'"{i}"' for i in ORDER)
    names = "{" + ",".join(
        (f'"default":"{NAMES[None]}"' if i is None else f'"{i}":"{NAMES[i]}"')
        for i in ORDER) + "}"
    notes = "{" + ",".join(
        (f'"default":"{NOTES[None]}"' if i is None else f'"{i}":"{NOTES[i]}"')
        for i in ORDER) + "}"
    dots = "{" + ",".join(
        ('"default":"linear-gradient(135deg,#1E5B47,#B4522B)"' if i is None
         else f'"{i}":"{next(t["vars"]["--green"] for t in THEMES if t["id"] == i)}"')
        for i in ORDER) + "}"
    return {"__ORDER__": order, "__NAMES__": names, "__NOTES__": notes, "__DOTS__": dots}


def theme_picker_script(slug: str) -> str:
    data = _js_data()
    return """<style id="deck-theme-ui">
.dtheme-fab{position:fixed;right:16px;bottom:64px;z-index:980;display:flex;align-items:center;gap:6px;
  padding:7px 13px;border-radius:999px;border:1px solid rgba(128,128,128,.45);
  background:rgba(127,127,127,.14);backdrop-filter:blur(6px);cursor:pointer;
  color:inherit;font:12.5px/1 -apple-system,"PingFang SC",sans-serif;letter-spacing:.03em;
  opacity:.6;transition:opacity .2s,transform .15s}
.dtheme-fab:hover{opacity:1;transform:translateY(-1px)}
.dtheme-fab .dt-ico{font-size:13px;line-height:1}
.dtheme-panel{position:fixed;right:16px;bottom:106px;z-index:981;display:none;flex-direction:column;gap:2px;
  background:rgba(20,20,20,.9);backdrop-filter:blur(8px);border-radius:12px;padding:8px;min-width:230px;
  box-shadow:0 14px 40px rgba(0,0,0,.3)}
.dtheme-panel.is-open{display:flex}
.dt-item{display:flex;align-items:center;gap:9px;padding:8px 11px;border:0;border-radius:8px;background:none;
  color:#eee;font:12.5px/1 -apple-system,"PingFang SC",sans-serif;cursor:pointer;text-align:left;white-space:nowrap}
.dt-item:hover{background:rgba(255,255,255,.14)}
.dt-dot{width:15px;height:15px;border-radius:50%;display:inline-block;flex:none;box-shadow:inset 0 0 0 1px rgba(255,255,255,.25)}
.dt-item .dt-note{color:#9a9a9a;font-size:11px;margin-left:auto;padding-left:12px}
.dt-item.is-cur{background:rgba(255,255,255,.1)}
.dt-item.is-cur span:not(.dt-note){font-weight:700}
.dt-item.is-cur::after{content:"✓";color:#7ec8a9;margin-left:6px}
.dtheme-toast{position:fixed;top:14px;left:50%;transform:translateX(-50%);z-index:982;padding:8px 18px;
  border-radius:999px;background:rgba(20,20,20,.85);color:#eee;font:13px/1 -apple-system,"PingFang SC",sans-serif;
  opacity:0;transition:opacity .25s;pointer-events:none}
.dtheme-toast.is-show{opacity:1}
/* 放映模式：不消失，只是更低调；鼠标一碰即满显 —— 保证任何时刻都能鼠标切换 */
body.is-presenting .dtheme-fab,body.chrome-hidden .dtheme-fab{opacity:.28}
body.is-presenting .dtheme-fab:hover,body.chrome-hidden .dtheme-fab:hover{opacity:1}
</style>
<script>(function(){
if (window.__deckThemes) return; window.__deckThemes = 1;
var SLUG = "__SLUG__";
var ORDER = [__ORDER__];
var NAMES = __NAMES__;
var NOTES = __NOTES__;
var DOTS = __DOTS__;
var KEY = "dtheme:" + SLUG;
var root = document.documentElement, cur = null;
function apply(id, save){
  root.setAttribute("data-dtheme", id || "default");
  cur = id;
  if (save){
    try { if (id) localStorage.setItem(KEY, id); else localStorage.removeItem(KEY); } catch(e){}
  }
  var p = document.getElementById("dtPanel");
  if (p) [].forEach.call(p.querySelectorAll(".dt-item"), function(b){
    b.classList.toggle("is-cur", (b.getAttribute("data-t") || null) === cur);
  });
}
function toast(msg){
  var t = document.getElementById("dtToast");
  if (!t) return;
  t.textContent = msg; t.classList.add("is-show");
  clearTimeout(toast._tm);
  toast._tm = setTimeout(function(){ t.classList.remove("is-show"); }, 1300);
}
function set(id, save){
  apply(id, save);
  toast("配色 · " + NAMES[cur || "default"] + (cur ? "（" + NOTES[cur || "default"] + "）" : "（deck 原配色）"));
}
function cycle(){
  set(ORDER[(ORDER.indexOf(cur) + 1) % ORDER.length], true);
}
window.addEventListener("keydown", function(e){
  if (e.key !== "c" && e.key !== "C") return;
  var t = e.target;
  if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable)) return;
  if (e.metaKey || e.ctrlKey || e.altKey) return;
  cycle();
}, true);
function buildUI(){
  var fab = document.createElement("button");
  fab.className = "dtheme-fab"; fab.id = "dtFab";
  fab.title = "切换配色方案（快捷键 C）";
  fab.setAttribute("aria-label", "切换配色方案");
  fab.innerHTML = '<span class="dt-ico">🎨</span><span>配色</span>';
  fab.addEventListener("click", function(e){
    e.stopPropagation();
    document.getElementById("dtPanel").classList.toggle("is-open");
  });
  var panel = document.createElement("div");
  panel.className = "dtheme-panel"; panel.id = "dtPanel";
  panel.innerHTML = ORDER.map(function(id){
    var key = id || "default";
    return '<button class="dt-item" data-t="' + (id || "") + '" title="' + NOTES[key] + '">' +
      '<i class="dt-dot" style="background:' + DOTS[key] + '"></i>' +
      '<span>' + NAMES[key] + '</span><span class="dt-note">' + NOTES[key] + '</span></button>';
  }).join("");
  panel.addEventListener("click", function(e){
    var b = e.target.closest(".dt-item");
    if (!b) return;
    set(b.getAttribute("data-t") || null, true);
    panel.classList.remove("is-open");
  });
  document.addEventListener("click", function(e){
    if (!panel.classList.contains("is-open")) return;
    if (panel.contains(e.target) || fab.contains(e.target)) return;
    panel.classList.remove("is-open");
  }, true);
  var toast = document.createElement("div");
  toast.className = "dtheme-toast"; toast.id = "dtToast";
  document.body.appendChild(fab);
  document.body.appendChild(panel);
  document.body.appendChild(toast);
  apply(cur, false);
}
if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", buildUI);
else buildUI();
(function(){
  var wanted = null;
  try { wanted = new URLSearchParams(location.search).get("dtheme"); } catch(e){}
  if (wanted !== null) {
    if (wanted === "default" || wanted === "") { apply(null, false); return; }
    if (ORDER.indexOf(wanted) >= 0) { apply(wanted, false); return; }
  }
  var saved = null;
  try { saved = localStorage.getItem(KEY); } catch(e){}
  if (saved && ORDER.indexOf(saved) >= 0) apply(saved, false);
})();
})();</script>""".replace("__SLUG__", slug).replace("__ORDER__", data["__ORDER__"]) \
        .replace("__NAMES__", data["__NAMES__"]).replace("__NOTES__", data["__NOTES__"]) \
        .replace("__DOTS__", data["__DOTS__"])


def theme_assets(slug: str) -> str:
    """deck 页注入资产：变量覆盖样式 + 切换器（含记忆）。"""
    return theme_style_block() + theme_picker_script(slug)
