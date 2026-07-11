---
name: lecture-to-notes
description: Use when users provide YouTube, Bilibili, or X(Twitter) lecture URLs and want structured Chinese LaTeX/PDF course notes, especially requests phrased as X/Twitter lecture notes, 视频转PDF, 课程笔记, 讲义, or BV号.
---

# Lecture to Notes

Turn a YouTube, Bilibili, or X/Twitter lecture video into a complete, compilable `.tex` note set and a rendered PDF.

## Dependencies

Check before starting (use `which`). Prompt the user to install any missing tools.

| Tool | Required | Purpose |
|------|----------|---------|
| `yt-dlp` | Always | Video/subtitle/metadata download (supports YouTube + Bilibili + X/Twitter) |
| `ffmpeg` | Always | Frame extraction, audio extraction |
| `xelatex` | Always | LaTeX compilation (TeX Live + CTeX for Chinese) |
| `magick` | Always | Frame montage and contact sheets |
| `python3` | Always | Installed helper scripts and Whisper support |
| `whisper` | Bilibili / X fallback / no-CC | Speech-to-text fallback (openai-whisper) |

Additional Python dependencies: `Pillow` (`pip install Pillow`) only for the optional
`/ABSOLUTE/PATH/TO/lecture-to-notes/assets/smart_crop.py` experiment.

## YouTube Cookie Notice

YouTube may require authentication to avoid bot detection. When `yt-dlp` fails with "Sign in to confirm you're not a bot", add `--cookies-from-browser chrome` (or `safari`/`firefox`/`edge`) to all `yt-dlp` commands.

## Goal

Produce a professional Chinese lecture note from a YouTube, Bilibili, or X/Twitter video URL. The output must:

- use the video's actual teaching content, not just subtitle transcription
- place the video's original cover image on the front page
- include selected full-frame slide figures chosen by contact-sheet review
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
| `x.com/<user>/status/<id>[/video/<n>]` | X/Twitter |
| `twitter.com/<user>/status/<id>[/video/<n>]` | X/Twitter |

Adapt the acquisition workflow accordingly (see below).

For X/Twitter, preserve the exact input URL throughout acquisition. Do not shorten,
canonicalize, or remove an optional `/video/<n>` suffix.

## Workflow

### Working Directory Convention

Resolve the absolute assets directory from the loaded SKILL.md before running helpers.
Then substitute that literal directory for `/ABSOLUTE/PATH/TO/lecture-to-notes/assets`
everywhere below before executing a command. Each fenced command may run in a fresh shell,
so never rely on a path variable defined by an earlier command.

```bash
for helper in \
  "/ABSOLUTE/PATH/TO/lecture-to-notes/assets/video_source.py" \
  "/ABSOLUTE/PATH/TO/lecture-to-notes/assets/check_srt_health.py" \
  "/ABSOLUTE/PATH/TO/lecture-to-notes/assets/clean_subs.py" \
  "/ABSOLUTE/PATH/TO/lecture-to-notes/assets/correct_srt.py" \
  "/ABSOLUTE/PATH/TO/lecture-to-notes/assets/llm_correct_srt.py" \
  "/ABSOLUTE/PATH/TO/lecture-to-notes/assets/verify_figures.py" \
  "/ABSOLUTE/PATH/TO/lecture-to-notes/assets/prepare_cover.sh" \
  "/ABSOLUTE/PATH/TO/lecture-to-notes/assets/notes-template.tex" \
  "/ABSOLUTE/PATH/TO/lecture-to-notes/assets/whisper_prompts/nju_os.txt" \
  "/ABSOLUTE/PATH/TO/lecture-to-notes/assets/whisper_prompts/glossary_nju_os.json"; do
  test -e "$helper" || { echo "Missing installed helper: $helper" >&2; exit 1; }
done
```

**CRITICAL**: Always use absolute paths for background commands (Whisper, video download).
Claude Code's shell resets the working directory between commands. Background tasks that
use relative paths will write output to the wrong location.

Recommended naming: `<course_id>_<lecture_number>_<short_title>/`
- Example: `nju_os_01_intro/`, `nju_os_02_app_view/`, `tamu_biegler_nlp/`

### Phase 1: Source Acquisition

#### 1a. Offline Platform Detection and Bilibili Part Selection

```bash
python3 "/ABSOLUTE/PATH/TO/lecture-to-notes/assets/video_source.py" detect "<URL>"
```

This detection is offline. If it prints `bilibili`, enumerate the parts before any
metadata, subtitle, audio, thumbnail, or video acquisition. This discovery command must
not use `--no-playlist`, because the playlist is the information being inspected:

```bash
yt-dlp --flat-playlist --print "%(playlist_index)s\t%(title)s" "<URL>"
```

