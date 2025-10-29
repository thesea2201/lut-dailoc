# syntax=docker/dockerfile:1
FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_HOME=/app

WORKDIR ${APP_HOME}

RUN apt-get update && apt-get install -y --no-install-recommends \
        cron \
        nginx \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY plot_baocaothuydien.py run_report.sh ./
COPY public ./public

RUN chmod +x run_report.sh

RUN printf '*/15 * * * * /app/run_report.sh >> /var/log/cron.log 2>&1\n' >/etc/cron.d/report-cron \
    && crontab /etc/cron.d/report-cron

COPY docker/nginx.conf /etc/nginx/sites-available/default
RUN mkdir -p /var/www/html && ln -sf /app/public /var/www/html/public

CMD service cron start && \
    /app/run_report.sh && \
    nginx -g 'daemon off;'
