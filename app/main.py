#!/usr/bin/env python3
"""Docker Telegram Updater - Main entry point."""

import os
import signal
import threading
import time
import sys

from config import Config
from telegram_bot import TelegramBot
from update_checker import UpdateChecker
from scheduler import Scheduler


def main():
    config = Config.from_env()

    if not config.bot_token or not config.chat_id:
        print("ERROR: BOT_TOKEN and CHAT_ID environment variables are required.")
        sys.exit(1)

    bot = TelegramBot(config)
    checker = UpdateChecker(config)
    scheduler = Scheduler(config, checker, bot)

    # Graceful shutdown
    def shutdown(sig, frame):
        print("Shutting down...")
        scheduler.stop()
        bot.stop()

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    # Start scheduler in background
    scheduler.start()

    print(f"Docker Telegram Updater started.")
    print(f"Schedule: {config.cron_schedule}")
    print(f"Excluded: {config.exclude_containers or 'none'}")

    # Start bot listener (blocking)
    bot.listen(checker, scheduler)


if __name__ == "__main__":
    main()
