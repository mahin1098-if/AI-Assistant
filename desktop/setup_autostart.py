"""
Makes Joey start automatically when you log in to Windows.

Run once:   python setup_autostart.py
To undo:    python setup_autostart.py remove

It also puts a "Start Joey.bat" in this folder, so you can start Joey any time by double-clicking it.
"""

import os
import sys

FOLDER = os.path.dirname(os.path.abspath(__file__))
PYTHON = sys.executable  # the same Python you use for Joey
STARTUP = os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs\Startup")
STARTUP_FILE = os.path.join(STARTUP, "Joey.bat")
LAUNCHER = os.path.join(FOLDER, "Start Joey.bat")

STARTUP_DELAY = 20  # seconds to wait after login, so the internet and microphone are ready
PYTHONW = os.path.join(os.path.dirname(PYTHON), "pythonw.exe")  # runs without a black window
USE_APP = os.path.exists(os.path.join(FOLDER, "joey_app.py")) and os.path.exists(PYTHONW)


def launcher_script(at_startup: bool) -> str:
    lines = ["@echo off", "rem Starts Joey, your AI assistant", f'cd /d "{FOLDER}"']
    if USE_APP:
        # The orb window. Closing it turns Joey off. Problems are written to joey_log.txt
        extra = " --startup" if at_startup else ""
        lines.append(f'start "" "{PYTHONW}" joey_app.py{extra}')
    else:
        # Terminal version in a minimized window that stays open if something goes wrong
        if at_startup:
            lines.insert(2, f"timeout /t {STARTUP_DELAY} /nobreak >nul")
        lines.append(f'start "Joey" /min cmd /k ""{PYTHON}" joey_wake.py"')
    return "\r\n".join(lines) + "\r\n"


def install():
    if not os.path.isdir(STARTUP):
        print(f"Couldn't find your Startup folder ({STARTUP}).")
        return
    with open(STARTUP_FILE, "w", encoding="utf-8") as f:
        f.write(launcher_script(at_startup=True))
    with open(LAUNCHER, "w", encoding="utf-8") as f:
        f.write(launcher_script(at_startup=False))
    print("Done! Joey will now start by himself every time you log in to Windows.")
    if USE_APP:
        print(f"  - His orb window opens at login and he wakes up about {STARTUP_DELAY} seconds later.")
        print("  - Close the orb window to turn Joey off.")
        print("  - If something goes wrong, the message is saved in joey_log.txt in this folder.")
    else:
        print(f"  - About {STARTUP_DELAY} seconds after login, a minimized 'Joey' window appears on the taskbar.")
        print("  - Close that window to turn Joey off.")
    print(f'  - You can also start him any time by double-clicking "Start Joey.bat" in {FOLDER}')
    print("\nTo stop him starting automatically:  python setup_autostart.py remove")


def remove():
    if os.path.exists(STARTUP_FILE):
        os.remove(STARTUP_FILE)
        print("Joey will no longer start automatically.")
    else:
        print("Joey wasn't set to start automatically.")
    print('("Start Joey.bat" in the joey folder still works if you want to start him yourself.)')


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1].lower() in {"remove", "off", "undo", "uninstall"}:
        remove()
    else:
        install()
