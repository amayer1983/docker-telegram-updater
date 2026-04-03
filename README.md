# Docker Telegram Updater 🐳

Monitor your Docker containers for image updates and manage them directly via Telegram.

![Docker Pulls](https://img.shields.io/docker/pulls/amayer1983/docker-telegram-updater)
![Docker Image Size](https://img.shields.io/docker/image-size/amayer1983/docker-telegram-updater)
![License](https://img.shields.io/github/license/amayer1983/docker-telegram-updater)

## Features

- **Automatic update detection** — compares local and remote image digests on a configurable schedule
- **Telegram notifications** — get notified when updates are available
- **Per-container or bulk updates** — update individual containers or all at once with inline buttons
- **Self-update** — the bot can update itself via `/selfupdate` or automatically with `AUTO_SELFUPDATE=true`
- **Cleanup** — remove old unused images via `/cleanup`
- **Debug mode** — toggle detailed diagnostics via `/debug`
- **Auto-rollback** — failed updates automatically restore the previous container
- **Multi-language** — 16 languages included, switch via `/lang` or add your own JSON file
- **Optional Web UI** — dashboard with container status and settings, password-protected
- **Works with and without Docker Hub login** — credentials are optional
- **Lightweight** — Python standard library only, no extra dependencies
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

**Basic (without Docker Hub login):**

```bash
docker run -d \
  --name docker-telegram-updater \
  --restart unless-stopped \
  -e BOT_TOKEN=your-bot-token \
  -e CHAT_ID=your-chat-id \
  -v /var/run/docker.sock:/var/run/docker.sock \
  amayer1983/docker-telegram-updater:latest
```

**With Docker Hub login (recommended, avoids rate limits):**

```bash
docker run -d \
  --name docker-telegram-updater \
  --restart unless-stopped \
  -e BOT_TOKEN=your-bot-token \
  -e CHAT_ID=your-chat-id \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v /root/.docker/config.json:/.docker/config.json:ro \
  amayer1983/docker-telegram-updater:latest
```

> Run `docker login` on your host first to create the credentials file.

### Or use Docker Compose / Portainer Stack

**Without Docker Hub login:**

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
      - /var/run/docker.sock:/var/run/docker.sock
      - updater_data:/data
    security_opt:
      - no-new-privileges:true

volumes:
  updater_data:
```

**With Docker Hub login (add this line to volumes):**

```yaml
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
      - updater_data:/data
      - /root/.docker/config.json:/.docker/config.json:ro
```

## Telegram Commands

| Command | Description |
|---------|-------------|
| `/status` | Show all running containers and their status |
| `/check` | Manually trigger an update check |
| `/updates` | Show pending updates |
| `/cleanup` | Remove old unused Docker images |
| `/selfupdate` | Update the bot itself to the latest version |
| `/debug` | Toggle debug mode for detailed diagnostics |
| `/lang` | Switch language (e.g. `/lang en`, `/lang de`) |
| `/settings` | Show current configuration |
| `/help` | Show available commands |

## Update Workflow

When updates are found, you receive a message with image sizes, dates, and buttons:

```
🔄 Docker Updates Available

• nginx (nginx:latest)
  📦 141 MB | 📅 Current: 2026-03-15
• redis (redis:7)
  📦 117 MB | 📅 Current: 2026-03-20

[🔄 nginx (141 MB)]
[🔄 redis (117 MB)]
[🚀 Update all] [✋ Manual]
```

- **Individual buttons** — update a single container, button changes to ✅ when done
- **🚀 Update all** — pull and restart all containers at once
- **✋ Manual** — dismiss and handle updates yourself

The bot recreates containers with the same configuration (ports, volumes, environment, labels, networks). If an update fails, it automatically rolls back to the previous container.

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `BOT_TOKEN` | *required* | Telegram Bot API token |
| `CHAT_ID` | *required* | Your Telegram chat ID |
| `CRON_SCHEDULE` | `0 18 * * *` | Cron expression for scheduled checks |
| `EXCLUDE_CONTAINERS` | | Comma-separated container names to exclude |
| `AUTO_SELFUPDATE` | `false` | Automatically update the bot on each scheduled check |
| `LANGUAGE` | `en` | Bot language (`en`, `de`, `fr`, `es`, `it`, `nl`, `pt`, `pl`, `tr`, `ru`, `uk`, `ar`, `hi`, `ja`, `ko`, `zh`) |
| `WEB_UI` | `false` | Enable optional web dashboard |
| `WEB_PORT` | `8080` | Web UI port (inside container) |
| `WEB_PASSWORD` | | Password for Web UI (Basic Auth). Leave empty for no protection |
| `TZ` | `Europe/Berlin` | Timezone for scheduling |

### Cron Schedule Examples

| Schedule | Description |
|----------|-------------|
| `0 18 * * *` | Daily at 18:00 |
| `0 9,18 * * *` | Twice daily at 9:00 and 18:00 |
| `0 18 * * 1-5` | Weekdays at 18:00 |
| `*/30 * * * *` | Every 30 minutes |

## Docker Hub Rate Limits

| | Update checks | Image pulls |
|---|---|---|
| **Without login** | Unlimited (uses registry API) | 100 per 6 hours |
| **With login** | Unlimited | Unlimited |

Update checks use the registry API and do **not** count against pull limits. For most setups without login, the rate limit is not an issue.

To use authenticated pulls, mount your Docker credentials:

```yaml
volumes:
  - /root/.docker/config.json:/.docker/config.json:ro
```

If the credentials file doesn't exist, simply leave out this line — the bot works fine without it.

## Web UI (Optional)

Enable a lightweight web dashboard for status overview and settings:

```bash
docker run -d \
  --name docker-telegram-updater \
  -e BOT_TOKEN=your-bot-token \
  -e CHAT_ID=your-chat-id \
  -e WEB_UI=true \
  -e WEB_PASSWORD=your-secret \
  -p 8080:8080 \
  -v /var/run/docker.sock:/var/run/docker.sock \
  amayer1983/docker-telegram-updater:latest
```

The Web UI is **disabled by default** to keep the container minimal. When enabled, it provides:
- **Status page** — live container overview with health badges
- **Settings page** — change language, debug mode, and auto-selfupdate via browser
- **Update check** — trigger a check from the dashboard

Access it at `http://your-server:8080` with the configured password.

## Multi-Language

16 languages are included out of the box:

🇬🇧 English · 🇩🇪 Deutsch · 🇫🇷 Français · 🇪🇸 Español · 🇮🇹 Italiano · 🇳🇱 Nederlands · 🇧🇷 Português · 🇵🇱 Polski · 🇹🇷 Türkçe · 🇷🇺 Русский · 🇺🇦 Українська · 🇸🇦 العربية · 🇮🇳 हिन्दी · 🇯🇵 日本語 · 🇰🇷 한국어 · 🇨🇳 中文

**Switch language:**
- Via Telegram: `/lang de`, `/lang fr`, etc.
- Via Web UI: Settings page
- Via environment variable: `LANGUAGE=de`

**Add your own language:**

Create a JSON file in the `lang/` directory (e.g. `sv.json` for Swedish) with all translation keys. Use `en.json` as a template. You can mount a custom lang directory:

```yaml
volumes:
  - ./my-languages:/app/lang
```

## How it works

1. On the configured schedule, the checker compares local image digests with remote registry digests via the Docker Registry HTTP API
2. If differences are found, a Telegram notification is sent with inline action buttons for each container
3. When you press update, the bot pulls the new image, stops the old container, and recreates it with the same configuration
4. If recreation fails, the old container is automatically restored (rollback)
5. Results are reported back via Telegram

## What gets skipped

- The bot's own container (use `/selfupdate` instead)
- Containers running with image IDs instead of tags (locally built images)
- Containers in the `EXCLUDE_CONTAINERS` list

## Security

- The Docker socket is required for container management
- Only the configured `CHAT_ID` can interact with the bot
- `no-new-privileges` security option is recommended
- No external dependencies beyond Python standard library and Docker CLI
- Docker credentials are mounted read-only

## License

MIT License - see [LICENSE](LICENSE)
