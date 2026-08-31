# lecture-to-notes

**[在线浏览课程讲义和论文解读 →](https://blog.simona.plus/lecture-to-notes/)**

两个 AI 驱动的学习工具，以及一个由仓库内容自动生成的课程资料库：

1. **lecture-to-notes**：将 YouTube / Bilibili / X(Twitter) 讲座视频转换为专业的中文 LaTeX 课程笔记和 PDF
2. **paper-to-html**：将学术论文转换为结构化的中文 HTML 解读页面
3. **course library**：按课程浏览 PDF，在专用阅读器中切换讲次，并通过 PDF-only PR 贡献资料

> 视频 URL → LaTeX PDF 讲义 | 论文 → 自包含 HTML 解读

## 特性

- **多平台支持**：YouTube、Bilibili 和 X/Twitter（自动识别 URL）
- **字幕四级回退**：CC 字幕 → 平台自动字幕（YouTube 自动去重）→ Whisper 语音转写 → 纯视觉模式
- **字幕清洗**：YouTube auto-subs 自动去重（通常去除 50% 重复行）
- **密集帧采样**：每 15 秒采样 + contact sheet 批量审查，不遗漏关键画面
- **图文三方验证**：每个配图写入前必须通过「帧画面 + 字幕内容 + 描述文字」三方一致性检查，防止图文不匹配
- **高信息密度写作**：结构化章节、教学信号盒（核心概念/背景知识/常见误区）、时间溯源脚注
- **数学公式支持**：准确转写 PPT 中的数学公式为 LaTeX display math + 符号解释
- **完整交付**：`.tex` 源文件 + 配图 + 编译好的 PDF
- **课程化归档**：课程书脊、讲次刻度、全文检索、独立 PDF 阅读页和移动端讲次切换
- **安全贡献**：外部 PR 只允许向 `content/inbox/` 添加 PDF；自动检查结构、页数、标题和首图，合并后才发布

## 仓库结构

```text
.
├── README.md
├── CONTRIBUTING.md             # PDF-only PR 投稿说明
├── LICENSE
├── content/
│   ├── courses/                # 课程 manifest 与已发布 PDF
│   ├── inbox/                  # 社区 PDF 投稿入口
│   └── papers.json             # 论文解读目录
├── ci/
│   └── pdf-sandbox.Dockerfile  # PDF 检查与站点构建沙箱
├── scripts/
│   ├── video_source.py        # YouTube / Bilibili / X(Twitter) URL 识别与元数据探测
│   ├── check_srt_health.py    # X/Twitter 字幕结构健康检查
│   ├── clean_subs.py          # YouTube 自动字幕去重
│   ├── correct_srt.py         # Whisper SRT 词典级修正（数据驱动，快）
│   ├── llm_correct_srt.py     # Whisper SRT 段级修正（LLM + 多模态，慢但更准）
│   ├── verify_figures.py      # 图文三方验证（时间戳 × 字幕 × 画面）
│   ├── prepare_cover.sh       # 封面格式转换（webp/png → jpg）
│   ├── smart_crop.py          # 课件区域检测（实验性，实际流程中通常直接用全帧）
│   ├── pdf_inspector.py        # PDF 安全检查、元数据与首图解析
│   ├── site_catalog.py         # 生成可信课程目录
│   ├── build_site.py           # 构建静态站点
│   └── whisper_prompts/        # Whisper --initial_prompt 术语表
├── docs/
│   ├── index.html              # 课程资料首页
│   ├── reader.html             # 目录白名单驱动的 PDF 阅读器
│   ├── contribute.html         # PDF 贡献入口
│   ├── assets/                 # 无框架前端模块与样式
│   └── papers/                 # 已发布的论文解读 HTML
└── skills/
    └── lecture-to-notes/
        ├── SKILL.md            # Skill 主定义（适用于 Codex / Claude Code）
        ├── agents/
        │   └── openai.yaml     # Agent UI 元数据
        ├── references/
        │   └── reader-first-writing.md  # 读者优先写作规则
        └── assets/
            └── notes-template.tex  # LaTeX 模板
```

## 快速开始

### 作为 Codex Skill

```bash
mkdir -p ~/.codex/skills
cp -R skills/lecture-to-notes ~/.codex/skills/
cp scripts/*.py scripts/prepare_cover.sh ~/.codex/skills/lecture-to-notes/assets/
cp -R scripts/whisper_prompts ~/.codex/skills/lecture-to-notes/assets/
```

### 作为 Claude Code Skill

```bash
# 复制 skill + 所有辅助脚本
mkdir -p ~/.claude/skills/lecture-to-notes/assets
mkdir -p ~/.claude/skills/lecture-to-notes/references
cp skills/lecture-to-notes/SKILL.md ~/.claude/skills/lecture-to-notes/
cp skills/lecture-to-notes/assets/notes-template.tex ~/.claude/skills/lecture-to-notes/assets/
cp skills/lecture-to-notes/references/reader-first-writing.md ~/.claude/skills/lecture-to-notes/references/
cp scripts/*.py scripts/prepare_cover.sh ~/.claude/skills/lecture-to-notes/assets/
cp -R scripts/whisper_prompts ~/.claude/skills/lecture-to-notes/assets/
```

然后在 Claude Code 中使用 `/lecture-to-notes <URL>` 触发（或直接贴一个 B 站 / YouTube / X(Twitter) 链接，skill 会被自动匹配）。

### 浏览课程资料

课程站点收录多门课程的 PDF 和论文解读，包括 Stanford
CS336: Language Modeling from Scratch（Spring 2026）前三讲的分讲笔记与合集。
课程卡片进入讲次列表后，PDF 会在独立阅读页中打开；若浏览器内嵌预览不可用，仍可
直接打开或下载原始 PDF。

### 贡献 PDF

普通贡献者不能直接修改本仓库的 `main` 分支。他们需要先 Fork 仓库，在自己的
Fork 中把 PDF 添加到 `content/inbox/` 并保存 commit，再使用 PDF contribution
模板向本仓库提交 PR。PR 只是一份合并申请，不会让贡献者获得写入权限。

自动化会从可信基础分支启动隔离容器，验证完整提交差异并解析 PDF；只有维护者
合并后的内容才会部署。网页步骤、命令行步骤和 PR 字段见
[CONTRIBUTING.md](CONTRIBUTING.md)。

外部投稿的安全容量边界是：单个 PDF 不超过 25 MiB、每个 PR 不超过 10 个 PDF、
合计不超过 100 MiB。这只是 PR 扫描范围，不是课程库或维护者发布的开发上限。

### 视频源检测与探测

支持 YouTube、Bilibili，以及 `https://x.com/<user>/status/<id>[/video/<n>]` 和对应的
Twitter URL。对 X/Twitter 必须保留用户输入的完整 URL，包括可选的 `/video/<n>`。

```bash
python3 scripts/video_source.py detect "<URL>"
python3 scripts/video_source.py probe "<URL>"
```

下载到的 X/Twitter 字幕必须先通过 `scripts/check_srt_health.py` 的结构健康检查，
再在视频时长 10%、50%、90% 三处对照音频和画面做语义抽样；任一检查失败时，改用
X 音频 → Whisper → 现有 SRT 修正流程。

## 依赖

### macOS

```bash
brew install yt-dlp ffmpeg imagemagick poppler
brew install --cask mactex        # 含 xelatex + CTeX 中文支持
pip install openai-whisper         # Bilibili / 无字幕视频必需
pip install Pillow                 # 仅 smart_crop.py 需要（可选）
```

### Windows（winget，已实测通过）

```powershell
pip install --user yt-dlp
winget install --id Gyan.FFmpeg -e --silent
winget install --id ImageMagick.ImageMagick -e --silent
winget install --id MiKTeX.MiKTeX -e --silent      # ~140 MB，首次编译会自动装 ctex
pip install --user openai-whisper                  # 会一起装 torch，~2 GB
```

> 注意：MiKTeX 默认需要对缺失宏包手动放行；命令行调用 `xelatex` 时加 `-enable-installer` 让它自动下。Whisper 依赖的 ffmpeg 需要在 PATH 中（否则跑 Whisper 时会 `FileNotFoundError`）。

### Linux（Debian / Ubuntu 参考）

```bash
sudo apt install yt-dlp ffmpeg imagemagick texlive-xetex texlive-lang-chinese
pip install openai-whisper
```

### 工具一览

| 工具 | 必需 | 用途 |
|------|:---:|------|
| `yt-dlp` | ✓ | 视频 / 字幕 / 元数据下载 |
| `ffmpeg` | ✓ | 帧提取、音频提取、Whisper 前置 |
| `xelatex` | ✓ | LaTeX 编译（含 ctex 宏包） |
| `magick` | ✓ | Contact sheet、帧处理 |
| `whisper` | ✓ | 语音转写（Bilibili 基本无 CC，必用） |
| `python3` | ✓ | 运行 `scripts/` 下所有脚本 |
| `scripts/video_source.py` | ✓ | YouTube / Bilibili / X/Twitter URL 识别与元数据探测 |
| `scripts/check_srt_health.py` | X/Twitter 字幕 | 检查 SRT 覆盖率、重复率和运行时窗口 |
| `Pillow` | △ | 仅 `smart_crop.py` 需要 |
| Claude Code CLI | △ | 仅 `llm_correct_srt.py` 需要（复用本地登录态，无需 API key） |

## 工作流程

```
视频 URL（YouTube / Bilibili / X/Twitter）
  │
  ├─ video_source.py ──→ 平台识别 + 元数据探测
  │
  ├─ yt-dlp ──→ 封面 + 字幕(CC/自动轨) + 视频
  │                                │
  │  字幕不可用或 X 字幕检查失败？──→ Whisper 转写
  │                                │（可选配 --initial_prompt 喂领域术语表）
  │                                ▼
  │                          correct_srt.py      （词典级快速修正）
  │                                │
  │                          llm_correct_srt.py  （LLM + 多模态段级修正，可选）
  │
  ├─ ffmpeg ──→ 按章节密集帧采样 (1帧/15秒)
  │
  ├─ magick montage ──→ Contact sheet 批量审查（直接用全帧，smart_crop 通常不启用）
  │
  ├─ 筛选候选帧 ──→ verify_figures.py 三方校验（时间戳 × 字幕 × 画面）
  │
  ├─ 通过校验的 ──→ figures/ 目录
  │
  ├─ 基于模板生成 .tex ──→ 结构化中文讲义
  │
  └─ xelatex ×2 ──→ 最终 PDF（含目录 / TOC）
```

### SRT 修正两阶段

- **阶段 1 — 词典级**（`correct_srt.py`）：用 `whisper_prompts/glossary_<course>.json` 里的
  `wrong → right` pair 做批量替换。对专业术语、人名、课程常用词非常有效，毫秒完成。
- **阶段 2 — 段级语义**（`llm_correct_srt.py`）：按 ~90 秒切段，每段抽一个中间帧，
  调 `claude -p` 做多模态校准。能修语境级错误（"PASSNAME" → "PATHNAME" 这类同音错），
  但耗时长，一般只对要发布的讲义跑。

## 相比现有工具的改进

| 特性 | [llm-note-generator](https://github.com/Stefan0219/llm-note-generator) | [wdkns-skills](https://github.com/wdkns/wdkns-skills) | **lecture-to-notes** |
|------|:---:|:---:|:---:|
| 全自动（无需手动粘贴 prompt） | ✗ | ✓ | ✓ |
| Bilibili 支持 | ✗ | ✗ | ✓ |
| X/Twitter 支持 | ✗ | ✗ | ✓ |
| 字幕回退（Whisper） | ✗ | ✗ | ✓ |
| 分P视频处理 | ✗ | ✗ | ✓ |
| Contact sheet 帧审查 | ✗ | ✓ | ✓ |
| 时间溯源脚注 | ✗ | ✓ | ✓ |
| 高信息密度 box 系统 | ✓ | ✓ | ✓ |

## 适用场景

- 大学公开课笔记整理（南京大学、MIT OCW、Stanford CS 等）
- 技术讲座/会议 talk 转结构化文档
- YouTube / Bilibili / X/Twitter 教学视频的知识提取与归档

## 致谢

本项目受以下开源工作启发：

- [Stefan0219/llm-note-generator](https://github.com/Stefan0219/llm-note-generator) — PDF+字幕→prompt 的原始思路
- [wdkns/wdkns-skills](https://github.com/wdkns/wdkns-skills) — YouTube 视频转 LaTeX 的 Codex skill 设计

## License

GPL-3.0 — 与上游项目保持一致。
