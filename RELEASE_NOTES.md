# Release notes

## 2026-09-05 — PR-time CI

- `tests.yml` runs `unit` (all Python tests) and `template` (XeLaTeX compile of
  `notes-template.tex` with every macro) on pull requests and pushes to `main`; both are
  required status checks on `main`.
- Weekly / manual jobs: `synthetic-video` renders a deterministic lecture video with
  burned-in subtitles, a static navigation strip, and a presenter block, then runs the
  real `ocr_hardsubs.py` and `frame_filter.py` pipeline against it; `macos-smoke` runs the
  suite on Apple silicon and checks that `transcribe_whisper.py` selects mlx-whisper.
- Tests that need optional tools (xelatex, ffmpeg, rapidocr, a CJK font, numpy/Pillow)
  skip instead of failing when the tool is absent.

## 2026-09-04 — Hard-sub OCR, budgeted transcription, overlay-aware figures, one-shot gate

Driven by a 160-minute DeepSeek Harness run on a 61-minute Bilibili lecture (session
`session-18d94bd5`): 62 minutes were spent waiting on a CPU Whisper that never finished,
half of 12.9M input tokens went to hand-written post-compile checks, and 13 of 44 figures
were presenter-only or subtitle-covered frames because the model could not see images.

### Highlights

- `scripts/transcribe_whisper.py` picks the transcription backend per platform (`mlx-whisper` on
  Apple silicon, `faster-whisper` elsewhere, `openai-whisper` last), moves model caches
  into the workdir when `~/.cache` is not writable, and exits 3 when no segment appears
  within `--budget-minutes` so the agent switches instead of waiting.
- `scripts/ocr_hardsubs.py` detects burned-in subtitles, OCRs the band into `hardsub_ocr.srt`
  (≈2 s per video minute measured), reports overlay geometry (`bands.json`), and derives a
  Whisper correction glossary by aligning the two tracks (刻石→刻蚀, 光眼膜→光掩膜).
- `scripts/frame_filter.py` measures and crops the navigation strip and subtitle band and
  scores frames so hosts without image input can reject presenter-only frames.
- `scripts/extract_claims.py` builds `numerical_claims.tsv` from subtitle and OCR tracks and
  checks every number against `notes.tex`, tolerant of LaTeX spacing and unit macros.
- `scripts/verify_notes.py` replaces the inline density script with one gate covering
  density, mandatory artifacts, the compile log, figure files, and same-page footnotes.
- `notes-template.tex` defines `\vtag`, `\srcnote`, `\degC`, `\um`, `\nm`, and `\angstrom`.
- `scripts/install_skill.sh` installs the skill into `~/.agents/skills` (DeepSeek Harness /
  Codex agents), `~/.claude/skills`, or `~/.codex/skills`; SKILL.md now starts with an
  installation check that stops on a missing helper and records whether the host can
  show images.

### Compatibility

- No breaking changes to existing helpers; the new scripts are additive and SKILL.md
  still accepts `\protect\footnotemark` / `\footnotetext` figure provenance.

## 2026-08-31

- Published Stanford CS336 Spring 2026 as a complete 18-lecture Chinese course, with a
  Lecture 4–18 bundle and official course materials.
- Added Stanford CS336 Spring 2025 Lectures 4–8 and NJU Generative Software Engineering
  2026 Lecture 1 to the course library.
- Added an optional sherpa-onnx X ASR backend for fast local Chinese/English transcription,
  with bounded chunks, token-timestamp SRT generation, health gates, tests, and a reproducible
  CPU benchmark. Whisper remains the fallback.
- Merged the reader-first writing workflow from PR #13 so density requirements adapt to
  technical, conceptual, and mixed lectures without inventing figures or equations.

## 2026-07-16 — Course library, dedicated PDF reader, and community inbox

### Highlights

- The website is now a catalog-driven course library with search, course spines,
  one visual tick per PDF, responsive course detail views, and a dedicated reader.
- The initial catalog contains 6 courses, 34 PDFs, 588 pages, and 9 paper notes.
  Stanford CS336: Language Modeling from Scratch (Spring 2026) now includes
  separate notes for lectures 1–3 and a 94-page combined edition.
