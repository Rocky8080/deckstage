# 因果链 / 价值链写作能力

用同一口径比较投入，说明产生结果的动作，并在图注中指明可核对的证据。
方法、作者模板与提示词见 [写作规则](SKILL.md)、[幻灯片模板](slide-template.html)及 [提示词](prompts/)。

## 安装与使用

仓库内的 `AGENTS.md` 和构建检查已随代码提供。
`./install.sh` 还会安装 Python 工具链、DSH 技能与用户级规则，并把 `frame` 链到 `~/.local/bin`。
安装后可在新 DSH 会话使用 `causal-value-chain` 技能。

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

如需将写作规则合并到其他工作区的 `AGENTS.md`，运行 `python3 tools/install_capability.py --workspace <目录>`。
撤销用户级安装可运行 `python3 tools/install_capability.py --uninstall`，可通过同时传入 `--workspace <目录>` 撤销该工作区的规则。

## 构建时检查

```bash
node build.mjs --src src-sample --deck sample-deck
```

构建会运行 `frame audit`。无基准倍数、表格缺结论、人月量纲混用等 P0 问题会阻断构建。其余提示供复查。
