"""
JOEY - Step 5: memory
Lets Joey remember facts about you and your recent conversations, even after you close him.
joey.py loads this automatically if this file is in the same folder.

Joey keeps two files in your joey folder:
  joey_memory.json   - facts he has learned about you (your name, likes, important things)
  joey_history.json  - your most recent conversations
You can open them in Notepad to see what he knows. Delete them to make him forget everything.
"""

import datetime
import json
from pathlib import Path

FOLDER = Path(__file__).parent
MEMORY_FILE = FOLDER / "joey_memory.json"
HISTORY_FILE = FOLDER / "joey_history.json"
HISTORY_LIMIT = 40  # how many recent messages to keep between sessions


# ---------- Long-term facts ----------

def _load_facts() -> list:
    try:
        return json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save_facts(facts: list):
    MEMORY_FILE.write_text(json.dumps(facts, indent=2, ensure_ascii=False), encoding="utf-8")


def remember(fact: str) -> str:
    """Save an important fact about the user to long-term memory, so you still know it in
    future conversations. Use this whenever the user tells you something worth keeping:
    their name, birthday, family, friends, pets, job, school, likes and dislikes, goals,
    or when they say "remember that...". Write the fact as a short sentence,
    for example "User's name is Mahin" or "User's favourite food is biryani".

    Args:
        fact: The fact to remember, as a short sentence.
    """
    facts = _load_facts()
    if any(f["fact"].lower() == fact.lower() for f in facts):
        return "Already remembered."
    facts.append({"fact": fact, "saved": datetime.date.today().isoformat()})
    _save_facts(facts)
    print(f"  [remembered: {fact}]")
    return "Saved to memory."


def forget(about: str) -> str:
    """Remove facts from long-term memory, for example when the user says "forget that"
    or a fact has changed (forget the old one, then remember the new one).

    Args:
        about: A word or phrase from the fact(s) to forget, for example "birthday".
    """
    facts = _load_facts()
    keep = [f for f in facts if about.lower() not in f["fact"].lower()]
    removed = len(facts) - len(keep)
    _save_facts(keep)
    if removed:
        print(f"  [forgot {removed} fact(s) about {about}]")
    return f"Forgot {removed} fact(s)." if removed else "Nothing in memory matched that."


def list_memories() -> str:
    """List everything you remember about the user, for when they ask "what do you know about me?"."""
    facts = _load_facts()
    if not facts:
        return "Memory is empty."
    return "\n".join(f"- {f['fact']}" for f in facts)


def forget_everything() -> str:
    """Wipe ALL memory: every saved fact and the conversation history.
    Only use this when the user clearly asks to erase all of your memory."""
    for f in [MEMORY_FILE, HISTORY_FILE] + list(FOLDER.glob("joey_history_*.json")):
        if f.exists():
            f.unlink()
    print("  [all memory wiped]")
    return "All memory erased."


MEMORY_TOOLS = [remember, forget, list_memories, forget_everything]


def memory_prompt() -> str:
    """Extra instructions added to Joey's personality, including what he knows about you."""
    facts = _load_facts()
    known = "\n".join(f"- {f['fact']}" for f in facts) or "- (nothing yet)"
    now = datetime.datetime.now().strftime("%A %d %B %Y, %I:%M %p")
    return f"""

You have a long-term memory. Things you know about the user:
{known}

Use these naturally (for example, greet them by name), but don't list them unless asked.
When the user shares a new personal fact or preference, save it with the remember tool
without making a big deal of it. If something changes, forget the old fact and remember the new one.
You can also see your recent conversations with the user from earlier sessions.
Right now it is {now}."""


# ---------- Conversation history ----------

def history_file(character: str = "joey"):
    # Joey keeps the original file name; other characters get their own (joey_history_ryan.json)
    return HISTORY_FILE if character == "joey" else FOLDER / f"joey_history_{character}.json"


def load_history(character: str = "joey") -> list:
    """Load recent conversations saved from earlier sessions."""
    try:
        raw = json.loads(history_file(character).read_text(encoding="utf-8"))
    except Exception:
        return []
    # keep only simple {"role", "content": text} messages (older Gemini-style files are skipped)
    history = [m for m in raw if isinstance(m, dict) and m.get("role") in ("user", "assistant")
               and isinstance(m.get("content"), str)]
    while history and history[0]["role"] != "user":
        history.pop(0)
    return history


def save_history(history: list, character: str = "joey") -> list:
    """Save the most recent messages so Joey remembers them next time. Returns the trimmed list."""
    recent = list(history)[-HISTORY_LIMIT:]
    while recent and recent[0]["role"] != "user":  # must start with something the user said
        recent.pop(0)
    try:
        history_file(character).write_text(json.dumps(recent, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception as e:
        print(f"  [couldn't save conversation: {e}]")
    return recent
