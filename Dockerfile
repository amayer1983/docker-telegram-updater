FROM python:3.12-alpine

LABEL maintainer="Andreas Mayer <andreas.mayer.1983@outlook.de>"
LABEL org.opencontainers.image.source="https://github.com/amayer1983/docker-telegram-updater"
LABEL org.opencontainers.image.description="Monitor Docker containers for image updates and manage them via Telegram"

RUN apk add --no-cache docker-cli docker-cli-compose

WORKDIR /app

COPY app/ .

RUN mkdir -p /data

ENV BOT_TOKEN=""
ENV CHAT_ID=""
ENV CRON_SCHEDULE="0 18 * * *"
ENV EXCLUDE_CONTAINERS=""
ENV TZ="Europe/Berlin"
ENV PYTHONUNBUFFERED=1

VOLUME ["/data"]

HEALTHCHECK --interval=60s --timeout=10s --retries=3 \
  CMD python3 /app/healthcheck.py || exit 1

ENTRYPOINT ["python3", "/app/main.py"]
