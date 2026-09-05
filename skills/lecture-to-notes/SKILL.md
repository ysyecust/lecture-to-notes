---
name: lecture-to-notes
description: Use when users provide YouTube, Bilibili, or X/Twitter lecture URLs and want reader-first Chinese LaTeX/PDF notes with source-faithful claims, fluent authored prose, and verified teaching figures, especially requests phrased as lecture notes, 视频转PDF, 课程笔记, 讲义, YouTube笔记, B站笔记, X/Twitter lecture notes, or BV号; do not produce transcript dumps, quota-padded prose, or screenshot galleries.
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
| `ffprobe` | Always | Duration and frame height (ships with ffmpeg) |
| `pdftotext` | Always | Rendered-page checks in `verify_notes.py` (poppler) |
| `python3` | Always | Installed helper scripts and local ASR support |
| `sherpa-onnx` + X ASR model | Optional zh/en ASR | Fast local Chinese/English transcription with token timestamps |
| Whisper backend | ASR fallback / non-zh-en / no-CC | `transcribe_whisper.py` picks `mlx-whisper` (macOS arm64) → `faster-whisper` → `openai-whisper` |
| `rapidocr-onnxruntime` | Bilibili / any burned-in subtitles | `ocr_hardsubs.py` reads the subtitle band and overlay geometry |
| `Pillow` + `numpy` | Always | `frame_filter.py` overlay crop and talking-head scores |

Install the Python side with `pip install rapidocr-onnxruntime Pillow numpy` plus one
transcription backend: `pip install mlx-whisper` on Apple silicon, otherwise
`pip install faster-whisper` (or `openai-whisper` as the slowest fallback).
`/ABSOLUTE/PATH/TO/lecture-to-notes/assets/smart_crop.py` remains an optional experiment.

### LaTeX package check (do NOT skip — `which xelatex` alone is insufficient)

`which xelatex` passing does **not** mean the required LaTeX packages are installed.
On minimal TeX installs (e.g. MacTeX Basic, TeX Live `scheme-basic`), the binary exists
but `ctex`, `tcolorbox`, and other packages are missing. This causes silent failures:
long Chinese lines overflow `\textwidth` (no CJK line breaking) or compilation aborts
with `File '...' not found`.

Check required packages before starting:

```bash
MISSING=0
for pkg in ctex tcolorbox environ trimspaces listings hyperref booktabs float subcaption etoolbox; do
  if ! kpsewhich "$pkg.sty" >/dev/null 2>&1; then
    echo "❌ Missing LaTeX package: $pkg"
    MISSING=1
  fi
done
if [ "$MISSING" -ne 0 ]; then
  echo "Install missing packages:"
  echo "  tlmgr install ctex tcolorbox environ trimspaces etoolbox"
  echo "Or install full TeX distribution:"
  echo "  macOS:  https://www.tug.org/mactex/  (~4 GB, includes everything)"
  echo "  Linux:  sudo apt install texlive-full"
fi
```

If `ctex` cannot be installed (e.g. due to `l3kernel` version conflicts on minimal installs),
the `notes-template.tex` includes a fallback that uses XeTeX's built-in CJK line breaking
(`\XeTeXlinebreaklocale "zh"`) with system fonts — no `ctex` or `xeCJK` needed.

## YouTube Cookie Notice

YouTube may require authentication to avoid bot detection. When `yt-dlp` fails with "Sign in to confirm you're not a bot", add `--cookies-from-browser chrome` (or `safari`/`firefox`/`edge`) to all `yt-dlp` commands.

## Goal

Produce a professional Chinese lecture note from a YouTube, Bilibili, or X/Twitter video URL. The output must:

- use the video's actual teaching content, not just subtitle transcription
- place the video's original cover image on the front page
- include selected full-frame teaching figures chosen by contact-sheet review
- let a capable first-time reader understand the question, mechanism, evidence, consequence, and boundary without decoding the transcript
- achieve source-fit information density — every figure, box, formula, and paragraph earns its space
- be structurally organized with `\section{}` / `\subsection{}`
- end with a synthesis section combining speaker's conclusions and your own distillation
- be a complete `.tex` from `\documentclass` to `\end{document}`
- compile successfully to PDF

## Non-negotiable quality bar (Codex / production mode)

**STOP and do not claim completion** unless every item below is true. Skeleton outlines,
image-heavy PDFs with thin prose, or missing intermediate artifacts are automatic failures.

### Mandatory workdir artifacts (must exist on disk before saying "done")

