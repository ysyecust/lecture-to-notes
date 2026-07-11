# X/Twitter Video Source Support Design

## Context

`lecture-to-notes` currently treats YouTube and Bilibili as first-class video
sources. The repository is skill-driven: `skills/lecture-to-notes/SKILL.md`
defines the acquisition workflow, while small scripts provide bounded helpers.
There is no unified downloader CLI to extend.

The new support must accept X/Twitter video-post URLs, including URLs ending in
`/video/<n>`, and take them through the same metadata, subtitle, video, cover,
frame, writing, and PDF workflow. X captions are not assumed to be complete or
correct merely because `yt-dlp` returns a subtitle track.

## Goals

1. Recognize X/Twitter status URLs as a supported lecture source.
2. Probe source metadata without downloading the full video.
3. Preserve the existing YouTube and Bilibili behavior.
4. Define a reliable X subtitle decision path, including mechanical health
   checks and the existing Whisper fallback.
5. Document the exact workflow in both the public README and the installed
   skill.
6. Add offline unit coverage plus an opt-in network smoke probe.

## Non-goals

- Using the X API or adding X developer credentials.
- Supporting X Spaces, image-only posts, threads, or arbitrary social posts.
- Building a general-purpose media downloader.
- Replacing `yt-dlp` or rewriting the lecture pipeline as a monolithic CLI.
- Automatically trusting captions copied from a second publication of a video.

## Architecture

The implementation adds two small, independently testable helpers and then
updates the instruction surfaces that orchestrate them.

### 1. Source helper

Add `scripts/video_source.py` with two commands:

```text
python3 scripts/video_source.py detect <URL>
python3 scripts/video_source.py probe <URL>
```

`detect` is offline and prints one of `youtube`, `bilibili`, or `x`. It accepts:

- `youtube.com` and `youtu.be` video URLs;
- `bilibili.com/video/BV...` and `b23.tv` URLs;
- `x.com/<user>/status/<id>[/video/<n>]`;
- `twitter.com/<user>/status/<id>[/video/<n>]`.

`www` and `mobile` subdomains are normalized before matching. An X/Twitter
hostname without a status identifier is not a supported video source. Query
strings and fragments do not affect detection. Redirect-only `t.co` links are
outside the offline detector's scope. Unsupported or malformed URLs produce a
clear stderr message and exit status 2.

`probe` first performs the same offline validation, then runs the installed
`yt-dlp` with `--dump-single-json --no-playlist --skip-download`. It emits a
compact JSON record containing the detected platform, source ID, title,
uploader, duration, webpage URL, thumbnail availability, and advertised
subtitle languages. It fails before the expensive pipeline when metadata lacks
a playable video ID or a positive duration. Authentication, private-post,
region, or extractor failures remain visible; the helper must not silently
switch to an unrelated mirror.

This helper is intentionally limited to detection and metadata validation.
Actual subtitle, cover, and media commands remain explicit in the skill so the
agent can adapt cookies, formats, and fallbacks to the source.

### 2. Subtitle health helper

Add `scripts/check_srt_health.py`:

```text
python3 scripts/check_srt_health.py <SRT> --duration <seconds>
```

It parses SRT timestamps and prints a JSON health report containing entry count,
first and last timestamps, duration coverage, non-empty-window status, and exact
repetition ratio. It exits nonzero for parse errors, non-monotonic timestamps,
coverage below 90 percent, empty beginning/middle/ending windows, or excessive
exact repetition. Thresholds are named command-line options with documented
defaults so unusual lectures can be reviewed explicitly rather than patched in
code. This helper assesses structural health only; it cannot certify semantic
accuracy.

### 3. Platform-specific acquisition rules

Update `skills/lecture-to-notes/SKILL.md` as follows:

- include X/Twitter in the description, goal, dependency text, and platform
  table;
- run `video_source.py probe` before acquisition;
- use `--no-playlist` for X metadata, subtitle, thumbnail, audio, and video
  commands so a status is treated as one source;
- retain the `/video/<n>` suffix instead of normalizing it away;
- use the normal `bestvideo+bestaudio/best` merge path for the video and the
  normal thumbnail conversion path for the cover;
- describe cookie use as an error-dependent fallback, not a default.

YouTube cookie guidance and Bilibili multi-part handling remain unchanged.

### 4. X subtitle acceptance and fallback

For X, subtitle presence is not sufficient evidence of subtitle quality. The
skill will require these checks before accepting a downloaded SRT:

1. timestamps parse and remain monotonic;
2. the final subtitle reaches at least 90 percent of the video duration;
3. beginning, middle, and ending windows contain non-empty, non-repeating text;
4. samples near 10, 50, and 90 percent of the runtime agree with the audio or
   visible lecture content.

The first three checks are performed by `check_srt_health.py`; the fourth is a
required semantic sample performed during the normal multimodal review.
Mechanical checks may reject a track, but they do not claim semantic
correctness. When an X subtitle fails, the default fallback is Whisper on the X
audio, followed by the existing dictionary and optional LLM correction passes.

An official second publication may supply captions only when identity is
explicitly established using speaker/title plus visual or audio matches at
multiple points and near-equal duration. The workflow must record the source,
calculate any constant time offset, validate aligned samples near the start,
middle, and end, and state the provenance in the notes. If identity or alignment
is uncertain, use Whisper instead.

### 5. Documentation

Update `README.md` to:

- list X/Twitter alongside YouTube and Bilibili;
- show an X status URL in quick-start examples;
- explain that X caption tracks are quality-checked before use;
- update the workflow, supported-use cases, and comparison table;
- document `video_source.py detect` and `probe`, plus
  `check_srt_health.py`, in the tool overview.

No published lecture PDF or site catalog is added as part of this feature.

## Error handling

- Missing `yt-dlp`: `probe` reports the missing executable and exits nonzero.
- Unsupported URL: fail offline with exit status 2.
- X post has no playable video: fail during metadata validation.
- Private, deleted, age-gated, or region-restricted post: surface the original
  extractor error and suggest browser cookies only when applicable.
- Missing or unhealthy captions: continue through Whisper rather than silently
  switching to visual-only notes.
- Official-source alignment cannot be proven: reject the external captions and
  use the X audio.

## Testing

Add standard-library `unittest` coverage under `tests/test_video_source.py` and
`tests/test_check_srt_health.py`. Offline tests cover:

- representative YouTube, Bilibili, `x.com`, and `twitter.com` URLs;
- X `/video/1`, query-string, fragment, and mobile-share variants;
- unsupported X pages and malformed URLs;
- compact probe-record validation using mocked `yt-dlp` JSON;
- missing executable, nonzero extractor exit, missing ID, and zero duration;
- healthy SRT input plus malformed, non-monotonic, truncated, empty-window, and
  highly repetitive subtitle fixtures.

The deterministic test command is:

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
```

An opt-in live smoke check uses `probe` against a known public X video and
verifies metadata only. It is documented but not part of the default unit suite,
because public posts and extractor behavior are network-dependent.

## Success criteria

The feature is complete when:

1. all supported URL families are classified correctly offline;
2. the provided X `/video/1` URL passes a metadata-only probe without media
   download;
3. existing YouTube and Bilibili detection tests remain green;
4. README and skill instructions agree on X acquisition and subtitle fallback;
5. the unit suite passes without network access;
6. one live X metadata probe passes in the current environment;
7. no existing untracked lecture artifacts are modified or committed.