STOP and ask the user which part(s) to process. Do not continue until the selection is
known. For each selected part, use a part-specific Bilibili URL such as
`https://www.bilibili.com/video/<BV_ID>?p=<n>`, create a separate working directory and run
the entire workflow there, and replace `<URL>` below with that part-specific URL before
the metadata probe. Process multiple selected parts as separate runs.

#### 1b. Metadata Inspection

```bash
python3 "/ABSOLUTE/PATH/TO/lecture-to-notes/assets/video_source.py" probe "<URL>" > metadata.json
```

Extract: platform, title, uploader, duration, thumbnail availability, and subtitle
languages. For X/Twitter, pass the full original `<URL>` including optional
`/video/<n>`; `/ABSOLUTE/PATH/TO/lecture-to-notes/assets/video_source.py` retains that URL and probes it with
`--no-playlist`.

#### 1c. Subtitle Acquisition (Four-Stage Fallback: Manual CC → Automatic Captions → Whisper → Visual-Only)

**Stage 1 — Manual CC subtitles:**
```bash
# YouTube
yt-dlp --no-playlist --write-subs --sub-langs "zh.*,en.*" --convert-subs srt --skip-download "<URL>"

# Bilibili
yt-dlp --no-playlist --write-subs --sub-langs "zh-Hans,zh-CN,zh,ai-zh" --convert-subs srt --skip-download "<URL>"

# X/Twitter manual caption tracks (keep the full input URL)
yt-dlp --no-playlist --write-subs --sub-langs "all,-live_chat" --convert-subs srt --skip-download -o "x_caption.%(id)s.%(ext)s" "<URL>"
```

**Stage 2 — Automatic captions** (when no manual CC):
```bash
# YouTube
yt-dlp --no-playlist --write-auto-subs --sub-langs "en" --convert-subs srt --skip-download "<URL>"
# IMPORTANT: Clean duplicates — YouTube auto-subs repeat every line 2-3x
python3 "/ABSOLUTE/PATH/TO/lecture-to-notes/assets/clean_subs.py" subs.en.srt --stats

# X/Twitter automatic caption tracks (keep the full input URL)
yt-dlp --no-playlist --write-auto-subs --sub-langs "all,-live_chat" --convert-subs srt --skip-download -o "x_caption.%(id)s.%(ext)s" "<URL>"
```

**X/Twitter caption acceptance gate (mandatory):**

After conversion, the deterministic template produces language-tagged candidates such
as `x_caption.<id>.<lang>.srt`. Enumerate every candidate and run the structural health
check with the duration extracted from `metadata.json`:

```bash
# X_CAPTION_HEALTH_BLOCK
DURATION="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["duration"])' < metadata.json)"
find . -maxdepth 1 -type f -name 'x_caption.*.srt' -print > x_caption_candidates.txt
if [ ! -s x_caption_candidates.txt ]; then
  echo "No X caption candidates; continue with Whisper fallback."
else
  while IFS= read -r srt; do
    if python3 "/ABSOLUTE/PATH/TO/lecture-to-notes/assets/check_srt_health.py" "$srt" --duration "$DURATION"; then
      echo "Structurally healthy candidate: $srt"
    else
      echo "Rejected structurally unhealthy candidate: $srt"
    fi
  done < x_caption_candidates.txt
fi
```

For every candidate reported as structurally healthy, sample that specific track against
both the audio and visible teaching content at 10%, 50%, and 90% of the runtime. Record
the three results per candidate. Select exactly one track only after all three checks
align, and persist the explicit choice:

```bash
printf '%s\n' "<one explicitly accepted x_caption path>" > selected_x_caption.txt
```

Do not select a merely structurally healthy track. If there are no candidates, or no
candidate passes all three semantic samples, use X audio → Whisper → the existing
dictionary and LLM SRT correction passes below.

External official captions may be used only when all of the following are documented:

- identity proof that the caption source and X post contain the same lecture and video variant
- constant-offset alignment using one fixed time shift, never independent per-segment shifts
- three-point audio/visual validation at 10%, 50%, and 90% after applying that offset
- provenance disclosure naming the external caption URL/provider and the applied offset

Put an external official track under the deterministic `x_caption.<id>.<lang>.srt`
naming scheme and apply the same structural and semantic gates; provenance never bypasses
validation.

**Stage 3 — Whisper speech-to-text** (when captions are absent or rejected):
```bash
yt-dlp --no-playlist -x --audio-format wav -o "audio.%(ext)s" "<URL>"
# IMPORTANT: Use absolute paths for Whisper to avoid working directory issues
# when running in background. The shell may reset cwd between commands.
# IMPORTANT: ffmpeg must be on PATH — Whisper uses it internally to read audio.
WORKDIR="$(pwd)"
whisper "$WORKDIR/audio.wav" --model small --language zh \
  --output_format srt --output_dir "$WORKDIR" --fp16 False \
  --initial_prompt "$(cat "/ABSOLUTE/PATH/TO/lecture-to-notes/assets/whisper_prompts/nju_os.txt")"  # Optional: domain glossary
```

