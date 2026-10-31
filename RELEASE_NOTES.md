# Release notes

## v1.2.0 — 2026-10-31 — CMU 15-418/618 course, NJU GSE Lectures 5–10, technical talks, and Markdown delivery gate

- **CMU 15-418/618 Parallel Computer Architecture and Programming (Spring 2018)**: Published all 27 lectures plus a 475-page unified compendium (`content/courses/cmu-15-418-2018/`, contributed by `@fengchen321` in `#41`–`#43`), covering modern multicore & SIMD/GPU architecture, parallel programming abstractions, cache coherence, memory consistency, interconnection networks, lock-free synchronization, transactional memory, and domain-specific parallel systems.
- **NJU GSE 2026 Lectures 5–10**: Added Lectures 5–10 (`content/courses/nju-gse-2026/`, `#35`–`#37`, `347a836`, `b1c6f52`) in both PDF and verified web-article (`web_source`) formats, extending the *Generative Software Engineering* course from repository management through specification, verification, DeepSeek Harness, and software evolution.
- **Technical Talks (`content/courses/technical-talks/`)**: Added Jascha Sohl-Dickstein's *Advice for a Young Investigator in the Anthropocene* (`ab20f0e`, 30 pages, 19 figures) and Lauren Tan's *How to Trust Your Coding Agents — `control-glass`, `pstack`, `Benny`, and `Dune`* (`0ecd21a`, 33 pages, 20 figures) in both PDF and verified web-article formats. The course library now spans **10 courses, 105 lecture items, 3,600 pages, 9 paper analyses, and 16 verified dual-format web articles**.
- **Markdown workflow delivery gate & workspace cleanup (`#40`, contributed by `@vo1dLee3`)**: Added `verify_notes_md.py` for `lecture-to-md` (enforcing evidence tables, numerical-claim synchronization, uncropped-frame verification, and speaker-attribution checks) and `scripts/clean_artifacts.py` for whitelist-based workspace artifact cleanup.
- **Pipeline reliability & documentation**: Downsampled review frames (`frames/*.jpg`) to `1280px` JPEG and batched multimodal image reads (`<= 6` frames per turn) to prevent session timeouts on high-resolution recordings (`cf65376`, closes `#39`); added an empty-SRT guard in `correct_srt.py` and streamlined `README.md`, `README.en.md`, and `docs/contribute.html` (`ef2199b`).

## v1.1.0 — 2026-09-16 — Online web reading documentation and NJU GSE Lecture 4

- Added NJU GSE 2026 Lecture 4 (软件仓库管理（二）) in both PDF and verified web-article formats.
- Documented the dual-format web/PDF reader, bundled PDF.js viewer, local reading-position persistence, mobile layout, and conversion verification rules in `README.md`, `README.en.md`, and `docs/development/web-reading.md`.

## v1.0.1 — 2026-09-13 — Readable slide panels for composite lecture recordings

- Re-cropped 221 composite (camera-plus-slides) figures across NJU GSE Lectures 2–3 and CMU 11-768 Lectures 1–4 using `scripts/frame_filter.py layout` so slide text renders at full column width.
- Preserved blackboard panels alongside slides where the lecture discussion references board writing, and regenerated the corresponding PDFs and `web_source` profiles.
- Updated `scripts/web_notes.py` to support multi-image figures during HTML conversion.

## v1.0.0 — 2026-09-13 — First tagged release

- End-to-end pipeline turning YouTube, Bilibili, and X/Twitter lecture videos into reader-first Chinese LaTeX notes and compiled PDFs.
- Five-stage subtitle fallback: manual CC, automatic captions (`clean_subs.py`, `check_srt_health.py`), burned-in subtitle OCR (`ocr_hardsubs.py`), local ASR (`transcribe_x_asr.py`, `transcribe_whisper.py`), and dictionary/LLM correction (`correct_srt.py`, `llm_correct_srt.py`).
- Automatic overlay and composite-panel measurement (`frame_filter.py`), numerical-claim verification (`extract_claims.py`), three-way figure checks (`verify_figures.py`), and one-shot delivery gate (`verify_notes.py`).
- Catalog-driven course library (`build_site.py`, `site_catalog.py`, `web_notes.py`) with dual-format HTML/PDF reading and containerized community PDF contribution checks (`pdf_inspector.py`).
- Semantic versioning via `VERSION`, `scripts/release_notes.py`, and automated GitHub Releases (`.github/workflows/release.yml`).
