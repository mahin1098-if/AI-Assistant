"""
JOEY & RYAN - on your phone (Telegram)
Message your own private Telegram bot and Joey or Ryan reply - from anywhere, while your PC is on
and Joey is running. Only YOUR Telegram account can use it; everyone else is ignored.

Setup once:  python setup_telegram.py
No extra installs needed.
"""

import json
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path

CONFIG_FILE = Path(__file__).parent / "joey_telegram.json"
API = "https://api.telegram.org/bot{token}/{method}"


def load_config():
    try:
        cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        return cfg if cfg.get("token") and cfg.get("owner_id") else None
    except Exception:
        return None


def call(token, method, timeout=35, **params):
    data = json.dumps(params).encode("utf-8")
    req = urllib.request.Request(API.format(token=token, method=method), data=data,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        out = json.loads(r.read().decode("utf-8"))
    if not out.get("ok"):
        raise RuntimeError(out.get("description", "Telegram error"))
    return out["result"]


class TelegramLink:
    """Listens for your messages and sends replies. on_message(text) runs for each message."""

    def __init__(self, config, on_message):
        self.token = config["token"]
        self.owner = int(config["owner_id"])
        self.chat = int(config.get("chat_id", self.owner))
        self.on_message = on_message
        self.offset = None
        self.running = False

    def start(self):
        self.running = True
        threading.Thread(target=self._loop, daemon=True).start()

    def send(self, text):
        text = (text or "").strip() or "(no reply)"
        for i in range(0, len(text), 4000):  # Telegram's limit is 4096 characters per message
            call(self.token, "sendMessage", chat_id=self.chat, text=text[i:i + 4000],
                 link_preview_options={"is_disabled": True})

    def typing(self):
        try:
            call(self.token, "sendChatAction", timeout=10, chat_id=self.chat, action="typing")
        except Exception:
            pass

    def _loop(self):
        # skip messages sent while Joey was off (they'd be stale)
        try:
            old = call(self.token, "getUpdates", timeout=15, offset=-1)
            if old:
                self.offset = old[-1]["update_id"] + 1
        except Exception as e:
            print(f"  [telegram: {e}]")
        print("  [phone link: listening for Telegram messages]")
        while self.running:
            try:
                params = {"timeout": 25, "allowed_updates": ["message"]}
                if self.offset is not None:
                    params["offset"] = self.offset
                for update in call(self.token, "getUpdates", **params):
                    self.offset = update["update_id"] + 1
                    msg = update.get("message") or {}
                    sender = (msg.get("from") or {}).get("id")
                    text = msg.get("text")
                    if sender != self.owner:
                        continue          # not you: ignore completely
                    if not text:
                        self.send("I can only read text messages for now.")
                        continue
                    threading.Thread(target=self._handle, args=(text,), daemon=True).start()
            except Exception as e:
                print(f"  [telegram connection problem: {e}; retrying]")
                time.sleep(5)

    def _handle(self, text):
        try:
            self.on_message(text)
        except Exception as e:
            print(f"  [telegram message failed: {e}]")
            try:
                self.send("Sorry, something went wrong on the PC.")
            except Exception:
                pass
