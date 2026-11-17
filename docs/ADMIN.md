# 管理后台 /admin

`tools/serve_deck.py` 内置的管理面：访问追踪、deck 门禁（密码 / 下架）。由服务端动态实现，
**不需要重新 build** —— 开关即时生效。

## 启动与登录

```bash
python3 tools/serve_deck.py            # 首次启动会生成初始管理密码并打印一次
python3 tools/serve_deck.py --admin-password 新密码   # 随时重置
DECK_ADMIN_PASSWORD=xxx python3 tools/serve_deck.py  # 首次初始化用环境变量
```

打开 `/admin/`（展示台页脚有入口），输入管理密码登录。登录态为签名 Cookie，12 小时有效；
密码错误有 IP 限流（10 分钟 8 次）。全部秘密（管理密码哈希 + Cookie 签名密钥）在
`data/admin.json`（0600，不入库 git）；删除该文件即全部登出并重新生成。

## 功能

| 区块 | 说明 |
| --- | --- |
| 概览 | 累计访问 / 独立访客 / 总观看时长 / 今日 / 近 7 天 |
| 内容管理 | 每个 deck：上架 ⇄ 下架（前端立即消失并 404）、设置 / 移除访问密码 + 门禁页提示语 |
| 逐屏热度 | 按内容查看每屏进入次数、平均 / 总停留（热度条） |
| 访问记录 | 最近 100 条：时间、内容、时长、看到第几屏、访客、IP、客户端、来源 |

面板每 30 秒自动刷新；「清空统计」不可恢复。

## 追踪机制

- 展示台首页与每个 deck 的 HTML 由服务端注入追踪脚本（`?export=1` 的本机缩略图采集不注入）。
- 访客 id 是 `localStorage` 里的随机 UUID，无任何个人身份信息。
- 每 1 秒累计一次「页面可见」时间（后台标签页不计），每 15 秒批量上报；翻页时逐屏停留
  归属到对应屏（slide 序号取自引擎写的 `location.hash`）。
- 接口：`POST /api/track/init`（建 visit）、`/api/track/beat`、`/api/track/end`
  （`sendBeacon` 收尾）。公网经隧道可写，带 IP 频率限制。
- 存储：`data/tracking.db`（SQLite，WAL）：`visits` 一次访问一行，`slide_stats` 逐屏聚合。

## 门禁机制

- **下架**：`decks/<slug>/` 整目录（含缩略图）返回 404 页；展示台卡片服务端实时移除。
- **密码**：访问 deck 出门禁页；通过 `POST /api/access` 校验后发 HMAC 签名 Cookie
  （30 天免重输）。展示台卡片加 🔒 需密码标签；缩略图换为占位图，内容不出网。
  密码同样哈希存放（PBKDF2-SHA256），可配提示语（如「会议当天发的编号」）。
- **展示台首页门禁**（伪 slug `__library`）：管理端「展示台首页」行可设密码 + 提示语。
  默认所有人可访问；设密码后，直接访问 `/`、`/library.html`、`/decks.json`
  或从 deck 按 `H` / 点「‹ 展示台」返回，都会被门禁页拦下（`/decks.json` 返回 401）。
  各 deck 直链的独立门禁不受影响；解锁后 30 天免重输。
- 例外：本机 `?export=1`（`build_library.py` 拍缩略图）不注入、不拦截；
  公网伪造该参数无效（校验 Host 是否 loopback）。

## API 一览

| 方法 | 路径 | 鉴权 |
| --- | --- | --- |
| POST | `/api/admin/login` / `logout` / `password` | 密码 / 登录态 |
| GET | `/api/admin/session` · `overview` · `visits` · `decks` · `slides` | 登录态（session 除外） |
| POST | `/api/admin/deck`（`{slug, enabled?, password?, hint?}`）· `stats/clear` | 登录态 |
| POST | `/api/track/init` · `beat` · `end` | 公网（限流） |
| POST | `/api/access` `{deck, password}` | 公网（限流） |

admin / track / access 不受导入 API 的本机 Host 守卫影响（那道守卫只管
`/api/inventory|import|cancel|publish`，约定未变）。

## 数据文件（均在 `data/`，gitignore）

- `admin.json` — 管理密码哈希、cookie 签名密钥
- `access.json` — 各 deck 的 `enabled` / 密码哈希 / 提示语
- `tracking.db` — 访问与逐屏统计
