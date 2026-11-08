"""
JOEY - the app
A window with Joey's animated sci-fi HUD ring (or a hologram head, a face, or an orb) that shows
what Joey is doing.
Say "Hey Joey" as usual, or type in the box at the bottom.

Run:  python joey_app.py   (or double-click "Start Joey.bat" after running setup_autostart.py)
The face needs:  pip install pillow    (without it, Joey shows the orb instead)

HUD ring: dim and slow = sleeping, bright = listening, fast spin with a sweeping light = thinking,
centre pulsing with the voice = talking. Choose the look with AVATAR below. The colour changes too:
  dim blue, slow  = sleeping, waiting for "Hey Joey"
  bright cyan     = listening to you
  purple, spinning = thinking
  green, pulsing  = talking
"""

import math
import os
import queue
import sys
import threading
import time
import tkinter as tk

from joey_lipsync import LipSync

FOLDER = os.path.dirname(os.path.abspath(__file__))
START_TIME = time.time()
KEEP_RUNNING_WHEN_CLOSED = True   # the X button hides Joey instead of shutting her down
INSTANCE_PORT = 8764              # lets a second "Start Joey" just bring back the one already running
SHOW_STARTUP_TIMES = True   # prints how long each startup step takes (to find what's slow)


def step(name):
    if SHOW_STARTUP_TIMES:
        print(f"  [startup {time.time() - START_TIME:5.1f}s] {name}", flush=True)

# With no console window (pythonw), send messages to a log file instead
if sys.stdout is None or sys.stderr is None:
    _log = open(os.path.join(FOLDER, "joey_log.txt"), "a", encoding="utf-8", buffering=1)
    sys.stdout = sys.stderr = _log
    print(f"\n===== Joey started {time.ctime()} =====")

STARTUP_DELAY = 20  # seconds to wait when started automatically with Windows
LIPSYNC_DELAY = 0.05  # seconds; increase a little (e.g. 0.12) if the lips move before the sound
# How Joey looks:
#   "hud"      - sci-fi HUD ring, JARVIS style (default)
#   "hologram" - glowing 3D wireframe head (needs face_mesh.obj in this folder)
#   "face"     - illustrated woman's face
#   "orb"      - simple glowing orb
AVATAR = "hud"

SHOW_FACE = False
if AVATAR == "hud":
    try:
        from PIL import ImageTk

        from joey_hud import H as FACE_H, W as FACE_W, HudRing as Face
        SHOW_FACE = True
    except ImportError as e:
        print(f"HUD unavailable ({e}), showing the orb")
        AVATAR = "orb"
if AVATAR == "hologram" and os.path.exists(os.path.join(FOLDER, "face_mesh.obj")):
    try:
        from PIL import ImageTk

        from joey_holo import H as FACE_H, W as FACE_W, HoloHead as Face
        SHOW_FACE = True
    except ImportError as e:
        print(f"Hologram unavailable ({e}), trying the face")
        AVATAR = "face"
if AVATAR in ("hologram", "face") and not SHOW_FACE:
    try:
        from PIL import ImageTk

        from joey_face import H as FACE_H, W as FACE_W, Face
        AVATAR, SHOW_FACE = "face", True
    except ImportError as e:
        print(f"Face unavailable ({e}), showing the orb")
        AVATAR = "orb"

BG = "#0a0e17"
PANEL = "#121826"
TEXT = "#e8ecf4"
MUTED = "#7d879c"
STATES = {
    #            colour            label                           pulse speed, size
    "starting": ((90, 100, 130),  "Starting up...",               1.0, 0.85),
    "sleeping": ((40, 95, 210),   "Sleeping · say \"Hey Joey\"",   0.6, 0.85),
    "listening": ((0, 200, 255),  "Listening...",                 2.0, 1.0),
    "thinking": ((150, 95, 255),  "Thinking...",                  3.0, 0.95),
    "speaking": ((0, 225, 160),   "Speaking...",                  5.0, 1.0),
    "error":    ((230, 70, 80),   "Something's wrong",            0.8, 0.85),
}

