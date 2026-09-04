---
name: lecture-to-md
description: 把课堂视频（本地或 B 站/YouTube）、文字稿、课件三者（任意组合）整理成一份详细的中文 Markdown 课堂笔记，输出按课程标题命名的 `{title_name}.md`（首行为 `# 文档标题`）+ 相对路径图片。Markdown 工作流，与上游 `lecture-to-notes` 的 LaTeX/PDF 输出并行存在；上游 skill 完全不动。触发词：markdown 笔记、md 笔记、视频转 markdown、Markdown 讲义、不要 LaTeX、不要 PDF、纯文本笔记。
---

# Lecture to Notes (Markdown)

把课堂视频（本地或 B 站/YouTube）、文字稿、课件三者（任意组合）整理成一份详细的中文 Markdown 课堂笔记，输出按课程标题命名的 `{title_name}.md`（首行为 `# 文档标题`）+ 相对路径图片。**作为上游 `lecture-to-notes` LaTeX/PDF 流的 Markdown 平行方案；本 skill 与上游 skill 完全独立，不修改也不依赖上游 skill 的脚本。**

> **子代理分工**：素材获取（下载/ASR/抽帧/课件转 PNG）委派 **S0** 子代理并行做；主代理通读文字稿定死一级标题结构后，切素材（文字稿切片 / 帧按时段分目录 / 课件标页码）委派 **S1** 子代理做；然后每个撰写子代理领 1–3 个 H1 并行撰写 → 主代理汇总 → **对照文字稿重排目录结构**（只改标题、不动正文）→ 交付。
> 切分与素材委派见 [`references/splitting.md`](references/splitting.md)，派发与汇总见 [`references/subagent-workflow.md`](references/subagent-workflow.md)，结构重排见 [`references/structure-reorder.md`](references/structure-reorder.md)。

## 与 LaTeX 版的区别

|       | lecture-to-notes (LaTeX) | 本 skill (Markdown)    |
| ----- | ------------------------ | --------------------- |
| 输出    | `.tex` + PDF             | `{title_name}.md` + 图片  |
| 抽帧    | 每 15s（按章节）               | 严格每 5s                |
| 配图    | 全帧 + contact sheet 人工选   | LLM 多模态按 `###` 标题自动选图 |
| 配图优先级 | 视频帧                      | 课件截图 > 视频帧            |
| 编译    | xelatex                  | 无需编译                  |

## 子技能（asr 与云端转写）

本 skill 包内自带两个 ASR 子 skill，**默认走本地 ASR（见下「ASR 选型」一节）**：

| 子 skill 路径                              | 何时用                                                                  |
| ---------------------------------------- | -------------------------------------------------------------------- |
| [`local-asr/`](../local-asr/SKILL.md)       | **默认**。无字幕时全文转写 / 短片段核验。已在 **macOS Apple Silicon**、**Linux ARM64**（CPU）与 **Windows**（PowerShell 5.1，CPU）端到端跑通。       |
| [`volcengine-asr/`](../volcengine-asr/SKILL.md) | 备用。火山引擎豆包 BigASR / 豆包 2.0，需要 APP ID + Token；长音频首选异步模式       |

调用约定见各子 skill 的 SKILL.md，本 SKILL.md 不重复列参数。

## ASR 选型

- **首选 `local-asr/`**（sherpa-onnx X-ASR，跨平台路径齐备、int8 量化、对核显友好）。
- 若用户已自带文字稿（火山引擎豆包、飞书妙记等），**跳过 ASR**，直接走 Phase 1 的文字稿核验。
- 火山引擎走 `volcengine-asr/`，把产出的 `transcript.txt` 当作 S0-a 的产物继续。

## Dependencies

跨平台检查命令是否就位，缺则按平台提示用户安装（具体安装命令见各子 skill 的 setup 脚本）：

| 平台                              | 检查命令                              | 备注                                                                                              |
| ------------------------------- | --------------------------------- | ----------------------------------------------------------------------------------------------- |
| macOS / Linux shell             | `which <cmd>` 或 `command -v <cmd>` | 沙箱 PATH 可能不含 `/opt/homebrew/bin`（macOS）/ `/usr/local/bin`（Linux），见「已知坑」#1                  |
| Windows PowerShell 5.1 / cmd    | `where.exe <cmd>`                 | **`which` 不是 Windows 内建命令**，PowerShell 5.1 也没有该 alias；只有装了 Git for Windows / msys2 时才会有 `which.exe`（实测）。Windows 沙箱 PATH 可能不含 winget links / scoop shims / Chocolatey bin，见「已知坑」#1 |

