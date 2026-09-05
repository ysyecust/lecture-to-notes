#Requires -Version 5.1
<#
    sherpa-onnx X-ASR 一键安装脚本（Windows / PowerShell）。

    步骤：
      1) 检查 ffmpeg / ffprobe
      2) 找到可用的 Python 3（优先 py -3 启动器，自动跳过 Microsoft Store 占位程序）
      3) pip 装 sherpa-onnx
      4) 下载 + 校验 SHA-256 + 解压 X-ASR 模型到 %USERPROFILE%\.cache\sherpa-onnx-models\

    兼容性：
      - 面向 Windows PowerShell 5.1（Win10/11 自带）编写并验证，PowerShell 7+ 同样可用。
      - 不使用 PowerShell 7 才有的语法（?.、&&、|| 等）。
      - 本文件保存为 UTF-8 with BOM，保证 5.1 下中文提示不乱码。

    环境变量（可选）：
      PYTHON_EXE  / PIP_EXE     指定 python.exe 绝对路径
      X_ASR_RELEASE_URL         自定义 release URL
      X_ASR_SHA256              覆盖默认 SHA-256（自定义下载 URL 时需同步提供）
      ASR_MODEL_DIR             模型目录（默认 %USERPROFILE%\.cache\sherpa-onnx-models\<...>）
      GITHUB_PROXY              GitHub 镜像前缀（如 https://gh-proxy.com/）
      SKIP_PIP=1                跳过 pip install
      SKIP_MODEL=1              跳过模型下载
      REINSTALL_MODEL=1         模型已存在时强制重下
#>

[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
# 关掉进度条：Invoke-WebRequest 在 5.1 下带进度条会慢一个数量级
$ProgressPreference = "SilentlyContinue"
# GitHub 下载要求 TLS 1.2；老机器上 5.1 默认可能只开 TLS 1.0
try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 } catch { }

$XASRReleaseName = "sherpa-onnx-x-asr-zipformer-transducer-zh-en-punct-int8-2026-06-03"
$XASRReleaseUrl = if ($env:X_ASR_RELEASE_URL) { $env:X_ASR_RELEASE_URL } else {
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/$XASRReleaseName.tar.bz2"
}
# SHA-256 由上游 docs/asr-benchmark-2026-08-31.md 记录。解压前必校验，
# 不一致就丢弃，避免被替换的 ONNX 权重进入推理链。
$XASRSHA256 = if ($env:X_ASR_SHA256) { $env:X_ASR_SHA256 } else {
    "5d02c36d7b44e886b7c8f0d8e051f8713acab96c264bb6ef9e718be39a6a2224"
}
$ModelDir = if ($env:ASR_MODEL_DIR) { $env:ASR_MODEL_DIR } else {
    Join-Path $env:USERPROFILE ".cache\sherpa-onnx-models\$XASRReleaseName"
}

function Write-Step { param([string]$Message) Write-Host "==> $Message" }
function Write-Ok   { param([string]$Message) Write-Host "  [OK] $Message" }
function Write-Info { param([string]$Message) Write-Host "      $Message" }
function Write-Warn { param([string]$Message) Write-Host "  [!]  $Message" }
function Stop-Setup { param([string]$Message) Write-Host "  [X]  $Message"; exit 1 }

<#
    PowerShell 5.1 的两个坑，都在这里绕开：

    1) $ErrorActionPreference='Stop' 时，原生命令只要往 stderr 写一个字节，
       再配合 2>$null / 2>&1 重定向，就会被当成 terminating error 抛出。
       pip 的 WARNING、Microsoft Store 的 python 占位程序都会触发，
       导致脚本在"看起来正常"的机器上莫名中断。
       解法：在函数作用域内把 EAP 临时降为 Continue，只回报退出码。

    2) 原生命令接 Select-Object -First N 会提前掐断管道，
       使 $LASTEXITCODE 变成 -1。所以这里不用管道截断，调用方自己取 [0]。

    -Quiet 表示丢掉 stderr（用于"探测某个 python 到底能不能用"这类场景）。
