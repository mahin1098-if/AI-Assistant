"""
JOEY - Step 3 powers: news, calendar and messages.
joey.py loads these automatically if this file is in the same folder.

Calendar setup (once):  python setup_calendar.py
Needs:  pip install icalendar recurring-ical-events
"""

import datetime
import json
import re
import urllib.parse
import urllib.request
import webbrowser
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from pathlib import Path

FOLDER = Path(__file__).parent
CALENDARS_FILE = FOLDER / "joey_calendars.json"
CONTACTS_FILE = FOLDER / "joey_contacts.json"

NEWS_REGION = "hl=en-AU&gl=AU&ceid=AU:en"   # Australian news. US: hl=en-US&gl=US&ceid=US:en
NEWS_TOPICS = {"world": "WORLD", "australia": "NATION", "nation": "NATION", "business": "BUSINESS",
               "technology": "TECHNOLOGY", "tech": "TECHNOLOGY", "entertainment": "ENTERTAINMENT",
               "sport": "SPORTS", "sports": "SPORTS", "science": "SCIENCE", "health": "HEALTH"}


def _get(url, timeout=12):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Joey assistant)"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


# ---------- News ----------

def parse_rss(data: bytes, limit: int):
    root = ET.fromstring(data)
    items = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        source = (item.findtext("source") or "").strip()
        if source and title.endswith(" - " + source):
            title = title[: -len(source) - 3]
        when = ""
        try:
            pub = parsedate_to_datetime(item.findtext("pubDate"))
            hours = (datetime.datetime.now(datetime.timezone.utc) - pub).total_seconds() / 3600
            when = f"{int(hours)}h ago" if hours >= 1 else "just now"
        except Exception:
            pass
        items.append(f"- {title}" + (f" ({source}, {when})" if source else f" ({when})" if when else ""))
        if len(items) >= limit:
            break
    return items


def get_news(topic: str = "top", count: int = 5) -> str:
    """Get the latest news headlines. Read out just a few, briefly, unless the user asks for more.

    Args:
        topic: "top" for top stories, or one of: world, australia, business, technology, sport,
            science, health, entertainment. Anything else is treated as a search, e.g. "AI" or "cricket".
        count: How many headlines (1-10).
    """
    print(f"  [getting {topic} news]")
    count = max(1, min(int(count), 10))
    key = topic.lower().strip()
    if key in ("top", "", "latest", "headlines"):
        url = f"https://news.google.com/rss?{NEWS_REGION}"
    elif key in NEWS_TOPICS:
        url = f"https://news.google.com/rss/headlines/section/topic/{NEWS_TOPICS[key]}?{NEWS_REGION}"
    else:
        url = f"https://news.google.com/rss/search?q={urllib.parse.quote_plus(topic)}+when:2d&{NEWS_REGION}"
    try:
        items = parse_rss(_get(url), count)
    except Exception as e:
        return f"Couldn't get the news right now ({e})."
    return "\n".join(items) if items else f"No news found for {topic}."


# ---------- Calendar ----------

