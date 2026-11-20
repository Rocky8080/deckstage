#!/usr/bin/env python3
"""install_capability.py — 把「因果链 / 价值链」能力装进当前机器（可重复执行、可撤销）

装的东西：
  1. DSH 技能   ~/.dsh/skills/causal-value-chain/     （详解层，可选加载）
  2. 用户级约定  ~/.dsh/AGENTS.md                      （所有 DSH 会话自动注入）
  3. 工作区约定  <workspace>/AGENTS.md                 （显式指定其他工作区）
  4. 构建门禁   本仓库 build.mjs 已内置，不重复安装

用法：
  python3 tools/install_capability.py --check        # 只体检
  python3 tools/install_capability.py --all          # 安装技能、用户级规则和 frame 命令
  python3 tools/install_capability.py --user         # 只装用户级
  python3 tools/install_capability.py --workspace .  # 只装工作区约定
  python3 tools/install_capability.py --uninstall    # 撤销标记块与技能目录
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CAP = REPO / "capabilities" / "causal-value-chain"
BEGIN = "<!-- causal-value-chain:begin -->"
END = "<!-- causal-value-chain:end -->"
SKILL_NAME = "causal-value-chain"


def dsh_home() -> Path:
    import os
    return Path(os.environ.get("DSH_HOME", Path.home() / ".dsh"))


def block_from(path: Path) -> str:
    return f"{BEGIN}\n{path.read_text(encoding='utf-8').rstrip()}\n{END}\n"


def merge_block(target: Path, block: str) -> str:
    """幂等合并：已存在标记块则替换，否则追加。"""
    target.parent.mkdir(parents=True, exist_ok=True)
    old = target.read_text(encoding="utf-8") if target.exists() else ""
    if BEGIN in old and END in old:
        head = old.split(BEGIN)[0]
        tail = old.split(END, 1)[1].removeprefix("\n")
        new = head + block + tail
        action = "更新"
    else:
        sep = "" if old.endswith("\n\n") or not old else ("\n" if old.endswith("\n") else "\n\n")
        new = old + sep + block
        action = "追加"
    target.write_text(new, encoding="utf-8")
    return action


def strip_block(target: Path) -> bool:
    if not target.exists():
        return False
    old = target.read_text(encoding="utf-8")
    if BEGIN not in old or END not in old:
        return False
    head = old.split(BEGIN)[0].rstrip()
    tail = old.split(END, 1)[1].lstrip("\n")
    target.write_text((head + ("\n" if head else "") + tail).rstrip() + "\n", encoding="utf-8")
    return True


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


def install_user() -> None:
    link = install_cli()
    home = dsh_home()
    skill_dst = home / "skills" / SKILL_NAME
    if skill_dst.exists():
        shutil.rmtree(skill_dst)
    shutil.copytree(CAP, skill_dst, ignore=shutil.ignore_patterns("README-AGENTS-*"))
    print(f"✓ 技能        {skill_dst}")
    agents = home / "AGENTS.md"
    action = merge_block(agents, block_from(CAP / "README-AGENTS-user.md"))
    print(f"✓ 用户级约定  {agents}（{action}）")
    print(f"✓ 全局命令    frame → {link}" + ("" if cli_on_path() else "（将 ~/.local/bin 加到 PATH 后可直接调用）"))


def install_workspace(ws: Path) -> None:
    ws = ws.resolve()
    agents = ws / "AGENTS.md"
    if ws == REPO and agents.is_file():
        print(f"✓ 仓库约定    {agents}")
        return
    action = merge_block(agents, block_from(CAP / "README-AGENTS-workspace.md"))
    print(f"✓ 工作区约定  {agents}（{action}）")


def check(ws: Path) -> int:
    ok = True
    home = dsh_home()
    skill = home / "skills" / SKILL_NAME / "SKILL.md"
    print(f"{'✓' if skill.exists() else '✗'} 技能        {skill}")
    ok &= skill.exists()
    for label, p in (("用户级约定", home / "AGENTS.md"), ("工作区约定", ws / "AGENTS.md")):
        has = p.is_file() and (p == REPO / "AGENTS.md" or BEGIN in p.read_text(encoding="utf-8"))
        print(f"{'✓' if has else '✗'} {label}  {p}")
        ok &= has
    gate = "frameGate" in (REPO / "build.mjs").read_text(encoding="utf-8")
    print(f"{'✓' if gate else '✗'} 构建门禁    build.mjs frameGate()")
    ok &= gate
    cli = REPO / "tools" / "frame.py"
    print(f"{'✓' if cli.exists() else '✗'} 检查器      {cli}")
    ok &= cli.exists()
    link = cli_link()
    linked = link.is_symlink() and link.resolve() == cli
    print(f"{'✓' if linked else '✗'} 全局命令    {link}")
    if linked and not cli_on_path():
        print("  将 ~/.local/bin 加到 PATH 后可直接调用 frame")
    ok &= linked
    print("\n结论：" + ("已安装，写 PPT 时自动生效" if ok else "未装全，跑 python3 tools/install_capability.py --all"))
    return 0 if ok else 1


def uninstall(ws: Path) -> None:
    home = dsh_home()
    skill_dst = home / "skills" / SKILL_NAME
    if skill_dst.exists():
        shutil.rmtree(skill_dst)
        print(f"✓ 已移除技能 {skill_dst}")
    global_cli = cli_link()
    if global_cli.is_symlink() and global_cli.resolve() == REPO / "tools" / "frame.py":
        global_cli.unlink()
        print(f"✓ 已移除全局命令 {global_cli}")
    for p in (home / "AGENTS.md", ws / "AGENTS.md"):
        if strip_block(p):
            print(f"✓ 已从 {p} 移除约定块")
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
    print("\n下次新开 DSH 会话即自动带着这套纪律；构建时门禁自动拦截 P0。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
