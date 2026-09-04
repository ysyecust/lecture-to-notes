# Linux 环境配置（ARM64 / x86_64，含 Ubuntu、Debian、CentOS、Arch）

> 本 skill 在 Linux ARM64（aarch64，例如 Apple Silicon 下的 Asahi、AWS Graviton、
> 树莓派 64-bit）与 Linux x86_64（Intel/AMD）上均已端到端验证。默认走 `cpu` provider；
> 若检测到 NVIDIA GPU 可选 `cuda`（需先装 `onnxruntime-gpu`）。

## 0. 环境要求

| 组件 | 最低 | 推荐 | 备注 |
|---|---|---|---|
| 内核 | 4.x | 5.x+ | x86_64 需支持 AVX2；ARM64 需支持 NEON + dotprod |
| glibc | 2.28 | 2.31+（Ubuntu 20.04 / Debian 11 起） | sherpa-onnx 官方 wheel 要求 |
| Python | 3.9 | 3.10 / 3.11 / 3.12 | 多数发行版自带 3.10+ |
| ffmpeg / ffprobe | 4.x | 6.x / 7.x | apt 默认装 4.x 或 5.x，建议额外加 PPA / static build |
| 磁盘空间 | ~300 MB | ~500 MB | 模型约 200 MB |
| 内存 | 8 GB | 16 GB+ | 长视频峰值 1–2 GB |

> **不支持 musl libc**（Alpine 原生 Python）。如需 Alpine，先装 glibc 兼容层或在 Docker 镜像里用 `python:3.12-slim-bookworm`（Debian 系）。

## 1. 一键安装（推荐）

```bash
cd "<skill 目录>"    # 即 skills/lecture-to-md/local-asr

# 首次：装依赖 + 下载模型（约 200 MB）
bash scripts/setup.sh
```

`setup.sh` 自动：

1. 检查 `ffmpeg` / `ffprobe`（没有则报错并提示 `sudo apt install ffmpeg`）。
2. `python3 -m pip install -U sherpa-onnx`（含 onnxruntime CPU 版）。
3. 下载 X-ASR int8 Zipformer transducer（~200 MB），**SHA-256 校验**后解压到 `~/.cache/sherpa-onnx-models/`。
4. 检测到 `nvidia-smi` 时询问是否装 `onnxruntime-gpu`。

## 2. 分步手工安装

### 2.1 安装 ffmpeg

**Ubuntu / Debian：**

```bash
sudo apt update
sudo apt install -y ffmpeg
# 验证
ffmpeg -version | head -1
ffprobe -version | head -1
```

**CentOS / RHEL（需要 EPEL + RPM Fusion）：**

```bash
sudo dnf install -y epel-release
sudo dnf install -y --nogpgcheck https://download1.rpmfusion.org/free/el/rpmfusion-free-release-$(rpm -E %rhel).noarch.rpm
sudo dnf install -y ffmpeg
```

**Arch / Manjaro：**

```bash
sudo pacman -S ffmpeg
```

**Alpine（不推荐 glibc 缺失）：**

```bash
apk add ffmpeg
# Python 走 py3-sherpa-onnx 不存在；建议改 Docker 镜像
```

**无 sudo 权限时用静态 build（任意发行版，推荐 aarch64 装 BtbN / x86_64 装 johnvansickle）：**

```bash
# 静态 build 备选：放到 ~/.local/bin/（已在 common.py PATH 兜底列表里）

# x86_64
curl -fsSL --max-time 60 https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz \
  | tar -xJ -C /tmp
cp /tmp/ffmpeg-*-amd64-static/{ffmpeg,ffprobe} ~/.local/bin/
chmod +x ~/.local/bin/ffmpeg ~/.local/bin/ffprobe

# aarch64（arm64）
curl -fsSL --max-time 90 -L \
  -o /tmp/ffmpeg-arm64.tar.xz \
  https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-linuxarm64-gpl.tar.xz
tar -xJf /tmp/ffmpeg-arm64.tar.xz -C /tmp
cp /tmp/ffmpeg-*-linuxarm64-gpl/bin/{ffmpeg,ffprobe} ~/.local/bin/
chmod +x ~/.local/bin/ffmpeg ~/.local/bin/ffprobe
rm -rf /tmp/ffmpeg-arm64.tar.xz /tmp/ffmpeg-*-linuxarm64-gpl

# 注意：imageio_ffmpeg 自带的 ffmpeg 二进制常装到 ~/.local/bin/，
# 但它阉割了一些选项（遇 -hide_banner 会报 nostdin 错误）。
# 如出现 "Failed to set value '-hide_banner' for option 'nostdin'"，
# 直接 rm ~/.local/bin/{ffmpeg,ffprobe}，再用上面静态 build 覆盖。
```

> 装好后**确认是哪个 ffmpeg 在被 PATH 找到**：`which -a ffmpeg`；如果有多个，前面的优先。
> 验证选项完整：`ffmpeg -hide_banner -version | head -1`（应该只输出版本，不报 "Option not found"）。

