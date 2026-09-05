# Windows 环境配置（PowerShell 5.1 / 7+）

> 本 skill 在 Windows 10 / 11 自带的 PowerShell 5.1 上已端到端验证，PowerShell 7+ 同样可用。
> Windows 默认走 `cpu` provider；不推荐在 Windows 上跑 CUDA（sherpa-onnx CUDA EP 在
> Windows 上支持较弱，建议 GPU 加速走 Linux）。

## 0. 环境要求

| 组件 | 最低 | 推荐 | 备注 |
|---|---|---|---|
| Windows | 10 1809 | 11（22H2+） | 需自带 tar.exe（Win10 17063+，否则脚本自动 fallback Python tarfile） |
| PowerShell | 5.1（自带） | 7.4+（`winget install Microsoft.PowerShell`） | 脚本兼容 5.1，不使用 `?.` / `&&` 等 PS7 专有语法 |
| Python | 3.9 | 3.11 / 3.12 / 3.13 | 不支持 Microsoft Store 的「python 占位」；脚本会自动跳过 |
| ffmpeg / ffprobe | 4.x | 6.x / 7.x | 用 `winget install Gyan.FFmpeg`（推荐） |
| 磁盘空间 | ~300 MB | ~500 MB | 模型约 200 MB |
| 内存 | 8 GB | 16 GB+ | 长视频峰值 1–2 GB |

## 1. 一键安装（推荐）

> **首次必须在脚本目录下用相对路径调用**，因为脚本靠 `$PSScriptRoot` 定位自身。

```powershell
cd "<skill 目录>"    # 即 skills/lecture-to-md/local-asr

# 首次：装依赖 + 下载模型（~200 MB，耐心等）
powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1

# 之后正常转写（命令与 macOS/Linux 相同，只是路径用反斜杠）
python scripts\transcribe.py "C:\path\to\课程录像.mp4"
```

`setup.ps1` 自动：

1. 检查 `ffmpeg` / `ffprobe`（没有则报错并提示 `winget install Gyan.FFmpeg`）。
2. 解析 Python 3：优先 `py -3` 启动器，再 `python` / `python3`，**主动跳过 Microsoft Store 的 0 字节 python 占位程序**（直接执行会弹商店）。
3. `pip install -U sherpa-onnx`。
4. 下载 X-ASR int8 Zipformer transducer（~200 MB），**SHA-256 校验**后解压到 `%USERPROFILE%\.cache\sherpa-onnx-models\`。解压优先用系统 `tar.exe`，老机器上自动 fallback Python `tarfile`。
5. 强制 TLS 1.2（GitHub release 要求；老 5.1 默认可能只开 TLS 1.0）。

## 2. 分步手工安装

### 2.1 安装 ffmpeg

**推荐 winget：**

```powershell
winget install Gyan.FFmpeg
# 装完必须重开 PowerShell 让 PATH 生效
ffmpeg -version
ffprobe -version
```

**Chocolatey：**

```powershell
choco install ffmpeg
```

**Scoop：**

```powershell
scoop install ffmpeg
```

**手动：**

1. 从 [gyan.dev/ffmpeg/builds](https://www.gyan.dev/ffmpeg/builds/) 下载 `ffmpeg-release-essentials.zip`。
2. 解压到 `C:\Program Files\ffmpeg\`（脚本里 `common.py` PATH 兜底已含此目录）。
3. 把 `C:\Program Files\ffmpeg\bin\` 加到 PATH，或直接放进去即可。

### 2.2 安装 Python 3

**推荐 winget：**

```powershell
winget install Python.Python.3.12
# 装完重开 PowerShell
python --version
where python
```

**官方安装包：**

从 [python.org/downloads/windows](https://www.python.org/downloads/windows/) 下载安装。
**第一屏务必勾选** `Add python.exe to PATH`，否则 `python` 命令找不到。

**不要安装 Microsoft Store 版 Python**：那是 0 字节的 app execution alias，
执行后会直接弹应用商店。本 skill 的 `setup.ps1` 已经主动检测并跳过它，但你手工跑
`transcribe.py` 时记得用 `py -3` 或 `python.exe` 绝对路径。

### 2.3 装 sherpa-onnx

```powershell
python -m pip install -U sherpa-onnx
```

验证：

```powershell
python -c "import sherpa_onnx; print(sherpa_onnx.__version__)"
```

> Windows 上**不推荐** `pip install onnxruntime-gpu`：sherpa-onnx 的 CUDA EP 在 Windows 上
> 支持较弱，需要装 CUDA toolkit + cuDNN + 正确的 Visual Studio Runtime。建议需要 GPU 加速
> 时直接用 Linux。

### 2.4 下载并解压 X-ASR 模型

```powershell
$CACHE = "$env:USERPROFILE\.cache\sherpa-onnx-models"
New-Item -ItemType Directory -Force -Path $CACHE | Out-Null
Set-Location $CACHE

