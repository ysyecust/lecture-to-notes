# lecture-to-notes

**[在线预览所有讲义 →](http://blog.simona.plus/lecture-to-notes/)**

将 YouTube / Bilibili 讲座视频转换为专业的中文 LaTeX 课程笔记和 PDF。

> 全自动流水线：视频 URL → 字幕获取 → 密集帧采样 → 结构化 LaTeX → 编译 PDF。

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
│   ├── prepare_cover.sh       # 封面格式转换（webp/png → jpg）
│   ├── verify_figures.py      # 图文三方验证（时间戳 × 字幕 × 画面）
│   └── smart_crop.py          # 课件区域检测（实验性，默认不启用）
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
cp scripts/smart_crop.py ~/.codex/skills/lecture-to-notes/
```

### 作为 Claude Code Skill

```bash
# 复制 skill
cp skills/lecture-to-notes/SKILL.md ~/.claude/commands/lecture-to-notes.md

# 复制资产
mkdir -p ~/.claude/assets/lecture-to-notes
cp skills/lecture-to-notes/assets/notes-template.tex ~/.claude/assets/lecture-to-notes/
cp scripts/smart_crop.py ~/.claude/assets/lecture-to-notes/
```

然后在 Claude Code 中使用 `/lecture-to-notes <URL>` 触发。

## 依赖

### 系统工具

```bash
# macOS
brew install yt-dlp ffmpeg imagemagick poppler

# LaTeX（需要 CTeX 中文支持）
# 如果尚未安装：brew install --cask mactex
```

### Python 包

```bash
pip install Pillow           # smart_crop.py 必需
pip install openai-whisper   # Bilibili / 无字幕视频必需
```

### 工具一览

| 工具 | 必需 | 用途 |
|------|:---:|------|
| `yt-dlp` | ✓ | 视频/字幕/元数据下载 |
| `ffmpeg` | ✓ | 帧提取、音频提取 |
| `xelatex` | ✓ | LaTeX 编译 |
| `magick` | ✓ | Contact sheet、帧处理 |
| `python3` + `Pillow` | ✓ | 智能裁剪 |
| `whisper` | △ | 语音转写（无 CC 字幕时） |

## 工作流程

```
视频 URL
  │
  ├─ yt-dlp ──→ 元数据 + 封面 + 字幕(CC) + 视频
  │                                │
  │              字幕不可用？──→ Whisper 转写
  │
  ├─ ffmpeg ──→ 按章节密集帧采样 (1帧/15秒)
  │
  ├─ smart_crop.py ──→ 自动裁剪课件区域，去除讲师
  │
  ├─ magick montage ──→ Contact sheet 人工/AI审查
  │
  ├─ 筛选高价值帧 ──→ figures/ 目录
  │
  ├─ 基于模板生成 .tex ──→ 结构化中文讲义
  │
  └─ xelatex ×2 ──→ 最终 PDF（含目录）
```

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