# the HUD/hologram colours: Joey in blue, Ryan in amber/gold
HOLO_COLORS = {"starting": (60, 110, 190), "sleeping": (30, 90, 220), "listening": (40, 200, 255),
               "thinking": (110, 120, 255), "speaking": (70, 185, 255), "error": (230, 80, 90)}
CHARACTER_COLORS = {
    "joey": HOLO_COLORS,
    "ryan": {"starting": (150, 80, 25), "sleeping": (170, 75, 15), "listening": (255, 140, 25),
             "thinking": (255, 90, 40), "speaking": (255, 150, 35), "error": (230, 80, 90)},
}
CHARACTER_ACCENTS = {"joey": (255, 196, 60), "ryan": (90, 210, 255)}  # small details in the other colour


def mix(c1, c2, t):
    return "#%02x%02x%02x" % tuple(int(a + (b - a) * t) for a, b in zip(c1, c2))


def hex_to_rgb(h):
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


class JoeyWindow:
    def __init__(self, name="Joey"):
        self.name = name
        self.events = queue.Queue()  # messages from Joey's background thread
        self.on_typed = None          # set by the app: what to do with typed messages
        self.state = "starting"
        self.character = "joey"       # who is active: changes the colours and the name shown
        self.names = {"joey": "Joey"}
        self.color = STATES["starting"][0]
        self.level = 0.0              # smooth size
        self.speech = (None, 0.0, 0.0)  # loudness-based fallback: (loudness list, seconds per value, start)
        self.lips = LipSync()           # exact lip sync from the sounds being spoken
        self.synthetic = False          # Windows voice: no timing, so use a general talking motion

        self.root = tk.Tk()
        self.root.title(name)
        self.root.configure(bg=BG)
        self.root.geometry("352x600" if SHOW_FACE else "340x500")
        self.root.minsize(300, 440)
        self.root.protocol("WM_DELETE_WINDOW", self.hide if KEEP_RUNNING_WHEN_CLOSED else self.close)
        self.on_hidden = None         # set by the app: what to do the first time the window is hidden
        self.hidden_before = False

        if SHOW_FACE:
            self.face = Face()
            self.photo = ImageTk.PhotoImage("RGB", (FACE_W, FACE_H))
            self.canvas = tk.Label(self.root, image=self.photo, bg=BG, bd=0)
            self.canvas.pack(pady=(12, 0))
        else:
            self.canvas = tk.Canvas(self.root, bg=BG, highlightthickness=0, height=260)
            self.canvas.pack(fill="x", pady=(18, 0))

        self.status = tk.Label(self.root, text="Starting up...", bg=BG, fg=MUTED,
                               font=("Segoe UI", 11))
        self.status.pack(pady=(4, 10))

        convo = tk.Frame(self.root, bg=PANEL, padx=14, pady=10)
        convo.pack(fill="both", expand=True, padx=16)
        self.you_label = tk.Label(convo, text="", bg=PANEL, fg=MUTED, font=("Segoe UI", 10),
                                  justify="left", anchor="w", wraplength=280)
        self.you_label.pack(fill="x")
        self.joey_label = tk.Label(convo, text="", bg=PANEL, fg=TEXT, font=("Segoe UI", 11),
                                   justify="left", anchor="nw", wraplength=280)
        self.joey_label.pack(fill="both", expand=True, pady=(6, 0))
        self.sources_frame = tk.Frame(convo, bg=PANEL)   # clickable links to web sources
        self.sources_frame.pack(fill="x", pady=(4, 0))
        convo.bind("<Configure>", self._rewrap)

        self.entry = tk.Entry(self.root, bg=PANEL, fg=MUTED, insertbackground=TEXT, relief="flat",
                              font=("Segoe UI", 11), highlightthickness=1,
                              highlightbackground="#1f2738", highlightcolor="#3a4a6b")
        self.entry.pack(fill="x", padx=16, pady=14, ipady=8)
        self.placeholder = "Type a message and press Enter..."
        self._show_placeholder()
        self.entry.bind("<FocusIn>", self._clear_placeholder)
        self.entry.bind("<FocusOut>", lambda e: self._show_placeholder() if not self.entry.get() else None)
        self.entry.bind("<Return>", self._send_typed)

        self.root.after(30, self._animate)
        self.root.after(50, self._process_events)

    # ----- called from Joey's background thread (safe) -----
    def set_state(self, state):
        self.events.put(("state", state))

    def you(self, text):
        self.events.put(("you", text))

    def joey(self, text):
        self.events.put(("joey", text))

    def sources(self, items):
        """Show the web pages an answer came from, as clickable links."""
        self.events.put(("sources", list(items or [])))

    def set_character(self, key, name=None):
        if name:
            self.names[key] = name
        self.events.put(("character", key))

    def error(self, text):
        self.events.put(("state", "error"))
        self.events.put(("joey", text))

    def quit(self):
        self.events.put(("quit", None))

    def lipsync(self, envelope, step, phonemes=None):
        """Called the moment the voice starts playing: only now does the mouth start moving."""
        now = time.time() + LIPSYNC_DELAY
        self.speech = (envelope, step, now)
        self.synthetic = not envelope and not phonemes
        if phonemes:
            self.lips.start(phonemes, now)
        else:
            self.lips.stop()
        self.events.put(("state", "speaking"))

    # ----- window internals -----
    def _show_sources(self, items):
        import webbrowser
        from urllib.parse import urlparse
        for w in self.sources_frame.winfo_children():
            w.destroy()
        if not items:
            return
        tk.Label(self.sources_frame, text="Sources:", bg=PANEL, fg=MUTED,
                 font=("Segoe UI", 9)).pack(side="left")
        for title, url in items[:4]:
            site = urlparse(url).netloc.replace("www.", "") or title
            link = tk.Label(self.sources_frame, text=site, bg=PANEL, fg="#6fb6ff", cursor="hand2",
                            font=("Segoe UI", 9, "underline"))
            link.pack(side="left", padx=(6, 0))
            link.bind("<Button-1>", lambda e, u=url: webbrowser.open(u))

    def _show_status(self):
        label = STATES[self.state][1]
        if self.state not in ("starting", "error"):
            if self.state == "sleeping":
                names = " or ".join(f"\"Hey {n}\"" for n in self.names.values())
                label = f"Sleeping · say {names}"
            else:
                label = f"{self.names.get(self.character, '')} · {label}"
        self.status.config(text=label)

    def _process_events(self):
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == "state":
                    self.state = value
                    self._show_status()
                elif kind == "character":
                    self.character = value
                    if hasattr(self.face, "accent") if SHOW_FACE else False:
                        self.face.accent = CHARACTER_ACCENTS.get(value, self.face.accent)
                    self._show_status()
                elif kind == "you":
                    self.you_label.config(text=f"You: {value}")
                    self.joey_label.config(text="")
                    self._show_sources([])
                elif kind == "joey":
                    self.joey_label.config(text=value)
                elif kind == "sources":
                    self._show_sources(value)
                elif kind == "show":
                    self._show_window()
                elif kind == "quit":
                    self.close()
                    return
        except queue.Empty:
            pass
        self.root.after(50, self._process_events)

    def _mouth_target(self, t):
        """Mouth shape right now: (how open 0..1, how wide -1 rounded .. 1 spread)."""
        if self.state != "speaking":
            return (0.0, 0.0)
        shape = self.lips.shape(t)  # exact: the right shape for each sound
        if shape is not None:
            return shape
        envelope, step, start = self.speech
        if envelope:  # fallback: follow the loudness of the voice
            i = int((t - start) / step)
            return (envelope[i] * 0.8 if 0 <= i < len(envelope) else 0.0, 0.15)
        if self.synthetic:  # Windows voice: general talking movement
            return (max(0.0, math.sin(t * 13) * 0.4 + math.sin(t * 5.3) * 0.25 + 0.15), 0.15)
        return (0.0, 0.0)   # no sound playing yet: keep the mouth closed

    def _animate(self):
        if SHOW_FACE:
            target_color, _, speed, _ = STATES[self.state]
            if AVATAR in ("hologram", "hud"):
                palette = CHARACTER_COLORS.get(self.character, HOLO_COLORS)
                target_color = palette.get(self.state, target_color)
            self.color = tuple(c + (tc - c) * 0.08 for c, tc in zip(self.color, target_color))
            t = time.time()
            glow = (math.sin(t * min(speed, 2.5)) + 1) / 2
            frame = self.face.render(self.state, t, tuple(int(c) for c in self.color), glow,
                                     self._mouth_target(t))
            self.photo.paste(frame)
            spent = int((time.time() - t) * 1000)
            self.root.after(max(10, 36 - spent), self._animate)  # about 28 frames a second
            return
        target_color, _, speed, size = STATES[self.state]
        # glide smoothly between colours and sizes
        self.color = tuple(c + (t - c) * 0.08 for c, t in zip(self.color, target_color))
        self.level += (size - self.level) * 0.08
        t = time.time()
        pulse = (math.sin(t * speed) + 1) / 2

        c = self.canvas
        c.delete("all")
        w = max(c.winfo_width(), 1)
        cx, cy = w / 2, 130
        core = (52 + 8 * pulse) * self.level
        bg = hex_to_rgb(BG)

        # outer glow: rings fading into the background
        rings = 16
        for i in range(rings, 0, -1):
            r = core + i * 4.2
            fade = (i / rings) ** 0.7
            c.create_oval(cx - r, cy - r, cx + r, cy + r, outline="",
                          fill=mix(self.color, bg, 0.55 + 0.45 * fade))
        # core with a bright centre
        for i in range(8, 0, -1):
            r = core * i / 8
            c.create_oval(cx - r, cy - r, cx + r, cy + r, outline="",
                          fill=mix(self.color, (255, 255, 255), (1 - i / 8) * 0.55))

        if self.state == "thinking":  # spinning arcs
            r = core + 24
            for k in range(3):
                start = (t * 220 + k * 120) % 360
                c.create_arc(cx - r, cy - r, cx + r, cy + r, start=start, extent=50,
                             style="arc", width=3, outline=mix(self.color, (255, 255, 255), 0.35))
        if self.state == "listening":  # expanding ripple
            r = core + 10 + (t * 40 % 40)
            c.create_oval(cx - r, cy - r, cx + r, cy + r, width=2,
                          outline=mix(self.color, bg, (r - core - 10) / 40))

        self.root.after(33, self._animate)

    def _rewrap(self, event):
        width = max(event.width - 30, 100)
        self.you_label.config(wraplength=width)
        self.joey_label.config(wraplength=width)

    def _show_placeholder(self):
        self.entry.delete(0, "end")
        self.entry.insert(0, self.placeholder)
        self.entry.config(fg=MUTED)

    def _clear_placeholder(self, _event=None):
        if self.entry.get() == self.placeholder:
            self.entry.delete(0, "end")
            self.entry.config(fg=TEXT)

    def _send_typed(self, _event=None):
        text = self.entry.get().strip()
        if not text or text == self.placeholder:
            return
        self.entry.delete(0, "end")
        if self.on_typed:
            self.on_typed(text)

    def show(self):
        """Bring the window back (safe from any thread)."""
        self.events.put(("show", None))

    def hide(self):
        self.root.withdraw()
        print("  [Joey is still running in the background - open her again, say \"Hey Joey\", "
              "or say/type \"shut down\" to quit]")
        if not self.hidden_before and self.on_hidden:
            self.hidden_before = True
            threading.Thread(target=self.on_hidden, daemon=True).start()

    def _show_window(self):
        self.root.deiconify()
        self.root.lift()
        self.root.attributes("-topmost", True)                         # pop in front of other windows,
        self.root.after(300, lambda: self.root.attributes("-topmost", False))  # then behave normally
        self.root.focus_force()

    def close(self):
        try:
            self.root.destroy()
        finally:
            os._exit(0)  # also stops the microphone thread

    def run(self):
        self.root.mainloop()


