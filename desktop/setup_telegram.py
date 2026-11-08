"""
Connect Joey & Ryan to Telegram (one time), so you can message them from your phone.

Run:  python setup_telegram.py
"""

import json
import time

from joey_telegram import CONFIG_FILE, call

STEPS = """
STEP 1 - make your bot (2 minutes, in the Telegram app on your phone or PC):
  1. Search for  @BotFather  (it has a blue tick) and open it
  2. Send:  /newbot
  3. Give it a name, e.g.  Joey & Ryan
  4. Give it a username ending in "bot", e.g.  mahin_joey_bot
  5. BotFather replies with a TOKEN like  123456789:AAH...  - copy it
     (keep it private: anyone with the token controls the bot)
"""


def main():
    print(STEPS)
    token = input("Paste the token here: ").strip().strip('"')
    try:
        me = call(token, "getMe", timeout=15)
    except Exception as e:
        print(f"\nThat token didn't work ({e}). Check you copied all of it and try again.")
        return
    print(f"\nConnected to your bot @{me['username']}.")
    try:  # ignore anything sent before now
        old = call(token, "getUpdates", timeout=15, offset=-1)
        offset = old[-1]["update_id"] + 1 if old else None
    except Exception:
        offset = None

    print(f"\nSTEP 2 - in Telegram, open  @{me['username']}  , press START (or send 'hi').")
    print("Waiting for your message (2 minutes)...")
    deadline = time.time() + 120
    while time.time() < deadline:
        params = {"timeout": 20}
        if offset is not None:
            params["offset"] = offset
        for update in call(token, "getUpdates", **params):
            offset = update["update_id"] + 1
            msg = update.get("message") or {}
            user = msg.get("from") or {}
            if not user.get("id"):
                continue
            CONFIG_FILE.write_text(json.dumps({"token": token, "owner_id": user["id"],
                                               "chat_id": msg["chat"]["id"]}, indent=2), encoding="utf-8")
            call(token, "getUpdates", timeout=15, offset=offset)  # mark it as read
            call(token, "sendMessage", chat_id=msg["chat"]["id"],
                 text="✅ Connected! Joey & Ryan will reply here while your PC is on and Joey is running.\n"
                      "Try: \"Joey, what's on today?\" or \"Ryan, any tech news?\"")
            print(f"\nDone! Locked to your Telegram account ({user.get('first_name', '')}). "
                  f"Restart Joey and message the bot from anywhere.")
            return
    print("\nNo message arrived. Run this again and send the bot a message while it's waiting.")


if __name__ == "__main__":
    main()
