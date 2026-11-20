#!/usr/bin/env bash
# DeckStage 一键安装：依赖 + 写作能力（因果链 / 价值链）
#
#   ./install.sh              # 装依赖 + 装写作能力 + 自检
#   ./install.sh --no-deps    # 只装写作能力（依赖已就绪时）
#   ./install.sh --check      # 只自检，不改任何文件
#
# DSH 提供用户级写作规则。仓库内的 AGENTS.md 和构建检查随代码提供。
set -euo pipefail
cd "$(dirname "$0")"

NO_DEPS=0
CHECK_ONLY=0
for arg in "$@"; do
  case "$arg" in
    --no-deps) NO_DEPS=1 ;;
    --check)   CHECK_ONLY=1 ;;
    -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
  esac
done

say() { printf '\n\033[1m%s\033[0m\n' "$*"; }

if [ "$CHECK_ONLY" = "1" ]; then
  say "1/1 写作能力自检"
  python3 tools/install_capability.py --check
  exit $?
fi

say "1/3 运行环境"
command -v node >/dev/null && echo "  node  $(node -v)" || { echo "  ✗ 需要 Node ≥ 18"; exit 1; }
command -v python3 >/dev/null && echo "  python $(python3 -V 2>&1 | awk '{print $2}')" || { echo "  ✗ 需要 Python 3.9+"; exit 1; }

if [ "$NO_DEPS" = "1" ]; then
  say "2/3 依赖（--no-deps，跳过）"
else
  say "2/3 Python 工具链"
  python3 -m pip install -q -r requirements.txt
  echo "  ✓ requirements.txt 已安装"
fi

say "3/3 写作能力（因果链 / 价值链）"
python3 tools/install_capability.py --all
echo
python3 tools/install_capability.py --check

say "完成"
echo "  构建：node build.mjs --deck <slug>      （P0 表达问题会阻断构建）"
echo "  展示台：python3 tools/serve_deck.py     → http://127.0.0.1:8899/"
echo "  撤销能力：python3 tools/install_capability.py --uninstall"
