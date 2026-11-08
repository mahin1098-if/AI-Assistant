"""
JOEY - HUD ring
A sci-fi heads-up-display ring (JARVIS style): rotating rings, tick marks, a glowing segmented
arc, a yellow accent and a sphere of light points in the middle that pulses with Joey's voice.
Used by joey_app.py. Needs:  pip install pillow numpy
"""

import math
import random

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter

W, H = 320, 340
BG = (10, 14, 23)          # same as the app window
ACCENT = (255, 196, 60)    # the yellow details
SS = 2                     # draw at double size, then shrink, for smooth circles
CX, CY = W / 2, H / 2 - 4


def scale_col(c, f):
    return tuple(max(0, min(255, int(v * f))) for v in c)


class HudRing:
    def __init__(self):
        rng = np.random.default_rng(7)
        # sphere of points in the middle
        n = 850
        k = np.arange(n) + 0.5
        phi = np.arccos(1 - 2 * k / n)
        theta = math.pi * (1 + 5 ** 0.5) * k
        self.sphere = np.column_stack([np.cos(theta) * np.sin(phi), np.cos(phi), np.sin(theta) * np.sin(phi)])
        self.sphere += rng.normal(0, 0.03, self.sphere.shape)
        # constellation around the ring
        m = 120
        ang = rng.uniform(0, 2 * math.pi, m)
        rad = rng.uniform(138, 168, m) * np.where(rng.random(m) < 0.3, 1.0, rng.uniform(0.98, 1.1, m))
        self.stars = np.column_stack([ang, rad, rng.uniform(0, 6.28, m)])
        pos = np.column_stack([np.cos(ang) * rad, np.sin(ang) * rad])
        links = []
        for i in range(m):
            d = np.linalg.norm(pos - pos[i], axis=1)
            for j in np.argsort(d)[1:3]:
                if d[j] < 26 and i < j:
                    links.append((i, j))
        self.links = links
        self.speed = 0.3
        self.angle = {"outer": 0.0, "ticks": 0.0, "bar": 0.0, "accent": 0.0, "sphere": 0.0, "stars": 0.0}
        self.level = 0.3          # how full the segmented arc is
        self.pulse = 0.0          # voice pulse
        self.bright = 0.6
        self.last_t = None
        self.background = Image.new("RGB", (W, H), BG)
        self.accent = ACCENT

    # ---------- drawing helpers (in double-size coordinates) ----------
    @staticmethod
    def _arc(d, r, a0, a1, col, width):
        s = SS
        box = [(CX - r) * s, (CY - r) * s, (CX + r) * s, (CY + r) * s]
        d.arc(box, a0, a1, fill=col, width=max(1, int(width * s)))

    @staticmethod
    def _segment(d, r0, r1, a0, a1, col):
        s = SS
        steps = max(2, int(abs(a1 - a0) / 2))
        outer = [((CX + r1 * math.cos(math.radians(a0 + (a1 - a0) * i / steps))) * s,
                  (CY + r1 * math.sin(math.radians(a0 + (a1 - a0) * i / steps))) * s) for i in range(steps + 1)]
        inner = [((CX + r0 * math.cos(math.radians(a1 - (a1 - a0) * i / steps))) * s,
                  (CY + r0 * math.sin(math.radians(a1 - (a1 - a0) * i / steps))) * s) for i in range(steps + 1)]
        d.polygon(outer + inner, fill=col)

    @staticmethod
    def _tick(d, r0, r1, a, col, width=1):
        s, ca, sa = SS, math.cos(math.radians(a)), math.sin(math.radians(a))
        d.line([((CX + r0 * ca) * s, (CY + r0 * sa) * s), ((CX + r1 * ca) * s, (CY + r1 * sa) * s)],
               fill=col, width=max(1, int(width * s)))

    def render(self, state, t, color, glow, mouth_target):
        if isinstance(mouth_target, (tuple, list)):
            voice = float(mouth_target[0])
        else:
            voice = float(mouth_target)
        if state != "speaking":
            voice = 0.0
        dt = 0.035 if self.last_t is None else max(0.0, min(0.1, t - self.last_t))
        self.last_t = t

        # mood
        speed, level, bright = {
            "sleeping": (0.25, 0.25, 0.5), "listening": (0.8, 0.55, 1.0),
            "thinking": (2.2, 0.7, 0.9), "speaking": (0.9, 0.5, 1.0),
        }.get(state, (0.4, 0.3, 0.6))
        self.speed += (speed - self.speed) * 0.05
        self.bright += (bright - self.bright) * 0.06
        if state == "speaking":
            level = 0.35 + 0.6 * voice
        elif state == "listening":
            level += 0.06 * math.sin(t * 6)
        self.level += (level - self.level) * 0.25
        self.pulse += (voice - self.pulse) * 0.5

        sp = self.speed * dt
        self.angle["outer"] += 8 * sp
        self.angle["ticks"] -= 14 * sp
        self.angle["bar"] += 5 * sp
        self.angle["accent"] -= 22 * sp
        self.angle["sphere"] += 0.6 * sp
        self.angle["stars"] += 1.5 * sp

        b = self.bright * (0.85 + 0.15 * glow)
        col = tuple(color)
        light = tuple(min(255, int(v + 110)) for v in col)

        big = (W * SS, H * SS)
        lines = Image.new("RGB", big)
        d = ImageDraw.Draw(lines)
        fill_layer = Image.new("RGB", big)
        f = ImageDraw.Draw(fill_layer)

        # outer constellation
        st = self.stars
        ang = st[:, 0] + math.radians(self.angle["stars"])
        px = CX + np.cos(ang) * st[:, 1]
        py = CY + np.sin(ang) * st[:, 1]
        tw = 0.45 + 0.55 * np.sin(t * 1.7 + st[:, 2]) ** 2
        for i, j in self.links:
            d.line([(px[i] * SS, py[i] * SS), (px[j] * SS, py[j] * SS)], fill=scale_col(col, 0.22 * b))
        for i in range(len(px)):
            r = 1.2 * SS
            d.ellipse([px[i] * SS - r, py[i] * SS - r, px[i] * SS + r, py[i] * SS + r],
                      fill=scale_col(light, 0.7 * b * tw[i]))
        # faint dotted circle
        for a in range(0, 360, 4):
            aa = a + self.angle["stars"] * 0.5
            if (a // 40) % 3 == 2:
                continue
            x, y = CX + 150 * math.cos(math.radians(aa)), CY + 150 * math.sin(math.radians(aa))
            d.ellipse([(x - 0.7) * SS, (y - 0.7) * SS, (x + 0.7) * SS, (y + 0.7) * SS], fill=scale_col(light, 0.5 * b))

        # outer bracket ring: thick segments with notches
        o = self.angle["outer"]
        for k in range(4):
            a0 = o + k * 90 + 6
            self._arc(d, 128, a0, a0 + 66, scale_col(col, 0.95 * b), 4)
            self._arc(d, 133, a0 + 70, a0 + 82, scale_col(col, 0.8 * b), 3)
            self._tick(d, 122, 134, a0 + 66, scale_col(col, 0.9 * b), 2)
        self._arc(d, 121, o * -0.5, o * -0.5 + 360, scale_col(col, 0.35 * b), 1)
        # little bar stacks on the ring, like the picture
        for k in range(2):
            base = o + 180 * k + 30
            for m in range(5):
                self._tick(d, 131, 138, base + m * 2.2, scale_col(light, 0.8 * b), 1.4)

        # tick ring
        tk = self.angle["ticks"]
        for i in range(72):
            a = tk + i * 5
            long = i % 6 == 0
            self._tick(d, 108 if long else 111, 117, a, scale_col(col, (0.9 if long else 0.55) * b), 1.3 if long else 1)

        # segmented arc (the blue bar) - how full shows activity / voice level
        bar0 = 200 + self.angle["bar"] * 0.3
        span = 70 + 250 * self.level
        seg = 9
        nseg = int(span // seg)
        sweep = (t * 120 * self.speed) % 360 if state == "thinking" else None
        for i in range(nseg):
            a0 = bar0 + i * seg
            hl = 1.0
            if sweep is not None:
                dist = abs(((a0 - bar0) - sweep * span / 360 + 180) % 360 - 180)
                hl = 1.0 + 1.2 * max(0.0, 1 - dist / 30)
            self._segment(f, 86, 104, a0, a0 + seg - 1.2, scale_col(col, 0.30 * b * hl))
            self._arc(d, 104, a0, a0 + seg - 1.2, scale_col(light, 0.55 * b * hl), 1)
        # yellow accent arc and dots
        ac = self.angle["accent"]
        self._arc(d, 81, ac + 150, ac + 215, scale_col(self.accent, 0.95 * b), 2)
        self._arc(d, 78, ac + 150, ac + 160, scale_col(self.accent, 0.8 * b), 2)
        self._tick(d, 74, 84, ac + 215, scale_col(self.accent, 0.9 * b), 2)
        for k in range(5):
            a = math.radians(-115 + k * 9 + ac * 0.2)
            x, y = CX + 96 * math.cos(a), CY + 96 * math.sin(a)
            d.ellipse([(x - 1.6) * SS, (y - 1.6) * SS, (x + 1.6) * SS, (y + 1.6) * SS], fill=scale_col(self.accent, b))

        # inner bright ring (pulses with the voice)
        ring_glow = 0.9 + 0.8 * self.pulse
        self._arc(d, 70, 0, 360, scale_col(light, ring_glow * b), 3.2 + 1.5 * self.pulse)
        self._arc(d, 64, 0, 360, scale_col(col, 0.5 * b), 1)
        for i in range(24):
            self._tick(d, 64, 67, i * 15 - tk * 0.3, scale_col(col, 0.6 * b), 1)

        # sphere of points in the middle (rotates, swells and brightens with the voice)
        a = self.angle["sphere"]
        ca, sa = math.cos(a), math.sin(a)
        p = self.sphere
        x = p[:, 0] * ca + p[:, 2] * sa
        z = -p[:, 0] * sa + p[:, 2] * ca
        y = p[:, 1]
        radius = 56 * (1 + 0.06 * self.pulse)
        sx = CX + x * radius
        sy = CY + y * radius
        depth = (z + 1) / 2
        acc = np.zeros((H, W, 3), dtype=np.float32)
        ok = (sx >= 0) & (sx < W - 2) & (sy >= 0) & (sy < H - 2)
        ix, iy = sx[ok].astype(int), sy[ok].astype(int)
        val = ((0.22 + 0.75 * depth[ok] ** 2) * b * (0.85 + 0.9 * self.pulse))[:, None] * \
            np.array([205, 222, 240], dtype=np.float32)[None, :]
        np.add.at(acc, (iy, ix), val)
        dots = Image.fromarray(np.clip(acc, 0, 255).astype(np.uint8))

        art = ImageChops.add(ImageChops.add(lines, fill_layer).reduce(SS), dots)
        bloom = art.resize((W // 2, H // 2), Image.BILINEAR).filter(ImageFilter.GaussianBlur(3)) \
            .resize((W, H), Image.BILINEAR)
        haze = art.resize((W // 6, H // 6), Image.BILINEAR).filter(ImageFilter.GaussianBlur(3)) \
            .resize((W, H), Image.BILINEAR)
        frame = ImageChops.add(ImageChops.add(self.background, haze), bloom)
        return ImageChops.add(frame, art)


if __name__ == "__main__":
    import time as _t
    h = HudRing()
    t0 = _t.time()
    for i in range(30):
        h.render("speaking", i / 30, (70, 185, 255), 0.6, (abs(math.sin(i)), 0))
    print(f"{(_t.time() - t0) / 30 * 1000:.1f} ms per frame")
    shots = []
    cols = {"sleeping": (30, 90, 220), "listening": (40, 200, 255), "thinking": (110, 120, 255), "speaking": (70, 185, 255)}
    for st, m in [("sleeping", 0), ("listening", 0), ("thinking", 0), ("speaking", 0.9)]:
        h2 = HudRing()
        img = None
        for i in range(60):
            img = h2.render(st, 3 + i * 0.035, cols[st], 0.6, (m, 0))
        shots.append(img)
    sheet = Image.new("RGB", (W * 4 + 30, H), (255, 255, 255))
    for i, im in enumerate(shots):
        sheet.paste(im, (i * (W + 10), 0))
    sheet.save("hud_preview.png")
