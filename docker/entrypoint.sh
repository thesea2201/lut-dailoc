#!/usr/bin/env bash
set -euo pipefail

mkdir -p /app/public

/app/run_report.sh

service cron start

touch /var/log/cron.log
tail -F /var/log/cron.log &

exec nginx -g 'daemon off;'
