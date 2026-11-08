"""
JOEY - Step 4: powers
Extra abilities for Joey. joey.py loads these automatically if this file is in the same folder.

To add your own power: write a function with a clear docstring (Joey reads it to decide
when to use it), then add it to POWER_TOOLS at the bottom.
"""

import ctypes
import datetime
import difflib
import json
import os
import re
import subprocess
import threading
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path

NOTES_FILE = Path(__file__).parent / "joey_notes.txt"

# How Joey announces timers and reminders. The voice versions replace this so he says it out loud.
announce = print
# Where the current request came from ("pc" or "phone"), and how to message the phone.
# joey_app.py sets these when Telegram is connected, so reminders set from the phone go to the phone.
request_origin = threading.local()
notify_phone = None


# ---------- Open apps ----------

KNOWN_APPS = {
    "notepad": "notepad", "calculator": "calc", "calc": "calc", "paint": "mspaint",
    "file explorer": "explorer", "explorer": "explorer", "files": "explorer", "my files": "explorer",
    "command prompt": "cmd", "terminal": "wt", "task manager": "taskmgr", "control panel": "control",
    "settings": "ms-settings:", "camera": "microsoft.windows.camera:", "clock": "ms-clock:",
    "alarms": "ms-clock:", "microsoft store": "ms-windows-store:", "store": "ms-windows-store:",
    "edge": "msedge", "microsoft edge": "msedge", "chrome": "chrome", "google chrome": "chrome",
    "word": "winword", "excel": "excel", "powerpoint": "powerpnt", "outlook": "outlook",
    "snipping tool": "snippingtool",
}

_start_apps = None  # cache of every app in the Start menu


def _list_start_apps():
    """Ask Windows for every app in the Start menu (including Store apps like WhatsApp or Spotify)."""
    global _start_apps
    if _start_apps is None:
        try:
            out = subprocess.run(
                ["powershell", "-NoProfile", "-Command", "Get-StartApps | ConvertTo-Json -Compress"],
                capture_output=True, text=True, timeout=20,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            ).stdout
            data = json.loads(out) if out.strip() else []
            _start_apps = {a["Name"]: a["AppID"] for a in (data if isinstance(data, list) else [data])}
        except Exception:
            _start_apps = {}
    return _start_apps


def _best_match(wanted, names):
    wanted = wanted.lower()
    lowered = {n.lower(): n for n in names if "uninstall" not in n.lower()}
    if wanted in lowered:
        return lowered[wanted]
    starts = [n for low, n in lowered.items() if low.startswith(wanted)]
    if starts:
        return min(starts, key=len)
    contains = [n for low, n in lowered.items() if wanted in low]
    if contains:
        return min(contains, key=len)
    close = difflib.get_close_matches(wanted, list(lowered), n=1, cutoff=0.6)
    return lowered[close[0]] if close else None


def open_app(app_name: str) -> str:
    """Open an app or program on the user's Windows computer, for example Notepad,
    Calculator, Spotify, WhatsApp, Discord, Steam, Word, File Explorer or Settings.

    Args:
        app_name: The name of the app, for example "spotify" or "calculator".
    """
    print(f"  [opening {app_name}]")
    key = app_name.lower().strip()
    if key in KNOWN_APPS:
        try:
            os.startfile(KNOWN_APPS[key])
            return f"Opened {app_name}."
        except OSError:
            pass
    apps = _list_start_apps()
    match = _best_match(key, apps)
    if match:
        subprocess.Popen(["explorer.exe", f"shell:AppsFolder\\{apps[match]}"])
        return f"Opened {match}."
    try:
        os.startfile(key)
        return f"Opened {app_name}."
    except OSError:
        return f"Couldn't find an app called {app_name} on this computer."


# ---------- Music ----------

def play_music(song_or_artist: str) -> str:
    """Play a song, artist, album or any video on YouTube in the browser.

    Args:
        song_or_artist: What to play, for example "Shape of You Ed Sheeran" or "lofi beats".
    """
    print(f"  [playing {song_or_artist} on YouTube]")
    query = urllib.parse.quote_plus(song_or_artist)
    try:
        request = urllib.request.Request(
            f"https://www.youtube.com/results?search_query={query}",
            headers={"User-Agent": "Mozilla/5.0", "Accept-Language": "en"},
        )
        html = urllib.request.urlopen(request, timeout=10).read().decode("utf-8", "ignore")
        video = re.search(r'"videoId":"([\w-]{11})"', html)
        if video:
            webbrowser.open(f"https://www.youtube.com/watch?v={video.group(1)}")
            return f"Playing {song_or_artist} on YouTube."
    except Exception:
        pass
    webbrowser.open(f"https://www.youtube.com/results?search_query={query}")
    return f"Opened YouTube search results for {song_or_artist}."


# ---------- Volume and media keys ----------

