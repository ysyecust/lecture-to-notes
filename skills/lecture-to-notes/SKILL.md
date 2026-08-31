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
| `python3` | Always | Installed helper scripts and local ASR support |
| `sherpa-onnx` + X ASR model | Optional zh/en ASR | Fast local Chinese/English transcription with token timestamps |
| `whisper` | ASR fallback / non-zh-en / no-CC | Speech-to-text fallback (openai-whisper) |

Additional Python dependencies: `Pillow` (`pip install Pillow`) only for the optional
`/ABSOLUTE/PATH/TO/lecture-to-notes/assets/smart_crop.py` experiment.

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
| `audio.srt` | Final subtitle track used for writing (manual CC, cleaned auto, X ASR, or Whisper) |
| `audio_corrected.srt` | Copy of final track, or LLM/dictionary-corrected track when local ASR was used |
| `cover.jpg` | Front-page cover |
| `video.mp4` | Source for frames (may omit only if user forbids download and provides frames) |
| `frames/` | Dense sample, default 1 frame / 15s |
| `figures/` | Selected full-frame figure assets with **semantic names** (`fig_01_topic.jpg`, …) |
| `figure_manifest.tsv` | Header `figure\tframe\tstart\tend\ttopic` — one row per figure |
| `figure_verification.txt` | Full stdout of `verify_figures.py` over **all** manifest timestamps |
| `lecture_profile.json` | Reader and source-fit profile; required fields are described below |
| `teaching_atoms.tsv` | Header `atom\tstatus\tevidence` — every teaching atom mapped to the notes |
| `numerical_claims.tsv` | Header `claim\tvalue\tsource_time\tin_notes`; header-only is valid when the lecture contains no numerical claims |
| `notes.tex` | Complete Chinese lecture notes |
| `notes.pdf` | Two-pass `xelatex` output |

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
     before writing, extract every concrete number/formula from SRT+selected frames
     (e.g. `6PT`, `12 bytes/param`, `I_*=295`, `144 days`, `53.3B`, peak TFLOP/s, bandwidth).
     After writing, every row must be `in_notes=yes`. Topic-only atoms without numbers still FAIL
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
  "/ABSOLUTE/PATH/TO/lecture-to-notes/assets/transcribe_x_asr.py" \
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

**CRITICAL**: Always use absolute paths for background commands (local ASR, video download).
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

#### 1c. Subtitle Acquisition (Four-Stage Fallback: Manual CC → Automatic Captions → Local ASR → Visual-Only)

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

**Stage 3 — Local speech-to-text** (when captions are absent or rejected):

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

**Whisper fallback:**
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

**Post-ASR SRT correction passes:**
```bash
# Stage A — fast dictionary-level fix (wrong → right pairs)
python3 "/ABSOLUTE/PATH/TO/lecture-to-notes/assets/correct_srt.py" audio.srt \
    -g "/ABSOLUTE/PATH/TO/lecture-to-notes/assets/whisper_prompts/glossary_nju_os.json" --stats

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

### Phase 4: Compilation, Reader-First Gate, Density Gate, and Delivery

```bash
xelatex -interaction=nonstopmode notes.tex && xelatex -interaction=nonstopmode notes.tex
```

#### Pre-delivery density check (run and report numbers)

```bash
python3 - <<'PY'
from pathlib import Path
import re, json
tex = Path("notes.tex").read_text(encoding="utf-8")
cn = sum(1 for c in tex if "\u4e00" <= c <= "\u9fff")
figs = len([p for p in Path("figures").glob("*") if p.is_file()])
secs = len(re.findall(r"\\section\{", tex))
boxes = len(re.findall(r"\\begin\{(important|knowledge|warning|practice)box\}", tex))
maths = len(re.findall(r"\\\[|\\begin\{equation", tex))
codes = len(re.findall(r"\\begin\{lstlisting\}", tex))
tables = len(re.findall(r"\\begin\{tabular", tex))
print(f"CJK_chars={cn} figures={figs} sections={secs} boxes={boxes} display_math={maths} code={codes} tables={tables}")
meta = json.loads(Path("metadata.json").read_text()) if Path("metadata.json").exists() else {}
T = float(meta.get("duration") or 0) / 60.0
profile_path = Path("lecture_profile.json")
if not profile_path.exists():
    raise SystemExit("FAIL — lecture_profile.json missing")
