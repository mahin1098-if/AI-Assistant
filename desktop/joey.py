"""
JOEY - the brain (powered by Claude)

Setup (Windows), once:
  1. pip install anthropic
  2. setx ANTHROPIC_API_KEY "your-key-here"      (then close and reopen the terminal)

Run:
  python joey.py         (typing)
  python joey_voice.py   (press Enter and talk)
  python joey_wake.py    (say "Hey Joey")
"""

import datetime
import json
import os
import time
import urllib.parse
import urllib.request
import webbrowser

import anthropic
from anthropic import beta_tool

NAME = "Joey"  # the main assistant's name

# Which Claude model to use:
#   "claude-haiku-5-5"  - fastest and cheapest, great for a voice assistant (default)
#   "claude-sonnet-5-5" - smarter, a bit slower, costs more
MODEL = "claude-haiku-5-5"
BACKUP_MODEL = "claude-sonnet-5-5"  # used if the main model is overloaded
MAX_REPLY_TOKENS = 1024

HOME_CITY = "Sydney"  # used for the weather when you don't say a city

# Real web answers: Claude searches the web and answers out loud (about 1 cent per search)
WEB_SEARCH = True
WEB_SEARCHES_PER_QUESTION = 3
WEB_LOCATION = {"type": "approximate", "city": "Sydney", "region": "New South Wales",
                "country": "AU", "timezone": "Australia/Sydney"}

# The assistants. Each has a name, a voice and a personality. Say "Hey Joey" or "Hey Ryan".
CHARACTERS = {
    "joey": {
        "name": "Joey",
        "voice": "en_US-lessac-medium",      # female voice
        "personality": "a calm, warm, witty and highly capable personal assistant",
        "greetings": ["Hi, Joey here. How can I help?", "Joey here. What can I do for you?",
                      "Hey, it's Joey. What do you need?"],
    },
    "ryan": {
        "name": "Ryan",
        "voice": "en_US-ryan-medium",        # male voice
        "personality": ("a confident, quick-witted and slightly cheeky personal assistant with dry humour, "
                        "who gets straight to the point"),
        "greetings": ["Ryan here. What do you need?", "Hey, it's Ryan. What's up?",
                      "Ryan on the line. Go ahead."],
    },
}
DEFAULT_CHARACTER = "joey"

COMMON_RULES = f"""Keep replies short and natural (1-3 sentences) unless the user asks for detail,
because your replies are spoken out loud. Don't use markdown, bullet points or emoji.
Use your tools whenever they help answer accurately. Never make up the time or weather.
The user lives in {HOME_CITY}. If they ask about the weather without saying where, use {HOME_CITY}.
For anything current or factual you aren't sure about (scores, news, opening hours, prices, people,
events, facts), use the web_search tool, then give the answer in 1-3 spoken sentences. Never read out
web addresses; you can mention the source by name, like "according to the ABC"."""


def system_prompt_for(key: str) -> str:
    me = CHARACTERS[key]
    others = ", ".join(c["name"] for k, c in CHARACTERS.items() if k != key)
    return (f"You are {me['name']}, {me['personality']}. You share this computer with another assistant, "
            f"{others}; you both work for the same user and share what you know about them. "
            f"Stay in your own character.\n" + COMMON_RULES)


SYSTEM_PROMPT = system_prompt_for(DEFAULT_CHARACTER)


# ---------- Tools: things the assistant can actually do ----------
# Claude reads each function's name, inputs and description (the docstring)
# and decides on its own when to call it.

def get_time() -> str:
    """Get the current local date and time."""
    print("  [checking the time]")
    now = datetime.datetime.now()
    return now.strftime("It is %A, %d %B %Y, %I:%M %p (local time).")


def _fetch_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=10) as resp:
        return json.loads(resp.read().decode())