| File | Required content |
|------|------------------|
| `metadata.json` | From `video_source.py probe` (or equivalent full dump) |
| `audio.srt` | Final subtitle track used for writing (manual CC, cleaned auto, hard-sub OCR, X ASR, or Whisper) |
| `audio_corrected.srt` | Copy of final track, or glossary/LLM-corrected track when local ASR was used |
| `hardsub_ocr.srt` | `ocr_hardsubs.py extract` output when `ocr_hardsubs.py detect` reported burned-in subtitles; absent otherwise |
| `bands.json` | Overlay geometry (navigation strip, subtitle band) from `ocr_hardsubs.py detect --geometry` or `frame_filter.py bands` |
| `cover.jpg` | Front-page cover |
| `video.mp4` | Source for frames (may omit only if user forbids download and provides frames) |
| `frames/` | Dense sample, default 1 frame / 15s |
| `frame_scores.json` | `frame_filter.py score` over the dense sample; mandatory when the host cannot show you images |
| `figures/` | Selected full-frame figure assets with **semantic names** (`fig_01_topic.jpg`, …), overlays cropped via `bands.json` |
| `figure_manifest.tsv` | Header `figure\tframe\tstart\tend\ttopic` — one row per figure |
| `figure_verification.txt` | Full stdout of `verify_figures.py` over **all** manifest timestamps |
| `lecture_profile.json` | Reader and source-fit profile; required fields are described below |
| `teaching_atoms.tsv` | Header `atom\tstatus\tevidence` — every teaching atom mapped to the notes |
| `numerical_claims.tsv` | Generated by `extract_claims.py extract`, filled by `extract_claims.py check --write`; header-only is valid when the lecture contains no numerical claims |
| `notes.tex` | Complete Chinese lecture notes |
| `notes.pdf` | Two-pass `xelatex` output |
| `verify_notes.txt` | Full stdout of `verify_notes.py`, ending in `OVERALL PASS` |

### Source-fit profile and reader contract (hard)

After subtitle correction and contact-sheet review, create `lecture_profile.json` before
outlining the notes:

```json
{
  "mode": "technical-slide",
  "audience": "capable first-time reader",
  "central_question": "What should the reader be able to explain after reading?",
  "reader_outcome": "A concrete capability, decision, or mental model",
  "visual_teaching_atoms": 24,
  "formula_teaching_atoms": 18
}
```

Choose exactly one mode:

- `technical-slide`: slides, board work, formulas, code, or diagrams carry most teaching content;
- `conceptual-talk`: a talk, interview, or discussion carries most content through claims,
  examples, and reasoning rather than visual mechanisms;
- `mixed`: both modes contribute substantial teaching content.

Count `visual_teaching_atoms` and `formula_teaching_atoms` from the source, not from the
draft. A visual atom is a distinct source visual that helps teach a point. A formula atom
is a source equation or derivation worth preserving. Do not inflate these counts to justify
more assets, and do not classify a conceptual talk as technical merely to trigger quotas.

For every mode, the hard gates are source fidelity, complete teaching-atom coverage,
traceable numerical claims, clear source attribution, and a coherent reader path. The
numeric density gates below are source-fit backstops. They never authorize invented
equations, low-value talking-head screenshots, repetitive boxes, or synonym padding.

### Density and structure gates (source-adaptive)

For a lecture of duration $T$ minutes (from metadata):

**Gate vs target (do not confuse):** the numbers below are **hard gates** (fail = no delivery).
A high-quality Codex-class note often lands ~25–40% above the CJK gate; that is a **target**,
not a second hard floor. Raising the hard floor to the measured gold value encourages
padding, not more teaching atoms. (Validated on CS336 L3: $T\approx 89$ → gate CJK 6246 /
figs 25; gold ~8035 CJK / 27 figs / 31 pages.)

1. **Chinese character count** in the `notes.tex` body (CJK unified ideographs only):
   - `technical-slide`: at least $\max(5000,\ \mathrm{round}(70\times T))$;
   - `mixed`: at least $\max(3500,\ \mathrm{round}(55\times T))$;
   - `conceptual-talk`: at least $\max(2500,\ \mathrm{round}(45\times T))$.
   Do not count English jargon, LaTeX commands, or captions alone. These are completeness
   floors, not invitations to repeat the same idea.
2. **Figures**: include every distinct visual teaching atom that materially improves
   understanding, up to the technical target $\max(20,\ \mathrm{round}(T/3.5))$. A
   `conceptual-talk` with four real visual atoms should contain four verified figures, not
   twenty talking-head frames. A slide-led lecture with thirty distinct mechanisms must not
   stop at twenty.
3. **Sections** for $T\ge 60$: use at least 8 for `technical-slide`, 6 for `mixed`, and 5
   for `conceptual-talk`, unless fewer reader questions produce a demonstrably clearer
   structure. Each major section answers one reader question and ends with
   `\subsection{本章小结}` that states the answer and prepares the next question.
4. **Judgment boxes**: use boxes only when they separate a definition, background dependency,
   decision rule, or failure boundary from the main flow. The technical default is 12 for
   $T\ge60$; `mixed` and `conceptual-talk` have no box quota. Never split continuous reasoning
   into boxes merely to raise a count.
5. **Teaching atom shape** (adapt, do not stamp out a template):
   - state what the reader needs to understand and why it matters;
   - explain the mechanism or reasoning in the order needed to follow it;
   - attach source evidence: a number, example, quotation-level paraphrase, formula, code,
     table, or verified figure as appropriate;
   - state the consequence or boundary when it changes interpretation.
   Use only the components that the source and the reader need. After every display formula
   with at least two symbols, add an immediate symbol explanation list.
6. **No outline-only sections.** If a 5-minute span of the lecture introduces a distinct
   mechanism, number, or design choice, it must appear as its own subsection or a clearly
   labeled paragraph with evidence — not a bullet in a summary list.
7. **Coverage audit before compile (timeline):** walk the timeline in 3–5 minute steps using the SRT;
   list any gap without corresponding prose or figure; fill gaps before `xelatex`.
