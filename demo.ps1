#requires -Version 5.1
<#
.SYNOPSIS
    Roda o demo do agente Cienty — 4 alertas de WhatsApp em sequência.

.EXAMPLE
    .\demo.ps1
    # Sequência completa, 3s entre alertas

.EXAMPLE
    .\demo.ps1 -Interval 5
    # 5s entre alertas (bom pra screen recording)

.EXAMPLE
    .\demo.ps1 -Only 3
    # Só o cenário #3 (CIENTY_BETTER · Paracetamol + Codeína)
#>
[CmdletBinding()]
param(
    [double]$Interval = 3.0,
    [int]$Only = 0
)

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Definition
$py = Join-Path $here ".venv\Scripts\python.exe"
$script = Join-Path $here "scripts\demo_client.py"

if (-not (Test-Path $py)) {
    Write-Error "Python venv não encontrado em $py. Rodar: uv venv --python 3.12 ; uv pip install -r agent/requirements.txt"
}

# Carrega ANTHROPIC_API_KEY do arquivo key.txt um nível acima (se a env var não estiver setada)
if (-not $env:ANTHROPIC_API_KEY) {
    $keyFile = Join-Path (Split-Path -Parent $here) "key.txt"
    if (Test-Path $keyFile) {
        $env:ANTHROPIC_API_KEY = (Get-Content $keyFile -Raw).Trim()
    }
}

$env:PYTHONIOENCODING = "utf-8"

$args = @("--interval", $Interval)
if ($Only -gt 0) { $args += @("--only", $Only) }

& $py $script @args
