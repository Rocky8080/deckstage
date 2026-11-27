#!/usr/bin/env python3
"""_platform.py — DeckStage 工具链的跨平台助手（Windows 支持）

import 即生效的副作用：把 stdout / stderr 重配成 UTF-8。Windows 的 GBK 管道下
print 中文或 emoji 会 UnicodeEncodeError——而 build.mjs 的门禁用 spawnSync 捕获
stdout，编码崩了等于门禁失效。其余是按需调用的函数：

  python_candidates()  依次探测的 Python 解释器（[[exe, arg...], ...]）
  find_soffice()       LibreOffice 可执行文件路径（找不到返回 None）
  launch_chromium(pw)  playwright 启动浏览器：Chrome → Edge → 自带 chromium
  first_existing(...)  返回第一个存在的路径

约定：所有解析都是「原值优先，找不到才走新分支」，macOS 行为不变。
"""
import os
import shutil
import sys


def _setup_streams():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass  # 旧版 Python 或非常规流；保持原样


_setup_streams()


def python_candidates():
    """依次尝试的 Python 解释器命令行；py 启动器带 -3 前缀。

    返回 [[exe, arg...], ...]；调用方用 cand + [script, ...] 拼完整 argv。
    """
    cands = []
    seen = set()
    names = ("python3", "python") if sys.platform == "win32" else ("python3", "python")
    for name in names:
        found = shutil.which(name)
        if found and found.lower() not in seen:
            seen.add(found.lower())
            cands.append([found])
    if sys.platform == "win32":
        launcher = shutil.which("py")
        if launcher and launcher.lower() not in seen:
            cands.append([launcher, "-3"])
    else:
        for fixed in ("/usr/bin/python3", "/opt/homebrew/bin/python3"):
            if os.path.exists(fixed) and fixed.lower() not in seen:
                cands.append([fixed])
    return cands


def find_soffice():
    """LibreOffice 可执行文件：环境变量 → PATH → 各平台默认安装位置。"""
    for var in ("SOFFICE", "LIBREOFFICE_PATH"):
        env = os.environ.get(var)
        if env and os.path.exists(env):
            return env
    found = shutil.which("soffice")
    if found:
        return found
    if sys.platform == "darwin":
        mac = "/Applications/LibreOffice.app/Contents/MacOS/soffice"
        return mac if os.path.exists(mac) else None
    if sys.platform == "win32":
        bases = [
            os.environ.get("PROGRAMFILES") or r"C:\Program Files",
            os.environ.get("PROGRAMFILES(X86)") or r"C:\Program Files (x86)",
        ]
        local = os.environ.get("LOCALAPPDATA")
        if local:
            bases.append(os.path.join(local, "Programs"))
        for base in bases:
            win = os.path.join(base, "LibreOffice", "program", "soffice.exe")
            if os.path.exists(win):
                return win
        return None
    for posix in ("/usr/bin/soffice", "/usr/local/bin/soffice", "/snap/bin/soffice"):
        if os.path.exists(posix):
            return posix
    return None


def launch_chromium(pw, headless=True, **kwargs):
    """playwright 启动浏览器：Chrome → Edge（Windows 常见只有 Edge）→ 自带 chromium。"""
    last = None
    for channel in ("chrome", "msedge"):
        try:
            return pw.chromium.launch(channel=channel, headless=headless, **kwargs)
        except Exception as exc:  # 该 channel 的浏览器不存在 → 试下一个
            last = exc
    try:
        sys.stderr.write("[platform] 未找到 Chrome / Edge，改用 playwright 自带 chromium（需先 playwright install）\n")
        return pw.chromium.launch(headless=headless, **kwargs)
    except Exception:
        raise last


def first_existing(*paths):
    """返回第一个存在的路径；都没有返回 None。"""
    for p in paths:
        if p and os.path.exists(p):
            return p
    return None
