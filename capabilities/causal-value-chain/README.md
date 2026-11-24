# 因果链 / 价值链写作能力

用同一口径比较投入，说明产生结果的动作，并在图注中指明可核对的证据。
方法、作者模板与提示词见 [写作规则](SKILL.md)、[幻灯片模板](slide-template.html)及 [提示词](prompts/)。

## 安装与使用

仓库内的 `AGENTS.md` 和构建检查已随代码提供。
`./install.sh` 还会安装 Python 工具链，并把本能力、`point-hierarchy` 与 `design-quality` 三套技能装进本机
**已检测到的所有 AI 客户端**，同时把用户级写作与结构规则并入各客户端的规则文件、把 `frame` 链到 `~/.local/bin`：

| 客户端 | 技能目录 | 用户级规则 | 生效方式 |
|---|---|---|---|
| DSH | `~/.dsh/skills/` | `~/.dsh/AGENTS.md` | 新开会话 |
| Codex | `~/.codex/skills/` | `~/.codex/AGENTS.md` | 重启 Codex |
| ZCode | `~/.zcode/skills/` | `~/.zcode/AGENTS.md` | 设置 → 技能 → 刷新 |
| WorkBuddy | `~/.workbuddy/skills/` | `~/.workbuddy/AGENTS.md` | 新开对话（技能页确认启用） |
| Claude Code | `~/.claude/skills/` | `~/.claude/CLAUDE.md` | 新开会话 |

技能目录里会写一个 `.deckstage.json` 记录来源与内容摘要：重装即覆盖更新，
`--check` 能看出哪个客户端是旧版本，`--uninstall` 只删本系统装的技能，不动你自己同名的技能。

```bash
python3 -m venv .venv
source .venv/bin/activate
./install.sh
./install.sh --check
frame framework
frame audit "src-sample/slides/*.html"
frame lint "待检查的句子"
```

将 `~/.local/bin` 加入 `PATH` 后即可直接调用 `frame`。在仓库中也可使用 `python3 tools/frame.py` 加同样的参数。

只装指定客户端 / 只看检测结果 / 只装某个工作区：

```bash
python3 tools/install_capability.py --agents codex,workbuddy --user   # 只装这两个；all=全部，auto=自动（默认）
python3 tools/install_capability.py --list-agents                 # 本机检测到哪些客户端
python3 tools/install_capability.py --workspace <目录>             # 只把写作规则并入该工作区 AGENTS.md
python3 tools/install_capability.py --uninstall                   # 撤销技能、规则块与全局命令
```

以后新装了客户端，重跑一次 `./install.sh` 或 `python3 tools/install_capability.py --all` 即补装。

### 支持更多客户端

技能就是通用的 `SKILL.md`（YAML 头里至少 `name` + `description`），任何支持该格式的客户端都能直接用。
要加一个新客户端，在 `tools/install_capability.py` 的 `AGENTS` 表里补一条即可：
`id`、`label`、`home`（配置目录）、`rules`（规则文件名，通常是 `AGENTS.md`）、`detect`（怎么判断本机装了它）。
不在支持列表里的客户端，也可以从已装目录导入 —— 例如 ZCode 的「设置 → 技能 → 导入」会自动扫描
Claude Code、Codex CLI 等外部技能目录，可软链或复制过来。WorkBuddy 除了 `~/.workbuddy/skills/`，
也认共享的 `~/.agents/skills/` 与项目 `.agents/skills/`；它的数据根目录可用官方 `WORKBUDDY_DIR` 迁移，
安装脚本会自动跟随。

## 构建时检查

```bash
node build.mjs --src src-sample --deck sample-deck
```

构建会运行 `frame audit`。无基准倍数、表格缺结论、人月量纲混用等 P0 问题会阻断构建。其余提示供复查。
