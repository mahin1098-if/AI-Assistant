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

Optional extras:

| Run | To |
|---|---|
| `python setup_calendar.py` | Connect a Google/Outlook calendar (private ICS link) |
| `python setup_autostart.py` | Start Joey when Windows starts |
| `python setup_phone.py` | Use it from your phone on home Wi-Fi |
| `python setup_telegram.py` | Talk to it from anywhere through a private Telegram bot |

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