最简做法：跑 `local-asr/scripts/common.py::require("<cmd>")`，它内部已经做了 `shutil.which` 兜底 + 按平台补齐常见 bin 目录（macOS `/opt/homebrew/bin`、Windows `winget links` / `%ProgramFiles%\ffmpeg\bin` / `~\scoop\shims` / `%ProgramData%\chocolatey\bin` 等），并返回**绝对路径**，避免子进程再吃 PATH 的亏。

| 工具                      | 必需 | 用途                                                            |
| ----------------------- | -- | ------------------------------------------------------------- |
| `yt-dlp`                | ✓  | 视频/字幕/元数据下载（YouTube + Bilibili）                               |
| `ffmpeg`                | ✓  | 5s 抽帧、音频提取（`ffprobe` 随 ffmpeg 一起装，Phase 4 判时长要用）              |
| `python3`               | ✓  | `clean_subs.py`                                                |
| `pdftoppm`              | △  | 课件 PDF → PNG                                                  |
| `soffice` (LibreOffice) | △  | 课件 PPT/PPTX → PDF                                             |
| `local-asr/`            | △  | 无字幕时全文转写 / 前 1min 核验；可加 `--timestamps` 出 srt/vtt 时间戳             |
| `volcengine-asr/`       | △  | 调用火山引擎豆包 ASR（需要凭据）                                           |
| `sherpa-onnx` (pip 包)     | △  | `local-asr/` 后端依赖，首次跑 `bash ../local-asr/scripts/setup.sh` 自动装           |

## 已知坑（务必遵守）

1. **PATH 兜底**：沙箱 PATH 可能丢以下常用 bin 目录——macOS `/opt/homebrew/bin`、`/usr/local/bin`、`/opt/local/bin`；Linux `/usr/local/bin`、`~/.local/bin`、`/snap/bin`；Windows `%LOCALAPPDATA%\Microsoft\WinGet\Links`、`%ProgramFiles%\ffmpeg\bin`、`~\scoop\shims`、`~\scoop\apps\<app>\current\bin`、`%ProgramData%\chocolatey\bin`。`yt-dlp`/`ffmpeg`/`pdftoppm`/`soffice` 一律用绝对路径，或先 `require()` 兜底（参考 `../local-asr/scripts/common.py::require`，Python 脚本首选；它内部已按平台列好候选目录）。
2. **帧序号 → 时间戳**：`verify_figures.py`（LaTeX 版脚本）硬编码 `×15`，本 skill 不复用该脚本。**不要硬编码 `帧时间 = (帧序号-1)×5`**——`fps=1/5` 的首帧可能不落在 0s、末尾帧可能被被丢、起始 PTS/掉帧都会让算术失真（实测 12s 片段只出 2 帧而非 3 帧）。帧时间一律由 ffmpeg 的 `showinfo` 记录真实 `pts_time`（见 Phase 1 的 S0-b）。
3. **ASR 时间戳选型**：`local-asr/` 默认 sherpa-onnx X-ASR 模型直接产出 token 级时间戳（transducer 模型自带）。**需要字幕时间戳时**，给 S0-a 的命令加 `--timestamps`（`transcribe.py --timestamps`，会写 srt/vtt）；若是已有稿子想补时间戳，跑一次 `transcribe.py 音频 --timestamps`，把生成的 srt 时间轴对齐到原文即可（sherpa-onnx 不需要独立的 ForcedAligner 模型）。

## 平台识别

| 匹配                                | 平台       |
| --------------------------------- | -------- |
| `youtube.com`, `youtu.be`         | YouTube  |
| `bilibili.com/video/BV`, `b23.tv` | Bilibili |

B 站分 P（多 part）视频：先用 `yt-dlp --flat-playlist --dump-json "<URL>"` 列出所有 part，**先问用户处理哪几 P** 再下载。

## 输入矩阵（视频 × 文字稿 × 课件）

