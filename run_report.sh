#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$PROJECT_DIR/.venv"
OUTPUT_DIR="$PROJECT_DIR/public"
HOURLY_OUTPUT="$OUTPUT_DIR/baocaothuydien_plot.png"
OVERLAY_OUTPUT="$OUTPUT_DIR/baocaothuydien_plot_overlay.png"
MOBILE_HOURLY_OUTPUT="$OUTPUT_DIR/baocaothuydien_plot_mobile.png"
MOBILE_OVERLAY_OUTPUT="$OUTPUT_DIR/baocaothuydien_plot_overlay_mobile.png"
TRAM_OUTPUT="$OUTPUT_DIR/tram_ainghia_plot.png"
TRAM_OUTPUT_MOBILE="$OUTPUT_DIR/tram_ainghia_plot_mobile.png"
GIT_REMOTE="${GIT_REMOTE:-origin}"
GIT_BRANCH="${GIT_BRANCH:-main}"

mkdir -p "$OUTPUT_DIR"

if [ -d "$VENV_DIR" ]; then
  PYTHON_BIN="${PYTHON_BIN:-$VENV_DIR/bin/python}"
else
  DEFAULT_PYTHON="${PYTHON_BIN:-/usr/local/bin/python}";
  if [ ! -x "$DEFAULT_PYTHON" ]; then
    DEFAULT_PYTHON="$(command -v python3 2>/dev/null || echo python3)"
  fi
  PYTHON_BIN="$DEFAULT_PYTHON"
fi

if command -v git >/dev/null 2>&1 && git -C "$PROJECT_DIR" rev-parse --git-dir >/dev/null 2>&1; then
  echo "Updating repository from $GIT_REMOTE/$GIT_BRANCH..."
  git -C "$PROJECT_DIR" fetch "$GIT_REMOTE" "$GIT_BRANCH"
  git -C "$PROJECT_DIR" pull --ff-only "$GIT_REMOTE" "$GIT_BRANCH"
fi

timestamp="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
echo "[$timestamp] Running report using $PYTHON_BIN" >> "$PROJECT_DIR/run_report.log"

"$PYTHON_BIN" "$PROJECT_DIR/plot_baocaothuydien.py" \
  --output "$HOURLY_OUTPUT" \
  --mobile-output "$MOBILE_HOURLY_OUTPUT" \
  --mobile-overlay-output "$MOBILE_OVERLAY_OUTPUT" \
  --cache-dir "$PROJECT_DIR/.cache" \
  --force-refresh \
  "$@"

"$PYTHON_BIN" "$PROJECT_DIR/plot_tram_ainghia.py" \
  --output "$TRAM_OUTPUT" \
  --mobile-output "$TRAM_OUTPUT_MOBILE"