### 2.2 安装 Python 3

多数现代发行版已自带 Python 3.10+。验证：

```bash
python3 --version
which python3
```

太老时：

```bash
# Ubuntu 22.04+ / Debian 12+ 通常够用
sudo apt install -y python3 python3-pip python3-venv

# 极老发行版（Ubuntu 18.04 / CentOS 7）：用 deadsnakes / IUS / conda
```

> **不要用 `sudo pip install`**：会破坏发行版包管理。务必用 venv 或 `--user`。

```bash
# 推荐：venv（隔离依赖）
python3 -m venv .venv
source .venv/bin/activate
which python3   # 应该指向 .venv/bin/python3
```

### 2.3 装 sherpa-onnx

```bash
# CPU（默认；绝大多数情况够用）
python3 -m pip install -U sherpa-onnx

# 验证
python3 -c "import sherpa_onnx; print(sherpa_onnx.__version__)"
```

**NVIDIA GPU 加速（可选）：**

```bash
# 先装 CUDA / cuDNN（按官方矩阵选版本，例 CUDA 12.x + cuDNN 9）
# https://onnxruntime.ai/docs/execution-providers/CUDA-ExecutionProvider.html

# 装 GPU 版 onnxruntime（替代 sherpa-onnx 默认的 CPU 版）
python3 -m pip install -U onnxruntime-gpu

# 然后装 sherpa-onnx
python3 -m pip install -U sherpa-onnx
```

验证 GPU：

```bash
python3 -c "
import onnxruntime as ort
print('providers:', ort.get_available_providers())
print('cuda available:', 'CUDAExecutionProvider' in ort.get_available_providers())
"
```

### 2.4 下载并解压 X-ASR 模型

```bash
CACHE="$HOME/.cache/sherpa-onnx-models"
mkdir -p "$CACHE"
cd "$CACHE"

# 直连 GitHub release
curl -L --fail \
  -o sherpa-onnx-x-asr-zipformer-transducer-zh-en-punct-int8-2026-06-03.tar.bz2 \
  https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-x-asr-zipformer-transducer-zh-en-punct-int8-2026-06-03.tar.bz2

# 国内断流时走镜像
# curl -L --fail -o ... \
#   https://gh-proxy.com/https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/...

# 校验 SHA-256（与 setup.sh 顶部 X_ASR_SHA256 一致）
sha256sum sherpa-onnx-x-asr-zipformer-transducer-zh-en-punct-int8-2026-06-03.tar.bz2
# 期望：5d02c36d7b44e886b7c8f0d8e051f8713acab96c264bb6ef9e718be39a6a2224

tar -xjf sherpa-onnx-x-asr-zipformer-transducer-zh-en-punct-int8-2026-06-03.tar.bz2
rm sherpa-onnx-x-asr-zipformer-transducer-zh-en-punct-int8-2026-06-03.tar.bz2
```

目录应包含 `encoder-*.onnx` / `decoder-*.onnx` / `joiner-*.onnx` / `tokens.txt`。

## 3. 端到端自检

```bash
cd "<skill 目录>"
python3 scripts/transcribe.py "/path/to/short-lecture.mp4" --timestamps
```

预期：

- ARM64 CPU：~32× 实时（RTF ≈ 0.03，3 分钟视频约 6 秒跑完；实测过 aarch64 + X-ASR int8）。
- x86_64 CPU：~1× 实时（1 小时视频约 1 小时跑完，建议后台跑）。
- NVIDIA GPU + onnxruntime-gpu：~3× 实时起，取决于 GPU 算力（未实测，速度随硬件线性）。

后台跑长任务：

```bash
nohup python3 scripts/transcribe.py big-lecture.mp4 --timestamps \
  > asr.log 2>&1 &
# 看进度
tail -f asr.log
```

## 4. Provider / 加速

| 平台 | 默认 provider | 实测速度 |
|---|---|---|
| Linux x86_64 CPU | `cpu` | ~1× 实时 |
| Linux ARM64 CPU | `cpu` | ~32× 实时（RTF ≈ 0.03） |
| Linux + NVIDIA GPU | `cuda`（检测到时）或显式 `--provider cuda` | ~3× 实时+ |

强制切换：

```bash
# 强制 CPU
ASR_PROVIDER=cpu python3 scripts/transcribe.py input.mp4

# 强制 CUDA
ASR_PROVIDER=cuda python3 scripts/transcribe.py input.mp4
```

CPU 线程数（按物理核数调）：

```bash
python3 scripts/transcribe.py input.mp4 --num-threads 8
```

## 5. 在虚拟机/容器里跑

**VMware / VirtualBox / Parallels（macOS 主机）：** macOS 的 home 目录通常以 `vmhgfs-fuse` 或 `virtiofs` 挂到 Linux 的 `/mnt/hgfs/<user>/` 或 `/media/psf/Home/`。常见挂载点：