# ---------- Joey's brain, ears and mouth, running in the background ----------

def start_joey(ui: JoeyWindow):
    step("window open, loading Joey's parts")
    from joey import CHARACTERS, DEFAULT_CHARACTER, Brain
    import joey_voice
    from joey_voice import measure_background_noise, speak
    from joey_wake import (EXIT_PHRASES, FOLLOW_UP_SECONDS, SLEEP_PHRASES, beep, detect_wake,
                           handoff, handoff_lines, hear, says)
    import joey_powers
    from joey_duet import STOP_PHRASES, Duet, duet_request
    import joey_briefing

    brain_lock = threading.Lock()
    mode = {"voice": "sleeping"}               # what the voice loop is currently doing
    current = {"who": DEFAULT_CHARACTER}       # who answered last (typed messages go to them)

    def switch_to(key):
        current["who"] = key
        ui.set_character(key, CHARACTERS[key]["name"])

    def say(text, who=None):
        who = who or current["who"]
        ui.joey(f"{CHARACTERS[who]['name']}: {text}")
        speak(text, who)  # the display switches to "speaking" when the sound actually starts

    def respond(command, who):
        switch_to(who)
        ui.set_state("thinking")
        with brain_lock:
            reply = brains[who].ask(command)
            found = getattr(brains[who], "last_sources", [])
        ui.joey(f"{CHARACTERS[who]['name']}: {reply}")
        ui.sources(found)
        speak(reply, who)

    def hand_over(target):
        """The current assistant passes you to the other one, who greets you. Returns who is active now."""
        old = current["who"]
        if target == old:
            say("I'm right here.", old)
            return old
        bye, hello = handoff_lines(old, target)
        ui.set_state("speaking")
        say(bye, old)
        switch_to(target)
        say(hello, target)
        return target

    def duet_line(who, line):
        switch_to(who)
        ui.joey(f"{CHARACTERS[who]['name']}: {line}")
        ui.sources([])
        speak(line, who)

    def run_duet(topic, mode, starter):
        """Joey and Ryan talk to each other. Returns whoever spoke last."""
        with brain_lock:
            transcript = duet.run(topic, mode, starter, duet_line)
        return transcript[-1][0] if transcript else starter

    def announce(text):  # timers and reminders, said by whoever is active
        ui.you("(reminder)")
        say(text)
        ui.set_state(mode["voice"])

    def typed(text):
        if duet.running and says(text, STOP_PHRASES):   # "stop" cuts their conversation short
            duet.stop()
            return
        ui.you(text)
        found = detect_wake(text)               # "Ryan, ..." or "Joey, ..." picks who answers
        who, command = (found if found and found[1] else (current["who"], text))

        def work():
            nonlocal who, command
            if joey_briefing.wants_briefing(text):     # "give me my briefing"
                ui.set_state("thinking")
                with brain_lock:
                    joey_briefing.run(brains, duet_line)
                ui.set_state(mode["voice"])
                return
            together = duet_request(text)       # "you two debate ..." -> they talk to each other
            if together:
                run_duet(together[0], together[1], who)
                ui.set_state(mode["voice"])
                return
            swap = handoff(text)                # "switch to Ryan" / "let me talk to Joey"
            if swap:
                with brain_lock:
                    who = hand_over(swap[0])
                command = swap[1]
                if not command:
                    ui.set_state(mode["voice"])
                    return
            if says(command, EXIT_PHRASES):
                say("Shutting down. Goodbye.", who)
                ui.quit()
                return
            respond(command, who)
            ui.set_state(mode["voice"])

        threading.Thread(target=work, daemon=True).start()

    # Start loading the voices straight away, each in its own thread, while everything else gets ready.
    # Only the talking-face looks need the slower sound-by-sound voice timing.
    joey_voice.SOUND_TIMING = AVATAR in ("hologram", "face")

    def preload(key):
        try:
            joey_voice._load_piper(CHARACTERS[key]["voice"])
            step(f"{CHARACTERS[key]['name']}'s voice loaded")
        except Exception as e:
            print(f"Couldn't preload a voice: {e}")

    first_voice = None
    if joey_voice.USE_NATURAL_VOICE:
        for key in CHARACTERS:
            t = threading.Thread(target=preload, args=(key,), daemon=True)
            t.start()
            if key == DEFAULT_CHARACTER:
                first_voice = t

    try:
        brains = {key: Brain(key) for key in CHARACTERS}
    except Exception:
        ui.error('No Claude API key found. Run:  setx ANTHROPIC_API_KEY "your-key"  then restart.')
        return
    step("brains ready")
    duet = Duet(brains)
    for key in CHARACTERS:
        ui.set_character(key, CHARACTERS[key]["name"])
    switch_to(DEFAULT_CHARACTER)

    try:
        threshold = measure_background_noise()
    except Exception as e:
        ui.error(f"Couldn't open the microphone: {e}")
        return
    step("microphone ready")

    joey_powers.announce = announce
    joey_voice.on_speech = ui.lipsync  # the display follows the voice
    ui.on_hidden = lambda: say("I'll keep running in the background. Just say Hey Joey when you need me.",
                               current["who"])
    ui.on_typed = typed
    start_phone_link(ui, brains, brain_lock, duet, CHARACTERS, DEFAULT_CHARACTER)
    start_phone_app(ui, brains, brain_lock, duet)
    step("phone links started")
    if first_voice:
        first_voice.join()       # Joey's voice is ready: she can talk now
    if joey_briefing.due_today():          # first start of the day: the morning briefing
        step("making the morning briefing")
        try:
            ui.set_state("thinking")
            with brain_lock:
                joey_briefing.run(brains, duet_line)
        except Exception as e:
            print(f"Briefing failed: {e}")
            say(f"{CHARACTERS[DEFAULT_CHARACTER]['name']} online.", DEFAULT_CHARACTER)
    else:
        step("saying hello")
        say(f"{CHARACTERS[DEFAULT_CHARACTER]['name']} online.", DEFAULT_CHARACTER)
        step("hello finished")
        for key in CHARACTERS:
            if key != DEFAULT_CHARACTER:
                switch_to(key)
                say(f"{CHARACTERS[key]['name']} here too.", key)
    switch_to(DEFAULT_CHARACTER)

    while True:
        mode["voice"] = "sleeping"
        ui.set_state("sleeping")
        text = hear(threshold, wait_seconds=float("inf"))
        if not text:
            continue
        found = detect_wake(text)
        if found is None:
            continue
        who, command = found
        switch_to(who)
        ui.show()                                 # "Hey Joey" brings the window back if it was hidden

        ui.you(text)
        beep(who)
        mode["voice"] = "listening"
        if not command:
            say("Yes?", who)
            ui.set_state("listening")
            command = hear(threshold, wait_seconds=6)
            if not command:
                continue
            ui.you(command)

        full = text  # the whole sentence, e.g. "Joey and Ryan, debate ..."
        while command:
            if joey_briefing.wants_briefing(command):   # "give me my briefing"
                ui.set_state("thinking")
                with brain_lock:
                    who = joey_briefing.run(brains, duet_line)
                ui.set_state("listening")
                command = full = hear(threshold, wait_seconds=FOLLOW_UP_SECONDS)
                if command:
                    ui.you(command)
                continue
            together = duet_request(full) or duet_request(command)
            if together:                          # they talk to each other
                who = run_duet(together[0], together[1], who)
                ui.set_state("listening")
                command = full = hear(threshold, wait_seconds=FOLLOW_UP_SECONDS)
                if command:
                    ui.you(command)
                continue
            swap = handoff(command)               # "switch to Ryan" / "let me talk to Joey"
            if swap:
                who = hand_over(swap[0])
                command = swap[1]
                if not command:                   # keep listening, now to the new one
                    ui.set_state("listening")
                    command = full = hear(threshold, wait_seconds=FOLLOW_UP_SECONDS)
                    if command:
                        ui.you(command)
                    continue
            again = detect_wake(command)          # "Joey, ..." mid-conversation hands over
            if again and again[1]:
                who, command = again
            if says(command, EXIT_PHRASES):
                say("Shutting down. Goodbye.", who)
                ui.quit()
                return
            if says(command, SLEEP_PHRASES):
                say("Okay.", who)
                break
            respond(command, who)
            ui.set_state("listening")
            command = full = hear(threshold, wait_seconds=FOLLOW_UP_SECONDS)
            if command:
                ui.you(command)


