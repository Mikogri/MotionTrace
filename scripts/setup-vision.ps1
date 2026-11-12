[CmdletBinding()]
param(
    [string]$CondaExe = "$env:USERPROFILE\miniconda3\Scripts\conda.exe",
    [string]$EnvironmentPath = "$env:USERPROFILE\miniconda3\envs\motiontrace-vision",
    [string]$ModelRoot = (Join-Path (Split-Path -Parent $PSScriptRoot) '.models\vision'),
    [switch]$SkipDownload
)

$ErrorActionPreference = 'Stop'
$RepositoryRoot = Split-Path -Parent $PSScriptRoot
$VisionPython = Join-Path $EnvironmentPath 'python.exe'

function Invoke-Checked {
    param([string]$Executable, [string[]]$Arguments)
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed ($LASTEXITCODE): $Executable $($Arguments -join ' ')"
    }
}

if (-not (Test-Path -LiteralPath $VisionPython)) {
    if (-not (Test-Path -LiteralPath $CondaExe)) {
        throw "Conda not found: $CondaExe. Pass -CondaExe and -EnvironmentPath explicitly."
    }
    Invoke-Checked $CondaExe @('create', '--yes', '--prefix', $EnvironmentPath, 'python=3.11.16', 'pip=25.3')
}

Invoke-Checked $VisionPython @('-c', 'import sys; assert sys.version_info[:2] == (3, 11), sys.version')
Invoke-Checked $VisionPython @('-m', 'pip', 'install', '--index-url', 'https://download.pytorch.org/whl/cu126', 'torch==2.8.0+cu126', 'torchvision==0.23.0+cu126')
$Requirements = Join-Path $RepositoryRoot 'ai\requirements-vision-lock.txt'
if (-not (Test-Path -LiteralPath $Requirements)) {
    $Requirements = Join-Path $RepositoryRoot 'ai\requirements-vision.txt'
}
Invoke-Checked $VisionPython @('-m', 'pip', 'install', '--requirement', $Requirements)
Invoke-Checked $VisionPython @('-m', 'pip', 'check')
Invoke-Checked $VisionPython @('-c', 'import torch; from transformers import XCLIPModel, XCLIPProcessor, AutoModelForZeroShotObjectDetection, AutoProcessor, Sam2VideoModel, Sam2VideoProcessor; assert torch.cuda.is_available(), "CUDA unavailable"; print(torch.__version__, torch.cuda.get_device_name(0))')

$env:HF_HUB_DISABLE_TELEMETRY = '1'
$ModelTool = Join-Path $PSScriptRoot 'vision_models.py'
if (-not $SkipDownload) {
    $PreviousOffline = $env:HF_HUB_OFFLINE
    try {
        $env:HF_HUB_OFFLINE = '0'
        Invoke-Checked $VisionPython @($ModelTool, '--root', $ModelRoot, '--download')
    }
    finally {
        $env:HF_HUB_OFFLINE = $PreviousOffline
    }
}
Invoke-Checked $VisionPython @($ModelTool, '--root', $ModelRoot, '--verify')
Invoke-Checked $VisionPython @($ModelTool, '--root', $ModelRoot, '--audit-environment')
Write-Host "Vision Python: $VisionPython"
Write-Host "Verified model manifest: $(Join-Path $ModelRoot 'manifest.json')"
