#!/usr/bin/env python3
"""privacy_check.py — 私人内容入库防线（提交前强制检查）

本仓库是"引擎 + 匿名示例"的开源形态，四套私人 deck（AI 改变学习方式、清华 x-lab 介绍
中/英、24steps）及其源码、产物、笔记一律不得入库。.gitignore 是第一道线（白名单式，
新 deck 目录默认忽略）；本脚本是第二道线：直接扫描暂存/跟踪文件的**路径与内容**，
命中任何私人标记即失败（退出码 1）。

用法：
  python3 tools/privacy_check.py                # 检查暂存区（pre-commit 钩子调这个）
  python3 tools/privacy_check.py --all          # 检查全部已跟踪文件（提交后审计）
  python3 tools/privacy_check.py --install-hook # 安装 .git/hooks/pre-commit（本机生效，不入库）

只用标准库，任何 python3 都能跑。
"""
import _platform  # noqa: F401  — Windows GBK 管道下的 stdout UTF-8 兜底（见 _platform.py）
import argparse
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 路径标记：入库文件**路径**命中即失败（个人 deck 的目录/文件名）
PATH_MARKERS = [
    "tsinghua-xlab", "xlab-2026-10", "src-xlab", "ai-learning-report",
    "24steps", "本地笔记", "夏立", "AI改变学习方式", "rockybong",
    "单机版", "EXPORT.md",
]

# 内容标记：入库文件**文本内容**命中即失败（真名 / 域名 / 私有标题 / 微信路径）
CONTENT_MARKERS = [
    "夏立", "AI改变学习方式", "rockybong", "macstudioxia", "xwechat",
    "清华x-lab介绍", "About_Tsinghua_x-lab", "com.rockybong",
    "ppt.rockybong.com",
]

HOOK = """#!/bin/sh
# 私人内容入库防线（python3 tools/privacy_check.py --install-hook 生成）
python3 tools/privacy_check.py || exit 1
"""


def git(*args):
    return subprocess.run(["git", "-C", ROOT, *args], capture_output=True, text=True).stdout


def files_to_check(all_tracked):
    if all_tracked:
        names = git("ls-files").splitlines()
    else:
        names = git("diff", "--cached", "--name-only").splitlines()
        if not names:                       # 无暂存内容时退化为全量跟踪文件
            names = git("ls-files").splitlines()
    return [n for n in names if n.strip()]


def main():
    ap = argparse.ArgumentParser(description="私人内容入库防线")
    ap.add_argument("--all", action="store_true", help="扫描全部已跟踪文件（默认扫描暂存区）")
    ap.add_argument("--install-hook", action="store_true", help="安装 .git/hooks/pre-commit")
    opts = ap.parse_args()

    if opts.install_hook:
        os.makedirs(os.path.join(ROOT, ".git", "hooks"), exist_ok=True)
        hook_path = os.path.join(ROOT, ".git", "hooks", "pre-commit")
        with open(hook_path, "w", encoding="utf-8") as fh:
            fh.write(HOOK)
        os.chmod(hook_path, 0o755)
        print(f"[privacy] 已安装钩子 {hook_path}")
        return 0

    names = files_to_check(opts.all)
    if not names:
        print("[privacy] 没有可检查的文件")
        return 0

    self_rel = os.path.relpath(os.path.abspath(__file__), ROOT).replace(os.sep, "/")
    hits = []
    for name in names:
        if name == self_rel:                # 本脚本自带标记清单，跳过自扫
            continue
        low = name.lower()
        if any(m.lower() in low for m in PATH_MARKERS):
            hits.append(f"路径命中: {name}")
            continue
        path = os.path.join(ROOT, name)
        if not os.path.isfile(path) or os.path.getsize(path) > 64 * 1024 * 1024:
            continue
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as fh:
                text = fh.read()
        except OSError:
            continue
        for m in CONTENT_MARKERS:
            if m in text:
                hits.append(f"内容命中 [{m}]: {name}")
                break

    if hits:
        print(f"[privacy] ✗ 发现 {len(hits)} 处私人内容，禁止提交：")
        for h in hits[:20]:
            print(f"    {h}")
        if len(hits) > 20:
            print(f"    … 还有 {len(hits) - 20} 处")
        print("  处理：git reset <文件> 后检查 .gitignore；详见 CONTRIBUTING.md")
        return 1
    print(f"[privacy] ✓ {len(names)} 个文件全部干净")
    return 0


if __name__ == "__main__":
    sys.exit(main())
