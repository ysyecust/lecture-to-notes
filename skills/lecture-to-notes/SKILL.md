---
name: lecture-to-notes
description: Generate professional, information-dense, figure-rich LaTeX course notes and compiled PDF from a YouTube or Bilibili lecture video. Use when the user provides a video URL and wants structured Chinese teaching notes. Key features include smart slide-region cropping (removes lecturer, keeps only slide content), three-level subtitle fallback (CC → Whisper → visual-only), dense frame sampling with contact-sheet review, and high information density writing. Trigger words include lecture notes, 课程笔记, 视频转PDF, 讲义, YouTube笔记, B站笔记, BV号.
---

# Lecture to Notes

Turn a lecture video (YouTube or Bilibili) into a complete, compilable `.tex` note set and a rendered PDF.

## Dependencies

Check before starting (use `which`). Prompt the user to install any missing tools.

| Tool | Required | Purpose |
|------|----------|---------|
| `yt-dlp` | Always | Video/subtitle/metadata download (supports YouTube + Bilibili) |
| `ffmpeg` | Always | Frame extraction, audio extraction |
| `xelatex` | Always | LaTeX compilation (TeX Live + CTeX for Chinese) |
| `magick` | Always | Frame montage, contact sheets, cropping |
| `python3` | Always | Smart crop script, Whisper |
| `whisper` | Bilibili / no-CC | Speech-to-text fallback (openai-whisper) |

Additional Python dependencies: `Pillow` (`pip install Pillow`).

## YouTube Cookie Notice

YouTube may require authentication to avoid bot detection. When `yt-dlp` fails with "Sign in to confirm you're not a bot", add `--cookies-from-browser chrome` (or `safari`/`firefox`/`edge`) to all `yt-dlp` commands.

## Goal

Produce a professional Chinese lecture note from a video URL. The output must:

- use the video's actual teaching content, not just subtitle transcription
- place the video's original cover image on the front page
- include **smart-cropped** slide figures (lecturer removed, only slide/PPT content)
- achieve high information density — every figure, box, and paragraph earns its space
- be structurally organized with `\section{}` / `\subsection{}`
- end with a synthesis section combining speaker's conclusions and your own distillation
- be a complete `.tex` from `\documentclass` to `\end{document}`
- compile successfully to PDF

## Platform Detection

Detect the platform from the URL:

| Pattern | Platform |
|---------|----------|
| `youtube.com`, `youtu.be` | YouTube |
| `bilibili.com/video/BV`, `b23.tv` | Bilibili |

Adapt the acquisition workflow accordingly (see below).

## Workflow

### Working Directory Convention

**CRITICAL**: Always use absolute paths for background commands (Whisper, video download).
Claude Code's shell resets the working directory between commands. Background tasks that
use relative paths will write output to the wrong location.

Recommended naming: `<course_id>_<lecture_number>_<short_title>/`
- Example: `nju_os_01_intro/`, `nju_os_02_app_view/`, `tamu_biegler_nlp/`

### Phase 1: Source Acquisition

#### 1a. Metadata Inspection

```bash
yt-dlp --dump-json --no-download "<URL>" > metadata.json
```

Extract: title, uploader, duration, chapters, thumbnail URL, subtitle availability. For Bilibili, also check for multi-part (分P) videos.

#### 1b. Subtitle Acquisition (Three-Level Fallback)

**Priority 1 — CC subtitles:**
```bash
# YouTube
yt-dlp --write-subs --sub-langs "zh.*,en.*" --convert-subs srt --skip-download "<URL>"

# Bilibili
yt-dlp --write-subs --sub-langs "zh-Hans,zh-CN,zh,ai-zh" --convert-subs srt --skip-download "<URL>"
```

**Priority 1.5 — YouTube auto-generated subtitles** (when no manual CC):
```bash
yt-dlp --write-auto-subs --sub-langs "en" --convert-subs srt --skip-download "<URL>"
# IMPORTANT: Clean duplicates — YouTube auto-subs repeat every line 2-3x
python3 scripts/clean_subs.py subs.en.srt --stats
```

**Priority 2 — Whisper speech-to-text** (when no CC subtitles):
```bash
yt-dlp -x --audio-format wav -o "audio.%(ext)s" "<URL>"
# IMPORTANT: Use absolute paths for Whisper to avoid working directory issues
# when running in background. The shell may reset cwd between commands.
WORKDIR="$(pwd)"
whisper "$WORKDIR/audio.wav" --model small --language zh \
  --output_format srt --output_dir "$WORKDIR"
```

