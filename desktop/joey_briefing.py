"""
JOEY & RYAN - morning briefing
The first time they start each day (before BRIEFING_UNTIL), Joey greets you with the weather,
today's calendar and the top headlines, then Ryan adds something light.
Ask any time with "Joey, give me my briefing".
"""

import datetime
import json
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from joey import CHARACTERS, DEFAULT_CHARACTER, HOME_CITY, MODEL, get_weather

MORNING_BRIEFING = True   # set to False to turn the automatic briefing off
BRIEFING_UNTIL = 14       # only give it automatically before this hour (2 PM)
HEADLINES = 3
STATE_FILE = Path(__file__).parent / "joey_briefing.json"

ASK_RE = re.compile(r"\b(briefing|brief me|daily update|morning update|catch me up|what did i miss)\b",
                    re.IGNORECASE)


def wants_briefing(text: str) -> bool:
    return bool(text and ASK_RE.search(text))


def due_today() -> bool:
    """True if the automatic briefing hasn't been given yet today."""
    if not MORNING_BRIEFING or datetime.datetime.now().hour >= BRIEFING_UNTIL:
        return False
    try:
        last = json.loads(STATE_FILE.read_text(encoding="utf-8")).get("last")
    except Exception:
        last = None
    return last != datetime.date.today().isoformat()


def mark_done():
    try:
        STATE_FILE.write_text(json.dumps({"last": datetime.date.today().isoformat()}), encoding="utf-8")
    except Exception:
        pass


def gather():
    """Fetch the weather, calendar and news at the same time (faster)."""
    try:
        from joey_skills import get_news, get_schedule
    except ImportError:
        get_news = get_schedule = None
    jobs = {"weather": lambda: get_weather(HOME_CITY)}
    if get_schedule:
        jobs["calendar"] = lambda: get_schedule("today")
    if get_news:
        jobs["news"] = lambda: get_news("top", HEADLINES)
    out = {}
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {k: pool.submit(f) for k, f in jobs.items()}
        for k, f in futures.items():
            try:
                out[k] = f.result(timeout=25)
            except Exception as e:
                out[k] = f"(unavailable: {e})"
    cal = out.get("calendar", "")
    if "No calendars are connected" in cal:
        out["calendar"] = "(no calendar connected)"
    return out


def _ask(brain, prompt, tokens=400):
    r = brain.client.messages.create(model=MODEL, max_tokens=tokens, system=brain.system_prompt(),
                                     messages=[{"role": "user", "content": prompt}])
    return "".join(b.text for b in r.content if b.type == "text").strip()


def _facts():
    now = datetime.datetime.now()
    return now, ("morning" if now.hour < 12 else "afternoon")


def lead_script(brains, data):
    """Joey's briefing."""
    now, part = _facts()
    facts = (f"Now: {now.strftime('%A %d %B %Y, %I:%M %p')}\n"
             f"Weather in {HOME_CITY}: {data.get('weather')}\n"
             f"Today's calendar: {data.get('calendar', '(no calendar connected)')}\n"
             f"Top headlines:\n{data.get('news', '(unavailable)')}")
    return _ask(brains[DEFAULT_CHARACTER], (
        f"Give the user their {part} briefing, spoken out loud, about 30 seconds (5-7 short sentences). "
        f"Greet them by name if you know it. Cover: the weather (temperature and whether to take an "
        f"umbrella or jacket), what's on their calendar today (or that it's clear), and the top headlines "
        f"in a few words each. Natural speech, no lists, no markdown, don't read out web addresses. "
        f"Skip anything marked unavailable.\n\n{facts}"))


def extra_script(brains, other, main):
    """Ryan's short add-on after Joey's briefing."""
    _, part = _facts()
    return _ask(brains[other], (
        f"{CHARACTERS[DEFAULT_CHARACTER]['name']} just gave the user this briefing:\n\"{main}\"\n\n"
        f"Add ONE or TWO short spoken sentences of your own, in your personality: a light quip about the "
        f"day or weather, or a fun fact, and wish them a good {part}. Don't repeat the briefing."), tokens=120)


def run(brains, say_line):
    """Give the briefing. say_line(who, text) shows and speaks a line. Returns who spoke last."""
    print("  [preparing the briefing...]")
    lead = DEFAULT_CHARACTER
    other = next((k for k in CHARACTERS if k != lead), None)
    main = lead_script(brains, gather())
    mark_done()
    if not main:
        return lead
    with ThreadPoolExecutor(max_workers=1) as pool:
        extra_job = pool.submit(extra_script, brains, other, main) if other else None  # written while Joey talks
        say_line(lead, main)
        brains[lead].remember_turn("(daily briefing)", main)
        try:
            extra = extra_job.result(timeout=30) if extra_job else ""
        except Exception:
            extra = ""
    if extra:
        say_line(other, extra)
        brains[other].remember_turn(f"(add something after {CHARACTERS[lead]['name']}'s briefing)", extra)
        return other
    return lead