def get_weather(city: str) -> str:
    """Get the current weather and today's forecast for a city.

    Args:
        city: City name, for example Sydney.
    """
    print(f"  [checking the weather in {city}]")
    try:
        # Open-Meteo is free and needs no API key
        geo = _fetch_json(
            "https://geocoding-api.open-meteo.com/v1/search?"
            + urllib.parse.urlencode({"name": city, "count": 1})
        )
        if not geo.get("results"):
            return f"Couldn't find a place called {city}."
        place = geo["results"][0]
        weather = _fetch_json(
            "https://api.open-meteo.com/v1/forecast?"
            + urllib.parse.urlencode({
                "latitude": place["latitude"],
                "longitude": place["longitude"],
                "current": "temperature_2m,apparent_temperature,wind_speed_10m,precipitation",
                "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max",
                "timezone": "auto",
                "forecast_days": 1,
            })
        )
        cur, day = weather["current"], weather["daily"]
        return (
            f"{place['name']}, {place.get('country', '')}: currently {cur['temperature_2m']}°C "
            f"(feels like {cur['apparent_temperature']}°C), wind {cur['wind_speed_10m']} km/h, "
            f"precipitation {cur['precipitation']} mm. Today: high {day['temperature_2m_max'][0]}°C, "
            f"low {day['temperature_2m_min'][0]}°C, {day['precipitation_probability_max'][0]}% chance of rain."
        )
    except Exception as e:
        return f"Weather lookup failed: {e}"


def open_website(url: str) -> str:
    """Open a website in the user's web browser.

    Args:
        url: The website to open, for example youtube.com.
    """
    print(f"  [opening {url}]")
    if not url.startswith("http"):
        url = "https://" + url
    webbrowser.open(url)
    return f"Opened {url}"


TOOLS = [get_time, get_weather, open_website]

# Step 4: extra powers (apps, music, volume, timers, notes...) from joey_powers.py
try:
    from joey_powers import POWER_TOOLS
    TOOLS += POWER_TOOLS
except ImportError:
    pass

# Step 3 powers: news, calendar and messages from joey_skills.py
try:
    from joey_skills import SKILL_TOOLS
    TOOLS += SKILL_TOOLS
except ImportError:
    pass

# Screen help: look at the screen when asked, from joey_screen.py
try:
    from joey_screen import SCREEN_TOOLS
    TOOLS += SCREEN_TOOLS
except ImportError:
    pass

# Step 5: long-term memory from joey_memory.py
try:
    import joey_memory
    TOOLS += joey_memory.MEMORY_TOOLS
except ImportError:
    joey_memory = None


# ---------- The brain ----------

TOOL_LOOKUP = {}  # tool name -> runnable tool, filled in by Brain


