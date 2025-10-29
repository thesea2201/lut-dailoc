#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$PROJECT_DIR/.venv"
OUTPUT_DIR="$PROJECT_DIR/public"
HOURLY_OUTPUT="$OUTPUT_DIR/baocaothuydien_plot.png"
OVERLAY_OUTPUT="$OUTPUT_DIR/baocaothuydien_plot_overlay.png"
GIT_REMOTE="${GIT_REMOTE:-origin}"
GIT_BRANCH="${GIT_BRANCH:-main}"

mkdir -p "$OUTPUT_DIR"

if [ -d "$VENV_DIR" ]; then
  PYTHON_BIN="${PYTHON_BIN:-$VENV_DIR/bin/python}"
else
  PYTHON_BIN="${PYTHON_BIN:-python3}"
fi

if command -v git >/dev/null 2>&1; then
  echo "Updating repository from $GIT_REMOTE/$GIT_BRANCH..."
  git -C "$PROJECT_DIR" fetch "$GIT_REMOTE" "$GIT_BRANCH"
  git -C "$PROJECT_DIR" pull --ff-only "$GIT_REMOTE" "$GIT_BRANCH"
fi

"$PYTHON_BIN" "$PROJECT_DIR/plot_baocaothuydien.py" \
  --output "$HOURLY_OUTPUT" \
  --cache-dir "$PROJECT_DIR/.cache" \
  --force-refresh \
  "$@"