MEDIA_KEYS = {
    "volume_up": 0xAF, "volume_down": 0xAE, "mute": 0xAD,
    "play_pause": 0xB3, "next": 0xB0, "previous": 0xB1,
}


def media_control(action: str, times: int = 1) -> str:
    """Control the computer's sound and whatever media is playing.

    Args:
        action: One of: volume_up, volume_down, mute, play_pause, next, previous.
            "mute" toggles mute on and off. "play_pause" pauses or resumes music and videos.
        times: How many key presses. Each volume press changes volume by about 2%,
            so "a bit louder" is about 5 presses and "much louder" about 15.
    """
    action = action.lower().replace(" ", "_").replace("-", "_")
    if action not in MEDIA_KEYS:
        return f"Unknown action {action}. Use one of: {', '.join(MEDIA_KEYS)}."
    print(f"  [{action} x{times}]")
    try:
        for _ in range(max(1, min(int(times), 50))):
            ctypes.windll.user32.keybd_event(MEDIA_KEYS[action], 0, 0, 0)
            ctypes.windll.user32.keybd_event(MEDIA_KEYS[action], 0, 2, 0)
        return f"Done: {action}."
    except Exception as e:
        return f"Couldn't do that: {e}"


# ---------- Timers and reminders ----------

_timers = []  # (finish_time, message, timer)


def _alarm(message: str, entry, origin="pc"):
    if entry in _timers:
        _timers.remove(entry)
    if origin == "phone" and notify_phone:
        try:
            notify_phone(f"⏰ {message}")
            return
        except Exception as e:
            print(f"  [couldn't message the phone: {e}]")
    try:
        import winsound
        for _ in range(3):
            winsound.Beep(1000, 200)
    except Exception:
        pass
    announce(message)


def set_timer(minutes: float, message: str) -> str:
    """Set a timer or reminder. Joey will beep and say the message when time is up.
    For a reminder at a clock time (like "at 5:30pm"), call get_time first and work out
    how many minutes from now that is.

    Args:
        minutes: Minutes from now. Use decimals for seconds, for example 0.5 for 30 seconds.
        message: What to say when it goes off, for example "Time's up! Your pasta is ready."
    """
    seconds = max(1.0, float(minutes) * 60)
    finish = datetime.datetime.now() + datetime.timedelta(seconds=seconds)
    entry = [finish, message, None]
    origin = getattr(request_origin, "value", "pc")
    timer = threading.Timer(seconds, _alarm, args=(message, entry, origin))
    timer.daemon = True
    entry[2] = timer
    _timers.append(entry)
    timer.start()
    print(f"  [timer set for {finish.strftime('%I:%M:%S %p')}]")
    return f"Timer set. It will go off at {finish.strftime('%I:%M %p')}."


def list_timers() -> str:
    """List the timers and reminders that are still running."""
    if not _timers:
        return "No timers running."
    now = datetime.datetime.now()
    lines = []
    for finish, message, _ in sorted(_timers, key=lambda t: t[0]):
        left = int((finish - now).total_seconds())
        lines.append(f"'{message}' in {left // 60} min {left % 60} s (at {finish.strftime('%I:%M %p')})")
    return "Running timers: " + "; ".join(lines)


def cancel_timers() -> str:
    """Cancel all running timers and reminders."""
    count = len(_timers)
    for _, _, timer in _timers:
        timer.cancel()
    _timers.clear()
    return f"Cancelled {count} timer(s)."


# ---------- Web search ----------

def search_web(query: str) -> str:
    """Open a Google search in the user's browser. Only use this when the user wants to SEE the
    results on screen ("show me", "open a search for"). To answer a question, use web_search instead.

    Args:
        query: What to search for.
    """
    print(f"  [searching the web for {query}]")
    webbrowser.open("https://www.google.com/search?q=" + urllib.parse.quote_plus(query))
    return f"Opened a Google search for {query}."


# ---------- Notes ----------

def take_note(note: str) -> str:
    """Save a note for the user, like a shopping item, an idea or something to remember.

    Args:
        note: The note to save.
    """
    stamp = datetime.datetime.now().strftime("%d %b %Y %I:%M %p")
    with open(NOTES_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{stamp}] {note}\n")
    print("  [note saved]")
    return "Note saved."


def read_notes() -> str:
    """Read back the user's saved notes (the most recent 30)."""
    if not NOTES_FILE.exists():
        return "There are no notes yet."
    lines = NOTES_FILE.read_text(encoding="utf-8").strip().splitlines()
    return "\n".join(lines[-30:]) or "There are no notes yet."


def clear_notes() -> str:
    """Delete all of the user's saved notes. Only use this if the user clearly asks to delete them."""
    if NOTES_FILE.exists():
        NOTES_FILE.unlink()
    return "All notes deleted."


POWER_TOOLS = [
    open_app, play_music, media_control,
    set_timer, list_timers, cancel_timers,
    search_web, take_note, read_notes, clear_notes,
]
