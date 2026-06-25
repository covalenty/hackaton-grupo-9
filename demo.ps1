#requires -Version 5.1
<#
.SYNOPSIS
    Roda o demo do agente Cienty.

.EXAMPLE
    .\demo.ps1
    # Sequência completa de 4 mensagens texto (3s entre alertas)

.EXAMPLE
    .\demo.ps1 -Interval 5
    # 5s entre alertas (bom pra screen recording)

.EXAMPLE
    .\demo.ps1 -Only 3
    # Só o cenário #3 (CIENTY_BETTER · Paracetamol + Codeína)

.EXAMPLE
    .\demo.ps1 -Image runs\demo_offer.jpg
    # Roda extração de imagem (vision) e dispara os alertas correspondentes.

.EXAMPLE
    .\demo.ps1 -Image runs\demo_offer.jpg -MaxAlerts 3 -Sender "Eduardo MILFARMA"
    # Limita a 3 alertas / customiza o nome do rep.
#>
[CmdletBinding(DefaultParameterSetName='Text')]
param(
    [Parameter(ParameterSetName='Text')]
    [double]$Interval = 3.0,

    [Parameter(ParameterSetName='Text')]
    [int]$Only = 0,

    [Parameter(ParameterSetName='Image', Mandatory=$true)]
    [string]$Image,

    [Parameter(ParameterSetName='Image')]
    [string]$Sender = "Eduardo MILFARMA",

    [Parameter(ParameterSetName='Image')]
    [int]$MaxAlerts = 6,

    [Parameter(ParameterSetName='Image')]
    [string]$Caption = ""
)

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Definition
$py = Join-Path $here ".venv\Scripts\python.exe"

function Test-PythonVenv {
    if (-not (Test-Path $py)) { return $false }
    try { & $py --version 2>&1 | Out-Null; return ($LASTEXITCODE -eq 0) } catch { return $false }
}

if (-not (Test-PythonVenv)) {
    Write-Host "[demo] venv inválido — recriando (uv GC pode ter removido o Python base)..."
    $uv = "$env:LOCALAPPDATA\Microsoft\WinGet\Packages\astral-sh.uv_Microsoft.Winget.Source_8wekyb3d8bbwe\uv.exe"
    if (-not (Test-Path $uv)) { Write-Error "uv não encontrado. winget install astral-sh.uv" }
    Push-Location $here
    Remove-Item -Recurse -Force .venv -ErrorAction SilentlyContinue
    & $uv python install 3.12 2>&1 | Out-Null
    & $uv venv --python 3.12 --quiet
    & $uv pip install -r agent/requirements.txt pillow --python .venv\Scripts\python.exe --quiet 2>&1 | Out-Null
    Pop-Location
    if (-not (Test-PythonVenv)) { Write-Error "Falha ao recriar venv. Rodar manualmente os comandos uv." }
    Write-Host "[demo] venv recriado · " -NoNewline; & $py --version
}

if (-not $env:ANTHROPIC_API_KEY) {
    $keyFile = Join-Path (Split-Path -Parent $here) "key.txt"
    if (Test-Path $keyFile) {
        $env:ANTHROPIC_API_KEY = (Get-Content $keyFile -Raw).Trim()
    }
}

$env:PYTHONIOENCODING = "utf-8"
$bridgeSend = "https://used-pad-interstate-smithsonian.trycloudflare.com/send"

if ($PSCmdlet.ParameterSetName -eq 'Image') {
    $script = Join-Path $here "scripts\demo_image_e2e.py"
    $args = @($Image, "--sender", $Sender, "--send-url", $bridgeSend, "--max-alerts", $MaxAlerts)
    if ($Caption) { $args += @("--caption", $Caption) }
} else {
    $script = Join-Path $here "scripts\demo_client.py"
    $args = @("--interval", $Interval)
    if ($Only -gt 0) { $args += @("--only", $Only) }
}

& $py $script @args
