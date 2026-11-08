"""
JOEY & RYAN - remote conversations (phone app and Telegram)
Works out who should answer a message from your phone and how: a normal answer, switching
between Joey and Ryan, the two of them talking to each other, or the briefing.
"""

import random

import joey_briefing
import joey_powers
from joey import CHARACTERS, DEFAULT_CHARACTER
from joey_duet import duet_request
from joey_wake import detect_wake, handoff

PHONE_NOTE = ("(Message from the user's phone - they may be away from the PC. Don't open apps, websites "
              "or music on the PC unless they ask.) ")


class Router:
    def __init__(self, brains, brain_lock, duet):
        self.brains, self.lock, self.duet = brains, brain_lock, duet
        self.who = DEFAULT_CHARACTER   # who answers by default on this channel

    def handle(self, text, out_line):
        """Answer a message. out_line(who, text, sources) delivers each line of the reply."""
        origin = getattr(joey_powers, "request_origin", None)
        if origin is not None:
            origin.value = "phone"   # reminders set now go back to the phone
        if joey_briefing.wants_briefing(text):
            with self.lock:
                self.who = joey_briefing.run(self.brains, lambda w, t: out_line(w, t, []))
            return
        found = detect_wake(text)
        who, command = (found if found and found[1] else (self.who, text))
        together = duet_request(text)
        if together:
            with self.lock:
                self.duet.run(together[0], together[1], who, lambda w, t: out_line(w, t, []))
            return
        swap = handoff(text)
        if swap:
            who, command = swap
            self.who = who
            if not command:
                greet = random.choice(CHARACTERS[who].get("greetings", [f"{CHARACTERS[who]['name']} here."]))
                out_line(who, greet, [])
                return
        self.who = who
        with self.lock:
            reply = self.brains[who].ask(PHONE_NOTE + command)
            sources = list(getattr(self.brains[who], "last_sources", []))
        out_line(who, reply, sources)
