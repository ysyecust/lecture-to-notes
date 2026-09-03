# sherpa-onnx X-ASR 一键安装脚本（Windows / PowerShell）。
# 步骤：
#   1) 检查 ffmpeg / ffprobe（PATH 中）
#   2) pip 装 sherpa-onnx
#   3) 下载 + 解压 X-ASR 模型到 ~/.cache/sherpa-onnx-models/
#
# 进阶：
#   $env:X_ASR_RELEASE_URL  自定义 release URL
#   $env:ASR_MODEL_DIR      模型目录（默认 ~/.cache/sherpa-onnx-models/<...>）
#   $env:GITHUB_PROXY       GitHub 镜像前缀（如 https://gh-proxy.com/）
#   $env:SKIP_PIP=1         跳过 pip install
#   $env:SKIP_MODEL=1       跳过模型下载

$ErrorActionPreference = "Stop"

$XASRReleaseName = "sherpa-onnx-x-asr-zipformer-transducer-zh-en-punct-int8-2026-06-03"
$XASRReleaseUrl  = if ($env:X_ASR_RELEASE_URL) { $env:X_ASR_RELEASE_URL } else {
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/${XASRReleaseName}.tar.bz2"
}
$ModelDir = if ($env:ASR_MODEL_DIR) { $env:ASR_MODEL_DIR } else {
    Join-Path $env:USERPROFILE ".cache\sherpa-onnx-models\$XASRReleaseName"
}
$Py = $env:PIP_EXE
if (-not $Py) {
    $Py = (Get-Command python3 -ErrorAction SilentlyContinue)?.Source
    if (-not $Py) { $Py = (Get-Command python -ErrorAction SilentlyContinue)?.Source }
    if (-not $Py) {
        Write-Host "✗ 找不到 python3 / python"
        exit 1
    }
}

Write-Host "==> 检查 ffmpeg / ffprobe"
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    Write-Host "✗ 没找到 ffmpeg。请先安装（推荐 winget install Gyan.FFmpeg）并加入 PATH。"
    exit 1
}
ffmpeg -version | Select-Object -First 1
ffprobe -version | Select-Object -First 1

if (-not ($env:SKIP_PIP -eq "1")) {
    Write-Host "==> 安装 sherpa-onnx（pip）"
    & $Py -m pip install -U sherpa-onnx
}
& $Py -c "import sherpa_onnx; print('  ok: sherpa-onnx', getattr(sherpa_onnx, '__version__', 'unknown'))"

if (-not ($env:SKIP_MODEL -eq "1")) {
    Write-Host "==> 下载 X-ASR 模型（约 200 MB）：$XASRReleaseUrl"
    $CacheDir = Join-Path $env:USERPROFILE ".cache\sherpa-onnx-models"
    New-Item -ItemType Directory -Force -Path $CacheDir | Out-Null
    $TarFile = Join-Path $CacheDir "${XASRReleaseName}.tar.bz2"

    $DownloadUrl = $XASRReleaseUrl
    if ($env:GITHUB_PROXY) {
        $DownloadUrl = "${env:GITHUB_PROXY}${DownloadUrl}"
    }

    if ((Test-Path $ModelDir) -and (Test-Path "$ModelDir\tokens.txt") -and -not ($env:REINSTALL_MODEL -eq "1")) {
        Write-Host "  ✓ 模型已存在：$ModelDir（设 REINSTALL_MODEL=1 强制重下）"
    } else {
        Write-Host "  下载中..."
        Invoke-WebRequest -Uri $DownloadUrl -OutFile $TarFile -UseBasicParsing
        Write-Host "  解压中..."
        tar -xjvf $TarFile -C $CacheDir
        Remove-Item $TarFile -Force
        if (-not (Test-Path "$ModelDir\tokens.txt")) {
            Write-Host "✗ 解压后找不到 $ModelDir\tokens.txt"
            exit 1
        }
    }
    Write-Host "  ✓ 模型已就绪：$ModelDir"
}

Write-Host ""
Write-Host "==> 完成。下一步："
Write-Host '    py scripts\transcribe.py "D:\path\to\课程.mp4" --timestamps'
Write-Host "模型路径：$ModelDir"