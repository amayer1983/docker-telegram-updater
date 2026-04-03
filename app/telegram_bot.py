#!/usr/bin/env python3
"""Telegram Bot - handles messages, callbacks, and notifications."""

import json
import subprocess
import os
import sys
import threading
import urllib.request
import urllib.parse


class TelegramBot:
    def __init__(self, config):
        self.config = config
        self.running = True
        self.update_running = False

    def stop(self):
        self.running = False

    def api_call(self, method, data=None):
        url = f"https://api.telegram.org/bot{self.config.bot_token}/{method}"
        if data:
            req = urllib.request.Request(
                url,
                data=urllib.parse.urlencode(data).encode(),
                method="POST"
            )
        else:
            req = urllib.request.Request(url)
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read())
        except Exception as e:
            print(f"Telegram API error: {e}")
            return None

    def send_message(self, text, reply_markup=None):
        data = {
            "chat_id": self.config.chat_id,
            "text": text,
            "parse_mode": "Markdown",
            "disable_web_page_preview": "true"
        }
        if reply_markup:
            data["reply_markup"] = json.dumps(reply_markup)
        return self.api_call("sendMessage", data)

    def answer_callback(self, callback_id, text):
        self.api_call("answerCallbackQuery", {
            "callback_query_id": callback_id,
            "text": text
        })

    def remove_buttons(self, chat_id, message_id):
        self.api_call("editMessageReplyMarkup", {
            "chat_id": chat_id,
            "message_id": message_id,
            "reply_markup": json.dumps({"inline_keyboard": []})
        })

    def _remove_single_button(self, chat_id, message_id, callback_data):
        """Mark clicked button as done, keep remaining buttons."""
        keyboard = self._rebuild_keyboard_without(callback_data)
        self.api_call("editMessageReplyMarkup", {
            "chat_id": chat_id,
            "message_id": message_id,
            "reply_markup": json.dumps(keyboard)
        })

    def _rebuild_keyboard_without(self, callback_data):
        """Rebuild keyboard marking the clicked container as done."""
        if not os.path.exists(self.config.pending_file):
            return {"inline_keyboard": []}

        with open(self.config.pending_file) as f:
            updates = json.load(f)

        keyboard = []
        for u in updates:
            btn_data = f"update_one:{u['name']}"
            if btn_data == callback_data:
                keyboard.append([{"text": f"✅ {u['name']}", "callback_data": "noop"}])
            else:
                keyboard.append([{"text": f"🔄 {u['name']}", "callback_data": btn_data}])

        remaining = [u for u in updates if f"update_one:{u['name']}" != callback_data]
        if remaining:
            keyboard.append([
                {"text": "🚀 Alle updaten", "callback_data": "update_all"},
                {"text": "✋ Manuell", "callback_data": "update_skip"}
            ])

        return {"inline_keyboard": keyboard}

    def _run_single_update(self, checker, container_name):
        """Update a single container."""
        if not os.path.exists(self.config.pending_file):
            self.send_message("⚠️ Keine ausstehenden Updates gefunden.")
            return

        with open(self.config.pending_file) as f:
            updates = json.load(f)

        target = next((u for u in updates if u["name"] == container_name), None)
        if not target:
            self.send_message(f"⚠️ Container `{container_name}` nicht in der Update-Liste.")
            return

        self.send_message(f"⏳ Update `{container_name}`...")

        try:
            success, msg = checker.update_container(target["name"], target["image"])
            status = "✅" if success else "❌"
            self.send_message(f"{status} `{container_name}`: {msg}")
        except Exception as e:
            self.send_message(f"❌ `{container_name}`: {str(e)[:200]}")

        # Remove from pending list
        remaining = [u for u in updates if u["name"] != container_name]
        with open(self.config.pending_file, "w") as f:
            json.dump(remaining, f)

        if not remaining:
            self.send_message("✅ Alle Updates abgeschlossen.")

    def notify_updates(self, updates):
        if not updates:
            return
        names = [f"• `{u['name']}` ({u['image']})" for u in updates]
        text = "🔄 *Docker Updates verfügbar*\n\n" + "\n".join(names)

        # One button per container + all/skip at the bottom
        keyboard = []
        for u in updates:
            keyboard.append([
                {"text": f"🔄 {u['name']}", "callback_data": f"update_one:{u['name']}"}
            ])
        keyboard.append([
            {"text": "🚀 Alle updaten", "callback_data": "update_all"},
            {"text": "✋ Manuell", "callback_data": "update_skip"}
        ])

        reply_markup = {"inline_keyboard": keyboard}
        self.send_message(text, reply_markup)

    def notify_no_updates(self):
        self.send_message("✅ *Docker Update Check*\nAlle Images sind aktuell.")

    def _handle_selfupdate(self):
        """Pull latest image and recreate own container."""
        hostname = os.environ.get("HOSTNAME", "")
        if not hostname:
            self.send_message("❌ Self-Update fehlgeschlagen: Container-ID nicht gefunden.")
            return

        # Get own container info
        result = subprocess.run(
            ["docker", "inspect", hostname],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            self.send_message("❌ Self-Update fehlgeschlagen: Container nicht gefunden.")
            return

        config = json.loads(result.stdout)[0]
        own_name = config["Name"].lstrip("/")
        own_image = config["Config"]["Image"]

        self.send_message(f"🔄 Prüfe Update für `{own_image}`...")

        # Pull latest
        pull = subprocess.run(
            ["docker", "pull", own_image],
            capture_output=True, text=True, timeout=300
        )
        if pull.returncode != 0:
            self.send_message(f"❌ Pull fehlgeschlagen: {pull.stderr[:200]}")
            return

        # Check if image actually changed
        new_inspect = subprocess.run(
            ["docker", "inspect", "--format", "{{.Id}}", own_image],
            capture_output=True, text=True
        )
        new_id = new_inspect.stdout.strip()
        old_id = config["Image"]

        if new_id == old_id:
            self.send_message("✅ Bereits auf dem neuesten Stand.")
            return

        self.send_message("⏳ Neues Image gefunden. Starte Self-Update...\nBot wird kurz offline sein.")

        # Create update script that runs after this container stops
        # The script: rename old, create new with same config, remove old
        update_cmd = (
            f"docker stop {own_name} && "
            f"docker rename {own_name} {own_name}_old && "
            f"docker run -d "
        )

        # Rebuild run command from inspect
        run_args = []

        run_args.extend(["--name", own_name])

        # Restart policy
        restart = config.get("HostConfig", {}).get("RestartPolicy", {})
        if restart.get("Name"):
            policy = restart["Name"]
            if restart.get("MaximumRetryCount", 0) > 0:
                policy += f":{restart['MaximumRetryCount']}"
            run_args.extend(["--restart", policy])

        # Network
        network_mode = config.get("HostConfig", {}).get("NetworkMode", "")
        if network_mode and network_mode != "default":
            run_args.extend(["--network", network_mode])

        # Env vars
        for env in config.get("Config", {}).get("Env", []):
            run_args.extend(["-e", env])

        # Mounts
        for mount in config.get("Mounts", []):
            if mount["Type"] == "bind":
                bind = f"{mount['Source']}:{mount['Destination']}"
                if not mount.get("RW", True):
                    bind += ":ro"
                run_args.extend(["-v", bind])
            elif mount["Type"] == "volume":
                bind = f"{mount['Name']}:{mount['Destination']}"
                if not mount.get("RW", True):
                    bind += ":ro"
                run_args.extend(["-v", bind])

        # Ports
        ports = config.get("HostConfig", {}).get("PortBindings", {}) or {}
        for container_port, bindings in ports.items():
            if bindings:
                for b in bindings:
                    host_ip = b.get("HostIp", "")
                    host_port = b.get("HostPort", "")
                    if host_ip:
                        run_args.extend(["-p", f"{host_ip}:{host_port}:{container_port}"])
                    else:
                        run_args.extend(["-p", f"{host_port}:{container_port}"])

        # Labels
        for key, value in config.get("Config", {}).get("Labels", {}).items():
            run_args.extend(["--label", f"{key}={value}"])

        # Security opts
        for opt in config.get("HostConfig", {}).get("SecurityOpt", []) or []:
            run_args.extend(["--security-opt", opt])

        # Build full command
        run_parts = " ".join(f'"{a}"' if " " in a or "=" in a else a for a in run_args)
        update_cmd += f"{run_parts} {own_image} && docker rm {own_name}_old"

        # Execute: run update in background, then exit
        subprocess.Popen(
            ["sh", "-c", f"sleep 2 && {update_cmd}"],
            start_new_session=True
        )
        sys.exit(0)

    def run_updates(self, updater):
        if self.update_running:
            self.send_message("⚠️ Update läuft bereits...")
            return

        pending_file = self.config.pending_file
        if not os.path.exists(pending_file):
            self.send_message("⚠️ Keine ausstehenden Updates gefunden.")
            return

        with open(pending_file) as f:
            updates = json.load(f)

        if not updates:
            self.send_message("⚠️ Keine ausstehenden Updates gefunden.")
            return

        self.update_running = True
        self.send_message(f"⏳ Starte Update für {len(updates)} Container...")

        results = []
        for u in updates:
            try:
                success, msg = updater.update_container(u["name"], u["image"])
                status = "✅" if success else "❌"
                results.append(f"{status} `{u['name']}`: {msg}")
            except Exception as e:
                results.append(f"❌ `{u['name']}`: {str(e)[:200]}")

        try:
            os.remove(pending_file)
        except OSError:
            pass

        self.send_message("*Update-Ergebnis:*\n\n" + "\n".join(results))
        self.update_running = False

    def listen(self, checker, scheduler):
        import time as _time
        self.start_time = _time.time()

        # Flush old updates from queue to prevent replaying commands after restart
        flush = self.api_call("getUpdates", {"offset": -1, "timeout": 0})
        if flush and flush.get("ok") and flush.get("result"):
            offset = flush["result"][-1]["update_id"] + 1
            print(f"Flushed {len(flush['result'])} old updates from queue.")
        else:
            offset = 0

        print("Bot listener started. Waiting for Telegram messages...")

        while self.running:
            try:
                result = self.api_call("getUpdates", {
                    "offset": offset,
                    "timeout": 30,
                    "allowed_updates": json.dumps(["callback_query", "message"])
                })

                if not result or not result.get("ok"):
                    import time
                    time.sleep(5)
                    continue

                for update in result.get("result", []):
                    offset = update["update_id"] + 1

                    # Callback buttons
                    callback = update.get("callback_query")
                    if callback:
                        self._handle_callback(callback, checker)
                        continue

                    # Text commands
                    message = update.get("message", {})
                    self._handle_message(message, checker, scheduler)

            except Exception as e:
                print(f"Bot listener error: {e}")
                import time
                time.sleep(5)

        print("Bot listener stopped.")

    def _handle_callback(self, callback, checker):
        data = callback.get("data", "")
        user_id = str(callback["from"]["id"])
        msg_id = callback.get("message", {}).get("message_id")
        chat_id = callback.get("message", {}).get("chat", {}).get("id")

        if user_id != self.config.chat_id:
            self.answer_callback(callback["id"], "Nicht autorisiert.")
            return

        if data == "update_all":
            if msg_id and chat_id:
                self.remove_buttons(chat_id, msg_id)
            self.answer_callback(callback["id"], "Updates werden gestartet...")
            t = threading.Thread(target=self.run_updates, args=(checker,))
            t.start()
        elif data == "update_skip":
            if msg_id and chat_id:
                self.remove_buttons(chat_id, msg_id)
            self.answer_callback(callback["id"], "OK, manuell.")
            self.send_message("👍 Updates werden nicht automatisch durchgeführt.")
            try:
                os.remove(self.config.pending_file)
            except OSError:
                pass
        elif data.startswith("update_one:"):
            container_name = data.split(":", 1)[1]
            self.answer_callback(callback["id"], f"Update {container_name}...")
            # Remove only this button, keep the rest
            if msg_id and chat_id:
                self._remove_single_button(chat_id, msg_id, data)
            t = threading.Thread(target=self._run_single_update, args=(checker, container_name))
            t.start()

    def _handle_message(self, message, checker, scheduler):
        text = message.get("text", "")
        user_id = str(message.get("from", {}).get("id", ""))

        if user_id != self.config.chat_id:
            return

        if text == "/status":
            ps = subprocess.run(
                ["docker", "ps", "--format", "{{.Names}}\t{{.Status}}"],
                capture_output=True, text=True
            )
            self.send_message(f"*Container-Status:*\n```\n{ps.stdout}```")

        elif text == "/check":
            self.send_message("🔍 Prüfe auf Updates...")
            updates = checker.check_all(bot=self)
            if updates:
                self.notify_updates(updates)
            else:
                self.notify_no_updates()

        elif text == "/updates":
            if os.path.exists(self.config.pending_file):
                with open(self.config.pending_file) as f:
                    pending = json.load(f)
                if pending:
                    names = [f"• `{u['name']}`" for u in pending]
                    self.send_message("*Ausstehende Updates:*\n" + "\n".join(names))
                    return
            self.send_message("Keine ausstehenden Updates.")

        elif text == "/debug":
            self.config.debug = not self.config.debug
            status = "AN 🔍" if self.config.debug else "AUS"
            self.send_message(f"*Debug-Modus:* {status}")

        elif text == "/cleanup":
            self.send_message("🧹 Räume alte Images auf...")
            result = subprocess.run(
                ["docker", "image", "prune", "-a", "--force", "--filter", "until=24h"],
                capture_output=True, text=True, timeout=120
            )
            # Extract reclaimed space from output
            lines = result.stdout.strip().split("\n")
            space_line = [l for l in lines if "reclaimed" in l.lower()]
            if space_line:
                self.send_message(f"✅ {space_line[-1]}")
            else:
                self.send_message("✅ Keine ungenutzten Images gefunden.")

        elif text == "/selfupdate":
            self._handle_selfupdate()

        elif text == "/help" or text == "/start":
            self.send_message(
                "*Docker Telegram Updater v1.1.0* 🐳\n\n"
                "*Befehle:*\n"
                "/status — Container-Status anzeigen\n"
                "/check — Jetzt auf Updates prüfen\n"
                "/updates — Ausstehende Updates anzeigen\n"
                "/cleanup — Alte Images aufräumen\n"
                "/selfupdate — Bot selbst aktualisieren\n"
                "/debug — Debug-Modus ein/ausschalten\n"
                "/help — Diese Hilfe"
            )