8. **Teaching-atom checklist (topic coverage, hard for technical lectures):**
   Before delivery, extract a **lecture-specific atom list** from SRT + slides (15–40 atoms).
   Each atom must map to a subsection, a labeled paragraph, or a figure+caption in `notes.tex`.
   Missing atoms → expand prose; do **not** “pass” on CJK alone.
   Example atoms for an LLM-architecture lecture: Pre/Post-Norm, LN vs RMSNorm,
   FLOPs≠runtime, SwiGLU, serial vs parallel block, RoPE, FFN ratio, head dim, width/depth,
   vocab size, dropout vs weight decay, z-loss, QK-Norm, Prefill vs Decode, MQA/GQA,
   sliding window / interleaved / hybrid attention.
   Persist the checklist as `teaching_atoms.tsv` (`atom\tstatus\tevidence`).

9. **Mechanism density (hard — L2 gold comparison 2026-07-12):** CJK/fig/box gates alone are
   **not enough**. CS336 L2 first Grok pass: 5463 CJK / 8 formulas / 0 code (gate PASS, gold incomplete);
   after claim-driven补全: ~6450 CJK / 31 formulas / 3 code / 33 pages (matches Codex). Also require:
   - **Display math**: for source formula atoms, preserve at least
     $\min(N_{\mathrm{formula\ atoms}},\ \max(10,\ \mathrm{round}(T/4)))$ blocks
     (`\[ ... \]` or `equation`), each with an immediate symbol `itemize` when ≥2 symbols
     appear. If the source has no formula atoms, the correct count is zero; never invent
     equations to satisfy a density gate.
   - **Numerical claims file** `numerical_claims.tsv` (header `claim\tvalue\tsource_time\tin_notes`):
     before writing, generate it from the subtitle track plus every OCR track — the script,
     not the writer, decides which numbers exist in the source:
     `python3 "/ABSOLUTE/PATH/TO/lecture-to-notes/assets/extract_claims.py" extract audio.srt --ocr hardsub_ocr.srt --out numerical_claims.tsv`.
     Add rows by hand only for numbers the regex cannot see (e.g. `6PT`, `12 bytes/param`,
     `I_*=295`, `53.3B`, peak TFLOP/s, bandwidth). After writing, run
     `python3 "/ABSOLUTE/PATH/TO/lecture-to-notes/assets/extract_claims.py" check numerical_claims.tsv notes.tex --write`;
     every row must be `in_notes=yes`. Topic-only atoms without numbers still FAIL
     if the lecture stated a number.
   - **Code**: if slides/SRT show ≥1 non-trivial code fragment (einops, timing, AMP, …), notes must
     include ≥1 `lstlisting` (or equivalent verbatim) with the **same mechanism**, not a prose paraphrase only.
   - **Comparison tables**: if the lecture contrasts ≥3 formats/ops/modes (e.g. FP32/FP16/BF16/FP8),
     include a compact `tabular` — do not leave it only as prose.
   - **Per-section floor** (for `technical-slide` with $T\ge 60$): each major `\section` except title/appendix must have
     ≥ $\max(300,\ \mathrm{round}(0.7\times \mathrm{CJK}/N_{\mathrm{sec}}))$ Chinese chars **and**
     at least one of: display formula, table, code block, or ≥2 judgment boxes.
     A section that is only “术语澄清 + 小结” is FAIL.
   - **Fine-grained subsections**: for each 5–8 min teaching span that introduces a distinct mechanism,
     prefer a dedicated `\subsection` (Codex L2: 42 subs vs thin notes ~35). Merging is OK only if
     the merged subsection still contains **all numbers and derivations** from both spans.

10. **Write from evidence and a reader map, not from transcript order:**
    Order of work after frames/manifest:
    (a) build `numerical_claims.tsv` + `teaching_atoms.tsv` + `lecture_profile.json`;
    (b) write one-line answers for the central question and each planned section question;
    (c) draft a section outline keyed to those answers and the source evidence;
    (d) write prose that **discharges every claim** in a reader-comprehensible order;
    (e) run the reader-first revision passes in the Phase 3 reference;
    (f) run source-fit density, formula, claim, compilation, and rendered-page gates.

### Forbidden shortcuts

- Stopping after a “skeleton PDF” that only titles topics and pastes slides.
- Writing captions from section titles without reading the full-resolution frame.
- Claiming high density without measuring CJK character count against the gate above.
- Omitting `figure_manifest.tsv` / `figure_verification.txt` “because figures look fine”.
- Merging unrelated teaching points to reduce page count.
- Padding CJK with repeated slogans or synonym paraphrases that add no mechanism, formula, or decision rule.
- Treating the **target** (~Codex measured density) as a second **hard gate** and stuffing filler to hit it.
- Inventing formulas, examples, causal links, or certainty that the source does not support.
- Adding low-information screenshots, boxes, or micro-sections only to satisfy a numeric quota.
- Preserving oral repetition, self-correction, filler transitions, or Q&A order when they obstruct the teaching argument.
- Giving every paragraph the same claim-list-summary rhythm; density without sentence and paragraph flow still fails.
- **Summary-only mechanism sections**: describing Roofline / MFU / $6BP$ / checkpointing in words while
  omitting the lecture’s actual formulas, critical constants, and worked numerical examples.
- Marking a teaching atom `ok` because a **topic word** appears, when the lecture’s **number or derivation** is absent.

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

### Step 0 — Installation and host capability check (STOP on failure)

Resolve the absolute assets directory from the loaded SKILL.md before running helpers.
Then substitute that literal directory for `/ABSOLUTE/PATH/TO/lecture-to-notes/assets`
everywhere below before executing a command. Each fenced command may run in a fresh shell,
so never rely on a path variable defined by an earlier command.

