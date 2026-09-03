---
name: volcengine-asr
description: Transcribe local audio or video with Volcengine Doubao file ASR, including BigASR 1.0 Turbo direct upload and asynchronous 1.0 standard, 1.0 idle, or 2.0 standard jobs through TOS. Use when the user asks for 火山引擎、豆包语音、录音文件识别、音视频转文字、录音稿或字幕。作为 `lecture-to-md` 的可选云端 ASR 子 skill；默认走本地 sherpa-onnx X-ASR，仅在用户明确要求云端 API 或需更高准确率时启用。
---

# Volcengine ASR（`lecture-to-md` 子 skill）

Use the deterministic scripts in `scripts/`; do not reproduce API requests manually.

> 本 skill 是 [`lecture-to-md`](../SKILL.md) 的**云端 ASR 子 skill**。日常请走 [`local-asr/`](../local-asr/SKILL.md)（sherpa-onnx X-ASR，免费、跨平台、隐私友好）；只有当用户明确要求云端准确率，或本地模型不足以应对时，才启用本 skill。

## Choose a mode

- For `turbo-v1`, run `scripts/turbo_transcribe.py`. It accepts a local audio/video file, extracts a 16 kHz mono MP3, sends Base64 in one synchronous request, and writes JSON/TXT/SRT/Markdown.
- For `standard-v1`, `idle-v1`, or `standard-v2`, first run `scripts/upload_submit.py`, then run `scripts/poll_transcript.py` with the resulting `job.json`.
- Prefer `standard-v2` when the user has opened 豆包录音文件识别模型 2.0.
- Local asynchronous inputs require TOS credentials. If a direct-download HTTP(S) URL already exists, pass `--audio-url` and skip TOS.

Read [references/api-modes.md](references/api-modes.md) before changing endpoints, resource IDs, limits, or request fields.

## Credentials

Read credentials from `.secret` in this skill directory. Never print or copy credential values into results. `.secret` must remain gitignored and mode `0600`.

The ASR v3 calls use only `VOLCENGINE_ASR_APP_ID` and `VOLCENGINE_ASR_ACCESS_TOKEN`. `VOLCENGINE_ASR_SECRET_KEY` is retained locally but not sent. TOS uses a separate account-level AK/SK, endpoint, region, and bucket.

## Commands

When `.venv` is absent, prepare the optional TOS dependency once:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

`upload_submit.py` automatically re-executes with this environment for local TOS uploads.

Turbo 1.0:

```bash
python3 scripts/turbo_transcribe.py "/absolute/path/video.mp4"
```

Submit a local 2.0 standard job through TOS:

```bash
python3 scripts/upload_submit.py \
  --mode standard-v2 \
  --input "/absolute/path/video.mp4"
```

Poll the generated job:

```bash
python3 scripts/poll_transcript.py "/absolute/path/job.json"
```

For a pre-existing direct URL:

```bash
python3 scripts/upload_submit.py \
  --mode standard-v2 \
  --audio-url "https://example.com/audio.mp3"
```

## Operating rules

- Check that the requested service is open before a paid call. Do not invent undocumented `seedasr` Turbo or idle resource IDs.
- When testing multiple modes, use different source videos so paid/free ASR time produces useful, non-duplicate transcripts.
- Keep the TOS bucket private and use only short-lived pre-signed GET URLs.
- Leave a reusable `job.json` when polling times out. Delete the TOS object only after a terminal success/failure unless the user passes `--keep-upload`.
- Report the absolute paths of `transcript.txt`, `transcript.srt`, and `result.json` after success.
