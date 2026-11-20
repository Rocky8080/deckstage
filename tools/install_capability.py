#!/usr/bin/env python3
"""install_capability.py — 把「因果链 / 价值链」与「设计质量」两套能力装进本机所有 AI 客户端

装的东西：
  1. 技能        <客户端>/skills/<name>/（SKILL.md 与它引用的文件）
       DSH ~/.dsh/skills · Codex ~/.codex/skills · ZCode ~/.zcode/skills
       WorkBuddy ~/.workbuddy/skills · Claude Code ~/.claude/skills
       每个装好的技能里写一个 .deckstage.json（来源 / 内容摘要 / 时间）：
       重装 = 覆盖更新；--check 能看出「旧版本」；--uninstall 只删本系统装的技能，
       不会动用户自己同名的技能。
  2. 用户级约定   <客户端>/AGENTS.md（Claude Code 为 CLAUDE.md）里的写作规则标记块，
       幂等合并，链到已有内容后面，可单独撤销。
  3. 工作区约定   <workspace>/AGENTS.md。
  4. 构建门禁     本仓库 build.mjs / design_audit.py 已内置，不重复安装。

客户端范围：默认只装「这台机器上已安装」的客户端（DSH 是本体，始终装）；
  装了新客户端后重跑一次即可补装；也可手动指定 --agents。

用法：
  python3 tools/install_capability.py --check                 # 只体检，按客户端列出缺什么
  python3 tools/install_capability.py --all                   # 技能 + 用户级规则 + 工作区规则
  python3 tools/install_capability.py --user                  # 只装用户级（技能 + 规则）
  python3 tools/install_capability.py --agents codex,zcode    # 只装指定客户端
  python3 tools/install_capability.py --agents all            # 所有支持的客户端（不看是否已装）
  python3 tools/install_capability.py --workspace .            # 只装工作区约定
  python3 tools/install_capability.py --list-agents            # 支持的客户端 + 本机检测结果
  python3 tools/install_capability.py --uninstall              # 撤销技能目录、规则块与全局命令

装完在各客户端的生效方式：
  DSH 新开会话 · Codex 重启 · ZCode 设置 → 技能 → 刷新
  WorkBuddy 新开对话 · Claude Code 新开会话。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import unicodedata
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MARKER = ".deckstage.json"
TOOL_ID = "deckstage-capability-installer"

# 能力清单：--user / --all 会把这个目录整体复制到 <客户端>/skills/<name>/。
# required 是 --check 判定「技能就位」所需的文件（目录存在 + 文件齐全才算 ✓）。
# user_block / workspace_block 只有写作能力有；设计能力为 None，不碰规则文件。
CAPABILITIES = (
    {
        "name": "causal-value-chain",
        "label": "写作",
        "dir": REPO / "capabilities" / "causal-value-chain",
        "required": ("SKILL.md",),
        "user_block": "README-AGENTS-user.md",
        "workspace_block": "README-AGENTS-workspace.md",
    },
    {
        "name": "design-quality",
        "label": "设计",
        "dir": REPO / "capabilities" / "design-quality",
        "required": ("SKILL.md", "LAYOUTS.md"),
        "user_block": None,
        "workspace_block": None,
    },
)

# 客户端清单：
#   home     用户级配置目录（技能装到 <home>/skills/<name>）
#   rules    用户级规则文件（相对 home；DSH/Codex/ZCode/WorkBuddy 用 AGENTS.md，Claude Code 用 CLAUDE.md）
#   detect   判断「这台机器装了它」的依据：dir（配置目录存在）/ bin（命令在 PATH）/ app（应用存在）
#   always   即使没检测到也装（DSH 是本系统的运行环境）
#   env      可用 DECKSTAGE_HOME_<ID> 覆盖 home，便于测试或非默认安装位置
AGENTS = (
    {
        "id": "dsh",
        "label": "DSH",
        "name": "DeepSeek Harness",
        "home": Path.home() / ".dsh",
        "rules": "AGENTS.md",
        "detect": ("dir:home", "bin:dsh"),
        "always": True,
    },
    {
        "id": "codex",
        "label": "Codex",
        "name": "Codex CLI / Desktop",
        "home": Path.home() / ".codex",
        "rules": "AGENTS.md",
        "detect": ("dir:home", "bin:codex", "app:/Applications/ChatGPT.app"),
        "always": False,
    },
    {
        "id": "zcode",
        "label": "ZCode",
        "name": "ZCode",
        "home": Path.home() / ".zcode",
        "rules": "AGENTS.md",
        "detect": ("dir:home", "bin:zcode", "app:/Applications/ZCode.app"),
        "always": False,
    },
    {
        "id": "workbuddy",
        "label": "WorkBuddy",
        "name": "WorkBuddy",
        "home": Path.home() / ".workbuddy",
        "rules": "AGENTS.md",
        "detect": ("dir:home", "bin:workbuddy", "app:/Applications/WorkBuddy.app",
                   "app:~/Applications/WorkBuddy.app"),
        # WorkBuddy 官方支持用 WORKBUDDY_DIR 迁移数据根目录
        "env": ("WORKBUDDY_DIR",),
        "always": False,
    },
    {
        "id": "claude",
        "label": "Claude Code",
        "name": "Claude Code",
        "home": Path.home() / ".claude",
        "rules": "CLAUDE.md",
        "detect": ("dir:home", "bin:claude"),
        "always": False,
    },
)

AGENT_IDS = tuple(a["id"] for a in AGENTS)


def agent_home(agent: dict) -> Path:
    # 优先级：DECKSTAGE_HOME_<ID>（测试/自定义）> 客户端自己的 env（如 WORKBUDDY_DIR）> 默认目录
    override = os.environ.get(f"DECKSTAGE_HOME_{agent['id'].upper()}")
    if override:
        return Path(override).expanduser()
    for var in agent.get("env", ()):
        value = os.environ.get(var)
        if value:
            return Path(value).expanduser()
    return agent["home"]


def skills_root(agent: dict) -> Path:
    return agent_home(agent) / "skills"


def rules_path(agent: dict) -> Path:
    return agent_home(agent) / agent["rules"]


def agent_detected(agent: dict) -> bool:
    for rule in agent["detect"]:
        kind, _, value = rule.partition(":")
        if kind == "dir" and agent_home(agent).is_dir():
            return True
        if kind == "bin" and shutil.which(value):
            return True
        if kind == "app" and Path(value).expanduser().exists():
            return True
    return False


def resolve_agents(selector: str | None) -> tuple[list[dict], list[dict]]:
    """返回 (本次要装的客户端, 跳过的客户端)。selector=None 表示自动检测。"""
    if selector and selector.strip() != "auto":
        if selector.strip() == "all":
            return list(AGENTS), []
        wanted = [s.strip() for s in selector.split(",") if s.strip()]
        unknown = [s for s in wanted if s not in AGENT_IDS]
        if unknown:
            raise SystemExit(
                f"不认识的客户端：{', '.join(unknown)}\n"
                f"可选：{', '.join(AGENT_IDS)} 或 all / auto"
            )
        chosen = [a for a in AGENTS if a["id"] in wanted]
        skipped = [a for a in AGENTS if a["id"] not in wanted]
        return chosen, skipped
    # 自动：DSH 始终装，其余装「已检测到」的
    chosen = [a for a in AGENTS if a["always"] or agent_detected(a)]
    skipped = [a for a in AGENTS if a not in chosen]
    return chosen, skipped


# ---------------------------------------------------------------- 技能内容摘要
def _cap_files(src: Path) -> dict[str, bytes]:
    """源目录里要装的文件（不含 README-AGENTS-* 与安装标记）。"""
    files: dict[str, bytes] = {}
    for p in sorted(src.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(src).as_posix()
        if rel.startswith("README-AGENTS-") or rel == MARKER:
            continue
        files[rel] = p.read_bytes()
    return files


def _dir_files(dst: Path) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    for p in sorted(dst.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(dst).as_posix()
        if rel.startswith("README-AGENTS-") or rel == MARKER:
            continue
        files[rel] = p.read_bytes()
    return files


def _digest(files: dict[str, bytes]) -> str:
    h = hashlib.sha256()
    for rel in sorted(files):
        h.update(rel.encode("utf-8"))
        h.update(b"\0")
        h.update(files[rel])
        h.update(b"\0")
    return h.hexdigest()[:16]


def source_digest(cap: dict) -> str:
    return _digest(_cap_files(cap["dir"]))


def _frontmatter_name(skill_dir: Path) -> str | None:
    f = skill_dir / "SKILL.md"
    if not f.is_file():
        return None
    try:
        head = f.read_text(encoding="utf-8").split("---", 2)[1]
    except (IndexError, OSError, UnicodeDecodeError):
        return None
    for line in head.splitlines():
        key, _, value = line.partition(":")
        if key.strip() == "name":
            return value.strip().strip("\"'")
    return None


def owned_by_us(dst: Path, cap: dict) -> bool:
    """这个技能目录是不是本系统装进去的（用来决定能否覆盖 / 删除）。"""
    marker = dst / MARKER
    if marker.is_file():
        try:
            data = json.loads(marker.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False
        return data.get("capability") == cap["name"] and data.get("installed_by") == TOOL_ID
    # 旧版本安装（没有 marker）：SKILL.md 的 name 对得上就算我们的
    return _frontmatter_name(dst) == cap["name"]


def installed_digest(dst: Path) -> tuple[str | None, str]:
    """返回 (已装内容摘要, 来源)：marker 里记录的优先；没有就按现有文件算。"""
    marker = dst / MARKER
    if marker.is_file():
        try:
            data = json.loads(marker.read_text(encoding="utf-8"))
            if data.get("digest"):
                return data["digest"], "marker"
        except (OSError, json.JSONDecodeError):
            pass
    try:
        return _digest(_dir_files(dst)), "content"
    except OSError:
        return None, "unknown"


def write_marker(dst: Path, cap: dict, agent: dict) -> None:
    payload = {
        "capability": cap["name"],
        "agent": agent["id"],
        "installed_by": TOOL_ID,
        "source": (cap["dir"].relative_to(REPO)).as_posix() if cap["dir"].is_relative_to(REPO) else str(cap["dir"]),
        "digest": source_digest(cap),
        "installed_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    (dst / MARKER).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


# ---------------------------------------------------------------- 输出
WIDTH = 16


def _width(text: str) -> int:
    return sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in text)


def status(mark: str, label: str, detail: str = "", indent: int = 0) -> None:
    """统一 ✓/✗/↻ 输出，中文标签按显示宽度对齐。"""
    pad = " " * max(1, WIDTH - _width(label))
    print(f"{'  ' * indent}{mark} {label}{pad}{detail}".rstrip())


def group(title: str, detail: str = "") -> None:
    print(f"\n{title}" + (f"  {detail}" if detail else ""))


# ---------------------------------------------------------------- 规则块
def markers(name: str) -> tuple[str, str]:
    """每个能力的 AGENTS.md 标记块，沿用 <name>:begin / <name>:end 的旧格式。"""
    return f"<!-- {name}:begin -->", f"<!-- {name}:end -->"


def block_from(path: Path, begin: str, end: str) -> str:
    return f"{begin}\n{path.read_text(encoding='utf-8').rstrip()}\n{end}\n"


def merge_block(target: Path, block: str, begin: str, end: str) -> str:
    """幂等合并：已存在标记块则替换，否则追加。"""
    target.parent.mkdir(parents=True, exist_ok=True)
    old = target.read_text(encoding="utf-8") if target.exists() else ""
    if begin in old and end in old:
        head = old.split(begin)[0]
        tail = old.split(end, 1)[1].removeprefix("\n")
        new = head + block + tail
        action = "更新"
    else:
        sep = "" if old.endswith("\n\n") or not old else ("\n" if old.endswith("\n") else "\n\n")
        new = old + sep + block
        action = "追加"
    target.write_text(new, encoding="utf-8")
    return action


def strip_block(target: Path, begin: str, end: str) -> bool:
    if not target.exists():
        return False
    old = target.read_text(encoding="utf-8")
    if begin not in old or end not in old:
        return False
    head = old.split(begin)[0].rstrip()
    tail = old.split(end, 1)[1].lstrip("\n")
    target.write_text((head + ("\n" if head else "") + tail).rstrip() + "\n", encoding="utf-8")
    return True


# ---------------------------------------------------------------- frame 命令
def cli_link() -> Path:
    return Path.home() / ".local" / "bin" / "frame"


def install_cli() -> Path:
    link = cli_link()
    src = REPO / "tools" / "frame.py"
    if link.is_symlink() and link.resolve() == src:
        return link
    if link.is_symlink() or link.exists():
        raise FileExistsError(f"{link} 已存在。可直接运行 python3 {src}")
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(src)
    return link


def cli_on_path() -> bool:
    found = shutil.which("frame")
    return found is not None and Path(found).resolve() == REPO / "tools" / "frame.py"


# ---------------------------------------------------------------- 安装
def install_skill(cap: dict, agent: dict) -> bool:
    src: Path = cap["dir"]
    dst = skills_root(agent) / cap["name"]
    label = f"{cap['label']} · {agent['label']}"
    if not src.is_dir():
        status("✗", label, f"{dst}（源目录不存在：{src}）")
        return False
    if dst.exists():
        if not dst.is_dir():
            status("✗", label, f"{dst}（同名文件挡路，未处理）")
            return False
        if not owned_by_us(dst, cap):
            status("✗", label, f"{dst}（同名技能不是本系统装的，跳过；先移走再重装）")
            return False
        shutil.rmtree(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("README-AGENTS-*", MARKER))
    write_marker(dst, cap, agent)
    missing = [f for f in cap["required"] if not (dst / f).is_file()]
    note = f"（源目录缺 {', '.join(missing)}，补齐后 --check 才会通过）" if missing else ""
    status("✓", label, f"{dst}{note}")
    return True


def install_rules(agent: dict) -> bool:
    target = rules_path(agent)
    done = []
    ok = True
    for cap in CAPABILITIES:
        block_name = cap["user_block"]
        if not block_name:
            continue
        src = cap["dir"] / block_name
        begin, end = markers(cap["name"])
        if not src.is_file():
            status("✗", f"用户级 · {agent['label']}", f"{target}（缺 {src}）")
            ok = False
            continue
        action = merge_block(target, block_from(src, begin, end), begin, end)
        done.append(f"{cap['name']}（{action}）")
    if done:
        status("✓", f"用户级 · {agent['label']}", f"{target}（{'，'.join(done)}）")
    return ok


def install_clients(agents: list[dict]) -> bool:
    ok = True
    for agent in agents:
        group(f"{agent['name']}（{agent['id']}）", str(agent_home(agent)))
        for cap in CAPABILITIES:
            ok &= install_skill(cap, agent)
        ok &= install_rules(agent)
    link = install_cli()
    tail = "" if cli_on_path() else "（将 ~/.local/bin 加到 PATH 后可直接调用）"
    status("✓", "全局命令", f"frame → {link}{tail}")
    return ok


def install_workspace(ws: Path) -> None:
    ws = ws.resolve()
    agents = ws / "AGENTS.md"
    if ws == REPO and agents.is_file():
        status("✓", "工作区约定", str(agents))
        return
    cap = next((c for c in CAPABILITIES if c["workspace_block"]), None)
    if cap is None:
        return
    src = cap["dir"] / cap["workspace_block"]
    begin, end = markers(cap["name"])
    if not src.is_file():
        status("✗", "工作区约定", f"{agents}（缺 {src}）")
        return
    action = merge_block(agents, block_from(src, begin, end), begin, end)
    status("✓", "工作区约定", f"{agents}（{action}）")


# ---------------------------------------------------------------- 体检
def check(agents: list[dict], skipped: list[dict], ws: Path, explicit: bool) -> int:
    ok = True
    if agents:
        detected = "、".join(a["name"] for a in agents)
        print(f"要检查的客户端：{detected}")
    if skipped and not explicit:
        print(f"未检测到（跳过）：{'、'.join(a['name'] for a in skipped)}"
              "—— 装好后重跑本命令即可补装")
    if skipped and explicit:
        print(f"本次不检查：{'、'.join(a['name'] for a in skipped)}")

    for agent in agents:
        group(f"{agent['name']}（{agent['id']}）", str(agent_home(agent)))
        for cap in CAPABILITIES:
            dst = skills_root(agent) / cap["name"]
            label = f"{cap['label']} · {agent['label']}"
            if not dst.is_dir():
                status("✗", label, f"{dst}（未安装）", indent=1)
                ok = False
                continue
            missing = [f for f in cap["required"] if not (dst / f).is_file()]
            if missing:
                status("✗", label, f"{dst}（缺 {', '.join(missing)}）", indent=1)
                ok = False
                continue
            if not owned_by_us(dst, cap):
                status("✗", label, f"{dst}（同名技能不是本系统装的）", indent=1)
                ok = False
                continue
            current, _ = installed_digest(dst)
            if current != source_digest(cap):
                status("↻", label, f"{dst}（旧版本，重跑 --all 更新）", indent=1)
                ok = False
            else:
                status("✓", label, str(dst), indent=1)

        target = rules_path(agent)
        for cap in CAPABILITIES:
            if not cap["user_block"]:
                continue
            begin, end = markers(cap["name"])
            text = target.read_text(encoding="utf-8") if target.is_file() else ""
            has = bool(text) and begin in text and end in text
            status("✓" if has else "✗", f"用户级 · {agent['label']}", str(target), indent=1)
            ok &= has

    wscap = next((c for c in CAPABILITIES if c["workspace_block"]), None)
    if wscap is not None:
        group("工作区约定")
        p = ws.resolve() / "AGENTS.md"
        begin, end = markers(wscap["name"])
        text = p.read_text(encoding="utf-8") if p.is_file() else ""
        has = p.is_file() and (p == REPO / "AGENTS.md" or (begin in text and end in text))
        status("✓" if has else "✗", "工作区", str(p), indent=1)
        ok &= has

    group("仓库工具")
    gate_file = REPO / "build.mjs"
    gate = gate_file.is_file() and "frameGate" in gate_file.read_text(encoding="utf-8")
    status("✓" if gate else "✗", "构建门禁", "build.mjs frameGate()", indent=1)
    ok &= gate

    cli = REPO / "tools" / "frame.py"
    status("✓" if cli.exists() else "✗", "检查器", str(cli), indent=1)
    ok &= cli.exists()

    link = cli_link()
    linked = link.is_symlink() and link.resolve() == cli
    status("✓" if linked else "✗", "全局命令", str(link), indent=1)
    if linked and not cli_on_path():
        print("  将 ~/.local/bin 加到 PATH 后可直接调用 frame")
    ok &= linked

    print("\n结论：" + ("已装全，各客户端都能用到这两套技能" if ok
                       else "没装全：跑 python3 tools/install_capability.py --all"))
    return 0 if ok else 1


# ---------------------------------------------------------------- 卸载
def uninstall(ws: Path) -> None:
    removed = 0
    for agent in AGENTS:
        for cap in CAPABILITIES:
            dst = skills_root(agent) / cap["name"]
            if not dst.is_dir():
                continue
            if owned_by_us(dst, cap):
                shutil.rmtree(dst)
                print(f"✓ 已移除技能 {dst}")
                removed += 1
            else:
                print(f"· 跳过 {dst}（不是本系统装的）")
        for cap in CAPABILITIES:
            if not cap["user_block"]:
                continue
            begin, end = markers(cap["name"])
            if strip_block(rules_path(agent), begin, end):
                print(f"✓ 已从 {rules_path(agent)} 移除约定块")
    if not removed:
        print("（没有找到本系统安装的技能目录）")

    global_cli = cli_link()
    if global_cli.is_symlink() and global_cli.resolve() == REPO / "tools" / "frame.py":
        global_cli.unlink()
        print(f"✓ 已移除全局命令 {global_cli}")
    for cap in CAPABILITIES:
        if not cap["user_block"]:
            continue
        begin, end = markers(cap["name"])
        if cap["workspace_block"] and strip_block(ws.resolve() / "AGENTS.md", begin, end):
            print(f"✓ 已从 {ws.resolve() / 'AGENTS.md'} 移除约定块")
    print("（技能目录与规则标记块已撤销；仓库内 frame.py / 门禁仍在）")


# ---------------------------------------------------------------- 入口
def list_agents() -> None:
    group("支持的客户端", "用 --agents 指定；不带参数时自动检测")
    for agent in AGENTS:
        found = agent_detected(agent)
        marks = []
        if found:
            marks.append("已检测到")
        if agent["always"]:
            marks.append("始终安装")
        status("✓" if found or agent["always"] else "·", agent["name"],
               f"{str(agent_home(agent))}  skills/ 规则 {agent['rules']}"
               + (f"  [{', '.join(marks)}]" if marks else ""))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="技能 + 用户级规则 + 工作区规则")
    ap.add_argument("--user", action="store_true", help="只装用户级（技能 + 规则）")
    ap.add_argument("--workspace", nargs="?", const=".", default=None, help="只装工作区约定")
    ap.add_argument("--check", action="store_true", help="只体检")
    ap.add_argument("--uninstall", action="store_true", help="撤销安装")
    ap.add_argument("--agents", default=None,
                    help="客户端列表，逗号分隔：dsh,codex,zcode,workbuddy,claude；all=全部；auto=自动检测（默认）")
    ap.add_argument("--list-agents", action="store_true", help="列出支持的客户端与检测结果")
    a = ap.parse_args()

    if a.list_agents:
        list_agents()
        return 0
    if not any([a.all, a.user, a.workspace, a.check, a.uninstall]):
        ap.print_help()
        return 2

    explicit = a.agents is not None and a.agents.strip() not in ("", "auto")
    agents, skipped = resolve_agents(a.agents)
    if not agents:
        print("没有可安装的客户端。用 --agents all 强制装全部，或先安装 DSH / Codex / ZCode / WorkBuddy / Claude Code。")
        return 1

    workspace = Path(a.workspace).resolve() if a.workspace else REPO

    if a.check:
        return check(agents, skipped, workspace, explicit)
    if a.uninstall:
        uninstall(workspace)
        return 0

    ok = True
    if a.all or a.user:
        try:
            ok = install_clients(agents)
        except FileExistsError as exc:
            ap.exit(1, f"{exc}\n")
    elif skipped and not explicit:
        print(f"未检测到（跳过）：{'、'.join(x['name'] for x in skipped)}")
    if a.all or a.workspace:
        install_workspace(workspace)

    print("\n生效方式：DSH 新开会话 · Codex 重启 · ZCode 设置 → 技能 → 刷新\n          WorkBuddy 新开对话 · Claude Code 新开会话。")
    print("构建时门禁（frameGate / design_audit）随仓库提供，对所有 agent 都生效。")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
