"""
JOEY & RYAN - wake words (terminal version; joey_app.py is the window version)
They listen quietly in the background. Say "Hey Joey" or "Hey Ryan" and that one answers.
Uses joey.py (brain) and joey_voice.py (ears and mouth) - keep the files in the same folder.

Run:
  python joey_wake.py

How to use:
  - Say "Hey Joey, what's the weather?" or "Hey Ryan, play some music" (all in one go), or
  - Say "Hey Ryan", wait for the beep and "Yes?", then ask.
  - After an answer you can ask a follow-up straight away without saying the name.
    Say the other name to switch, e.g. "Joey, what do you think?"
  - "Go to sleep" sends them back to waiting.  "Shut down" turns them off.  Ctrl+C also quits.
"""

import random
import re
import time

import sounddevice as sd
import speech_recognition as sr

from joey import CHARACTERS, DEFAULT_CHARACTER, NAME, Brain
from joey_voice import LANGUAGE, MIC_DEVICE, measure_background_noise, record_speech, recognizer, speak

# Speech recognition often mishears names, so accept these too
WAKE_WORDS = {
    "joey": ["joey", "joy", "joe", "joie", "joeys", "zoey", "jowey", "jody"],
    "ryan": ["ryan", "rian", "ryann", "rion", "ryans", "ryan's"],
}
FOLLOW_UP_SECONDS = 8  # how long they keep listening for a follow-up after answering

SLEEP_PHRASES = ["go to sleep", "that's all", "thats all", "never mind", "nevermind", "stop listening"]
EXIT_PHRASES = ["shut down", "shutdown", "turn off", "quit", "exit", "goodbye", "good bye"]

WAKE_PATTERNS = {
    key: re.compile(r"\b(" + "|".join(re.escape(w) for w in words) + r")\b[\s,.!?]*", re.IGNORECASE)
    for key, words in WAKE_WORDS.items() if key in CHARACTERS
}


def beep(character: str = DEFAULT_CHARACTER):
    """A short sound so you know they woke up (Ryan's beep is lower)."""
    try:
        import winsound
        winsound.Beep(880 if character == "joey" else 620, 120)
    except Exception:
        print("\a", end="", flush=True)


def hear(threshold: float, wait_seconds: float):
    """Record until you stop talking and turn it into text. Returns None if nothing useful."""
    audio = record_speech(threshold, wait_seconds=wait_seconds, max_seconds=12)
    if audio is None:
        return None
    try:
        return recognizer.recognize_google(audio, language=LANGUAGE)
    except sr.UnknownValueError:
        return None
    except sr.RequestError as e:
        print(f"  [speech service problem: {e}]")
        time.sleep(2)
        return None


def detect_wake(text: str):
    """Which character was called, and what was said after the name.
    Returns (character, command) - command is '' if only the name was said - or None."""
    best = None
    for key, pattern in WAKE_PATTERNS.items():
        m = pattern.search(text)
        if m and (best is None or m.start() < best[1].start()):
            best = (key, m)
    if not best:
        return None
    key, m = best
    return key, text[m.end():].strip()


def after_wake_word(text: str):
    """Older helper: whatever came after any name ('' if nothing), or None."""
    found = detect_wake(text)
    return None if found is None else found[1]


# "switch to Ryan", "let me talk to Joey", "put Ryan on", "pass me to Joey"...
HANDOFF_WORDS = r"(switch|swap|change|hand|pass|put|transfer|talk|speak|bring|connect|give me|get me)"
HANDOFF_PATTERNS = {
    key: re.compile(r"\b" + HANDOFF_WORDS + r"\b(?:\W+\w+){0,4}?\W+(" +
                    "|".join(re.escape(w) for w in words) + r")\b[\s,.!?]*(?:on\b|please\b|now\b)?[\s,.!?]*",
                    re.IGNORECASE)
    for key, words in WAKE_WORDS.items() if key in CHARACTERS
}


def handoff(text: str):
    """If the user asks to switch to the other assistant, return (who, anything said after).
    For example "Joey, switch to Ryan" -> ("ryan", "") and
    "put Ryan on and ask him the score" -> ("ryan", "ask him the score"). Otherwise None."""
    if len(text.split()) > 14:
        return None
    for key, pattern in HANDOFF_PATTERNS.items():
        m = pattern.search(text)
        if m:
            rest = re.sub(r"^(and|then|to)\b[\s,]*", "", text[m.end():].strip(), flags=re.IGNORECASE)
            if rest.lower().strip(" .!?") in {"again", "please", "now", "instead", "back", "for a bit",
                                              "for a sec", "for a second", "for me", "thanks", "thank you"}:
                rest = ""
            return key, rest
    return None


def handoff_lines(old: str, new: str):
    """What the old assistant says, and how the new one greets you."""
    name = CHARACTERS[new]["name"]
    bye = random.choice([f"Sure, here's {name}.", f"Okay, passing you to {name}.", f"Of course. {name}, you're up."])
    hello = random.choice(CHARACTERS[new].get("greetings", [f"Hi, {name} here."]))
    return bye, hello