# 直连 GitHub release
Invoke-WebRequest -Uri "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-x-asr-zipformer-transducer-zh-en-punct-int8-2026-06-03.tar.bz2" -OutFile "sherpa-onnx-x-asr-zipformer-transducer-zh-en-punct-int8-2026-06-03.tar.bz2" -UseBasicParsing

# 国内断流时走镜像
# $env:GITHUB_PROXY = "https://gh-proxy.com/"
# Invoke-WebRequest -Uri "$env:GITHUB_PROXY$URL" -OutFile ... -UseBasicParsing

# 校验 SHA-256（与 setup.ps1 顶部 XASRSHA256 一致）
Get-FileHash -Algorithm SHA256 -LiteralPath "sherpa-onnx-x-asr-zipformer-transducer-zh-en-punct-int8-2026-06-03.tar.bz2"
# 期望：5D02C36D7B44E886B7C8F0D8E051F8713ACAB96C264BB6EF9E718BE39A6A2224

# 解压（Win10 17063+ 自带 tar.exe）
tar -xjf sherpa-onnx-x-asr-zipformer-transducer-zh-en-punct-int8-2026-06-03.tar.bz2
Remove-Item sherpa-onnx-x-asr-zipformer-transducer-zh-en-punct-int8-2026-06-03.tar.bz2
```

目录应包含 `encoder-*.onnx` / `decoder-*.onnx` / `joiner-*.onnx` / `tokens.txt`。

## 3. 端到端自检

```powershell
cd "<skill 目录>"
python scripts\transcribe.py "C:\path\to\short-lecture.mp4" --timestamps
```

预期：

- Windows CPU：~0.5–1× 实时（1 小时视频约 1–2 小时，建议后台跑）。
- 输出 `.txt` / `.md` / `.srt` 在源文件同目录。
- 中文字幕 / 路径均正常（脚本已强制 UTF-8 stdout + `PYTHONUTF8=1` + `PYTHONIOENCODING=utf-8`，GBK / cp1252 不会乱码）。

后台跑长任务（PowerShell 后台）：

```powershell
Start-Job -ScriptBlock {
    Set-Location $using:PWD
    & python scripts\transcribe.py "D:\big-lecture.mp4" --timestamps 2>&1
} | Tee-Object -FilePath asr.log
Get-Job | Receive-Job -Keep
```

## 4. Provider / 加速

| 平台 | 默认 provider | 实测速度 |
|---|---|---|
| Windows 10 / 11 | `cpu` | ~0.5–1× 实时 |

强制切换：

```powershell
# 强制 CPU
$env:ASR_PROVIDER = "cpu"
python scripts\transcribe.py input.mp4
```

CPU 线程数：

```powershell
python scripts\transcribe.py input.mp4 --num-threads 8
```

## 5. 编码与中文乱码

PowerShell 5.1 默认输出是 ANSI 代码页（中文机是 GBK，英文机是 cp1252）。脚本里 `common.py` 已自动：

```python
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
```

子进程环境强制：

```python
env["PYTHONUTF8"] = "1"
env["PYTHONIOENCODING"] = "utf-8"
```

但**老 PowerShell 宿主**（ISE、旧版 Windows Terminal）仍可能在窗口层乱码。建议：

- 用 Windows Terminal（自带 UTF-8 支持）打开 PowerShell。
- 或 `chcp 65001` 切到 UTF-8 代码页后再跑。
- 或在 PowerShell 7+ 下跑（`winget install Microsoft.PowerShell`，默认 UTF-8）。

## 6. 常见故障（Windows）

| 现象 | 处理 |
|---|---|
| `ffmpeg : 无法将"ffmpeg"项识别为 cmdlet` | `winget install Gyan.FFmpeg`，**重开 PowerShell** 让 PATH 生效 |
| `python : 无法将"python"项识别为 cmdlet` | 装 Python 时**必须勾** Add to PATH；或 `winget install Python.Python.3.12` 重开终端；或用 `py -3` 启动器 |
| `python` 一执行就弹 Microsoft Store | 你装了 Store 版 Python 占位程序。卸掉，改用 `python.org` 安装包或 winget |
| `无法加载文件 …因为在此系统上禁止运行脚本` | `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned`；或每次用 `powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1` |
| `Invoke-WebRequest` 报「请求被中止: 未能创建 SSL/TLS 安全通道」 | 老 5.1 默认只开 TLS 1.0，setup.ps1 顶部已 `SecurityProtocol = Tls12`；手工跑前手动设：`[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12` |
| 下载到一半失败 | 设镜像：`$env:GITHUB_PROXY = "https://gh-proxy.com/"` 后重跑 setup.ps1 |
| `tar : 无法将"tar"项识别为 cmdlet` | Win10 17063 之前没有自带 tar；setup.ps1 会自动 fallback Python `tarfile` 解压 |
| `tar -xjf` 报「bzip2: Cannot exec: No such file or directory」 | Win10 早期 tar 不支持 bz2；用 `tar -xf` 试；或直接用 7-Zip / Python `tarfile` 解 |
| `ModuleNotFoundError: sherpa_onnx` | 重跑 setup.ps1；或手工 `python -m pip install -U sherpa-onnx` |
| 输出中文路径乱码 | 用 Windows Terminal 打开 PowerShell；或在 `setup.ps1` 顶部加 `[Console]::OutputEncoding = [System.Text.Encoding]::UTF8` |
| 转写中文出现「汉字 汉字」中间多空格 | `transcribe.py` 已自动归一化；如仍出现，升级到最新 sherpa-onnx |
| 内存不足 | `--num-threads` 调小（如 `2`）；或换更小模型（找同系列更早日期的 release） |

## 7. 在 WSL 里跑（可选）

如果 Windows 上跑不顺，可以走 WSL（**WSL 2**，Ubuntu 22.04 / Debian 12）。流程见
[setup-linux.md](./setup-linux.md)，WSL 2 里挂载 Windows 盘：

```bash
# Windows D:\videos\课程.mp4 → WSL
python3 /mnt/d/CodePlace/lecture-to-notes/skills/lecture-to-md/local-asr/scripts/transcribe.py \
  "/mnt/d/videos/课程.mp4"
```

## 8. 升级

```powershell
# 升级 sherpa-onnx
python -m pip install -U sherpa-onnx

# 强制重下模型
$env:REINSTALL_MODEL = "1
powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1

# 升级 ffmpeg
winget upgrade Gyan.FFmpeg
```

## 9. 卸载

```powershell
# 删模型缓存
Remove-Item -Recurse -Force "$env:USERPROFILE\.cache\sherpa-onnx-models"

# 卸 sherpa-onnx
python -m pip uninstall sherpa-onnx

# 卸 ffmpeg / python（按需）
winget uninstall Gyan.FFmpeg
winget uninstall Python.Python.3.12
```

---

下一步：转写流程与参数详见 [SKILL.md](../SKILL.md)。