def _calendar_links():
    try:
        return json.loads(CALENDARS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def read_events(ics_data: bytes, start: datetime.datetime, end: datetime.datetime, name: str):
    import icalendar
    import recurring_ical_events

    cal = icalendar.Calendar.from_ical(ics_data)
    local = datetime.datetime.now().astimezone().tzinfo
    out = []
    for ev in recurring_ical_events.of(cal).between(start, end):
        title = str(ev.get("SUMMARY", "(no title)"))
        s = ev.get("DTSTART").dt
        e = ev.get("DTEND").dt if ev.get("DTEND") else None
        where = str(ev.get("LOCATION", "") or "")
        if isinstance(s, datetime.datetime):
            s = s.astimezone(local) if s.tzinfo else s.replace(tzinfo=local)
            e = (e.astimezone(local) if e.tzinfo else e.replace(tzinfo=local)) if isinstance(e, datetime.datetime) else None
            sort_key = s
            when = s.strftime("%a %d %b, %I:%M %p").replace(" 0", " ")
            if e:
                when += " - " + e.strftime("%I:%M %p").lstrip("0")
        else:  # all-day event
            sort_key = datetime.datetime.combine(s, datetime.time.min).replace(tzinfo=local)
            when = s.strftime("%a %d %b") + ", all day"
        out.append((sort_key, f"- {when}: {title}" + (f" @ {where}" if where else "") + f" [{name}]"))
    return out


def get_schedule(day: str = "today", days: int = 1) -> str:
    """Check the user's calendars (Google and Outlook) for events.

    Args:
        day: "today", "tomorrow", a weekday like "friday", or a date like "2026-10-25".
        days: How many days to include from that day, e.g. 7 for "this week".
    """
    links = _calendar_links()
    if not links:
        return ("No calendars are connected yet. The user needs to run:  python setup_calendar.py  "
                "in the joey folder (one time).")
    print(f"  [checking calendar: {day}, {days} day(s)]")
    today = datetime.date.today()
    d = day.lower().strip()
    weekdays = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    if d in ("today", ""):
        first = today
    elif d == "tomorrow":
        first = today + datetime.timedelta(days=1)
    elif d in weekdays:
        first = today + datetime.timedelta(days=(weekdays.index(d) - today.weekday()) % 7)
    else:
        try:
            first = datetime.date.fromisoformat(d)
        except ValueError:
            return f"I didn't understand the day '{day}'. Use today, tomorrow, a weekday or YYYY-MM-DD."
    local = datetime.datetime.now().astimezone().tzinfo
    start = datetime.datetime.combine(first, datetime.time.min).replace(tzinfo=local)
    end = start + datetime.timedelta(days=max(1, min(int(days), 31)))
    events, problems = [], []
    for name, url in links.items():
        try:
            events += read_events(_get(url.replace("webcal://", "https://"), 20), start, end, name)
        except Exception as e:
            problems.append(f"{name} ({e.__class__.__name__})")
    events.sort(key=lambda x: x[0])
    merged = {}  # the same event in both calendars is listed once
    for when, line in events:
        key = (when, line.split(": ", 1)[1].rsplit(" [", 1)[0].lower())
        if key in merged:
            merged[key] = merged[key][:-1] + " + " + line.rsplit("[", 1)[1]
        else:
            merged[key] = line
    text = "\n".join(merged.values()) if merged else "No events."
    if problems:
        text += "\nCouldn't read: " + ", ".join(problems)
    return text


# ---------- Contacts and messages ----------

def _contacts():
    try:
        return json.loads(CONTACTS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_contact(name: str, phone: str = "", email: str = "") -> str:
    """Save or update a contact so messages can be sent to them by name.

    Args:
        name: The contact's name, e.g. "Mum" or "Sarah".
        phone: Mobile number with country code, e.g. +61412345678 (Australian 04... numbers are fine too).
        email: Email address.
    """
    contacts = _contacts()
    c = contacts.get(name.lower(), {"name": name})
    if phone:
        digits = re.sub(r"[^\d+]", "", phone)
        if digits.startswith("04"):           # Australian mobile -> international format
            digits = "+61" + digits[1:]
        c["phone"] = digits
    if email:
        c["email"] = email.strip()
    contacts[name.lower()] = c
    CONTACTS_FILE.write_text(json.dumps(contacts, indent=2), encoding="utf-8")
    print(f"  [contact saved: {name}]")
    return f"Saved {name}."


def list_contacts() -> str:
    """List the saved contacts."""
    contacts = _contacts()
    if not contacts:
        return "No contacts saved yet."
    return "\n".join(f"- {c['name']}: {c.get('phone', 'no phone')}, {c.get('email', 'no email')}"
                     for c in contacts.values())


def _find(name):
    contacts = _contacts()
    key = name.lower().strip()
    if key in contacts:
        return contacts[key]
    for k, c in contacts.items():
        if key in k or k in key:
            return c
    return None


def send_whatsapp(to: str, message: str) -> str:
    """Open WhatsApp with a message ready to send. The user presses Enter to send it.
    Read the message back to the user first if they dictated it by voice.

    Args:
        to: A saved contact's name, or a phone number with country code.
        message: The message text.
    """
    contact = _find(to)
    phone = contact.get("phone") if contact else None
    if not phone:
        digits = re.sub(r"[^\d+]", "", to)
        if len(digits) >= 8:
            phone = "+61" + digits[1:] if digits.startswith("04") else digits
    if not phone:
        return f"I don't have a phone number for {to}. Ask for it and save it with save_contact."
    print(f"  [opening WhatsApp message to {to}]")
    number = phone.lstrip("+")
    query = urllib.parse.urlencode({"phone": number, "text": message})
    try:
        webbrowser.open(f"whatsapp://send?{query}")          # WhatsApp desktop app
    except Exception:
        webbrowser.open(f"https://wa.me/{number}?" + urllib.parse.urlencode({"text": message}))
    return "WhatsApp is open with the message ready. The user just needs to press Enter to send it."


def send_email(to: str, subject: str, body: str) -> str:
    """Open a Gmail email ready to send in the browser. The user clicks Send.

    Args:
        to: A saved contact's name, or an email address.
        subject: Email subject line.
        body: The email text.
    """
    contact = _find(to)
    address = contact.get("email") if contact else (to if "@" in to else None)
    if not address:
        return f"I don't have an email address for {to}. Ask for it and save it with save_contact."
    print(f"  [opening email to {to}]")
    query = urllib.parse.urlencode({"view": "cm", "fs": "1", "to": address, "su": subject, "body": body})
    webbrowser.open(f"https://mail.google.com/mail/?{query}")
    return "Gmail is open with the email ready. The user just needs to click Send."


SKILL_TOOLS = [get_news, get_schedule, save_contact, list_contacts, send_whatsapp, send_email]
