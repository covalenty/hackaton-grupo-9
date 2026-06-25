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

if (-not (Test-Path $py)) {
    Write-Error "Python venv não encontrado em $py. Rodar: uv venv --python 3.12 ; uv pip install -r agent/requirements.txt"
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
