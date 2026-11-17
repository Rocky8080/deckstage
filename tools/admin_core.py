#!/usr/bin/env python3
"""
admin_core.py — /admin 后台数据层：管理员会话、deck 门禁配置、访问追踪存储

约定（运行时数据都在 <root>/data/，不入库 git）：
    data/admin.json    管理员密码哈希 + cookie 签名密钥（0600）
    data/access.json   每个 deck 的门禁：enabled / password_hash / hint
    data/tracking.db   SQLite：visits（一次访问一行，心跳续写）+ slide_stats（逐屏停留）
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import threading
import time
from datetime import datetime, timedelta

PBKDF_ITERS = 120_000
SESSION_TTL = 12 * 3600          # 管理员登录态
DECK_COOKIE_TTL = 30 * 86400     # deck 密码通过后的免输期
LOGIN_WINDOW = 600               # 登录限流窗口（秒）
LOGIN_MAX_TRIES = 8

# 「未提供」哨兵：None 表示“明确删除密码”，缺省表示“不动这一项”
UNSET = object()


def _hash_pw(pw: str, salt_hex: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", pw.encode("utf-8"),
                               bytes.fromhex(salt_hex), PBKDF_ITERS).hex()


class Store:
    """全部状态落盘 / 落库，Handler 侧只持有这一个对象（线程安全：写操作串行化）。"""

    def __init__(self, root: str):
        self.root = root
        self.data_dir = os.path.join(root, "data")
        os.makedirs(self.data_dir, exist_ok=True)
        self.cfg_path = os.path.join(self.data_dir, "admin.json")
        self.access_path = os.path.join(self.data_dir, "access.json")
        self.db_path = os.path.join(self.data_dir, "tracking.db")
        self._lock = threading.Lock()
        self._fails: dict[str, list[float]] = {}
        self.generated_password: str | None = None   # 首次创建时的明文，仅供启动时打印一次
        self._ensure_admin_cfg()
        self._ensure_db()

    # ------------------------------------------------------------ 管理员配置
    def _ensure_admin_cfg(self):
        if os.path.exists(self.cfg_path):
            return
        initial = os.environ.get("DECK_ADMIN_PASSWORD") or secrets.token_urlsafe(9)
        salt = secrets.token_hex(16)
        cfg = {
            "secret": secrets.token_hex(32),          # cookie 签名密钥（轮换 = 全部登录态失效）
            "salt": salt,
            "password_hash": _hash_pw(initial, salt),
            "created": datetime.now().isoformat(timespec="seconds"),
        }
        self.generated_password = None if os.environ.get("DECK_ADMIN_PASSWORD") else initial
        fd = os.open(self.cfg_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(cfg, fh, ensure_ascii=False, indent=2)

    def _cfg(self) -> dict:
        with open(self.cfg_path, encoding="utf-8") as fh:
            return json.load(fh)

    def verify_admin_password(self, pw: str) -> bool:
        cfg = self._cfg()
        return hmac.compare_digest(_hash_pw(pw, cfg["salt"]), cfg["password_hash"])

    def set_admin_password(self, pw: str):
        cfg = self._cfg()
        cfg["salt"] = secrets.token_hex(16)
        cfg["password_hash"] = _hash_pw(pw, cfg["salt"])
        with open(self.cfg_path, "w", encoding="utf-8") as fh:
            json.dump(cfg, fh, ensure_ascii=False, indent=2)

    # ------------------------------------------------------------ 签名 token（admin 会话 / deck 免密 cookie）
    def _sign(self, msg: str) -> str:
        return hmac.new(self._cfg()["secret"].encode(), msg.encode(), hashlib.sha256).hexdigest()

    def make_token(self, key: str, ttl: int) -> str:
        exp = int(time.time()) + ttl
        return f"{exp}:{self._sign(f'{key}:{exp}')}"

    def check_token(self, key: str, tok: str | None) -> bool:
        if not tok or tok.count(":") != 1:
            return False
        exp, sig = tok.split(":", 1)
        try:
            exp = int(exp)
        except ValueError:
            return False
        if exp < time.time():
            return False
        return hmac.compare_digest(sig, self._sign(f"{key}:{exp}"))

    # ------------------------------------------------------------ 登录限流
    def login_allowed(self, ip: str) -> bool:
        now = time.time()
        self._fails[ip] = [t for t in self._fails.get(ip, []) if now - t < LOGIN_WINDOW]
        return len(self._fails[ip]) < LOGIN_MAX_TRIES

    def login_fail(self, ip: str):
        self._fails.setdefault(ip, []).append(time.time())

    # ------------------------------------------------------------ deck 门禁配置
    def _access(self) -> dict:
        try:
            with open(self.access_path, encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, json.JSONDecodeError):
            return {}

    def _write_access(self, data: dict):
        with self._lock:
            fd = os.open(self.access_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False, indent=2)

    def access_map(self) -> dict:
        """全部 deck 门禁原始配置（library 过滤用）。"""
        return self._access()

    def deck_cfg(self, slug: str) -> dict:
        """对外形状：{enabled, locked, hint}；没配置过的 deck = 公开 + 无密码。"""
        c = self._access().get(slug, {})
        return {"enabled": c.get("enabled", True),
                "locked": bool(c.get("password_hash")),
                "hint": c.get("hint", "")}

    def set_deck(self, slug: str, enabled=UNSET, password=UNSET, hint=UNSET):
        data = self._access()
        c = data.setdefault(slug, {})
        if enabled is not UNSET:
            c["enabled"] = bool(enabled)
        if password is not UNSET:
            if password in (None, ""):
                c.pop("password_hash", None)
                c.pop("salt", None)
            else:
                salt = secrets.token_hex(16)
                c["salt"] = salt
                c["password_hash"] = _hash_pw(str(password), salt)
        if hint is not UNSET:
            c["hint"] = str(hint)[:200]
        if all(k not in c for k in ("enabled", "password_hash", "hint")):
            data.pop(slug, None)
        self._write_access(data)

    def verify_deck_password(self, slug: str, pw: str) -> bool:
        c = self._access().get(slug, {})
        if not c.get("password_hash"):
            return False
        return hmac.compare_digest(_hash_pw(pw, c["salt"]), c["password_hash"])

    # ------------------------------------------------------------ 追踪写入
    def _ensure_db(self):
        with sqlite3.connect(self.db_path) as con:
            con.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS visits (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                deck       TEXT NOT NULL,
                visitor    TEXT NOT NULL,
                ip         TEXT, ua TEXT, referrer TEXT,
                started    REAL NOT NULL,
                last       REAL NOT NULL,
                active     REAL NOT NULL DEFAULT 0,
                max_slide  INTEGER NOT NULL DEFAULT 0,
                n_slides   INTEGER NOT NULL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_visits_deck ON visits(deck, started);
            CREATE TABLE IF NOT EXISTS slide_stats (
                visit_id INTEGER NOT NULL,
                deck     TEXT NOT NULL,
                slide    INTEGER NOT NULL,
                dwell    REAL NOT NULL DEFAULT 0,
                views    INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (visit_id, deck, slide)
            );
            CREATE INDEX IF NOT EXISTS idx_ss_deck ON slide_stats(deck);
            """)

    @staticmethod
    def _clamp(v, lo, hi, default=0) -> int:
        try:
            v = int(v)
        except (TypeError, ValueError):
            return default
        return max(lo, min(hi, v))

    def track_init(self, deck: str, visitor: str, ip: str, ua: str, referrer: str,
                   n_slides: int) -> int:
        now = time.time()
        with self._lock, sqlite3.connect(self.db_path) as con:
            cur = con.execute(
                "INSERT INTO visits(deck,visitor,ip,ua,referrer,started,last,n_slides) "
                "VALUES(?,?,?,?,?,?,?,?)",
                (deck[:80], visitor[:64], ip[:64], ua[:200], referrer[:200],
                 now, now, self._clamp(n_slides, 0, 500)))
            return cur.lastrowid

    def track_beat(self, visit_id: int, active_ms: int,
                   items: list) -> bool:
        """心跳续写：累计活跃秒数 + 逐屏停留批量入库。

        items: [[slide, dwell_ms, entered01], ...]。visit 不存在返回 False。"""
        now = time.time()
        a = self._clamp(active_ms, 0, 120_000) / 1000.0
        rows = []
        maxs = 0
        for it in (items or [])[:40]:
            if not isinstance(it, (list, tuple)) or len(it) < 2:
                continue
            s = self._clamp(it[0], 0, 500)
            d = self._clamp(it[1], 0, 120_000) / 1000.0
            e = 1 if len(it) > 2 and it[2] else 0
            rows.append((visit_id, s, d, e))
            maxs = max(maxs, s)
        with self._lock, sqlite3.connect(self.db_path) as con:
            row = con.execute("SELECT deck FROM visits WHERE id=?", (visit_id,)).fetchone()
            if not row:
                return False
            deck = row[0]
            if a or rows:
                con.execute("UPDATE visits SET last=?, active=active+?, max_slide=MAX(max_slide,?) "
                            "WHERE id=?", (now, a, maxs, visit_id))
            for visit_id_, s, d, e in rows:
                con.execute("""INSERT INTO slide_stats(visit_id,deck,slide,dwell,views)
                               VALUES(?,?,?,?,1)
                               ON CONFLICT(visit_id,deck,slide) DO UPDATE SET
                                 dwell = dwell + excluded.dwell,
                                 views = views + ?""",
                            (visit_id_, deck, s, d, e))
        return True

    # ------------------------------------------------------------ 追踪查询（admin 面板）
    def overview(self) -> dict:
        day0 = time.mktime(time.strptime(time.strftime("%Y-%m-%d"), "%Y-%m-%d"))
        week = time.time() - 7 * 86400
        with sqlite3.connect(self.db_path) as con:
            total, visitors, active = con.execute(
                "SELECT COUNT(*), COUNT(DISTINCT visitor), COALESCE(SUM(active),0) "
                "FROM visits").fetchone()
            today = con.execute("SELECT COUNT(*) FROM visits WHERE started>=?",
                                (day0,)).fetchone()[0]
            week_n = con.execute("SELECT COUNT(*) FROM visits WHERE started>=?",
                                 (week,)).fetchone()[0]
            new_today, new_7d, returning = con.execute(
                """SELECT COALESCE(SUM(CASE WHEN fs>=? THEN 1 ELSE 0 END),0),
                          COALESCE(SUM(CASE WHEN fs>=? THEN 1 ELSE 0 END),0),
                          COALESCE(SUM(CASE WHEN fs<?  THEN 1 ELSE 0 END),0)
                   FROM (SELECT visitor, MIN(started) AS fs
                         FROM visits GROUP BY visitor)""",
                (day0, week, week)).fetchone()
        return {"total": total, "visitors": visitors, "active": round(active),
                "today": today, "week": week_n,
                "new_today": new_today, "new_7d": new_7d, "returning": returning}

    def visitor_stats(self) -> list[dict]:
        """按访客聚合：次数/时长/首末访问/看过的内容/IP，用于新/老用户分析。"""
        with sqlite3.connect(self.db_path) as con:
            rows = con.execute(
                """SELECT v.visitor, COUNT(*), COALESCE(SUM(v.active),0), MIN(v.started),
                          MAX(v.started), COUNT(DISTINCT v.deck),
                          GROUP_CONCAT(DISTINCT v.deck),
                          (SELECT ip FROM visits WHERE visitor=v.visitor
                           ORDER BY started DESC, id DESC LIMIT 1),
                          COUNT(DISTINCT v.ip),
                          GROUP_CONCAT(DISTINCT v.ip)
                   FROM visits v GROUP BY v.visitor ORDER BY MAX(v.started) DESC"""
            ).fetchall()
        return [{"visitor": r[0], "visits": r[1], "active": round(r[2]),
                 "first_seen": r[3], "last_seen": r[4], "decks": r[5],
                 "deck_list": r[6] or "", "last_ip": r[7] or "—",
                 "ip_count": r[8] or 0, "all_ips": r[9] or ""} for r in rows]

    def deck_stats(self) -> dict:
        """slug → {visits, visitors, active, last}"""
        with sqlite3.connect(self.db_path) as con:
            rows = con.execute(
                "SELECT deck, COUNT(*), COUNT(DISTINCT visitor), COALESCE(SUM(active),0), "
                "MAX(last) FROM visits GROUP BY deck").fetchall()
        return {r[0]: {"visits": r[1], "visitors": r[2], "active": round(r[3]), "last": r[4]}
                for r in rows}

    def recent_visits(self, limit: int = 100, visitor: str | None = None) -> list[dict]:
        limit = self._clamp(limit, 1, 500, 100)
        with sqlite3.connect(self.db_path) as con:
            con.row_factory = sqlite3.Row
            if visitor:
                rows = con.execute(
                    "SELECT id,deck,visitor,ip,ua,referrer,started,last,active,max_slide,n_slides "
                    "FROM visits WHERE visitor=? ORDER BY id DESC LIMIT ?",
                    (visitor[:64], limit)).fetchall()
            else:
                rows = con.execute(
                    "SELECT id,deck,visitor,ip,ua,referrer,started,last,active,max_slide,n_slides "
                    "FROM visits ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def slide_stats(self, deck: str) -> list[dict]:
        with sqlite3.connect(self.db_path) as con:
            rows = con.execute(
                "SELECT slide, SUM(views), SUM(dwell) FROM slide_stats WHERE deck=? "
                "GROUP BY slide ORDER BY slide", (deck[:80],)).fetchall()
        return [{"slide": r[0], "views": r[1] or 0, "dwell": round(r[2] or 0, 1),
                 "avg": round((r[2] or 0) / r[1], 1) if r[1] else 0} for r in rows]

    def clear_stats(self):
        with self._lock, sqlite3.connect(self.db_path) as con:
            con.execute("DELETE FROM slide_stats")
            con.execute("DELETE FROM visits")

    # ------------------------------------------------------------ deck 目录扫描（管理面板的内容清单）
    def deck_list(self) -> list[dict]:
        decks_dir = os.path.join(self.root, "decks")
        out = []
        if not os.path.isdir(decks_dir):
            return out
        for name in sorted(os.listdir(decks_dir)):
            index = os.path.join(decks_dir, name, "index.html")
            if not os.path.isfile(index):
                continue
            meta = {}
            cfg = os.path.join(decks_dir, name, "deck.json")
            if os.path.isfile(cfg):
                try:
                    meta = json.loads(open(cfg, encoding="utf-8").read())
                except (OSError, json.JSONDecodeError):
                    pass
            try:
                text = open(index, encoding="utf-8", errors="ignore").read()
            except OSError:
                continue
            slides = len(_RE_SLIDE.findall(text)) or len(_RE_DT.findall(text))
            m = _RE_DT.search(text)
            out.append({"slug": name,
                        "title": meta.get("title") or (m.group(1) if m else name),
                        "n_slides": slides})
        return out


import re as _re
_RE_SLIDE = _re.compile(r'<section[^>]*class="slide')
_RE_DT = _re.compile(r'data-title="([^"]*)"')


def fmt_duration(sec: float) -> str:
    sec = int(sec)
    if sec < 60:
        return f"{sec}秒"
    if sec < 3600:
        return f"{sec // 60}分{sec % 60:02d}秒"
    return f"{sec // 3600}:{sec % 3600 // 60:02d}:{sec % 60:02d}"


def fmt_time(ts: float) -> str:
    if not ts:
        return "—"
    return datetime.fromtimestamp(ts).strftime("%m-%d %H:%M:%S")


def fmt_timedelta(ts: float) -> str:
    if not ts:
        return "—"
    delta = timedelta(seconds=max(0, time.time() - ts))
    s = int(delta.total_seconds())
    if s < 60:
        return "刚刚"
    if s < 3600:
        return f"{s // 60} 分钟前"
    if s < 86400:
        return f"{s // 3600} 小时前"
    return f"{s // 86400} 天前"