|  视频 | 文字稿 |  课件 | 处理动作                                         |
| :-: | :-: | :-: | -------------------------------------------- |
|  ✓  |  ✗  |  ✗  | 取视频 → 先试官方字幕（CC→自动字幕），兜底 `local-asr/` → 5s 抽帧配图    |
|  ✓  |  ✓  |  ✗  | 核验文字稿 → 5s 抽帧配图                              |
|  ✓  |  ✗  |  ✓  | 取视频 → 先试官方字幕，兜底 `local-asr/` → 课件截图优先 + 5s 抽帧（都要做） |
|  ✓  |  ✓  |  ✓  | 核验文字稿 → 课件截图优先 + 5s 抽帧（都要做）                  |
|  ✗  |  ✓  |  ✗  | 直接总结文字稿，无图                                   |
|  ✗  |  ✓  |  ✓  | 总结文字稿 + 课件截图                                 |
|  ✗  |  ✗  |  ✓  | 仅课件：**暂时禁止** → 提示用户补视频或文字稿                   |
|  ✗  |  ✗  |  ✗  | 询问用户至少提供一样                                   |

- **视频来源**：本地路径 → 直接用；B 站/YouTube URL → `yt-dlp` 下载。
- **文字稿来源**：路径/粘贴文本 → 直接用；否则下载官方字幕（CC → 自动字幕去重）；再否则 `local-asr/` 全文转写（火山引擎走 `volcengine-asr/`）。
- **课件来源**：PDF / PPT / PPTX 路径。

## 工作流

### 工作目录约定

默认输出到**当前仓库根目录**下，沿用 `<course_id>_<lecture>_<title>/` 子目录约定，例如 `nju_os_01_intro/`、`cs336_01_tokenization/`。

**CRITICAL**：后台/长命令一律用绝对路径（沙箱 shell 会重置 cwd，相对路径会写错地方）。

目录内布局（>30min 时 `outline.md` / `parts/` 才会出现）：

```text
<outdir>/
  {video_name}.mp4
  frames/                 ← 全课程 5s 帧 + times.txt（唯一时间依据）
  slides/                 ← 课件每页 PNG，共享不复制
  outline.md              ┐
  parts/                  │ 子代理模式（>30min）才出现
    transcript_part_XX.txt│
    frames_part_XX/       │ 本时段帧 + 局部 times.txt
    part_XX.md            ┘
  {title_name}.md
  assets/{title_name}/    ← 最终配图（pXX_ 前缀隔离）
```

### Phase 0 输入解析

按输入矩阵确定路径；缺输入先补齐，不空跑。三样都没有 → 用 AskUserQuestion 让用户至少提供一样。


### Phase 1 素材获取（委派 S0 子代理，主代理不亲自下载）

素材获取是机械操作，且过程嘈杂（yt-dlp 试 cookie / 换格式 / 应对 bot 验证、ASR 长转写重试、ffmpeg 抽帧日志），**一律委派给子代理**，主代理只拿结果——既隔离主代理上下文，又能与读稿并行。

按输入矩阵决定派哪些 S0（缺什么派什么，本地已提供的直接跳过）。`skills/lecture-to-md/` 是本 skill 的根目录，子代理用它定位脚本。

| 子代理      | 干什么                               | 何时派    | 产物                                           |
| -------- | --------------------------------- | ------ | -------------------------------------------- |
| **S0-a** | 文字稿获取：官方字幕 → 自动字幕 → 去重清洗 → 兜底 ASR | 无文字稿输入 | `transcript.txt`（尽量带时间戳）                     |
| **S0-b** | 视频下载 + 严格 5s 抽帧 + times.txt       | 有视频输入  | `video.mp4` + `frames/` + `frames/times.txt` |
| **S0-c** | 课件 PDF/PPT → 每页 PNG               | 有课件输入  | `slides/slide-*.png`                         |

三个 S0 彼此独立，**在同一条消息里并行派发**（`subagent_type: general-purpose`），下载 / 转写 / 抽帧同时跑。主代理趁这个空档等文字稿产出、为读稿做准备。

#### S0-a：文字稿获取

