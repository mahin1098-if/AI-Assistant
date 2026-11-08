"""
JOEY & RYAN - talking to each other
Ask them to debate, brainstorm or chat about something and they'll go back and forth out loud.

  "Joey and Ryan, debate whether cats are better than dogs"
  "You two brainstorm names for my cafe"
  "Ryan, talk with Joey about the best holiday spots"

Say or type "stop" to cut them off.
"""

import re
import threading
from concurrent.futures import ThreadPoolExecutor

from joey import CHARACTERS, MODEL

TURNS = 6            # lines in total (3 each)
LINE_TOKENS = 160

STOP_PHRASES = ["stop", "enough", "that's enough", "thats enough", "ok stop", "okay stop", "shut up",
                "be quiet", "quiet"]

_TOGETHER = (r"(each other|one another|together|you two|both of you|you both|between (yourselves|you)|"
             r"with (joey|joy|ryan|rian)|(joey|joy) and (ryan|rian)|(ryan|rian) and (joey|joy)|you guys)")
_VERBS = r"(debate|argue|discuss|brainstorm|talk|chat|have a (chat|conversation|debate)|come up with)"
_DUET = re.compile(r"\b" + _VERBS + r"\b", re.IGNORECASE)
_TOGETHER_RE = re.compile(r"\b" + _TOGETHER + r"\b", re.IGNORECASE)


def duet_request(text: str):
    """If the user wants them to talk to each other, return (topic, mode). Otherwise None.
    mode is "debate", "brainstorm" or "chat"."""
    verb = _DUET.search(text)
    if not verb or not _TOGETHER_RE.search(text):
        return None
    low = text.lower()
    mode = ("debate" if re.search(r"\b(debate|argue)\b", low)
            else "brainstorm" if re.search(r"\b(brainstorm|ideas|come up with)\b", low) else "chat")
    # the topic is what comes after the verb, minus "with each other", "about", etc.
    topic = _TOGETHER_RE.sub(" ", text[verb.end():])
    lead = re.compile(r"^\W*(with|and|to|about|on|over|regarding|for a bit|for a while)\b\s*", re.IGNORECASE)
    while lead.match(topic):
        topic = lead.sub("", topic, count=1)
    topic = re.sub(r"\s+", " ", topic).strip(" ,.!?")
    return (topic or "anything you like"), mode


def _instructions(mode, me, other, starter):
    if mode == "debate":
        side = "FOR it (agree)" if me == starter else "AGAINST it (disagree)"
        return (f"This is a friendly debate. You argue {side}. Make one sharp point per line and push back "
                f"on what {other} just said. Keep it playful.")
    if mode == "brainstorm":
        return (f"You're brainstorming together. Each line adds one concrete new idea, building on or "
                f"twisting what {other} said. Be specific.")
    return f"Have a natural, fun conversation. React to what {other} just said and add something of your own."


class Duet:
    def __init__(self, brains: dict):
        self.brains = brains
        self.stop_event = threading.Event()
        self.running = False

    def stop(self):
        self.stop_event.set()

    def _line(self, who, other, topic, mode, starter, transcript, last):
        me, them = CHARACTERS[who]["name"], CHARACTERS[other]["name"]
        so_far = "\n".join(f"{CHARACTERS[w]['name']}: {t}" for w, t in transcript) or "(nobody has spoken yet; you start)"
        ending = (" This is the final line: wrap it up in one sentence and ask the user what they think."
                  if last else "")
        prompt = (f"You and {them} are talking out loud in front of the user. Topic: \"{topic}\".\n"
                  f"{_instructions(mode, who, them, starter)}\n\nConversation so far:\n{so_far}\n\n"
                  f"Now give your next line as {me}: 1-2 short spoken sentences, in your own personality. "
                  f"No stage directions, no quotation marks, don't start with your name.{ending}")
        brain = self.brains[who]
        reply = brain.client.messages.create(
            model=MODEL, max_tokens=LINE_TOKENS, system=brain.system_prompt(),
            messages=[{"role": "user", "content": prompt}])
        text = "".join(b.text for b in reply.content if b.type == "text").strip()
        return re.sub(rf"^\s*{me}\s*:\s*", "", text).strip('" ')

    def run(self, topic, mode, starter, speak_line, turns=TURNS):
        """speak_line(who, text) shows and says a line. Returns the transcript."""
        other = next(k for k in CHARACTERS if k != starter)
        order = [starter, other]
        transcript = []
        self.stop_event.clear()
        self.running = True
        print(f"  [{mode}: {topic}]")
        try:
            with ThreadPoolExecutor(max_workers=1) as pool:
                def make(i):
                    who = order[i % 2]
                    return who, self._line(who, order[(i + 1) % 2], topic, mode, starter,
                                           list(transcript), i == turns - 1)
                job = pool.submit(make, 0)
                for i in range(turns):
                    who, line = job.result()
                    if self.stop_event.is_set() or not line:
                        break
                    transcript.append((who, line))
                    if i + 1 < turns:
                        job = pool.submit(make, i + 1)   # prepare the next line while this one is spoken
                    speak_line(who, line)
                    if self.stop_event.is_set():
                        break
        except Exception as e:
            print(f"  [conversation stopped: {e}]")
        finally:
            self.running = False
        # both of them remember the conversation, so you can ask about it afterwards
        if transcript:
            text = "\n".join(f"{CHARACTERS[w]['name']}: {t}" for w, t in transcript)
            for key, brain in self.brains.items():
                partner = next(CHARACTERS[k]["name"] for k in CHARACTERS if k != key)
                try:
                    brain.remember_turn(f"(Please {mode} with {partner} about: {topic})", text[:1500])
                except Exception:
                    pass
        return transcript
