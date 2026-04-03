# Docker Telegram Updater 🐳

Monitor your Docker containers for image updates and manage them directly via Telegram.

![Docker Pulls](https://img.shields.io/docker/pulls/amayer1983/docker-telegram-updater)
![Docker Image Size](https://img.shields.io/docker/image-size/amayer1983/docker-telegram-updater)
![License](https://img.shields.io/github/license/amayer1983/docker-telegram-updater)

## Features

- **Automatic update detection** — compares local and remote image digests on a configurable schedule
- **Telegram notifications** — get notified when updates are available, with inline buttons to update or skip
- **One-click updates** — update all containers directly from Telegram
- **Bot commands** — check status, trigger manual checks, view pending updates
- **Lightweight** — built with Python standard library, no extra dependencies
- **Docker-native** — runs as a container, manages containers via Docker socket

## Quick Start

### 1. Create a Telegram Bot

1. Message [@BotFather](https://t.me/BotFather) on Telegram
2. Send `/newbot` and follow the instructions
3. Copy the bot token

### 2. Get your Chat ID

Send a message to your bot, then open:
```
https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates
```
Look for `"chat":{"id":YOUR_CHAT_ID}` in the response.

### 3. Run the container

```bash
docker run -d \
  --name docker-telegram-updater \
  --restart unless-stopped \
  -e BOT_TOKEN=your-bot-token \
  -e CHAT_ID=your-chat-id \
  -v /var/run/docker.sock:/var/run/docker.sock:ro \
  amayer1983/docker-telegram-updater:latest
```

### Or use Docker Compose

```yaml
services:
  docker-telegram-updater:
    image: amayer1983/docker-telegram-updater:latest
    container_name: docker-telegram-updater
    restart: unless-stopped
    environment:
      - BOT_TOKEN=your-bot-token
      - CHAT_ID=your-chat-id
      - CRON_SCHEDULE=0 18 * * *
      - TZ=Europe/Berlin
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
      - updater_data:/data

volumes:
  updater_data:
```

## Telegram Commands

| Command | Description |
|---------|-------------|
| `/status` | Show all running containers and their status |
| `/check` | Manually trigger an update check |
| `/updates` | Show pending updates |
| `/help` | Show available commands |

When updates are found, you'll receive a message with two buttons:
- **🚀 Alle updaten** — Pull new images and restart containers via Docker Compose
- **✋ Manuell** — Dismiss the notification and update manually

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `BOT_TOKEN` | *required* | Telegram Bot API token |
| `CHAT_ID` | *required* | Your Telegram chat ID |
| `CRON_SCHEDULE` | `0 18 * * *` | Cron expression for scheduled checks |
| `EXCLUDE_CONTAINERS` | | Comma-separated container names to exclude |
| `TZ` | `Europe/Berlin` | Timezone for scheduling |

### Cron Schedule Examples

| Schedule | Description |
|----------|-------------|
| `0 18 * * *` | Daily at 18:00 |
| `0 9,18 * * *` | Twice daily at 9:00 and 18:00 |
| `0 18 * * 1-5` | Weekdays at 18:00 |
| `*/30 * * * *` | Every 30 minutes |

## How it works

1. On the configured schedule, the checker compares local image digests with remote registry digests
2. If differences are found, a Telegram notification is sent with inline action buttons
3. When you press "Update all", the bot pulls new images and restarts containers using `docker compose up -d`
4. Results are reported back via Telegram

## Requirements

- Docker containers managed with Docker Compose
- Docker socket access (mounted as volume)
- A Telegram Bot token and chat ID

## Docker Hub Rate Limits

Update checks use the registry API and do **not** count against Docker Hub pull limits. However, when pulling updated images, unauthenticated users are limited to 100 pulls per 6 hours.

To avoid rate limits, mount your Docker credentials into the container:

```yaml
volumes:
  - /root/.docker/config.json:/.docker/config.json:ro
```

If you haven't logged in yet, run `docker login` on your host first.

## Security

- The container needs read-only access to the Docker socket
- Only the configured `CHAT_ID` can interact with the bot
- `no-new-privileges` security option is set in the example compose file
- No external dependencies beyond Python standard library and Docker CLI

## License

MIT License - see [LICENSE](LICENSE)