def says(text: str, phrases) -> bool:
    words = text.lower().strip(" .!?")
    return len(words.split()) <= 5 and any(p in words for p in phrases)


def conversation(brains: dict, character: str, threshold: float, command: str, full: str = "") -> bool:
    """Answer, then keep listening for follow-ups. Returns False if they should shut down."""
    from joey_duet import Duet, duet_request
    full = full or command
    while command:
        import joey_briefing
        if joey_briefing.wants_briefing(command):   # "give me my briefing"
            def say_line(who, text):
                print(f"{CHARACTERS[who]['name']}: {text}")
                speak(text, who)
            character = joey_briefing.run(brains, say_line)
            command = full = hear(threshold, wait_seconds=FOLLOW_UP_SECONDS)
            if command:
                print(f"You: {command}")
            continue
        # "Joey and Ryan, debate ..." -> they talk to each other
        together = duet_request(full) or duet_request(command)
        if together:
            def line(who, text):
                print(f"{CHARACTERS[who]['name']}: {text}")
                speak(text, who)
            transcript = Duet(brains).run(together[0], together[1], character, line)
            if transcript:
                character = transcript[-1][0]
            command = full = hear(threshold, wait_seconds=FOLLOW_UP_SECONDS)
            if command:
                print(f"You: {command}")
            continue
        # "switch to Ryan" / "let me talk to Joey": the other one takes over
        swap = handoff(command)
        if swap:
            target, command = swap
            if target == character:
                speak("I'm right here.", character)
            else:
                bye, hello = handoff_lines(character, target)
                print(f"{CHARACTERS[character]['name']}: {bye}")
                speak(bye, character)
                character = target
                print(f"{CHARACTERS[character]['name']}: {hello}")
                speak(hello, character)
            if not command:
                command = full = hear(threshold, wait_seconds=FOLLOW_UP_SECONDS)
                if command:
                    print(f"You: {command}")
                continue
        # saying the other name mid-conversation hands over to them
        switch = detect_wake(command)
        if switch and switch[1]:
            character, command = switch
        name = CHARACTERS[character]["name"]
        if says(command, EXIT_PHRASES):
            print(f"{name}: Shutting down. Goodbye.")
            speak("Shutting down. Goodbye.", character)
            return False
        if says(command, SLEEP_PHRASES):
            print(f"{name}: Okay.")
            speak("Okay.", character)
            return True
        try:
            reply = brains[character].ask(command)
        except Exception as e:
            reply = "Sorry, something went wrong."
            print(f"  [error: {e}]")
        print(f"{name}: {reply}")
        for title, url in getattr(brains[character], "last_sources", [])[:4]:
            print(f"    source: {title} - {url}")
        print()
        speak(reply, character)

        print("  [still listening for a follow-up...]")
        command = full = hear(threshold, wait_seconds=FOLLOW_UP_SECONDS)
        if command:
            print(f"You: {command}")
    return True


def main():
    try:
        brains = {key: Brain(key) for key in CHARACTERS}
    except Exception:
        print("No API key found. Run:  setx ANTHROPIC_API_KEY \"your-key-here\"")
        print("Then close this window, open a new one, and try again.")
        return

    print("Checking your microphone, stay quiet for a second...")
    try:
        print(f"Using microphone: {sd.query_devices(MIC_DEVICE, 'input')['name']}")
        threshold = measure_background_noise()
    except Exception as e:
        print(f"Couldn't open the microphone: {e}")
        return

    names = " or ".join(f"'Hey {c['name']}'" for c in CHARACTERS.values())
    print(f"\nOnline. Say {names}. Press Ctrl+C to quit.\n")

    def line(who, text):
        print(f"{CHARACTERS[who]['name']}: {text}")
        speak(text, who)

    import joey_briefing
    if joey_briefing.due_today():           # first start of the day: the morning briefing
        try:
            joey_briefing.run(brains, line)
        except Exception as e:
            print(f"  [briefing failed: {e}]")
    else:
        speak(f"{NAME} online.", DEFAULT_CHARACTER)
        for key in CHARACTERS:
            if key != DEFAULT_CHARACTER:
                speak(f"{CHARACTERS[key]['name']} here too.", key)

    try:
        while True:
            print(f"  [sleeping... say {names}]")
            text = hear(threshold, wait_seconds=float("inf"))
            if not text:
                continue
            found = detect_wake(text)
            if found is None:
                continue  # you were talking, but not to them
            character, command = found

            print(f"You: {text}")
            beep(character)
            if not command:  # just "Hey Ryan" on its own
                speak("Yes?", character)
                command = hear(threshold, wait_seconds=6)
                if not command:
                    continue
                print(f"You: {command}")

            if not conversation(brains, character, threshold, command, text):
                break
    except KeyboardInterrupt:
        print("\nShutting down. Goodbye.")


if __name__ == "__main__":
    main()