**Whisper initial_prompt (strongly recommended for technical lectures):**
Point `--initial_prompt` at a plain-text file enumerating domain terms (syscalls, APIs,
speaker names, course-specific jargon). See
`/ABSOLUTE/PATH/TO/lecture-to-notes/assets/whisper_prompts/nju_os.txt` for a
working example. This dramatically reduces same-sound errors like
"PASSNAME" instead of "pathname" or "SAM" instead of "sum".

**Post-Whisper SRT correction passes:**
```bash
# Stage A — fast dictionary-level fix (wrong → right pairs)
python3 "/ABSOLUTE/PATH/TO/lecture-to-notes/assets/correct_srt.py" audio.srt \
    -g "/ABSOLUTE/PATH/TO/lecture-to-notes/assets/whisper_prompts/glossary_nju_os.json" --stats

# Stage B — slow LLM + multimodal fix (uses Claude Code CLI, no API key needed)
python3 "/ABSOLUTE/PATH/TO/lecture-to-notes/assets/llm_correct_srt.py" \
    --srt audio.srt --frames frames/ --out corrected.srt \
    --context "南京大学操作系统原理，讲师 jyy"
```
Stage A is essentially free and catches 80% of wrong characters. Stage B is expensive
(one Claude call per ~90s of audio) and only worth running for notes you plan to publish.

**Stage 4 — Visual-only mode** (when audio quality is unusable):
Skip subtitles. Use dense frame sampling (fps=1) and rely entirely on visual content.

#### 1d. Video and Cover Download

```bash
# Cover image (may be webp/png/jpg depending on platform)
yt-dlp --no-playlist --write-thumbnail --skip-download -o "cover" "<URL>"
# Convert to jpg for xelatex compatibility
bash "/ABSOLUTE/PATH/TO/lecture-to-notes/assets/prepare_cover.sh" .

# Video (for frame extraction)
yt-dlp --no-playlist -f "bestvideo+bestaudio/best" --merge-output-format mp4 -o "video.mp4" "<URL>"

# Bilibili 1080P+ (if user has logged in):
# yt-dlp --no-playlist --cookies-from-browser chrome -f "bestvideo+bestaudio/best" -o "video.mp4" "<URL>"
```

For every X/Twitter thumbnail, audio, and video command above, `<URL>` must be the
unchanged input URL, including an optional `/video/<n>`, and `--no-playlist` must remain
present. The same rule applies to X metadata probing as described in Phase 1b.

### Phase 2: Frame Extraction and Full-Frame Selection

Use dense extraction, contact-sheet review, and full-frame verification:

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

3. Start from `/ABSOLUTE/PATH/TO/lecture-to-notes/assets/notes-template.tex`. Fill metadata and replace the body block.

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
- [ ] Selected full-frame figure assets in `figures/`
- [ ] Compiled PDF (two-pass xelatex for TOC)
- [ ] Whisper-generated SRT file (if speech-to-text was used)
- [ ] X/Twitter SRT health result and 10% / 50% / 90% semantic samples (if X captions were used)

## Assets

- `/ABSOLUTE/PATH/TO/lecture-to-notes/assets/notes-template.tex`: LaTeX template
- `/ABSOLUTE/PATH/TO/lecture-to-notes/assets/video_source.py`: YouTube / Bilibili / X/Twitter URL detection and metadata probe
- `/ABSOLUTE/PATH/TO/lecture-to-notes/assets/check_srt_health.py`: Structural health gate for downloaded X/Twitter SRT tracks
- `/ABSOLUTE/PATH/TO/lecture-to-notes/assets/clean_subs.py`: YouTube auto-subtitle deduplication
- `/ABSOLUTE/PATH/TO/lecture-to-notes/assets/correct_srt.py`: Whisper SRT dictionary-level fix (fast, data-driven)
- `/ABSOLUTE/PATH/TO/lecture-to-notes/assets/llm_correct_srt.py`: Whisper SRT LLM + multimodal segment-level fix (slow, uses Claude Code CLI — no API key needed)
- `/ABSOLUTE/PATH/TO/lecture-to-notes/assets/verify_figures.py`: Three-way figure verification (timestamp × subtitle × frame)
- `/ABSOLUTE/PATH/TO/lecture-to-notes/assets/prepare_cover.sh`: Cover image format conversion (webp/png → jpg)
- `/ABSOLUTE/PATH/TO/lecture-to-notes/assets/smart_crop.py`: Slide-region detector; optional and experimental, while production uses full frames
- `/ABSOLUTE/PATH/TO/lecture-to-notes/assets/whisper_prompts/nju_os.txt`: Whisper `--initial_prompt` glossary example
- `/ABSOLUTE/PATH/TO/lecture-to-notes/assets/whisper_prompts/glossary_nju_os.json`: Dictionary of `wrong → right` pairs for `/ABSOLUTE/PATH/TO/lecture-to-notes/assets/correct_srt.py`