```bash
# 在 Linux VM 里查挂载点
mount | grep -i howen
# 例：vmhgfs-fuse on /mnt/hgfs/howen type fuse.vmhgfs-fuse (rw,...)

# 或直接尝试常见路径：
ls /mnt/hgfs/                   # VMware
ls /media/psf/Home/             # Parallels
ls /mnt/host/                   # WSL 2（实际为 /mnt/c, /mnt/d）
ls /howen/howen/                # 用户自定义挂载点
```

然后跑：

```bash
# 例：vmhgfs-fuse 挂到 /mnt/hgfs/howen
python3 /mnt/hgfs/howen/CodePlace/lecture-to-notes/skills/lecture-to-md/local-asr/scripts/transcribe.py \
  /mnt/hgfs/howen/Downloads/课程.mp4

# 例：用户自定义挂载点 /howen/howen
python3 /howen/howen/CodePlace/lecture-to-notes/skills/lecture-to-md/local-asr/scripts/transcribe.py \
  /howen/howen/Downloads/课程.mp4
```

**Docker（推荐基于 Debian bookworm 的镜像）：**

```dockerfile
FROM python:3.12-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg ca-certificates \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir sherpa-onnx
WORKDIR /skill
COPY skills/lecture-to-md/local-asr/scripts /skill/scripts
ENV PYTHONUNBUFFERED=1 PYTHONUTF8=1 PYTHONIOENCODING=utf-8
ENTRYPOINT ["python3", "/skill/scripts/transcribe.py"]
```

构建并跑：

```bash
docker build -t local-asr .
docker run --rm -v /path/to/videos:/videos local-asr /videos/课程.mp4 --timestamps
```

> 注意：`--rm` + `-v` 让模型缓存（默认在 `~/.cache`）也丢；如需持久化加 `-v asr-cache:/root/.cache/sherpa-onnx-models`。

## 6. 常见故障（Linux）

| 现象 | 处理 |
|---|---|
| `command not found: ffmpeg` | `sudo apt install ffmpeg`（Debian/Ubuntu），或装静态 build 到 `~/.local/bin/` |
| `Failed to set value '-hide_banner' for option 'nostdin'` | `~/.local/bin/ffmpeg` 是 imageio_ffmpeg 阉割版。`rm ~/.local/bin/{ffmpeg,ffprobe}` 后用静态 build（BtbN / johnvansickle）覆盖，详见「2.1 安装 ffmpeg」 |
| `pip install sherpa-onnx` 报 externally-managed-environment | 用 venv：`python3 -m venv .venv && source .venv/bin/activate && pip install sherpa-onnx` |
| wheel 安装失败：glibc 版本太老 | 升 Python：Ubuntu 18.04 / CentOS 7 装 Python 3.10+ via deadsnakes / IUS；或用 Docker |
| wheel 安装失败：aarch64 找不到匹配的 wheel | sherpa-onnx 官方支持 Linux aarch64 + glibc 2.28+；musl（Alpine）不支持，需换基础镜像 |
| `--provider cuda` 报错 | 没装 `onnxruntime-gpu`：先 `pip install -U onnxruntime-gpu`，并确认 CUDA / cuDNN 与之版本匹配 |
| `--provider cuda` 报 `libcudart.so not found` | `pip install nvidia-cudnn-cu12 nvidia-cuda-runtime-cu12`（pip wheel 自带）；或装系统级 CUDA toolkit |
| `libonnxruntime.so.1.x.x: cannot open shared object` | pip 装的 onnxruntime-gpu 与 sherpa-onnx 默认链接的 cpu 版本冲突；统一装 `onnxruntime-gpu`，必要时 `pip install --force-reinstall onnxruntime-gpu sherpa-onnx` |
| 模型下载失败 | 国内断流：`GITHUB_PROXY=https://gh-proxy.com/ bash scripts/setup.sh` |
| 转写慢 / 单核跑满 | 调 `--num-threads` 接近物理核数；或换 GPU |
| 中文出现「汉字 汉字」中间多空格 | `transcribe.py` 已自动归一化；如仍出现，升级到最新 sherpa-onnx |

## 7. 升级

```bash
# 升级 sherpa-onnx
python3 -m pip install -U sherpa-onnx

# 升级到 GPU 版
python3 -m pip install -U onnxruntime-gpu

# 强制重下模型
REINSTALL_MODEL=1 bash scripts/setup.sh

# 升级 ffmpeg（Ubuntu）
sudo add-apt-repository ppa:ubuntuhandbook1/ffmpeg7   # 7.x
sudo apt update && sudo apt upgrade ffmpeg
```

## 8. 卸载

```bash
# 删模型缓存
rm -rf ~/.cache/sherpa-onnx-models/

# 卸 sherpa-onnx / onnxruntime-gpu
python3 -m pip uninstall sherpa-onnx onnxruntime-gpu

# 卸 ffmpeg（按发行版命令）
sudo apt remove ffmpeg
```

---

下一步：转写流程与参数详见 [SKILL.md](../SKILL.md)。
