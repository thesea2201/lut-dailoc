#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CERTS_DIR="$ROOT_DIR/docker/certs"
ENV_FILE="$ROOT_DIR/.env"
ENV_EXAMPLE="$ROOT_DIR/.env.example"

if [ ! -f "$ENV_FILE" ] && [ -f "$ENV_EXAMPLE" ]; then
  cp "$ENV_EXAMPLE" "$ENV_FILE"
  echo "Created .env from .env.example. Update it with your credentials."
fi

mkdir -p "$CERTS_DIR"

if [ -z "${SERVER_NAME:-}" ]; then
  export SERVER_NAME="localhost"
fi

if command -v docker-compose >/dev/null 2>&1; then
  COMPOSE_CMD=(docker-compose -f docker-compose.dev.yml)
else
  COMPOSE_CMD=(docker compose -f docker-compose.dev.yml)
fi

"${COMPOSE_CMD[@]}" up --build -d

echo "Container started with dev override. TLS certificates live under $CERTS_DIR and will be generated on first run."
