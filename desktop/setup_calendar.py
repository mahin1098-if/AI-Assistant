"""
Connect your calendars to Joey (one time). Joey can then tell you what's on.
It uses each calendar's private "iCal" link: read-only, no passwords.

Run:  python setup_calendar.py
"""

import datetime
import json
from pathlib import Path

FILE = Path(__file__).parent / "joey_calendars.json"

GOOGLE_HELP = """
GOOGLE CALENDAR - where to find the link:
  1. Open calendar.google.com on your computer
  2. Click the gear (top right) -> Settings
  3. On the left, under "Settings for my calendars", click your calendar
  4. Click "Integrate calendar"
  5. Copy the "Secret address in iCal format" (it ends in basic.ics)
"""

OUTLOOK_HELP = """
OUTLOOK CALENDAR - where to find the link:
  1. Open outlook.live.com (or outlook.office.com for work) and go to Calendar
  2. Settings (gear) -> Calendar -> Shared calendars
  3. Under "Publish a calendar", pick your calendar and "Can view all details", then Publish
  4. Copy the ICS link (it ends in .ics)
"""


def test(url):
    from joey_skills import _get, read_events
    local = datetime.datetime.now().astimezone().tzinfo
    start = datetime.datetime.combine(datetime.date.today(), datetime.time.min).replace(tzinfo=local)
    events = read_events(_get(url.replace("webcal://", "https://"), 20), start, start + datetime.timedelta(days=14), "")
    return len(events)


def ask(name, help_text, links):
    print(help_text)
    url = input(f"Paste your {name} link (or press Enter to skip): ").strip().strip('"')
    if not url:
        print(f"  Skipped {name}.")
        return
    try:
        n = test(url)
        links[name] = url
        print(f"  Connected! Found {n} event(s) in the next 2 weeks.")
    except Exception as e:
        print(f"  That link didn't work ({e}). Check you copied the whole link and try again.")


def main():
    try:
        links = json.loads(FILE.read_text(encoding="utf-8"))
    except Exception:
        links = {}
    print("Connect your calendars to Joey. Keep these links private - anyone with them can see your calendar.")
    ask("Google", GOOGLE_HELP, links)
    ask("Outlook", OUTLOOK_HELP, links)
    FILE.write_text(json.dumps(links, indent=2), encoding="utf-8")
    if links:
        print(f"\nSaved. Joey can now read: {', '.join(links)}. Try: \"Hey Joey, what's on today?\"")
    else:
        print("\nNo calendars connected. Run this again any time.")


if __name__ == "__main__":
    main()
