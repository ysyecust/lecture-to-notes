# Release notes

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