```text
你是素材准备子代理，负责给一门课的视频/音频准备文字稿。

工作目录（绝对路径）：{outdir}
仓库根目录：{repo_root}

## 任务
按下面优先级拿到文字稿，写到 {outdir}/transcript.txt（能带时间戳就带，保留时间戳）：

1. 官方 CC 字幕：
   yt-dlp --write-subs --sub-langs "zh.*,en.*" --convert-subs srt --skip-download "{URL}"
2. 无 CC 时自动字幕（YouTube）：
   yt-dlp --write-auto-subs --sub-langs "en" --convert-subs srt --skip-download "{URL}"
3. 自动字幕逐行重复 2-3 次，务必去重：
   python3 {repo_root}/skills/lecture-to-md/lecture-to-md/scripts/clean_subs.py subs.en.srt --stats
4. 无任何字幕 → 本地 ASR 全文转写（sherpa-onnx X-ASR，默认中文）：
   python3 {repo_root}/skills/lecture-to-md/local-asr/scripts/transcribe.py "{abs_video_path}" --lang zh --timestamps
   首次跑会提示执行 bash setup.sh 装 sherpa-onnx + 下载 X-ASR 模型（约 200MB）。

## 输出（返回给主代理，200 字内）
- 文字稿路径 + 行数/字数
- 来源：官方字幕 / 自动字幕 / local-asr
- 是否带时间戳
- ASR 转写时长（若走 ASR）
- 任何异常（下载失败、bot 验证、字幕语言缺失、ASR 模型未下载等）
```

#### S0-b：视频下载 + 抽帧

```text
你是素材准备子代理，负责下载视频并抽帧。

工作目录（绝对路径）：{outdir}
仓库根目录：{repo_root}

## 任务
1. 下载视频（本地路径则跳过）：
   yt-dlp -f "bestvideo+bestaudio/best" --merge-output-format mp4 -o "video.mp4" "{URL}"
   # YouTube 遇 bot 验证（"Sign in to confirm you're not a bot"）时追加：
   #   --cookies-from-browser chrome   （或 safari / firefox / edge）
2. 严格 5s 抽帧 + 记录真实时间（禁止按帧号推算，见 SKILL.md「已知坑」#2）：
   mkdir -p frames
   ffmpeg -i video.mp4 -vf "fps=1/5,showinfo" frames/f_%05d.png 2> frames/showinfo.log
3. 生成「帧文件 → 真实秒数」映射表 times.txt：
   python3 - <<'PY'
   import re, glob
   pts = re.findall(r'pts_time:(\d+(?:\.\d+)?)',
                    open('frames/showinfo.log', encoding='utf-8', errors='ignore').read())
   n_png = len(glob.glob('frames/f_*.png'))
   assert len(pts) == n_png, f"帧数不匹配: showinfo {len(pts)} vs png {n_png}"
   open('frames/times.txt', 'w', encoding='utf-8').write(
       "".join(f"f_{i:05d}.png\t{t}\n" for i, t in enumerate(pts, 1)))
   PY
4. 报时长：
   ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 video.mp4

## 输出（返回给主代理，200 字内）
- video.mp4 路径 + 时长
- 抽帧张数 + times.txt 首末帧时间（首帧应≈0，末帧应≈时长）
- 任何异常（下载失败、bot 验证、抽帧中断等）
```

#### S0-c：课件转 PNG

```text
你是素材准备子代理，负责把课件转成每页 PNG。

工作目录（绝对路径）：{outdir}
仓库根目录：{repo_root}

## 任务
- PDF 直接转：pdftoppm -png -r 120 deck.pdf slides/slide
- PPT/PPTX 先转 PDF 再转 PNG：
  soffice --headless --convert-to pdf deck.pptx --outdir .
  pdftoppm -png -r 120 deck.pdf slides/slide

## 输出（返回给主代理，200 字内）
- slides/ 路径 + 总页数
- 文件名命名规则（slide-01.png … slide-NNN.png，数字即 PDF 页码）
- 任何异常（转换失败、缺页、字体乱码等）
```

> **工具绝对路径**：沙箱 PATH 可能不含 `/opt/homebrew/bin`，子代理执行 `yt-dlp`/`ffmpeg`/`pdftoppm`/`soffice` 时同样要**先 `which` 或用绝对路径**（见「已知坑」#1）。

### Phase 2 文字稿核验（主代理，仅当「视频 + 用户另给的文字稿」同时提供）

S0-a 已经拿到官方字幕（或 ASR 转写），主代理用它核验用户额外提供的文字稿是否与视频对得上：

