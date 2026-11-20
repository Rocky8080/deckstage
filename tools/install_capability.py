#!/usr/bin/env python3
"""install_capability.py — 把「因果链 / 价值链」与「设计质量」两套能力装进当前机器（可重复执行、可撤销）

装的东西：
  1. DSH 技能   ~/.dsh/skills/causal-value-chain/   （写作：因果链 / 价值链详解，可选加载）
                ~/.dsh/skills/design-quality/       （设计：视觉质量门禁与排版检查）
  2. 用户级约定  ~/.dsh/AGENTS.md                    （写作规则，所有 DSH 会话自动注入）
  3. 工作区约定  <workspace>/AGENTS.md               （写作规则，显式指定其他工作区）
  4. 构建门禁   本仓库 build.mjs / design_audit.py 已内置，不重复安装

设计能力没有用户级 AGENTS 标记块，只装技能目录。

用法：
  python3 tools/install_capability.py --check        # 只体检
  python3 tools/install_capability.py --all          # 安装两个技能、用户级规则和 frame 命令
  python3 tools/install_capability.py --user         # 只装用户级（两个技能 + 写作规则）
  python3 tools/install_capability.py --workspace .  # 只装工作区约定
  python3 tools/install_capability.py --uninstall    # 撤销两个技能目录与约定标记块
"""
from __future__ import annotations

import argparse
import os
import shutil
import unicodedata
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# 能力清单：--user / --all 会把这个目录整体复制到 ~/.dsh/skills/<name>/。
# required 是 --check 判定「技能就位」所需的文件（目录存在 + 文件齐全才算 ✓）。
# user_block / workspace_block 只有写作能力有；设计能力为 None，不碰 AGENTS.md。
CAPABILITIES = (
    {
        "name": "causal-value-chain",
        "label": "技能（写作）",
        "dir": REPO / "capabilities" / "causal-value-chain",
        "required": ("SKILL.md",),
        "user_block": "README-AGENTS-user.md",
        "workspace_block": "README-AGENTS-workspace.md",
    },
    {
        "name": "design-quality",
        "label": "技能（设计）",
        "dir": REPO / "capabilities" / "design-quality",
        "required": ("SKILL.md", "LAYOUTS.md"),
        "user_block": None,
        "workspace_block": None,
    },
)


def dsh_home() -> Path:
    return Path(os.environ.get("DSH_HOME", Path.home() / ".dsh"))


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


def _width(text: str) -> int:
    return sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in text)


def status(mark: str, label: str, detail: str = "") -> None:
    """统一 ✓/✗ 输出，中文标签按显示宽度对齐。"""
    pad = " " * max(1, 14 - _width(label))
    print(f"{mark} {label}{pad}{detail}".rstrip())


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


def install_skill(cap: dict) -> None:
    src: Path = cap["dir"]
    dst = dsh_home() / "skills" / cap["name"]
    if not src.is_dir():
        status("✗", cap["label"], f"{dst}（源目录不存在：{src}）")
        return
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("README-AGENTS-*"))
    missing = [f for f in cap["required"] if not (dst / f).is_file()]
    note = f"（源目录缺 {', '.join(missing)}，补齐后 --check 才会通过）" if missing else ""
    status("✓", cap["label"], f"{dst}{note}")


def install_user() -> None:
    link = install_cli()
    home = dsh_home()
    for cap in CAPABILITIES:
        install_skill(cap)
    for cap in CAPABILITIES:
        block_name = cap["user_block"]
        if not block_name:
            continue  # design-quality 没有用户级标记块
        agents = home / "AGENTS.md"
        src = cap["dir"] / block_name
        begin, end = markers(cap["name"])
        if not src.is_file():
            status("✗", "用户级约定", f"{agents}（缺 {src}）")
            continue
        action = merge_block(agents, block_from(src, begin, end), begin, end)
        status("✓", "用户级约定", f"{agents}（{action}）")
    tail = "" if cli_on_path() else "（将 ~/.local/bin 加到 PATH 后可直接调用）"
    status("✓", "全局命令", f"frame → {link}{tail}")