def start_phone_link(ui, brains, brain_lock, duet, CHARACTERS, DEFAULT_CHARACTER):
    """Joey & Ryan by Telegram (set up with setup_telegram.py)."""
    try:
        import joey_telegram
        from joey_remote import Router
    except ImportError:
        return
    config = joey_telegram.load_config()
    if not config:
        return
    import joey_powers

    router = Router(brains, brain_lock, duet)

    def out_line(who, text, sources):
        name = CHARACTERS[who]["name"]
        message = f"{name}: {text}"
        if sources:
            message += "\n\nSources:\n" + "\n".join(f"• {title}: {url}" for title, url in sources[:4])
        link.send(message)
        if hasattr(link, "say"):
            link.say(text, who)   # also as a voice note, when you sent one
        ui.joey(f"📱 {name}: {text}")

    def on_message(text):
        ui.you(f"📱 {text}")
        link.typing()
        router.handle(text, out_line)

    link = joey_telegram.TelegramLink(config, on_message)
    joey_powers.notify_phone = link.send
    link.start()


def start_phone_app(ui, brains, brain_lock, duet):
    """Joey & Ryan in the phone app (set up with setup_phone.py)."""
    try:
        import joey_phone
    except ImportError:
        return
    if not joey_phone.load_config():
        print("Phone app not set up (run setup_phone.py to talk to Joey & Ryan from your phone).")
        return
    try:
        joey_phone.start(ui, brains, brain_lock, duet)
    except Exception as e:
        print(f"Phone app couldn't start: {e}")


