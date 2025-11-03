#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="/app/.env"

if [ -f "$ENV_FILE" ]; then
  # shellcheck disable=SC1090
  set -a
  . "$ENV_FILE"
  set +a
fi

exec /app/run_report.sh "$@"