class Brain:
    """Talks to Claude, lets Claude use Joey's tools, and remembers the conversation."""

    def __init__(self, character: str = DEFAULT_CHARACTER):
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise RuntimeError("ANTHROPIC_API_KEY is not set")
        self.character = character
        self.name = CHARACTERS[character]["name"]
        self.client = anthropic.Anthropic(timeout=30)  # reads ANTHROPIC_API_KEY from your environment
        self.tools = [beta_tool(f) for f in TOOLS]
        TOOL_LOOKUP.update({t.name: t for t in self.tools})
        self.tool_schemas = [t.to_dict() for t in self.tools]
        self.web_ok = WEB_SEARCH
        self.last_sources = []  # (title, url) of web pages behind the last answer
        # each character keeps their own recent conversation; facts about the user are shared
        self.history = joey_memory.load_history(character) if joey_memory else []

    def system_prompt(self) -> str:
        # rebuilt each time so newly remembered facts are included
        return system_prompt_for(self.character) + (joey_memory.memory_prompt() if joey_memory else "")

    def run_tool(self, name: str, args: dict):
        try:
            result = TOOL_LOOKUP[name].call(args)
            return result if isinstance(result, list) else str(result)  # a list can include images
        except Exception as e:
            return f"Tool error: {e}"

    def all_tools(self):
        tools = list(self.tool_schemas)
        if self.web_ok:
            tools.append({"type": "web_search_20250305", "name": "web_search",
                          "max_uses": WEB_SEARCHES_PER_QUESTION, "user_location": WEB_LOCATION})
        return tools

    @staticmethod
    def final_answer(content):
        """The spoken answer: the text after the last search, plus the sources it cites."""
        last = -1
        for i, b in enumerate(content):
            if b.type in ("server_tool_use", "web_search_tool_result", "tool_use"):
                last = i
        text, sources = [], []
        for b in content[last + 1:]:
            if b.type == "text":
                text.append(b.text)
                for c in getattr(b, "citations", None) or []:
                    url = getattr(c, "url", None)
                    if url and url not in [u for _, u in sources]:
                        sources.append((getattr(c, "title", "") or url, url))
        return "".join(text).strip(), sources

    def think(self, model: str, user_text: str) -> str:
        """One full turn: Claude may use several tools (and web searches) before the final answer."""
        messages = self.history + [{"role": "user", "content": user_text}]
        self.last_sources = []
        for _ in range(10):  # safety limit on tool steps
            try:
                response = self.client.messages.create(
                    model=model, max_tokens=MAX_REPLY_TOKENS, system=self.system_prompt(),
                    tools=self.all_tools(), messages=messages,
                )
            except anthropic.BadRequestError as e:
                if self.web_ok and "web" in str(e).lower() and "search" in str(e).lower():
                    print(f"  [web search not available ({e}); answering without it]")
                    self.web_ok = False
                    continue
                raise
            if response.stop_reason == "pause_turn":  # a long search: let it carry on
                messages.append({"role": "assistant", "content": response.content})
                continue
            if any(b.type == "server_tool_use" for b in response.content):
                for b in response.content:
                    if b.type == "server_tool_use":
                        print(f"  [searching the web: {b.input.get('query', '')}]")
            if response.stop_reason != "tool_use":
                answer, self.last_sources = self.final_answer(response.content)
                return answer
            messages.append({"role": "assistant", "content": response.content})
            results = [
                {"type": "tool_result", "tool_use_id": b.id, "content": self.run_tool(b.name, b.input)}
                for b in response.content if b.type == "tool_use"
            ]
            messages.append({"role": "user", "content": results})
        return "Sorry, that took too many steps. Can you ask in a simpler way?"

    def remember_turn(self, user_text: str, reply: str):
        self.history += [{"role": "user", "content": user_text},
                         {"role": "assistant", "content": reply or "(no reply)"}]
        if joey_memory:
            self.history = joey_memory.save_history(self.history, self.character)

    def ask(self, text: str) -> str:
        started = time.time()
        print("  [thinking...]")
        for model in [MODEL, BACKUP_MODEL]:
            try:
                reply = self.think(model, text)
                self.remember_turn(text, reply)
                note = f", used backup {model}" if model != MODEL else ""
                print(f"  [answered in {time.time() - started:.1f}s{note}]")
                return reply
            except anthropic.AuthenticationError:
                return "My API key isn't working. Please check the ANTHROPIC_API_KEY setting."
            except anthropic.PermissionDeniedError as e:
                print(f"  [error: {e}]")
                return "My API key doesn't have permission to do that. Please check the Claude Console."
            except anthropic.BadRequestError as e:
                print(f"  [error: {e}]")
                if "credit" in str(e).lower():
                    return "My Claude account is out of credit. Please top it up in the Claude Console."
                return "Sorry, something went wrong with that request."
            except anthropic.RateLimitError:
                print("  [rate limit reached, waiting a moment...]")
                time.sleep(3)
            except (anthropic.InternalServerError, anthropic.APIConnectionError, anthropic.APIStatusError) as e:
                print(f"  [{model} unavailable ({e.__class__.__name__}), trying backup...]")
        return "Claude is very busy right now, or the internet is down. Please try again in a minute."


def main():
    try:
        brain = Brain()
    except Exception:
        print("No API key found. Run:  setx ANTHROPIC_API_KEY \"your-key-here\"")
        print("Then close this window, open a new one, and try again.")
        return

    print(f"{NAME} online. Type 'quit' to exit.\n")
    while True:
        user_text = input("You: ").strip()
        if not user_text:
            continue
        if user_text.lower() in {"quit", "exit", "bye"}:
            print(f"{NAME}: Shutting down. Goodbye.")
            break
        print(f"{NAME}:", brain.ask(user_text))
        for title, url in brain.last_sources[:4]:
            print(f"    source: {title} - {url}")
        print()


if __name__ == "__main__":
    main()