1. 有官方字幕 → 直接拿官方字幕比对用户文字稿；
2. 无官方字幕 → 用 S0-a 的 ASR 结果（或 `local-asr/` 只转写**前 1 分钟**）比对；
3. 比对前 1min + 随机抽几段：**主题/关键词明显对不上才算不一致**（措辞不同属正常），明显不一致 → 停下用 AskUserQuestion 问用户是否继续；
4. 都无法核验（网站访问不了 / 无官方字幕且 ASR 不可用）→ 记录「文字稿未核验」并继续，不阻塞。

### Phase 3 验收素材（主代理，S0 产物必须亲自验）

委派不等于闭眼收结果——子代理可能抽帧失败却报「完成」、字幕下错语言、课件页码随手给个范围。主代理**亲自**跑几条命令验收，成本极低：

```bash
# ① times.txt 行数 == frames/*.png 数量（抓抽帧中途失败）
[ "$(wc -l < frames/times.txt)" = "$(ls frames/f_*.png | wc -l)" ] && echo "✓ 帧数一致" || echo "✗ 帧数不一致"

# ② times.txt 首行 ≈ 0、末行 ≈ 视频时长（抓 pts 偏移）
head -1 frames/times.txt; tail -1 frames/times.txt
ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 video.mp4

# ③ 文字稿非空、首尾合理
wc -l transcript.txt; head -5 transcript.txt; tail -5 transcript.txt

# ④ 课件 PNG 张数 == 页数（有课件时）
ls slides/slide-*.png | wc -l
```

`frames/times.txt` 是后续所有时间溯源的**唯一依据**：配图标注「画面时间」、子代理按时间区间取帧、大纲锚点换算，全部查这张表。

课件：直接用 S0-c 转出的每页 PNG（`slides/slide-01.png` …）。

### Phase 4 结构与分片：决定单线程还是子代理

**4.1 判定课程时长**

```bash
ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 video.mp4
```

无视频（纯文字稿）时按字数估算：中文约 **250 字/分钟**、英文约 **150 词/分钟**。

- **≤ 30 分钟** → 走 `Phase 5-A`：主代理单线程直出，不必拆分子代理。
- **> 30 分钟** → **必须**走 `Phase 5-B`：先出大纲 → 按一级标题切分 → 派子代理并行撰写 → 主代理汇总。
  - 切分侧（大纲格式、切分规则、切素材命令）见 **`references/splitting.md`**
  - 派发侧（prompt 模板、汇总、校验）见 **`references/subagent-workflow.md`**

**4.2 配图跟随撰写者**：单线程时主代理自己挑图；子代理模式下选图下沉给各子代理——它们手上有本片段的完整上下文，选图比主代理隔空猜更准。


### Phase 5 生成 md

读取 `assets/notes-prompt.md` 作为写作规范，产出 `<outdir>/{title_name}.md`。

- **文件名与文档标题**：`{title_name}` 取自课程标题（如 `cs336_01_tokenization`）；文件第一行是文档标题 `# <课程标题>`，与文件名对应，**不计入正文 H1 ≤ 10 的限额**；
- 图片用相对路径 `assets/{title_name}/xxx.png`；
- 视频帧图下用 `> 画面时间 00:12:31` 标注来源（时间查 `frames/times.txt`）；
- 课件图标注页码（如 `> 课件第 12 页`）。

**5-A 单线程（≤ 30 分钟）**

用多模态模型按**每个三级标题（`###`）** 挑 1~多张最相关图：

- **优先课件截图**，课件缺失时用视频帧；无合适图则该 H3 不配图（不硬凑）；
- 选出的图复制到 `assets/{title_name}/` 并统一命名（如 `h3_01.png`、`h3_02a.png`）；
- 然后一气写完全文。

**5-B 子代理并行（> 30 分钟）**

| 步骤            | 谁做                 | 产物                                                                |
| ------------- | ------------------ | ----------------------------------------------------------------- |
| ① 通读文字稿，定结构   | **主代理**（不可跳过、不可委派） | `outline.md`（H1 + 稿子锚点 + 帧区间 + **课件页码区间**）                        |
| ② 按一级标题切分     | **主代理**            | 切分方案（写进 outline.md）                                               |
| ③ 切素材         | **S1 子代理**         | `parts/transcript_part_XX.txt`、`parts/frames_part_XX/`（课件不搬，只标页码） |
| ④ 并行撰写 + 各自配图 | **再启动N 个子代理**      | `parts/part_XX.md` + `assets/{title_name}/pXX_*.png`              |
| ⑤ 按序汇总、统一风格   | **主代理**            | `{title_name}.md` → 接着做 **Phase 6 结构重排**                          |

