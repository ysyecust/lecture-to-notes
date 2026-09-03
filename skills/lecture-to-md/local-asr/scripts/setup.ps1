# sherpa-onnx X-ASR 一键安装脚本（Windows / PowerShell）。
# 步骤：
#   1) 检查 ffmpeg / ffprobe（PATH 中）
#   2) pip 装 sherpa-onnx
#   3) 下载 + 解压 X-ASR 模型到 ~/.cache/sherpa-onnx-models/
#
# 进阶：
#   $env:X_ASR_RELEASE_URL  自定义 release URL
#   $env:X_ASR_SHA256        覆盖默认 SHA-256（设空字符串跳过校验，不推荐）
#   $env:ASR_MODEL_DIR      模型目录（默认 ~/.cache/sherpa-onnx-models/<...>）
#   $env:GITHUB_PROXY       GitHub 镜像前缀（如 https://gh-proxy.com/）
#   $env:SKIP_PIP=1         跳过 pip install
#   $env:SKIP_MODEL=1       跳过模型下载

$ErrorActionPreference = "Stop"

$XASRReleaseName = "sherpa-onnx-x-asr-zipformer-transducer-zh-en-punct-int8-2026-06-03"
$XASRReleaseUrl  = if ($env:X_ASR_RELEASE_URL) { $env:X_ASR_RELEASE_URL } else {
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/${XASRReleaseName}.tar.bz2"
}
# SHA-256 由上游 README/docs/asr-benchmark-2026-08-31.md 记录。解压前必校验。
$XASRSHA256      = if ($env:X_ASR_SHA256) { $env:X_ASR_SHA256 } else {
    "5d02c36d7b44e886b7c8f0d8e051f8713acab96c264bb6ef9e718be39a6a2224"
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

        # ---- SHA-256 校验 ----
        # 不一致则删除并退出：避免被替换的 ONNX 模型进入推理链。
        if ($XASRSHA256) {
            Write-Host "==> 校验 SHA-256"
            $Actual = (Get-FileHash -Algorithm SHA256 -Path $TarFile).Hash
            Write-Host "    expected: $XASRSHA256"
            Write-Host "    actual:   $Actual"
            if ($Actual -ne $XASRSHA256) {
                Write-Host "✗ SHA-256 不匹配，删除下载文件并退出"
                Write-Host "  设 `$env:X_ASR_SHA256='' 可跳过校验（不推荐）"
                Write-Host "  或用 `$env:X_ASR_RELEASE_URL= 下载你信任的镜像，重跑本脚本"
                Remove-Item $TarFile -Force
                exit 1
            }
            Write-Host "  ✓ SHA-256 匹配"
        }

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