def install_workspace(ws: Path) -> None:
    ws = ws.resolve()
    agents = ws / "AGENTS.md"
    if ws == REPO and agents.is_file():
        status("✓", "仓库约定", str(agents))
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


def check(ws: Path) -> int:
    ok = True
    home = dsh_home()
    for cap in CAPABILITIES:
        dst = home / "skills" / cap["name"]
        missing = [f for f in cap["required"] if not (dst / f).is_file()]
        installed = dst.is_dir()
        good = installed and not missing
        if not installed:
            detail = f"{dst}（未安装）"
        elif missing:
            detail = f"{dst}（缺 {', '.join(missing)}）"
        else:
            detail = str(dst)
        status("✓" if good else "✗", cap["label"], detail)
        ok &= good

    for cap in CAPABILITIES:
        if not cap["user_block"]:
            continue
        p = home / "AGENTS.md"
        begin, end = markers(cap["name"])
        text = p.read_text(encoding="utf-8") if p.is_file() else ""
        has = bool(text) and begin in text and end in text
        status("✓" if has else "✗", "用户级约定", str(p))
        ok &= has

    wscap = next((c for c in CAPABILITIES if c["workspace_block"]), None)
    if wscap is not None:
        p = ws.resolve() / "AGENTS.md"
        begin, end = markers(wscap["name"])
        text = p.read_text(encoding="utf-8") if p.is_file() else ""
        has = p.is_file() and (p == REPO / "AGENTS.md" or (begin in text and end in text))
        status("✓" if has else "✗", "工作区约定", str(p))
        ok &= has

    gate_file = REPO / "build.mjs"
    gate = gate_file.is_file() and "frameGate" in gate_file.read_text(encoding="utf-8")
    status("✓" if gate else "✗", "构建门禁", "build.mjs frameGate()")
    ok &= gate

    cli = REPO / "tools" / "frame.py"
    status("✓" if cli.exists() else "✗", "检查器", str(cli))
    ok &= cli.exists()

    link = cli_link()
    linked = link.is_symlink() and link.resolve() == cli
    status("✓" if linked else "✗", "全局命令", str(link))
    if linked and not cli_on_path():
        print("  将 ~/.local/bin 加到 PATH 后可直接调用 frame")
    ok &= linked

    print("\n结论：" + ("已安装，写作与设计纪律自动生效" if ok else "未装全，跑 python3 tools/install_capability.py --all"))
    return 0 if ok else 1


def uninstall(ws: Path) -> None:
    home = dsh_home()
    for cap in CAPABILITIES:
        dst = home / "skills" / cap["name"]
        if dst.exists():
            shutil.rmtree(dst)
            print(f"✓ 已移除技能 {dst}")
    global_cli = cli_link()
    if global_cli.is_symlink() and global_cli.resolve() == REPO / "tools" / "frame.py":
        global_cli.unlink()
        print(f"✓ 已移除全局命令 {global_cli}")
    for cap in CAPABILITIES:
        if not cap["user_block"]:
            continue
        begin, end = markers(cap["name"])
        if strip_block(home / "AGENTS.md", begin, end):
            print(f"✓ 已从 {home / 'AGENTS.md'} 移除约定块")
        if cap["workspace_block"] and strip_block(ws.resolve() / "AGENTS.md", begin, end):
            print(f"✓ 已从 {ws.resolve() / 'AGENTS.md'} 移除约定块")
    print("（技能目录与 AGENTS 标记块已撤销；仓库内 frame.py / 门禁仍在）")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--user", action="store_true")
    ap.add_argument("--workspace", nargs="?", const=".", default=None)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--uninstall", action="store_true")
    a = ap.parse_args()
    if not any([a.all, a.user, a.workspace, a.check, a.uninstall]):
        ap.print_help(); return 2
    workspace = Path(a.workspace).resolve() if a.workspace else REPO
    if a.check:
        return check(workspace)
    if a.uninstall:
        uninstall(workspace)
        return 0
    if a.all or a.user:
        try:
            install_user()
        except FileExistsError as exc:
            ap.exit(1, f"{exc}\n")
    if a.all or a.workspace:
        install_workspace(workspace)
    print("\n下次新开 DSH 会话即自动带着这套规则；构建时门禁自动拦截表达与视觉问题。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