**Priority 3 — Visual-only mode** (when audio quality is unusable):
Skip subtitles. Use dense frame sampling (fps=1) and rely entirely on visual content.

#### 1c. Video and Cover Download

```bash
# Cover image (may be webp/png/jpg depending on platform)
yt-dlp --write-thumbnail --skip-download -o "cover" "<URL>"
# Convert to jpg for xelatex compatibility
bash scripts/prepare_cover.sh .

# Video (for frame extraction)
yt-dlp -f "bestvideo+bestaudio/best" --merge-output-format mp4 -o "video.mp4" "<URL>"

# Bilibili 1080P+ (if user has logged in):
# yt-dlp --cookies-from-browser chrome -f "bestvideo+bestaudio/best" -o "video.mp4" "<URL>"
```

#### 1d. Bilibili Multi-Part (分P) Handling

```bash
yt-dlp --flat-playlist --dump-json "<URL>"  # List all parts
yt-dlp --playlist-items 1-3 -o "P%(playlist_index)s.%(ext)s" "<URL>"  # Download specific parts
```

Always ask the user which parts to process before downloading.

### Phase 2: Frame Extraction and Smart Cropping

This is where we differ most from other tools. Two-stage process:

#### Stage 1: Dense frame extraction by chapter

```bash
mkdir -p frames
# Extract 1 frame every 15 seconds per chapter
ffmpeg -ss <start> -to <end> -i video.mp4 -vf "fps=1/15" frames/ch<N>_%03d.png
```

#### Stage 2: Frame selection (no automatic cropping)

Use the original full frames directly. Do NOT apply automatic cropping — heuristic-based
cropping is unreliable (misidentifies blackboard content as "low information" regions).

**Future direction**: Use multimodal LLM (e.g., Claude Vision API) to classify frames
and decide cropping per-frame. For now, use full frames and select the best ones manually
via contact sheet review.

#### Stage 3: Contact sheet review

```bash
# Generate contact sheets per chapter (keeps montage size manageable)
# For chapters: montage per chapter directory
magick montage frames/ch<N>_*.png -tile 5x -geometry 384x216+2+2 contact_ch<N>.png

# For unchaptered videos with many frames (>100):
# Split into batches of 50 to avoid montage failures
for i in $(seq 1 50 $(ls frames/*.png | wc -l)); do
  ls frames/*.png | tail -n +$i | head -50 | xargs magick montage \
    -tile 5x -geometry 384x216+2+2 contact_batch_${i}.png
done
```

Review contact sheets to select the best frames. Criteria:
- Pick the **final fully-populated state** of progressive reveals
- Prefer the frame with the **most complete and readable** information
- Drop repetitive or low-information frames
- Keep every frame that teaches something distinct

#### Stage 4: Figure Verification (CRITICAL — prevents figure-text mismatch)

**Problem**: ~40% of figures in early versions had mismatched timestamps, captions, or
surrounding text. Root cause: timestamps were estimated from frame numbers, captions were
written from "what should be here" rather than "what IS here", and content was inferred
from section structure rather than verified against the actual frame.

**Before writing ANY figure into LaTeX, perform this three-way verification:**

For each candidate figure:

1. **Compute exact timestamp**: `chapter_start_seconds + (frame_number - 1) × 15`

2. **Cross-reference with subtitle**: Find the Whisper/CC subtitle entry at that timestamp.
   Read 2-3 subtitle lines before and after. This tells you what the speaker is ACTUALLY
   saying at the moment of that frame.

   ```python
   # Quick lookup: what was being said at timestamp T?
   import re
   target_sec = 285  # example: 4:45
   for entry in srt_entries:
       if abs(entry.start - target_sec) < 15:
           print(f"{entry.start}s: {entry.text}")
   ```

3. **Read the frame at full resolution**: Use the Read tool to view the actual frame image.
   Identify the ACTUAL text/diagram/code shown on screen — not what you think should be there.

4. **Three-way match check**: Verify that ALL THREE align:
   - ✅ Frame visual content (what the slide/screen actually shows)
   - ✅ Subtitle content (what the speaker is saying at that moment)
   - ✅ Your caption + surrounding text (what you plan to write)

   If any mismatch: either pick a different frame, adjust the timestamp, or rewrite the caption.

