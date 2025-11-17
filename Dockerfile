# syntax=docker/dockerfile:1
FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_HOME=/app

WORKDIR ${APP_HOME}

RUN apt-get update && apt-get install -y --no-install-recommends \
        cron \
        nginx \
        iproute2 \
        gettext-base \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY plot_baocaothuydien.py plot_tram_ainghia.py run_report.sh telegram_notifier.py ./
COPY public ./public

RUN chmod +x run_report.sh

COPY docker/cron_wrapper.sh ./docker/cron_wrapper.sh
RUN chmod +x docker/cron_wrapper.sh

COPY docker/entrypoint.sh ./docker/entrypoint.sh
RUN chmod +x docker/entrypoint.sh

RUN printf '*/30 * * * * root /app/docker/cron_wrapper.sh >> /var/log/cron.log 2>&1\n' >/etc/cron.d/report-cron \
    && chmod 0644 /etc/cron.d/report-cron \
    && crontab /etc/cron.d/report-cron

COPY docker/nginx.conf ./docker/nginx.conf
RUN mkdir -p /var/www/html && ln -sf /app/public /var/www/html/public

ENTRYPOINT ["/app/docker/entrypoint.sh"]