四条硬规则：

1. **主代理必须先读完整个文字稿再定大纲**——只有通读才能按课程真实结构划分，不能让子代理边读边自由发挥。
2. **切分单位是一级标题，且大纲里的 H1 就是最终 `{title_name}.md` 里的 H1**——子代理不得改名、增删、调序。每个子代理最多分 **1–3 个一级标题**。
3. **素材按片段隔离**：文字稿切进 `parts/`（相邻段**重叠** 30–60 秒保证衔接），视频帧按时段切进 `parts/frames_part_XX/`（帧**不重叠**，避免重复配图）。**课件不复制**——只在 prompt 里给路径 + 页码区间；课件常是整门课合订 PDF，不标页码子代理就会用到别的课时的页。
4. **并行不共享文件**：每个子代理只写 `parts/part_XX.md` 和自己前缀为 `pXX_` 的图片，互不覆盖。

切素材是机械操作（`sed` 按行号切、srt 按时间切、帧按时段 `awk`+`cp`、课件页码定位），委派给 **S1 子代理**执行、主代理验收——见 **`references/splitting.md` 第 4 节**；派发 prompt 模板与汇总校验见 **`references/subagent-workflow.md`**。

### Phase 6 目录结构重排（主代理，只改标题不动正文）

汇总出来的 H1 反映的是「**切分块**」，不一定等于「**课程结构**」——定大纲时可能会为了让各子代理工作量均衡，容易把大主题拆散、把小主题合并。这一环把失真修回来。

**必做**：5-B 子代理模式。**建议做**：5-A 单线程模式（同样可能切偏，跑一遍诊断代价很低）。

|          |                                          |
| -------- | ---------------------------------------- |
| **谁做**   | 主代理，且**必须重新对照文字稿**，不能只看 `{title_name}.md` 自己改自己 |
| **改什么**  | 只有标题行：调层级、改文字、删重复、在段落边界插新标题、同步序号         |
| **不改什么** | 正文段落、公式代码、图片引用与图注、「画面时间」「课件第 N 页」标注      |
| **判据**   | **去掉所有标题行之后，重排前后的正文应逐字相同**（`diff` 可验）    |

诊断信号（命中任一条就该重排）：H1 带子层级编号（「2.3 …」「B2 …」）、H1 带续接词（「…（续）」「再谈…」）、相邻 H1 同属一个母题、各 H1 字数悬殊、H1 是具体技术点而非主题块。

完整诊断表、从文字稿识别真实母题的 5 类信号、执行步骤与自检命令见 **`references/structure-reorder.md`**。

### Phase 7 交付

报告 `{title_name}.md` 与 `assets/{title_name}/` 的绝对路径。（我们称这个 `{title_name}.md` 和 `assets/{title_name}/`）为成果，用户可能后续会要你移动这个到指定地方，你按这个粒度来理解成果或者产品）

## 复用资产

- `references/splitting.md`：**切分规范**——何时启用、outline.md 格式、切分规则、S0/S1 素材子代理委派（prompt 模板 + 主代理验收）
- `references/subagent-workflow.md`：**子代理规范**（派发与汇总）——prompt 模板、汇总校验、常见错误
- `references/structure-reorder.md`：**结构重排**（Phase 6）——诊断切分失真、对照文字稿定位真实母题、只改标题行不改正文的两级自检
- `scripts/clean_subs.py`：YouTube 自动字幕去重（✓ 复用，已复制到本 skill `scripts/`）
- `local-asr/`：**本地 ASR 子 skill**（sherpa-onnx X-ASR，跨平台）——见 [../local-asr/SKILL.md](../local-asr/SKILL.md)
- `volcengine-asr/`：**火山引擎 ASR 子 skill**（BigASR / 豆包 2.0，云端）——见 [../volcengine-asr/SKILL.md](../volcengine-asr/SKILL.md)
