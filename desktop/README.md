# Joey & Ryan — desktop app (Windows, Python)

The full version of the assistant: always listening for "Hey Joey" / "Hey Ryan", natural offline voices,
an animated HUD window, and tools that control the PC.

## Setup

1. Python 3.11 or newer on Windows.
2. Install the packages:
   ```
   pip install -r requirements.txt
   ```
3. Set your Claude API key (then open a new terminal):
   ```
   setx ANTHROPIC_API_KEY "sk-ant-..."
   ```
   Check it works with `python check_key.py`.
4. Test your microphone with `python mic_test.py`.
5. Start the app:
   ```
   python joey_app.py
   ```
   The first start downloads the two Piper voices.

Using it:

- Say **"Hey Joey"** or **"Hey Ryan"**, or type in the box.
- Closing the window (X) only **hides** Joey: she keeps listening and Telegram keeps working.
  Open her again with **Start Joey.bat**, by saying "Hey Joey", or from the tray icon by the clock.
- To quit completely, say or type **"shut down"**, or right-click the tray icon → **Quit Joey**.
- Settings are at the top of each file, for example `KEEP_RUNNING_WHEN_CLOSED` in `joey_app.py`
  and `VOICE_REPLIES` in `joey_telegram.py`.

Optional extras:

| Run | To |
|---|---|
| `python setup_calendar.py` | Connect a Google/Outlook calendar (private ICS link) |
| `python setup_autostart.py` | Start Joey when Windows starts |
| `python setup_phone.py` | Use it from your phone on home Wi-Fi |
| `python setup_telegram.py` | Talk to it from anywhere through a private Telegram bot |

## Use the PC version from your phone

The phone app on GitHub Pages is separate from this one. To reach **this** version from your phone,
with its memories, calendar, timers and PC control, use one of these. Joey must be running on the PC.

### Option A: Home Wi-Fi phone page (voice, only at home)

1. On the PC run `python setup_phone.py`. It shows a private link and a QR code. Keep the link private,
   because it contains your key.
2. Allow the phone-app ports through Windows Firewall, once. Open **PowerShell as administrator**
   (right-click → Run as administrator) and run:
   ```
   New-NetFirewallRule -DisplayName "Joey phone app" -Direction Inbound -Protocol TCP -LocalPort 8765,8766 -Action Allow -RemoteAddress LocalSubnet
   ```
   This only lets devices on your home network in.
3. Restart Joey on the PC. It should print `[phone app ready at http://...]`.
4. Make sure your phone is on the **same Wi-Fi** as the PC, then scan the QR code.
5. To use the microphone, the phone has to trust Joey's home certificate. The page that opens walks you through it:
   - Tap **Download certificate** → **Allow**.
   - iPhone: **Settings → Profile Downloaded → Install**.
   - Then **Settings → General → About → Certificate Trust Settings** → switch on **Joey Home Certificate**.
6. Go back to the page, tap **Open Joey with voice**, and then **Share → Add to Home Screen**.

If it stops working one day, your PC's home address has probably changed. Run `python setup_phone.py` again.

### Option B: Telegram (text, from anywhere)

1. In Telegram, open **@BotFather** (blue tick), send `/newbot`, and pick a name and a username ending in `bot`.
2. BotFather replies with a **token**. Copy it and keep it private, because anyone with it controls the bot.
3. On the PC run `python setup_telegram.py` and paste the token.
4. In Telegram, open your new bot and press **Start**. The bot locks itself to your account, so nobody else can use it.
5. Restart Joey on the PC. Message the bot from anywhere and Joey or Ryan reply, as long as the PC is on.
6. Voice notes work too: hold the mic in Telegram and talk. They reply in text and with a voice note in their own voice (needs `pip install av`).

## How the code is organised

| File | Job |
|---|---|
| `joey_app.py` | The window and main loop: listens, routes, speaks, animates |
| `joey.py` | The brain: characters, system prompts, Claude tool-use loop, web search, citations |
| `joey_voice.py` | Microphone capture, noise calibration, speech recognition, Piper text-to-speech |
| `joey_wake.py` | Wake words, "switch to Ryan" handoffs, and the terminal version |
| `joey_memory.py` | Long-term facts and per-character conversation history |
| `joey_powers.py` | PC tools: open apps, music, media keys, timers, notes, web search |
| `joey_skills.py` | News, calendar, contacts, WhatsApp and email drafts |
| `joey_screen.py` | Screenshot tool so Claude can see the screen |
| `joey_duet.py` | Joey and Ryan debating / brainstorming with each other |
| `joey_briefing.py` | The morning briefing |
| `joey_hud.py` | The HUD ring animation (current look) |
| `joey_holo.py`, `joey_face.py`, `joey_lipsync.py`, `face_mesh.obj` | Earlier face/hologram looks, still selectable in `joey_app.py` |
| `joey_remote.py` | Routes messages that arrive from the phone or Telegram |
| `joey_phone.py`, `joey_certs.py` | Home Wi-Fi phone server with its own HTTPS certificates |
| `joey_telegram.py` | Owner-only Telegram bot link |

## Private files

The app creates files such as `joey_memory.json`, `joey_calendars.json`, `joey_phone.json`,
`joey_telegram.json` and `*.key` next to the code. They contain personal data and secrets, so
`.gitignore` keeps them out of the repository. Never upload them.