- Existing public PDF URLs remain available while source assets now live beside
  trusted course manifests under `content/courses/`.
- The reader resolves only catalog item IDs and keeps direct-open, download, and
  source links available when an embedded browser preview is unavailable.

### PDF contribution workflow

- Contributors can add lowercase PDF files directly under `content/inbox/` in a
  fork and open a pull request using the repository template.
- The contribution page and template now explain the permission boundary directly:
  contributors commit in their own fork, a pull request does not grant write access,
  and maintainers alone decide what enters `main` and is published.
- Pull-request automation compares the complete base and submitted trees, permits
  PDF additions only, and runs the trusted scanner as an unprivileged container
  without network access. It checks structure and active content, then extracts a
  title, page count, SHA-256 digest, and WebP first-page preview.
- Unmerged pull-request content is never deployed. GitHub Pages builds only from
  trusted `main`, with every third-party action pinned to a full commit SHA.
- The 25 MiB per-file, 10-PDF, and 100 MiB per-PR bounds are an external
  contribution scanning envelope, not a limit on the course library.

### Verification evidence

- All 34 published PDFs passed the containerized `qpdf` structural check; the
  combined CS336 edition has a non-fatal object-count repair warning.
- The deterministic site build produced 6 courses, 34 PDFs, 588 pages, and 9 paper
  notes with 34 WebP previews.
- Desktop Chromium and an iPhone 14 viewport passed catalog search, focused course
  routing, reader allowlisting, PDF fallback-link, and contribution-entry tests.
- Static Python coverage includes catalog, build, contribution policy, workflow
  security, frontend CSP, DOM-safety, responsive design, and release contracts.

## 2026-07-16 — Minimal XeTeX fallback

- Lecture-note compilation now checks required LaTeX packages explicitly and falls
  back to native CJK line breaking when `ctex` is unavailable. Contribution:
  [@liyuankui](https://github.com/liyuankui) in
  [PR #4](https://github.com/ysyecust/lecture-to-notes/pull/4).
- Verification covered the complete `ctex` path and a restricted Debian XeTeX
  environment with `ctex.sty` intentionally absent.

## 2026-07-11 — X/Twitter lecture video support

### Highlights

- X/Twitter status URLs on `x.com` and `twitter.com` are now first-class video sources, including the optional `/video/<n>` suffix.
- `scripts/video_source.py` detects supported platforms and provides a metadata-only probe. The probe uses `--no-playlist` and skip-download behavior, so it does not create media files.
- `scripts/check_srt_health.py` validates SRT structure, coverage, repetition, and runtime-window evidence. A manual semantic check at 10%, 50%, and 90% of the video remains mandatory.
- Missing or unhealthy captions fall back to audio extraction, Whisper transcription, and the existing SRT-correction workflow.
- Installed-skill commands resolve tools from the skill asset path and work in a fresh shell. Existing Bilibili multipart selection is preserved.

### New commands and tools

```bash
python3 scripts/video_source.py detect "https://x.com/vicky_grok/status/2075594420163092606/video/1"
python3 scripts/video_source.py probe "https://x.com/vicky_grok/status/2075594420163092606/video/1"
python3 scripts/check_srt_health.py path/to/subtitles.srt --duration 5342.805
```

The first command prints the platform. The second emits compact JSON metadata without downloading media. The third reports structural subtitle health before the required semantic sampling gate.

### Upgrade and install

Re-copy the skill and its complete `assets/` directory using the Codex or Claude Code installation commands in the README's **Quick start** section. Start a fresh shell before validating the installed workflow.

### Compatibility

No breaking changes. YouTube and Bilibili workflows are retained, including Bilibili multipart selection; backward compatibility is retained.

### Verification evidence

- Python byte-compilation passed for `scripts/video_source.py` and `scripts/check_srt_health.py`.
- The complete `unittest` discovery passed all 38 tests.
- Detection returned `x` for the target status URL and `youtube` for a YouTube sample URL.
- The live metadata-only probe exited successfully with platform `x`, media ID `2075592697562456064`, duration `5342.805` seconds, and no created media files.
- The completed subtitle reported `healthy: true`, coverage `1.0`, all start/middle/end windows `true`, and 2,020 entries at that live-probe duration.