Run this loop before any download. If it prints `Missing installed helper`, STOP and tell
the user to reinstall the skill with `install_skill.sh` from the repository; do not
improvise replacements for the missing helper, and do not fall back to another skill.

```bash
for helper in \
  "/ABSOLUTE/PATH/TO/lecture-to-notes/assets/video_source.py" \
  "/ABSOLUTE/PATH/TO/lecture-to-notes/assets/check_srt_health.py" \
  "/ABSOLUTE/PATH/TO/lecture-to-notes/assets/clean_subs.py" \
  "/ABSOLUTE/PATH/TO/lecture-to-notes/assets/transcribe_x_asr.py" \
  "/ABSOLUTE/PATH/TO/lecture-to-notes/assets/correct_srt.py" \
  "/ABSOLUTE/PATH/TO/lecture-to-notes/assets/llm_correct_srt.py" \
  "/ABSOLUTE/PATH/TO/lecture-to-notes/assets/verify_figures.py" \
  "/ABSOLUTE/PATH/TO/lecture-to-notes/assets/transcribe_whisper.py" \
  "/ABSOLUTE/PATH/TO/lecture-to-notes/assets/ocr_hardsubs.py" \
  "/ABSOLUTE/PATH/TO/lecture-to-notes/assets/frame_filter.py" \
  "/ABSOLUTE/PATH/TO/lecture-to-notes/assets/extract_claims.py" \
  "/ABSOLUTE/PATH/TO/lecture-to-notes/assets/verify_notes.py" \
  "/ABSOLUTE/PATH/TO/lecture-to-notes/assets/prepare_cover.sh" \
  "/ABSOLUTE/PATH/TO/lecture-to-notes/assets/notes-template.tex" \
  "/ABSOLUTE/PATH/TO/lecture-to-notes/assets/whisper_prompts/nju_os.txt" \
  "/ABSOLUTE/PATH/TO/lecture-to-notes/assets/whisper_prompts/glossary_nju_os.json"; do
  test -e "$helper" || { echo "Missing installed helper: $helper" >&2; exit 1; }
done
```

