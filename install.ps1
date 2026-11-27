# DeckStage Windows 安装器（对应 macOS / Linux 的 install.sh）
#
#   powershell -ExecutionPolicy Bypass -File install.ps1              # 装依赖 + 技能 + 自检
#   powershell -ExecutionPolicy Bypass -File install.ps1 -NoDeps      # 依赖已就绪时
#   powershell -ExecutionPolicy Bypass -File install.ps1 -Check       # 只自检
#   powershell -ExecutionPolicy Bypass -File install.ps1 -Agents codex,zcode
#
# 依赖：Node 18+、Python 3.9+（py -3 或 python）、Chrome 或 Edge（缩略图 / 质检）；
# PPTX 导入另需 LibreOffice（默认识别 C:\Program Files\LibreOffice，可用环境变量 SOFFICE 指定）。
param(
    [switch]$NoDeps,
    [switch]$Check,
    [string]$Agents = ""
)
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

function Say($t) { Write-Host "`n== $t ==" }

# 选一个可用的 Python（py -3 → python3 → python）
$Py = $null
foreach ($c in @(@("py", "-3"), @("python3"), @("python"))) {
    try {
        & $c[0] @($c | Select-Object -Skip 1) -c "print(1)" *> $null
        if ($LASTEXITCODE -eq 0) { $Py = $c; break }
    } catch { }
}
if (-not $Py) {
    Write-Error "需要 Python 3.9+：请安装后重试（py -3 或 python 都可以）"
    exit 1
}
$PyArgs = @($Py | Select-Object -Skip 1)

$AgentsArgs = @()
if ($Agents -ne "") { $AgentsArgs = @("--agents", $Agents) }

if ($Check) {
    Say "1/1 写作、结构与设计能力自检"
    & $Py[0] @PyArgs tools/install_capability.py @AgentsArgs --check
    exit $LASTEXITCODE
}

Say "1/3 运行环境"
node -v
& $Py[0] @PyArgs --version

if ($NoDeps) {
    Say "2/3 依赖（-NoDeps，跳过）"
} else {
    Say "2/3 Python 工具链"
    & $Py[0] @PyArgs -m pip install -q -r requirements.txt
    Write-Host "  requirements.txt 已安装"
}

Say "3/3 写作、结构与设计能力 -> AI 客户端"
& $Py[0] @PyArgs tools/install_capability.py @AgentsArgs --all
& $Py[0] @PyArgs tools/install_capability.py @AgentsArgs --check

Say "完成"
Write-Host "  展示台：python tools/serve_deck.py  ->  http://127.0.0.1:8899/"
Write-Host "  构建：node build.mjs --deck <slug>  （P0 表达 / 结构问题会阻断构建）"
Write-Host "  首次访问 127.0.0.1 若弹防火墙提示，请允许（服务只绑定本机回环）。"