**Common failure modes to watch for:**

| Failure | Example | Fix |
|---------|---------|-----|
| Frame shows slide A, caption describes slide B | Frame shows "Language" section but caption says "Transformer" | Read frame at full res before writing caption |
| Timestamp off by 1-2 minutes | @07:00 claimed but actual content is at @09:00 | Cross-check with subtitle timestamps |
| Caption describes the section topic, not the frame | "Scaling Law 幂律关系" but frame shows a chess board | Write caption from frame content, not section title |
| Frame is transitional (between slides) | Half old slide, half new slide | Pick a frame 15s earlier or later |

### Phase 3: Writing

#### Teaching Content Rules

**Include:** title, chapters, on-screen diagrams/formulas/tables/code, subtitle explanations, speaker emphasis.

**Exclude:** greetings, small talk, sponsorship, channel logistics, 一键三连, 关注投币, closing pleasantries.

**Preserve:** speaker's closing discussion when it carries teaching value (synthesis, limitations, advice, open questions).

#### Writing Rules

1. **Chinese by default** unless user requests otherwise.

2. Organize with `\section{}` / `\subsection{}`. Reconstruct the teaching flow — don't mirror subtitle order.

3. Start from `assets/notes-template.tex`. Fill metadata and replace the body block.

4. **Front page cover**: video's original cover image, visually distinct from in-body figures.

5. **Figures: use full frames.** Use as many figures as needed for teaching clarity — do not optimize for a low count. **Every figure MUST pass the Stage 4 three-way verification before being written into LaTeX.** Never write a caption from section context alone — always read the actual frame first.

6. **No figures inside boxes.** `importantbox`, `knowledgebox`, `warningbox` must not contain `\includegraphics`.

7. **Math**: display math `$$...$$` followed immediately by a symbol explanation list.

8. **Code**: wrap in `lstlisting` with descriptive `caption`.

9. **Box strategy** — no quota, use as many as the teaching signal demands:
   - `importantbox`: core concepts, definitions, key mechanisms, theorem-like statements
   - `knowledgebox`: background, history, design tradeoffs, terminology, analogies
   - `warningbox`: common mistakes, hidden assumptions, pitfalls, causal confusions

10. Every major `\section` ends with `\subsection{本章小结}`. Add `\subsection{拓展阅读}` when worthwhile.

11. Final section `\section{总结与延伸}`:
    - Speaker's substantive closing (no sign-off fluff)
    - Your structured distillation of core claims and mechanisms
    - Cross-section synthesis, conceptual compression
    - Concrete takeaways, open questions, next steps

12. No `[cite]` placeholders.

#### Figure Time Provenance

Every figure from a video frame must have a same-page footnote with the source time interval:

```latex
\begin{figure}[H]
\centering
\includegraphics[width=\textwidth]{figures/fig_xxx.png}
\caption{描述\protect\footnotemark}
\end{figure}
\footnotetext{视频画面时间区间：00:12:31--00:12:46。}
```

- Time intervals come from subtitle alignment, not chapter-level guesses.
- Use `[H]` or stable placement to keep figure and footnote on the same page.

#### Visualization

For concepts that screenshots and prose can't explain clearly, add visualizations:
- LaTeX-native: TikZ / PGFPlots
- Pre-generated: Python matplotlib scripts

Use for: process flows, architecture layouts, scaling-law plots, comparison charts. No decorative graphics.

### Phase 4: Compilation and Delivery

```bash
xelatex -interaction=nonstopmode notes.tex && xelatex -interaction=nonstopmode notes.tex
```

#### Delivery Checklist

- [ ] Final `.tex` file
- [ ] Cover image (local file)
- [ ] All smart-cropped figure assets in `figures/`
- [ ] Compiled PDF (two-pass xelatex for TOC)
- [ ] Whisper-generated SRT file (if speech-to-text was used)

## Assets

- `assets/notes-template.tex`: LaTeX template
- `scripts/clean_subs.py`: YouTube auto-subtitle deduplication
- `scripts/prepare_cover.sh`: Cover image format conversion (webp/png → jpg)
- `scripts/smart_crop.py`: Slide region detection (experimental, not used by default)