**Host image input.** Try to read one image (the cover, once downloaded, or any PNG) with
the host's image-reading tool. If the host or model refuses (`does not declare image
input`, "cannot read as an image"), record `"vision": "no"` in `lecture_profile.json` and
follow every "host without image input" rule below; otherwise record `"vision": "yes"`.
Never write a caption as if you had seen a frame you could not open.

**CRITICAL**: Always use absolute paths for background commands (local ASR, video download).
Claude Code's shell resets the working directory between commands. Background tasks that
use relative paths will write output to the wrong location.

Recommended naming: `<course_id>_<lecture_number>_<short_title>/`
- Example: `nju_os_01_intro/`, `nju_os_02_app_view/`, `tamu_biegler_nlp/`

### Context hygiene (keep the transcript out of the prompt)

A 60-minute lecture is ~35k characters of subtitles; reading it whole into the
conversation, then re-reading it on every later request, was the largest avoidable token
cost measured on 2026-09-03 (transcript and OCR dumps of ~60k characters stayed resident for
70 requests). Rules:

- Write `transcript_indexed.txt` (one `[HH:MM:SS] text` line per entry) once, then read only
  the window for the section being written (`sed -n` by line range or a timestamp filter).
- Keep OCR output in files (`hardsub_ocr.srt`, `frame_scores.json`) and query them with
  `grep`/`python3` for the timestamps you need; never print a whole OCR digest.
- Never glob the whole workspace (`**/*lecture*` and similar); operate inside the working
  directory created for this lecture.
- Background jobs: poll with a bounded wait and read only the tail of their output; when a
  job has produced no output for the budget in `transcribe_whisper.py`, treat it as failed and
  switch backends instead of waiting again.

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

#### 1c. Subtitle Acquisition (Five-Stage Fallback: Manual CC → Automatic Captions → Burned-in Subtitle OCR → Local ASR → Visual-Only)

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
  echo "No X caption candidates; continue with local ASR fallback."
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
candidate passes all three semantic samples, use X audio → local ASR → the existing
dictionary and LLM SRT correction passes below.

External official captions may be used only when all of the following are documented:

- identity proof that the caption source and X post contain the same lecture and video variant
- constant-offset alignment using one fixed time shift, never independent per-segment shifts
- three-point audio/visual validation at 10%, 50%, and 90% after applying that offset
- provenance disclosure naming the external caption URL/provider and the applied offset

Put an external official track under the deterministic `x_caption.<id>.<lang>.srt`
naming scheme and apply the same structural and semantic gates; provenance never bypasses
validation.

**Stage 3a — Burned-in subtitles** (when captions are absent or rejected; needs `video.mp4`
from Phase 1d, so run that download first):

Bilibili uploads very often carry subtitles burned into the picture. Reading that band
with OCR is faster than any speech-to-text and spells every term the way the speaker's
editor did, so check before transcribing:

```bash
python3 "/ABSOLUTE/PATH/TO/lecture-to-notes/assets/ocr_hardsubs.py" detect video.mp4 --geometry bands.json
# has_hardsubs=true → OCR the whole band (measured ≈ 2 s per video minute on Apple silicon)
python3 "/ABSOLUTE/PATH/TO/lecture-to-notes/assets/ocr_hardsubs.py" extract video.mp4 --out hardsub_ocr.srt --fps 1
RUNTIME="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["duration"])' < metadata.json)"
python3 "/ABSOLUTE/PATH/TO/lecture-to-notes/assets/check_srt_health.py" hardsub_ocr.srt --duration "$RUNTIME"
```

`bands.json` also records the navigation strip and subtitle band for Phase 2 cropping.
When `hardsub_ocr.srt` passes the health check and a 10% / 50% / 90% spot-check against the
audio, copy it to `audio.srt` and skip local ASR. When it is partial (subtitles only in some
chapters), still keep it: Stage A below turns it into a correction glossary for the ASR track.

**Stage 3b — Local speech-to-text** (no captions and no usable hard subs):

For Chinese, English, or mixed zh/en lectures, prefer the local X ASR INT8 model when it
is already available or can be cached once. It is substantially faster on CPU and returns
token timestamps, but it is not trusted merely because it completed. Preserve the raw SRT,
run `check_srt_health.py`, and compare audio/visible content at 10%, 50%, and 90%. If X ASR
is unavailable or any gate fails, use Whisper. Use Whisper directly for languages outside
the selected X ASR model's documented scope.

The tested model is the official sherpa-onnx release asset
`sherpa-onnx-x-asr-zipformer-transducer-zh-en-punct-int8-2026-06-03.tar.bz2`
(SHA-256 `5d02c36d7b44e886b7c8f0d8e051f8713acab96c264bb6ef9e718be39a6a2224`).
Keep downloaded models outside Git. Install the optional runtime with
`python3 -m pip install "numpy>=1.24" "sherpa-onnx>=1.13.6"`, extract the model, then run:

```bash
yt-dlp --no-playlist -x --audio-format wav -o "audio.%(ext)s" "<URL>"
python3 "/ABSOLUTE/PATH/TO/lecture-to-notes/assets/transcribe_x_asr.py" audio.wav \
  --model-dir "/ABSOLUTE/PATH/TO/CACHED/X-ASR-MODEL" \
  --output audio.srt --report x_asr_report.json
python3 "/ABSOLUTE/PATH/TO/lecture-to-notes/assets/check_srt_health.py" \
  audio.srt --duration "<VIDEO_DURATION_SECONDS>"
```

The offline X ASR encoder requires bounded chunks. The helper normalizes audio with
ffmpeg, selects low-energy boundaries, keeps every chunk at or below 30 seconds, and
turns token timestamps into non-overlapping SRT cues. Do not pass a whole long lecture
directly to the model.

**Whisper fallback** (X ASR unavailable, a gate failed, or the language is out of scope):
```bash
yt-dlp --no-playlist -x --audio-format wav -o "audio.%(ext)s" "<URL>"
# IMPORTANT: Use absolute paths — the shell may reset cwd between commands.
# IMPORTANT: ffmpeg must be on PATH — every Whisper backend reads audio through it.
WORKDIR="$(pwd)"
python3 "/ABSOLUTE/PATH/TO/lecture-to-notes/assets/transcribe_whisper.py" "$WORKDIR/audio.wav" \
  --workdir "$WORKDIR" --language zh --budget-minutes 10 \
  --initial-prompt "/ABSOLUTE/PATH/TO/lecture-to-notes/assets/whisper_prompts/nju_os.txt"  # Optional: domain glossary
```

`transcribe_whisper.py` selects the backend (`mlx-whisper` on Apple silicon, `faster-whisper`
elsewhere, `openai-whisper` last), moves model caches under the workdir when `~/.cache` is
not writable (sandboxed hosts), streams progress, and **exits 3 when no segment has appeared
within `--budget-minutes`**. Exit 3 means switch `--backend` or use a smaller `--model`;
never wait past the budget for a silent process, and never run the bare `whisper` CLI in
the background without this budget. Measured 2026-09-03 on the same 61-minute audio:
CPU `whisper --model medium` produced nothing in 85 minutes; `mlx-whisper`
`large-v3-turbo` finished in 6 minutes.

**Whisper initial_prompt (strongly recommended for technical lectures):**
Point `--initial_prompt` at a plain-text file enumerating domain terms (syscalls, APIs,
speaker names, course-specific jargon). See
`/ABSOLUTE/PATH/TO/lecture-to-notes/assets/whisper_prompts/nju_os.txt` for a
working example. This dramatically reduces same-sound errors like
"PASSNAME" instead of "pathname" or "SAM" instead of "sum".

**Post-ASR SRT correction passes:**
```bash
# Stage A0 — derive the glossary from the video itself when hard subs exist (even partial)
python3 "/ABSOLUTE/PATH/TO/lecture-to-notes/assets/ocr_hardsubs.py" glossary hardsub_ocr.srt audio.srt \
    --out glossary_auto.json --min-count 2
# Review glossary_auto.json: keep term corrections (刻石→刻蚀, 光眼膜→光掩膜), delete
# pairs that only reflect OCR noise, then apply it with Stage A.

# Stage A — fast dictionary-level fix (wrong → right pairs)
python3 "/ABSOLUTE/PATH/TO/lecture-to-notes/assets/correct_srt.py" audio.srt \
    -g glossary_auto.json -o audio_corrected.srt --stats
# Course glossaries still apply, e.g.
# -g "/ABSOLUTE/PATH/TO/lecture-to-notes/assets/whisper_prompts/glossary_nju_os.json"

# Stage B — slow LLM + multimodal fix (uses Claude Code CLI, no API key needed)
python3 "/ABSOLUTE/PATH/TO/lecture-to-notes/assets/llm_correct_srt.py" \
    --srt audio.srt --frames frames/ --out corrected.srt \
    --context "南京大学操作系统原理，讲师 jyy"
```
Stage A is essentially free and catches common wrong characters. Stage B is expensive
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

#### Stage 2: Frame selection (no automatic cropping of slide content)

Use the original full frames directly. Do NOT apply automatic cropping to slide or board
content — heuristic region cropping is unreliable (misidentifies blackboard content as
"low information" regions). The one permitted crop removes overlays measured from the
video itself — the burned-in subtitle band and the static navigation strip in `bands.json`
— so a subtitle line never sits on top of a diagram in the PDF:

```bash
# bands.json comes from Phase 1 Stage 3a; without it, measure from the dense sample:
python3 "/ABSOLUTE/PATH/TO/lecture-to-notes/assets/frame_filter.py" bands frames/*.png --json bands.json
# Apply to every selected figure (never to contact sheets):
python3 "/ABSOLUTE/PATH/TO/lecture-to-notes/assets/frame_filter.py" crop frames/ch2_031.png \
    --out figures/fig_07_cz_diagram.jpg --bands bands.json
```

**Host without image input (mandatory fallback):** when Step 0 recorded `"vision": "no"`,
contact-sheet review is impossible, so text signals decide:

1. Score the dense sample: `python3 "/ABSOLUTE/PATH/TO/lecture-to-notes/assets/frame_filter.py" score frames/*.png --json frame_scores.json`.
2. Never select a frame flagged `talking_head`; the 2026-09-03 run shipped three presenter-only
   frames as "figures" because nothing rejected them.
3. Read on-screen text for candidates with OCR (`ocr_hardsubs.py extract video.mp4 --band 0:1 --fps 0.2 --out screen_text.srt`)
   and select only frames whose OCR text names a labelled diagram, formula, table, or
   process, not merely the subtitle line.
4. Write captions from that OCR text plus the subtitle at the timestamp, and say so in
   `figure_manifest.tsv` (`topic` column ends with `[ocr]`).

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
   With `"vision": "no"`, substitute the OCR text of that frame (Stage 2 fallback) and
   never describe visual elements the OCR did not report.

4. **Three-way match check**: Verify that ALL THREE align:
   - ✅ Frame visual content (what the slide/screen actually shows)
   - ✅ Subtitle content (what the speaker is saying at that moment)
   - ✅ Your caption + surrounding text (what you plan to write)

   If any mismatch: either pick a different frame, adjust the timestamp, or rewrite the caption.

5. **Persist audit artifacts (mandatory):**
   - Append every accepted figure to `figure_manifest.tsv` with columns
     `figure`, `frame`, `start`, `end`, `topic` (topic in Chinese, concrete).
   - Run `verify_figures.py` on **all** `start` times and save full stdout to
     `figure_verification.txt`. Do not delete these files after compile.

**Common failure modes to watch for:**

| Failure | Example | Fix |
|---------|---------|-----|
| Frame shows slide A, caption describes slide B | Frame shows "Language" section but caption says "Transformer" | Read frame at full res before writing caption |
| Timestamp off by 1-2 minutes | @07:00 claimed but actual content is at @09:00 | Cross-check with subtitle timestamps |
| Caption describes the section topic, not the frame | "Scaling Law 幂律关系" but frame shows a chess board | Write caption from frame content, not section title |
| Frame is transitional (between slides) | Half old slide, half new slide | Pick a frame 15s earlier or later |
| Too few figures / outline-only notes | 15 figures + 3k CJK chars for an 86-min lecture | Enforce density gates in "Non-negotiable quality bar" |

### Phase 3: Writing

#### Reader-first prose reference (mandatory)

Read [references/reader-first-writing.md](references/reader-first-writing.md) after the
final subtitle track, teaching atoms, numerical claims, and verified figures are ready.
Use it to build the reader argument map, draft the notes, and run the final prose passes.
The reference is self-contained; using this skill must not depend on another installed
writing skill or a network call.

#### Teaching Content Rules

**Include:** title, chapters, on-screen diagrams/formulas/tables/code, subtitle explanations, speaker emphasis.

**Exclude:** greetings, small talk, sponsorship, channel logistics, 一键三连, 关注投币, closing pleasantries.

**Preserve:** speaker's closing discussion when it carries teaching value (synthesis, limitations, advice, open questions).

#### Writing Rules

1. **Chinese by default** unless the user requests otherwise. Write authored teaching prose,
   not line-edited subtitles.

2. Organize with `\section{}` / `\subsection{}` around reader questions and prerequisites.
   Reconstruct the teaching flow; do not mirror subtitle or Q&A order.

3. Before outlining, complete `lecture_profile.json` and write one-line answers for the
   central question, reader outcome, and each planned section question.

4. Start from `/ABSOLUTE/PATH/TO/lecture-to-notes/assets/notes-template.tex`. Fill metadata and replace the body block.

5. **Front page cover**: use the video's original cover image, visually distinct from in-body figures.

6. **Source voice**: distinguish established background, the speaker's claim or forecast,
   and the note writer's synthesis. Preserve uncertainty and qualifiers; do not silently
   strengthen a claim while translating or compressing it.

7. **Paragraph flow**: give each paragraph one main job. Lead with the answer or mechanism,
   place evidence next to the point it supports, and end with the consequence or boundary.
   Do not force every paragraph into the same template.

8. **Terminology**: introduce plain meaning before acronyms, stage labels, variants, or
   project-specific terms. Keep one stable term for one concept.

9. **Figures: use full frames.** Use each distinct visual teaching atom that materially
   improves understanding. **Every figure MUST pass the Stage 4 three-way verification
   before being written into LaTeX.** Never write a caption from section context alone.

10. **No figures inside boxes.** `importantbox`, `knowledgebox`, `warningbox` must not contain `\includegraphics`.

11. **Math**: use display math only for a source formula or a faithful derivation needed to
    explain it. Follow each display with an immediate symbol explanation list when at least
    two symbols appear. Never invent an equation to make conceptual material look technical.

12. **Code**: wrap source-grounded code in `lstlisting` with a descriptive `caption`.

13. **Box strategy** — use boxes only when they improve the teaching signal:
   - `importantbox`: core concepts, definitions, key mechanisms, theorem-like statements
   - `knowledgebox`: background, history, design tradeoffs, terminology, analogies
   - `warningbox`: common mistakes, hidden assumptions, pitfalls, causal confusions

14. Every major `\section` ends with `\subsection{本章小结}`. Answer the section's reader
    question and create a natural handoff; do not repeat its subsection list. Add
    `\subsection{拓展阅读}` only when the source or verified external material supports it.

15. Final section `\section{总结与延伸}`:
    - Speaker's substantive closing (no sign-off fluff)
    - Your structured distillation of core claims and mechanisms
    - Cross-section synthesis, conceptual compression
    - Concrete takeaways, open questions, next steps

16. No `[cite]` placeholders, invented citations, or unattributed external facts.

#### Figure Time Provenance

Every figure from a video frame must have a same-page footnote with the source time interval:

```latex
\begin{figure}[H]
\centering
\includegraphics[width=\textwidth]{figures/fig_xxx.png}
\caption{描述\vtag}
\end{figure}
\srcnote{00:12:31--00:12:46}
```

- `\vtag` and `\srcnote` are defined in the template (they expand to
  `\protect\footnotemark` / `\footnotetext{视频画面时间区间：…}`); `verify_notes.py` accepts both spellings.
- Time intervals come from subtitle alignment, not chapter-level guesses.
- Use `[H]` or stable placement to keep figure and footnote on the same page.
- Units: write `1150\,\degC`, `20--50\,\um`, `14\,\nm`, `5.43\,\angstrom` with the template
  macros. Hand-written `$^\circ$\mathrm{C}$` and `\mathrm{\AA}` produced an error cascade and
  seven `invalid in math mode` warnings on 2026-09-03; `verify_notes.py` fails on those warnings.

#### Visualization

For concepts that screenshots and prose can't explain clearly, add visualizations:
- LaTeX-native: TikZ / PGFPlots
- Pre-generated: Python matplotlib scripts

Use for: process flows, architecture layouts, scaling-law plots, comparison charts. No decorative graphics.

### Phase 4: Compilation, Reader-First Gate, Density Gate, and Delivery

```bash
xelatex -interaction=nonstopmode notes.tex && xelatex -interaction=nonstopmode notes.tex
```

#### Pre-delivery gate (one command; run and report its output)

```bash
python3 "/ABSOLUTE/PATH/TO/lecture-to-notes/assets/extract_claims.py" check numerical_claims.tsv notes.tex --write
python3 "/ABSOLUTE/PATH/TO/lecture-to-notes/assets/verify_notes.py" --workdir . --overfull-pt 10 | tee verify_notes.txt
```

`verify_notes.py` runs every mechanical check in one pass and prints one `PASS`/`FAIL`
line each, ending with `OVERALL PASS` or `OVERALL FAIL`:

- **density** — `lecture_profile.json` mode and atom counts against `metadata.json`
  duration: CJK, figure, section, box, and display-math floors; `teaching_atoms.tsv`
  all `ok`; `numerical_claims.tsv` all `in_notes=yes`;
- **artifacts** — `figure_manifest.tsv`, `figure_verification.txt`, `audio.srt` non-empty;
- **compile log** — no `!` errors, no `Missing character`, no undefined references, no
  `invalid in math mode`, no `Overfull \hbox` above the threshold;
- **figures** — every `\includegraphics` file exists, every video frame has a time
  footnote, and (via `pdftotext`) the footnote renders on the same page as its caption.

If it prints `OVERALL FAIL`, fix the named item and rerun. Do not add formulas, figures,
boxes, or prose that the source and reader do not need, and do not re-implement any of
these checks by hand: on 2026-09-03 the ad-hoc equivalents took 31 requests and half of the
run's input tokens.

#### Reader-first prose check (manual and mandatory)

After the two-pass compile:

1. Extract the rendered text with `pdftotext notes.pdf rendered_notes.txt` when available.
2. Read the opening, every section opening, every `本章小结`, all figure/table captions,
   and the final synthesis in sequence.
3. Run the seven revision passes and final checklist in
   [references/reader-first-writing.md](references/reader-first-writing.md).
4. Verify that each strong claim is traceable, each speaker opinion is attributed where
   needed, terms appear after plain meanings, and adjacent paragraphs hand off naturally.
5. Inspect the final diff after prose revision to ensure no number, qualifier, timestamp,
   label, or claim boundary changed accidentally.

Phrase searches may identify candidates such as repeated “值得注意的是” or
“不是……而是……”; they cannot pass or fail the prose by themselves. A clean compile and
high density counts do not compensate for transcript-like, repetitive, or inflated prose.

#### Delivery Checklist

- [ ] `notes.tex` + two-pass `notes.pdf`
- [ ] `verify_notes.txt` ends with `OVERALL PASS`
- [ ] `bands.json` present; every selected figure was cropped through it when the video has overlays
- [ ] `frame_scores.json` present and no selected figure flagged `talking_head` (hosts without image input)
- [ ] `cover.jpg`
- [ ] `figures/` with semantic names; count passes density gate
- [ ] `figure_manifest.tsv` and `figure_verification.txt` present and non-empty
- [ ] `lecture_profile.json` records mode, audience, central question, reader outcome, and source atom counts
- [ ] `teaching_atoms.tsv` maps every teaching atom to concrete evidence in the notes
- [ ] `audio.srt` (and `audio_corrected.srt` when correction was applied or as a copy of the final track)
- [ ] CJK character count reported and ≥ the source-fit gate for the selected lecture mode
- [ ] Figure, box, section, and display-math counts satisfy the mode and source atom profile
- [ ] Every source-backed display formula with ≥2 symbols has an immediate symbol list
- [ ] `numerical_claims.tsv` complete (`in_notes=yes` for every row; header-only if no numerical claims)
- [ ] Code/table present when lecture showed code or multi-way format comparisons
- [ ] Timeline coverage audit done (no multi-minute teaching gaps without prose)
- [ ] Teaching-atom checklist reviewed (`teaching_atoms.tsv`; atoms require numbers when lecture had numbers)
- [ ] Reader-first prose reference applied; extracted rendered text reread through all seven passes
- [ ] Speaker claims, established background, and note-writer synthesis remain distinguishable
- [ ] No oral debris, repeated paragraph template, invented equation, unsupported causal link, or quota filler remains
- [ ] Raw ASR SRT and backend report retained if speech-to-text was used
- [ ] Local ASR SRT health result and 10% / 50% / 90% semantic samples recorded
- [ ] X/Twitter SRT health result and 10% / 50% / 90% semantic samples (if X captions were used)
- [ ] Absolute paths of PDF and workdir listed for the user

## Assets

- `/ABSOLUTE/PATH/TO/lecture-to-notes/assets/notes-template.tex`: LaTeX template
- `/ABSOLUTE/PATH/TO/lecture-to-notes/assets/video_source.py`: YouTube / Bilibili / X/Twitter URL detection and metadata probe
- `/ABSOLUTE/PATH/TO/lecture-to-notes/assets/check_srt_health.py`: Structural health gate for downloaded X/Twitter SRT tracks
- `/ABSOLUTE/PATH/TO/lecture-to-notes/assets/clean_subs.py`: YouTube auto-subtitle deduplication
- `/ABSOLUTE/PATH/TO/lecture-to-notes/assets/transcribe_x_asr.py`: optional local X ASR zh/en transcription with bounded chunks and SRT timestamps
- `/ABSOLUTE/PATH/TO/lecture-to-notes/assets/correct_srt.py`: Whisper SRT dictionary-level fix (fast, data-driven)
- `/ABSOLUTE/PATH/TO/lecture-to-notes/assets/llm_correct_srt.py`: Whisper SRT LLM + multimodal segment-level fix (slow, uses Claude Code CLI — no API key needed)
- `/ABSOLUTE/PATH/TO/lecture-to-notes/assets/verify_figures.py`: Three-way figure verification (timestamp × subtitle × frame)
- `/ABSOLUTE/PATH/TO/lecture-to-notes/assets/transcribe_whisper.py`: Whisper with platform-aware backend selection (mlx / faster / openai), workdir model caches, and a no-progress time budget
- `/ABSOLUTE/PATH/TO/lecture-to-notes/assets/ocr_hardsubs.py`: Burned-in subtitle detection, band OCR to SRT, overlay geometry, and Whisper glossary derivation
- `/ABSOLUTE/PATH/TO/lecture-to-notes/assets/frame_filter.py`: Overlay band measurement and crop, plus talking-head scores for hosts without image input
- `/ABSOLUTE/PATH/TO/lecture-to-notes/assets/extract_claims.py`: Builds `numerical_claims.tsv` from subtitle/OCR tracks and checks every number against `notes.tex`
- `/ABSOLUTE/PATH/TO/lecture-to-notes/assets/verify_notes.py`: One-shot pre-delivery gate (density, artifacts, compile log, figure files, same-page footnotes)
- `/ABSOLUTE/PATH/TO/lecture-to-notes/assets/prepare_cover.sh`: Cover image format conversion (webp/png → jpg)
- `/ABSOLUTE/PATH/TO/lecture-to-notes/assets/smart_crop.py`: Slide-region detector; optional and experimental, while production uses full frames
- `/ABSOLUTE/PATH/TO/lecture-to-notes/assets/whisper_prompts/nju_os.txt`: Whisper `--initial_prompt` glossary example
- `/ABSOLUTE/PATH/TO/lecture-to-notes/assets/whisper_prompts/glossary_nju_os.json`: Dictionary of `wrong → right` pairs for `/ABSOLUTE/PATH/TO/lecture-to-notes/assets/correct_srt.py`