def already_running():
    """If Joey is already running, ask her to show herself and return True."""
    import socket
    try:
        with socket.create_connection(("127.0.0.1", INSTANCE_PORT), timeout=1) as s:
            s.sendall(b"show")
        return True
    except OSError:
        return False


def listen_for_reopen(ui):
    """When you start Joey again while she's running, just bring the window back."""
    import socket
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        server.bind(("127.0.0.1", INSTANCE_PORT))   # this PC only
    except OSError:
        return
    server.listen(2)

    def loop():
        while True:
            try:
                conn, _ = server.accept()
                with conn:
                    if conn.recv(16) == b"show":
                        ui.show()
            except OSError:
                time.sleep(1)

    threading.Thread(target=loop, daemon=True).start()


def tray_icon(ui):
    """A small Joey icon by the clock: click to open, right-click to quit (needs: pip install pystray)."""
    try:
        import pystray
        from PIL import Image, ImageDraw
    except ImportError:
        return
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([4, 4, 60, 60], outline=(90, 190, 255, 255), width=6)
    d.ellipse([22, 22, 42, 42], fill=(220, 240, 255, 255))
    menu = pystray.Menu(pystray.MenuItem("Open Joey", lambda: ui.show(), default=True),
                        pystray.MenuItem("Quit Joey", lambda icon: (icon.stop(), ui.quit())))
    try:
        pystray.Icon("joey", img, "Joey & Ryan", menu).run_detached()
    except Exception as e:
        print(f"  [tray icon unavailable: {e}]")


def main():
    if already_running():          # Joey is already running in the background: she just pops up
        return
    ui = JoeyWindow("Joey & Ryan")
    listen_for_reopen(ui)
    tray_icon(ui)

    def background():
        try:
            if "--startup" in sys.argv:  # started with Windows: give the internet and mic time to wake up
                time.sleep(STARTUP_DELAY)
            start_joey(ui)
        except Exception as e:
            print(f"Joey crashed: {e}")
            ui.error(f"Joey hit a problem: {e}")

    threading.Thread(target=background, daemon=True).start()
    ui.run()


if __name__ == "__main__":
    main()