#>
function Invoke-Native {
    param(
        [Parameter(Mandatory = $true)][string]$Exe,
        [switch]$Quiet,
        [Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments
    )
    $ErrorActionPreference = 'Continue'
    if ($Quiet) { & $Exe @Arguments 2>$null } else { & $Exe @Arguments }
    $script:NativeExit = $LASTEXITCODE
}

function Get-AppPath {
    param([string]$Name)
    $cmd = Get-Command $Name -CommandType Application -ErrorAction SilentlyContinue |
           Select-Object -First 1
    if ($cmd) { return $cmd.Source }
    return $null
}

function Test-PythonExe {
    param([string]$Exe)
    if (-not $Exe) { return $false }
    if (-not (Test-Path -LiteralPath $Exe -PathType Leaf)) { return $false }
    $null = Invoke-Native $Exe -Quiet -c "import sys"
    return ($script:NativeExit -eq 0)
}

<#
    Windows 上 `python3.exe` / `python.exe` 常常是 Microsoft Store 的
    0 字节 app execution alias：Get-Command 能找到，一执行就弹商店。
    所以必须真的跑一次，用退出码判断，绝不能只看命令是否存在。
#>
function Resolve-PythonExe {
    foreach ($cand in @($env:PYTHON_EXE, $env:PIP_EXE)) {
        if (Test-PythonExe $cand) { return $cand }
    }

    # 1) Python Launcher（最可靠）：py -3 拿到真实的 python.exe 绝对路径
    $launcher = Get-AppPath "py"
    if ($launcher) {
        $exe = Invoke-Native $launcher -Quiet -3 -c "import sys; sys.stdout.write(sys.executable)"
        if (($script:NativeExit -eq 0) -and $exe) {
            $exe = ([string]$exe).Trim()
            if (Test-PythonExe $exe) { return $exe }
        }
    }

    # 2) PATH 里的 python / python3（会过滤掉 Store 占位程序）
    foreach ($name in @("python", "python3")) {
        $p = Get-AppPath $name
        if (Test-PythonExe $p) { return $p }
    }
    return $null
}

# -------------------- 1) ffmpeg / ffprobe --------------------
Write-Step "检查 ffmpeg / ffprobe"
$ffmpeg = Get-AppPath "ffmpeg"
if (-not $ffmpeg) {
    Stop-Setup "没找到 ffmpeg。请先安装：winget install Gyan.FFmpeg，然后重开终端。"
}
$ffprobe = Get-AppPath "ffprobe"
if (-not $ffprobe) {
    Stop-Setup "没找到 ffprobe（通常与 ffmpeg 一起装）。请确认 Gyan.FFmpeg 的完整版已装并重开终端。"
}
$ffmpegVer = @(Invoke-Native $ffmpeg -Quiet -version)[0]
$ffprobeVer = @(Invoke-Native $ffprobe -Quiet -version)[0]
Write-Ok "ffmpeg  $ffmpegVer"
Write-Ok "ffprobe $ffprobeVer"

# -------------------- 2) Python --------------------
Write-Step "解析 Python 3"
$Py = Resolve-PythonExe
if (-not $Py) {
    Stop-Setup ("找不到可用的 Python 3。`n" +
                "      建议：winget install Python.Python.3.12`n" +
                "      或在 https://www.python.org/downloads/windows/ 下载安装（记得勾 Add to PATH），`n" +
                "      装完重开终端再跑本脚本。")
}
$pyVer = Invoke-Native $Py -Quiet -c "import platform,sys; sys.stdout.write(platform.python_version())"
Write-Ok "$Py  (Python $pyVer)"

# -------------------- 3) sherpa-onnx --------------------
if ($env:SKIP_PIP -eq "1") {
    Write-Step "跳过 pip install（SKIP_PIP=1）"
} else {
    Write-Step "安装 sherpa-onnx（pip）"
    Invoke-Native $Py -m "pip" "install" "-U" "sherpa-onnx"
    if ($script:NativeExit -ne 0) {
        Stop-Setup "pip install sherpa-onnx 失败（退出码 $script:NativeExit）"
    }
}
$sherpaVer = Invoke-Native $Py -Quiet -c "import sherpa_onnx,sys; sys.stdout.write(str(getattr(sherpa_onnx, '__version__', 'unknown')))"
if ($script:NativeExit -ne 0) {
    Stop-Setup "sherpa_onnx 仍无法导入。请手动跑：& '$Py' -m pip install -U sherpa-onnx"
}
Write-Ok "sherpa-onnx $sherpaVer"

# -------------------- 4) 模型 --------------------
if ($env:SKIP_MODEL -eq "1") {
    Write-Step "跳过模型下载（SKIP_MODEL=1）"
} else {
    Write-Step "下载 X-ASR 模型（约 200 MB）"
    $CacheDir = Join-Path $env:USERPROFILE ".cache\sherpa-onnx-models"
    New-Item -ItemType Directory -Force -Path $CacheDir | Out-Null
    $TarFile = Join-Path $CacheDir "$XASRReleaseName.tar.bz2"

    $DownloadUrl = $XASRReleaseUrl
    if ($env:GITHUB_PROXY) { $DownloadUrl = "$($env:GITHUB_PROXY)$DownloadUrl" }

    $modelReady = (Test-Path -LiteralPath $ModelDir -PathType Container) -and
                  (Test-Path -LiteralPath (Join-Path $ModelDir "tokens.txt") -PathType Leaf)

    if ($modelReady -and ($env:REINSTALL_MODEL -ne "1")) {
        Write-Ok "模型已存在：$ModelDir（设 REINSTALL_MODEL=1 强制重下）"
    } else {
        Write-Info "URL: $DownloadUrl"
        try {
            Invoke-WebRequest -Uri $DownloadUrl -OutFile $TarFile -UseBasicParsing
        } catch {
            if (Test-Path -LiteralPath $TarFile) { Remove-Item -LiteralPath $TarFile -Force }
            Stop-Setup ("下载失败：$DownloadUrl`n" +
                        "      国内直连 GitHub 可能超时，试试镜像：`n" +
                        "        `$env:GITHUB_PROXY='https://gh-proxy.com/'`n" +
                        "      然后重跑本脚本。")
        }

        if ($XASRSHA256) {
            Write-Step "校验 SHA-256"
            $Actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $TarFile).Hash.ToLower()
            Write-Info "expected: $($XASRSHA256.ToLower())"
            Write-Info "actual:   $Actual"
            if ($Actual -ne $XASRSHA256.ToLower()) {
                Remove-Item -LiteralPath $TarFile -Force
                Stop-Setup ("SHA-256 不匹配，已删除下载文件。`n" +
                            "      若使用自定义 X_ASR_RELEASE_URL，请同步设置对应的 X_ASR_SHA256 后重跑。")
            }
            Write-Ok "SHA-256 匹配"
        }

        Write-Step "解压到 $CacheDir"
        $tarExe = Get-AppPath "tar"
        $extracted = $false
        if ($tarExe) {
            Invoke-Native $tarExe -Quiet "-xjf" $TarFile "-C" $CacheDir
            if ($script:NativeExit -eq 0) { $extracted = $true }
            else { Write-Warn "tar 退出码 $script:NativeExit，改用 Python tarfile 重试" }
        }
        if (-not $extracted) {
            # 兜底：Windows 10 17063 之前没有自带 tar.exe
            Invoke-Native $Py -Quiet -c "import sys, tarfile; tarfile.open(sys.argv[1], 'r:bz2').extractall(sys.argv[2])" $TarFile $CacheDir
            if ($script:NativeExit -ne 0) { Stop-Setup "解压失败（tar 与 Python tarfile 都不可用）" }
        }
        Remove-Item -LiteralPath $TarFile -Force

        if (-not (Test-Path -LiteralPath (Join-Path $ModelDir "tokens.txt") -PathType Leaf)) {
            Write-Host "      $CacheDir 下的内容："
            Get-ChildItem -LiteralPath $CacheDir | ForEach-Object { Write-Host "        $($_.Name)" }
            Stop-Setup "解压后找不到 $ModelDir\tokens.txt"
        }
        Write-Ok "模型已就绪：$ModelDir"
    }
}

Write-Host ""
Write-Host "==> 完成。下一步（PowerShell 里反引号不是续行符，请写成一行）："
Write-Host "    & '$Py' '$PSScriptRoot\transcribe.py' ""D:\path\to\课程.mp4"" --timestamps"
Write-Host "模型路径：$ModelDir"
Write-Host "提示：若提示“无法加载文件 …因为在此系统上禁止运行脚本”，用："
Write-Host "      powershell -ExecutionPolicy Bypass -File ""$PSCommandPath"""
