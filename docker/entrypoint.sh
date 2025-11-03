#!/usr/bin/env bash
set -euo pipefail

mkdir -p /app/public

SERVER_NAME=${SERVER_NAME:-thuydien.thebien.net}
SSL_CERT_PATH=${SSL_CERT_PATH:-/etc/nginx/certs/fullchain.pem}
SSL_KEY_PATH=${SSL_KEY_PATH:-/etc/nginx/certs/privkey.pem}
export SERVER_NAME SSL_CERT_PATH SSL_KEY_PATH

mkdir -p "$(dirname "$SSL_CERT_PATH")" "$(dirname "$SSL_KEY_PATH")"

if [ ! -f "$SSL_CERT_PATH" ] || [ ! -f "$SSL_KEY_PATH" ]; then
  echo "Generating self-signed certificate for $SERVER_NAME" >&2
  openssl req -x509 -nodes -newkey rsa:2048 \
    -keyout "$SSL_KEY_PATH" \
    -out "$SSL_CERT_PATH" \
    -days 365 \
    -subj "/CN=${SERVER_NAME}"
fi

envsubst '${SERVER_NAME} ${SSL_CERT_PATH} ${SSL_KEY_PATH}' < /app/docker/nginx.conf > /etc/nginx/sites-available/default

/app/run_report.sh

service cron start

touch /var/log/cron.log
tail -F /var/log/cron.log &

exec nginx -g 'daemon off;'
