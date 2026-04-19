# lecture-to-notes

**[在线预览所有讲义和论文解读 →](http://blog.simona.plus/lecture-to-notes/)**

两个 AI 驱动的学习工具：

1. **lecture-to-notes**：将 YouTube / Bilibili 讲座视频转换为专业的中文 LaTeX 课程笔记和 PDF
2. **paper-to-html**：将学术论文转换为结构化的中文 HTML 解读页面

> 视频 URL → LaTeX PDF 讲义 | 论文 → 自包含 HTML 解读

## 特性

- **多平台支持**：YouTube 和 Bilibili（自动识别 URL）
- **字幕四级回退**：CC 字幕 → YouTube 自动字幕（自动去重）→ Whisper 语音转写 → 纯视觉模式
- **字幕清洗**：YouTube auto-subs 自动去重（通常去除 50% 重复行）
- **密集帧采样**：每 15 秒采样 + contact sheet 批量审查，不遗漏关键画面
- **图文三方验证**：每个配图写入前必须通过「帧画面 + 字幕内容 + 描述文字」三方一致性检查，防止图文不匹配
- **高信息密度写作**：结构化章节、教学信号盒（核心概念/背景知识/常见误区）、时间溯源脚注
- **数学公式支持**：准确转写 PPT 中的数学公式为 LaTeX display math + 符号解释
- **完整交付**：`.tex` 源文件 + 配图 + 编译好的 PDF

## 仓库结构

```text
.
├── README.md
├── LICENSE
├── scripts/
│   ├── clean_subs.py          # YouTube 自动字幕去重
│   ├── correct_srt.py         # Whisper SRT 词典级修正（数据驱动，快）
│   ├── llm_correct_srt.py     # Whisper SRT 段级修正（LLM + 多模态，慢但更准）
│   ├── verify_figures.py      # 图文三方验证（时间戳 × 字幕 × 画面）
│   ├── prepare_cover.sh       # 封面格式转换（webp/png → jpg）
│   ├── smart_crop.py          # 课件区域检测（实验性，实际流程中通常直接用全帧）
│   └── whisper_prompts/       # Whisper --initial_prompt 术语表
│       ├── glossary_nju_os.json   # 词典修正的 wrong→right 对
│       └── nju_os.txt             # 引导 Whisper 正确转写专业术语
├── docs/
│   ├── index.html             # GitHub Pages 首页（讲义 + 论文卡片网格）
│   ├── pdfs/                  # 已发布的讲义 PDF
│   └── papers/                # 已发布的论文解读 HTML
└── skills/
    └── lecture-to-notes/
        ├── SKILL.md            # Skill 主定义（适用于 Codex / Claude Code）
        ├── agents/
        │   └── openai.yaml     # Agent UI 元数据
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
cp skills/lecture-to-notes/SKILL.md ~/.claude/skills/lecture-to-notes/
cp skills/lecture-to-notes/assets/notes-template.tex ~/.claude/skills/lecture-to-notes/assets/
cp scripts/*.py scripts/prepare_cover.sh ~/.claude/skills/lecture-to-notes/assets/
cp -R scripts/whisper_prompts ~/.claude/skills/lecture-to-notes/assets/
```

然后在 Claude Code 中使用 `/lecture-to-notes <URL>` 触发（或直接贴一个 B 站 / YouTube 链接，skill 会被自动匹配）。

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
| `Pillow` | △ | 仅 `smart_crop.py` 需要 |
| Claude Code CLI | △ | 仅 `llm_correct_srt.py` 需要（复用本地登录态，无需 API key） |

## 工作流程

```
视频 URL
  │
  ├─ yt-dlp ──→ 元数据 + 封面 + 字幕(CC) + 视频
  │                                │
  │              字幕不可用？──→ Whisper 转写
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
| 智能课件裁剪 | ✗ | ✗ | ✓ |
| 字幕回退（Whisper） | ✗ | ✗ | ✓ |
| 分P视频处理 | ✗ | ✗ | ✓ |
| Contact sheet 帧审查 | ✗ | ✓ | ✓ |
| 时间溯源脚注 | ✗ | ✓ | ✓ |
| 高信息密度 box 系统 | ✓ | ✓ | ✓ |

## 适用场景

- 大学公开课笔记整理（南京大学、MIT OCW、Stanford CS 等）
- 技术讲座/会议 talk 转结构化文档
- YouTube / Bilibili 教学视频的知识提取与归档

## 致谢

本项目受以下开源工作启发：

- [Stefan0219/llm-note-generator](https://github.com/Stefan0219/llm-note-generator) — PDF+字幕→prompt 的原始思路
- [wdkns/wdkns-skills](https://github.com/wdkns/wdkns-skills) — YouTube 视频转 LaTeX 的 Codex skill 设计

## License

GPL-3.0 — 与上游项目保持一致。
