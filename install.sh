#!/usr/bin/env bash
# DeckStage 一键安装：依赖 + 写作与设计能力（因果链 / 价值链 + 设计质量）
#
#   ./install.sh                      # 装依赖 + 把技能装进本机所有 AI 客户端 + 自检
#   ./install.sh --no-deps            # 只装技能与规则（依赖已就绪时）
#   ./install.sh --check              # 只自检，不改任何文件
#   ./install.sh --agents codex,workbuddy # 只装指定客户端（all=全部，auto=自动检测）
#
# 技能装进本机已检测到的客户端：DSH ~/.dsh/skills、Codex ~/.codex/skills、ZCode ~/.zcode/skills、
# WorkBuddy ~/.workbuddy/skills、Claude Code ~/.claude/skills；用户级写作规则分别并入
# 各客户端的 AGENTS.md / CLAUDE.md。仓库内的 AGENTS.md、构建门禁和视觉检查随代码提供。
set -euo pipefail
SELF="$0"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"
SELF="$SCRIPT_DIR/$(basename "$SELF")"

usage() { awk 'NR > 1 && /^#/ { sub(/^# ?/, ""); print; next } NR > 1 { exit }' "$SELF"; }

NO_DEPS=0
CHECK_ONLY=0
AGENT_ARGS=()
while [ $# -gt 0 ]; do
  case "$1" in
    --no-deps) NO_DEPS=1 ;;
    --check)   CHECK_ONLY=1 ;;
    --agents)  AGENT_ARGS=(--agents "$2"); shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "未知参数：$1"; echo; usage; exit 2 ;;
  esac
  shift
done

say() { printf '\n\033[1m%s\033[0m\n' "$*"; }

if [ "$CHECK_ONLY" = "1" ]; then
  say "1/1 写作与设计能力自检"
  python3 tools/install_capability.py ${AGENT_ARGS[@]+"${AGENT_ARGS[@]}"} --check
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

say "3/3 写作与设计能力 → AI 客户端（因果链 / 价值链 + 设计质量）"
python3 tools/install_capability.py ${AGENT_ARGS[@]+"${AGENT_ARGS[@]}"} --all || echo "  ⚠ 有客户端没装全，下面的自检会指出缺什么；修好后重跑即可。"
echo
python3 tools/install_capability.py ${AGENT_ARGS[@]+"${AGENT_ARGS[@]}"} --check

say "完成"
echo "  生效：DSH 新开会话 · Codex 重启 · ZCode 设置→技能→刷新 · WorkBuddy 新开对话（技能页确认启用） · Claude Code 新开会话"
echo "  只装指定客户端：python3 tools/install_capability.py --agents codex,zcode --user"
echo "  构建：node build.mjs --deck <slug>      （P0 表达问题会阻断构建）"
echo "  视觉：python3 tools/design_audit.py --index decks/<slug>/index.html"
echo "  展示台：python3 tools/serve_deck.py     → http://127.0.0.1:8899/"
echo "  撤销能力：python3 tools/install_capability.py --uninstall"
