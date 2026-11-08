"""
JOEY - lip sync
Turns the sounds Joey is saying (phonemes, with their exact timing from the voice engine)
into mouth shapes, so the lips match the words: "m/b/p" closes the lips, "oo" rounds them,
"ee" spreads them, "ah" opens wide, and so on.
"""

import bisect

# mouth shape = (how open, how wide)   open: 0 closed .. 1 wide open   wide: -1 rounded/pursed .. 1 spread smile
SHAPES = {
    "rest": (0.00, 0.00),
    "MBP": (0.00, -0.05),   # lips pressed together
    "FV": (0.12, 0.05),     # bottom lip under the top teeth
    "TH": (0.20, 0.10),
    "AA": (0.95, 0.20),     # f(a)ther, c(a)t, c(u)t
    "EH": (0.55, 0.40),     # b(e)d, (a)bout
    "EE": (0.28, 0.85),     # s(ee), b(i)t
    "OH": (0.65, -0.55),    # g(o), (o)ff
    "OO": (0.30, -1.00),    # f(oo)d, (w)e
    "SH": (0.22, -0.55),    # (sh)e, (ch)air, (j)ump
    "R": (0.25, -0.45),     # (r)ed
    "L": (0.35, 0.20),      # (l)ight
    "CONS": (0.22, 0.30),   # t, d, n, s, z, k, g, h...
}

PHONEME_SHAPES = {}
for chars, shape in [
    ("pbm", "MBP"), ("fv", "FV"), ("θð", "TH"),
    ("aɑɒæʌɐ", "AA"), ("eɛəɜɚɘᵻ", "EH"), ("iɪjy", "EE"),
    ("oɔ", "OH"), ("uʊwɯ", "OO"), ("ʃʒ", "SH"), ("ɹr", "R"), ("lɫ", "L"),
    ("tdnszkɡgŋhxʔɾç", "CONS"),
]:
    for ch in chars:
        PHONEME_SHAPES[ch] = shape
PAUSES = set(" ^$.,!?;:—-")


def build_track(timeline):
    """timeline: list of (phoneme, start, end) in seconds -> list of (start, end, open, wide)."""
    track = []
    last = SHAPES["rest"]
    last_ph = ""
    for i, (ph, start, end) in enumerate(timeline):
        if ph in ("ˈ", "ˌ"):           # stress mark: a transition into the next sound
            nxt = next((p for p, _, _ in timeline[i + 1:] if p in PHONEME_SHAPES), None)
            target = SHAPES[PHONEME_SHAPES[nxt]] if nxt else last
            if PHONEME_SHAPES.get(last_ph) == "MBP":
                shape = last            # lips stay pressed until the vowel starts
            else:
                shape = ((last[0] + target[0]) / 2, (last[1] + target[1]) / 2)
        elif ph == "ː":                 # long sound: hold the previous shape
            shape = last
        elif ph in PAUSES:
            # short gaps between words: relax, don't snap shut
            shape = SHAPES["rest"] if (end - start) > 0.09 or ph in "^$.!?" else (last[0] * 0.4, last[1] * 0.5)
        else:
            shape = SHAPES[PHONEME_SHAPES.get(ph, "CONS")]
        if PHONEME_SHAPES.get(ph) == "MBP" and track and end - start < 0.07:
            # m, b, p: lips must fully close, and for long enough to see it
            start = max(track[-1][0] + 0.02, end - 0.07)
            track[-1] = (track[-1][0], start, track[-1][2], track[-1][3])
        track.append((start, end, shape[0], shape[1]))
        last = shape
        if ph not in ("ˈ", "ˌ", "ː"):
            last_ph = ph
    return track


class LipSync:
    def __init__(self):
        self.track, self.starts, self.start_time = [], [], 0.0

    def start(self, timeline, start_time):
        self.track = build_track(timeline)
        self.starts = [s for s, _, _, _ in self.track]
        self.start_time = start_time

    def stop(self):
        self.track, self.starts = [], []

    def shape(self, now):
        """Mouth shape (open, wide) right now, blending into the next sound like real speech."""
        if not self.track:
            return None
        t = now - self.start_time
        i = bisect.bisect_right(self.starts, t) - 1
        if i < 0 or t > self.track[-1][1]:
            return (0.0, 0.0)
        start, end, o, w = self.track[i]
        if i + 1 < len(self.track):
            # in the last 40% of a sound, start moving towards the next one
            k = (t - start) / max(end - start, 1e-3)
            if k > 0.6 and o > 0:   # (closed lips stay closed until the sound ends)
                _, _, o2, w2 = self.track[i + 1]
                b = (k - 0.6) / 0.4 * 0.5
                o, w = o + (o2 - o) * b, w + (w2 - w) * b
        return (o, w)
