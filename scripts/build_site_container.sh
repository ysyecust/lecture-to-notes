#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUTPUT="${1:-$ROOT/_site}"
STAGING="$ROOT/.tmp/site-build"

rm -rf "$OUTPUT" "$STAGING"
mkdir -p "$STAGING"
docker build -f "$ROOT/ci/pdf-sandbox.Dockerfile" \
  -t lecture-to-notes-pdf-sandbox "$ROOT"
docker run --rm --network none --read-only --cap-drop ALL \
  --security-opt no-new-privileges --memory 1g --cpus 2 --pids-limit 256 \
  --tmpfs /tmp:rw,size=256m \
  -v "$ROOT:/input:ro" -v "$STAGING:/output:rw" \
  --entrypoint python3 lecture-to-notes-pdf-sandbox -m scripts.build_site \
  --root /input --output /output/site --generated-at 2026-07-16T00:00:00Z
mv "$STAGING/site" "$OUTPUT"
