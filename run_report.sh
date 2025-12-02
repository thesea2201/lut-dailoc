#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="$PROJECT_DIR/.env"
VENV_DIR="$PROJECT_DIR/.venv"
OUTPUT_DIR="$PROJECT_DIR/public"
HOURLY_OUTPUT="$OUTPUT_DIR/baocaothuydien_plot.png"
OVERLAY_OUTPUT="$OUTPUT_DIR/baocaothuydien_plot_overlay.png"
MOBILE_HOURLY_OUTPUT="$OUTPUT_DIR/baocaothuydien_plot_mobile.png"
MOBILE_OVERLAY_OUTPUT="$OUTPUT_DIR/baocaothuydien_plot_overlay_mobile.png"
STATIONS_JSON="$OUTPUT_DIR/stations.json"
GIT_REMOTE="${GIT_REMOTE:-origin}"
GIT_BRANCH="${GIT_BRANCH:-main}"

if [ -f "$ENV_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  . "$ENV_FILE"
  set +a
fi

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

raw_station_codes="${TRAM_STATION_CODES:-${TRAM_STATION_CODE:-553300}}"
IFS=',' read -r -a _station_code_candidates <<< "$raw_station_codes"
STATION_CODES=()
for raw_code in "${_station_code_candidates[@]}"; do
  trimmed_code="$(printf '%s' "$raw_code" | tr -d '[:space:]')"
  if [ -n "$trimmed_code" ]; then
    STATION_CODES+=("$trimmed_code")
  fi
done
if [ "${#STATION_CODES[@]}" -eq 0 ]; then
  STATION_CODES=("553300")
fi

"$PYTHON_BIN" "$PROJECT_DIR/plot_baocaothuydien.py" \
  --output "$HOURLY_OUTPUT" \
  --mobile-output "$MOBILE_HOURLY_OUTPUT" \
  --mobile-overlay-output "$MOBILE_OVERLAY_OUTPUT" \
  --cache-dir "$PROJECT_DIR/.cache" \
  --force-refresh \
  "$@"

echo "Generating station plots for: ${STATION_CODES[*]}"
first_station="${STATION_CODES[0]}"
for station_code in "${STATION_CODES[@]}"; do
  desktop_output="$OUTPUT_DIR/tram_${station_code}_plot.png"
  mobile_output="$OUTPUT_DIR/tram_${station_code}_plot_mobile.png"

  "$PYTHON_BIN" "$PROJECT_DIR/plot_tram_ainghia.py" \
    --ma-tram "$station_code" \
    --output "$desktop_output" \
    --mobile-output "$mobile_output"
done

if [ -n "$first_station" ]; then
  cp "$OUTPUT_DIR/tram_${first_station}_plot.png" "$OUTPUT_DIR/tram_ainghia_plot.png"
  cp "$OUTPUT_DIR/tram_${first_station}_plot_mobile.png" "$OUTPUT_DIR/tram_ainghia_plot_mobile.png"
fi

PYTHONPATH_VALUE="$PROJECT_DIR"
if [ -n "${PYTHONPATH:-}" ]; then
  PYTHONPATH_VALUE="$PROJECT_DIR:$PYTHONPATH"
fi

PYTHONPATH="$PYTHONPATH_VALUE" "$PYTHON_BIN" - "$STATIONS_JSON" "${STATION_CODES[@]}" <<'PY'
import json
import sys

from plot_tram_ainghia import get_station_config

output = sys.argv[1]
codes = sys.argv[2:]

payload: list[dict[str, str]] = []
seen: set[str] = set()
for code in codes:
    if code in seen:
        continue
    seen.add(code)
    config = get_station_config(code)
    payload.append(
        {
            "code": config.code,
            "label": config.label,
            "image": f"tram_{config.code}_plot.png",
            "imageMobile": f"tram_{config.code}_plot_mobile.png",
        }
    )

with open(output, "w", encoding="utf-8") as handle:
    json.dump(payload, handle, ensure_ascii=False, indent=2)
PY