profile = json.loads(profile_path.read_text(encoding="utf-8"))
mode = profile.get("mode")
if mode not in {"technical-slide", "conceptual-talk", "mixed"}:
    raise SystemExit(f"FAIL — invalid lecture mode: {mode!r}")
for key in ("audience", "central_question", "reader_outcome", "visual_teaching_atoms", "formula_teaching_atoms"):
    if key not in profile:
        raise SystemExit(f"FAIL — lecture_profile.json missing field: {key}")
visual_atoms = int(profile["visual_teaching_atoms"])
formula_atoms = int(profile["formula_teaching_atoms"])
if visual_atoms < 0 or formula_atoms < 0:
    raise SystemExit("FAIL — teaching atom counts must be non-negative")
if mode == "technical-slide":
    need_cn = max(5000, round(70 * T)) if T else 5000
    need_sec = 8 if T >= 60 else 1
    need_box = 12 if T >= 60 else 6
elif mode == "mixed":
    need_cn = max(3500, round(55 * T)) if T else 3500
    need_sec = 6 if T >= 60 else 1
    need_box = 0
else:
    need_cn = max(2500, round(45 * T)) if T else 2500
    need_sec = 5 if T >= 60 else 1
    need_box = 0
figure_target = max(20, round(T / 3.5)) if T else 20
need_fig = min(visual_atoms, figure_target)
math_target = max(10, round(T / 4)) if T else 10
need_math = min(formula_atoms, math_target)
print(f"mode={mode} duration_min={T:.1f} need_CJK>={need_cn} need_figures>={need_fig} need_sections>={need_sec} need_boxes>={need_box} need_math>={need_math}")
ok = cn >= need_cn and figs >= need_fig and secs >= need_sec and boxes >= need_box and maths >= need_math
print("PASS" if ok else "FAIL — fill source-backed teaching gaps; never pad prose, formulas, boxes, or figures")
atoms = Path("teaching_atoms.tsv")
if atoms.exists():
    rows = [r for r in atoms.read_text().splitlines()[1:] if r.strip()]
    missing = [r for r in rows if len(r.split("\t")) < 2 or r.split("\t")[1] != "ok"]
    print(f"teaching_atoms total={len(rows)} missing={len(missing)}")
    if missing:
        print("FAIL — teaching atom gaps remain"); ok = False
else:
    print("FAIL — teaching_atoms.tsv missing"); ok = False
claims = Path("numerical_claims.tsv")
if claims.exists():
    rows = [r for r in claims.read_text().splitlines()[1:] if r.strip()]
    miss = [r for r in rows if "yes" not in r.split("\t")[-1].lower()]
    print(f"numerical_claims total={len(rows)} missing_in_notes={len(miss)}")
    if miss:
        print("FAIL — numerical claims not discharged:"); ok = False
        for r in miss[:12]:
            print(" ", r)
else:
    print("FAIL — numerical_claims.tsv missing"); ok = False
print("OVERALL", "PASS" if ok else "FAIL")
PY
test -s figure_manifest.tsv && test -s figure_verification.txt && test -s audio.srt
```

If the script prints `FAIL`, fill the missing source-backed teaching atoms and rerun it.
Do not add formulas, figures, boxes, or prose that the source and reader do not need.

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
- `/ABSOLUTE/PATH/TO/lecture-to-notes/assets/prepare_cover.sh`: Cover image format conversion (webp/png → jpg)
- `/ABSOLUTE/PATH/TO/lecture-to-notes/assets/smart_crop.py`: Slide-region detector; optional and experimental, while production uses full frames
- `/ABSOLUTE/PATH/TO/lecture-to-notes/assets/whisper_prompts/nju_os.txt`: Whisper `--initial_prompt` glossary example
- `/ABSOLUTE/PATH/TO/lecture-to-notes/assets/whisper_prompts/glossary_nju_os.json`: Dictionary of `wrong → right` pairs for `/ABSOLUTE/PATH/TO/lecture-to-notes/assets/correct_srt.py`
