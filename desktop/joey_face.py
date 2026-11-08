"""
JOEY - the face
Draws Joey's animated face: she blinks, looks around while thinking,
closes her eyes when sleeping, and moves her lips in time with her voice.
Used by joey_app.py. Needs:  pip install pillow
"""

import math
import random

from PIL import Image, ImageDraw, ImageFilter

W, H = 320, 340          # size of the picture in the window
SS = 3                   # draw bigger then shrink, for smooth edges

# ---- Colours (change these to restyle her) ----
SKIN = (236, 189, 158)
SKIN_SHADE = (214, 160, 128)
BLUSH = (232, 130, 125)
HAIR = (58, 36, 26)
HAIR_LIGHT = (92, 60, 42)
EYE = (92, 62, 40)        # iris colour (brown). Try (60, 110, 90) for green, (70, 100, 150) for blue
LIPS = (196, 104, 100)
LIPS_LIGHT = (214, 128, 120)
TOP = (44, 56, 86)        # her top
BG_TOP = (10, 14, 23)
BG_BOTTOM = (17, 24, 40)

CX, CY = 160, 150        # centre of the face


# ---------- small drawing helpers ----------

def bezier(points, steps=24):
    """Smooth curve through control points (any number)."""
    def point(t):
        pts = list(points)
        while len(pts) > 1:
            pts = [(a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t) for a, b in zip(pts, pts[1:])]
        return pts[0]
    return [point(i / steps) for i in range(steps + 1)]


def scaled(points, s):
    return [(x * s, y * s) for x, y in points]


def egg(cx, cy, a, b, chin=0.26, n=90):
    """Face outline: an oval that narrows towards the chin."""
    pts = []
    for i in range(n):
        th = 2 * math.pi * i / n
        down = (1 - math.cos(th)) / 2          # 0 at top, 1 at chin
        w = 1 - chin * down ** 2.2
        pts.append((cx + a * math.sin(th) * w, cy - b * math.cos(th)))
    return pts


def soft_blob(size, box, color, alpha, blur, s=1):
    layer = Image.new("RGBA", size, color + (0,))
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).ellipse([v * s for v in box], fill=alpha)
    layer.putalpha(mask.filter(ImageFilter.GaussianBlur(blur * s)))
    return layer


# ---------- the parts that never move (drawn once) ----------

def draw_static():
    s = SS
    size = (W * s, H * s)
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # long hair behind the head
    back = bezier([(78, 150), (60, 240), (66, 300), (50, 345)]) + [(270, 345)] + \
        bezier([(270, 345), (254, 300), (262, 240), (242, 150)])
    d.polygon(scaled(back, s), fill=HAIR)
    d.ellipse(scaled([(62, 34), (258, 250)], s), fill=HAIR)

    # neck and shoulders
    d.polygon(scaled([(140, 215), (180, 215), (184, 290), (136, 290)], s), fill=SKIN_SHADE)
    d.ellipse(scaled([(30, 276), (290, 450)], s), fill=TOP)
    d.polygon(scaled(bezier([(128, 280), (160, 318), (192, 280)]), s), fill=SKIN_SHADE)

    # face with soft shading
    face_pts = egg(CX, CY, 76, 98)
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).polygon(scaled(face_pts, s), fill=255)
    face = Image.new("RGBA", size, SKIN_SHADE + (255,))
    face.alpha_composite(soft_blob(size, (96, 74, 224, 236), SKIN, 255, 14, s))
    face.alpha_composite(soft_blob(size, (110, 184, 140, 206), BLUSH, 70, 7, s))   # cheeks
    face.alpha_composite(soft_blob(size, (180, 184, 210, 206), BLUSH, 70, 7, s))
    face.alpha_composite(soft_blob(size, (148, 136, 172, 196), (250, 214, 190), 90, 6, s))  # nose light
    img.paste(face, (0, 0), mask)
    d = ImageDraw.Draw(img)

    # nose
    d.line(scaled(bezier([(164, 172), (168, 186), (162, 194)]), s), fill=SKIN_SHADE + (255,), width=2 * s)
    d.line(scaled(bezier([(152, 196), (160, 200), (168, 196)]), s), fill=(196, 140, 112, 255), width=2 * s)

    # fringe swept to one side, and locks framing the face
    fringe = bezier([(80, 160), (56, 36), (160, -24), (264, 36), (240, 160)], 40) + \
        bezier([(240, 160), (236, 110), (214, 92), (186, 92)], 20) + \
        bezier([(186, 92), (150, 96), (112, 112), (96, 150)], 20) + \
        bezier([(96, 150), (92, 158), (86, 166)], 6)
    d.polygon(scaled(fringe, s), fill=HAIR)
    for strand in ([(118, 62), (152, 66), (184, 90)], [(160, 46), (204, 58), (226, 100)],
                   [(98, 92), (104, 112), (100, 140)]):
        d.line(scaled(bezier(strand), s), fill=HAIR_LIGHT, width=2 * s)
    left_lock = bezier([(86, 150), (78, 220), (84, 280)]) + bezier([(98, 268), (92, 210), (96, 150)])
    right_lock = bezier([(232, 96), (246, 200), (238, 280)]) + bezier([(222, 268), (230, 190), (214, 100)])
    d.polygon(scaled(left_lock, s), fill=HAIR)
    d.polygon(scaled(right_lock, s), fill=HAIR)

    return img.resize((W, H), Image.LANCZOS)


def draw_background():
    bg = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(bg)
    for y in range(H):
        t = y / H
        d.line([(0, y), (W, y)], fill=tuple(int(a + (b - a) * t) for a, b in zip(BG_TOP, BG_BOTTOM)))
    return bg


def halo_mask():
    m = Image.new("L", (W, H), 0)
    ImageDraw.Draw(m).ellipse([CX - 120, CY - 125, CX + 120, CY + 135], fill=255)
    return m.filter(ImageFilter.GaussianBlur(28))


# ---------- the parts that move ----------

def draw_eye(target, ex, ey, openness, gaze, s, closed_smile):
    d = ImageDraw.Draw(target)
    w, h = 17, 9 * openness
    if openness < 0.15:
        # closed eye: a gentle curve with lashes
        curve = bezier([(ex - w, ey), (ex, ey + (6 if closed_smile else 2)), (ex + w, ey)])
        d.line(scaled(curve, s), fill=(40, 26, 20, 255), width=3 * s)
        return
    top = bezier([(ex - w, ey + 1), (ex - 4, ey - h * 1.5), (ex + w, ey - 1)])
    bottom = bezier([(ex + w, ey - 1), (ex + 2, ey + h * 1.15), (ex - w, ey + 1)])
    outline = top + bottom
    # white of the eye
    eye_mask = Image.new("L", (W * s, H * s), 0)
    ImageDraw.Draw(eye_mask).polygon(scaled(outline, s), fill=255)
    layer = Image.new("RGBA", (W * s, H * s), (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    ld.polygon(scaled(outline, s), fill=(248, 244, 240, 255))
    # iris, pupil and sparkle, moved by gaze
    ix, iy = ex + gaze[0] * 5, ey + gaze[1] * 3
    r = 8.2
    ld.ellipse(scaled([(ix - r, iy - r), (ix + r, iy + r)], s), fill=EYE + (255,))
    ld.ellipse(scaled([(ix - r * 0.6, iy - r * 0.6), (ix + r * 0.6, iy + r * 0.6)], s),
               fill=tuple(int(c * 0.75) for c in EYE) + (255,))
    ld.ellipse(scaled([(ix - 3.6, iy - 3.6), (ix + 3.6, iy + 3.6)], s), fill=(18, 12, 10, 255))
    ld.ellipse(scaled([(ix - 4.5, iy - 5), (ix - 1.5, iy - 2)], s), fill=(255, 255, 255, 235))
    clipped = Image.new("RGBA", layer.size, (0, 0, 0, 0))
    clipped.paste(layer, (0, 0), eye_mask)
    target.alpha_composite(clipped)
    # upper lid line and lashes
    d.line(scaled(top, s), fill=(36, 22, 18, 255), width=3 * s)
    side = 1 if ex > CX else -1
    tip = (ex + side * w, ey - 1)
    d.line(scaled([tip, (tip[0] + side * 5, tip[1] - 5)], s), fill=(36, 22, 18, 255), width=2 * s)
    d.line(scaled([(tip[0] - side * 4, tip[1] - 3), (tip[0] + side * 1, tip[1] - 8)], s),
           fill=(36, 22, 18, 255), width=2 * s)


def draw_brow(d, ex, ey, raise_by, tilt, s):
    side = 1 if ex > CX else -1
    inner, outer = ex - side * 15, ex + side * 18
    y = ey - 22 - raise_by
    pts = bezier([(inner, y + 2 + tilt * side), (ex, y - 4), (outer, y + 3)])
    d.line(scaled(pts, s), fill=HAIR + (255,), width=4 * s)


def draw_mouth(d, open_amount, smile, s, dy=0):
    mx, my = CX, 218 + dy
    w = 21 - open_amount * 3
    lift = smile * 4
    if open_amount < 0.06:
        upper = bezier([(mx - w, my - lift), (mx - 8, my - 6), (mx, my - 3), (mx + 8, my - 6), (mx + w, my - lift)])
        middle = bezier([(mx + w, my - lift), (mx, my + 2 + smile), (mx - w, my - lift)])
        d.polygon(scaled(upper + middle, s), fill=LIPS + (255,))
        lower = bezier([(mx - w + 3, my - lift + 1), (mx, my + 11 + smile), (mx + w - 3, my - lift + 1)])
        d.polygon(scaled(middle[::-1] + lower[::-1], s), fill=LIPS_LIGHT + (255,))
        d.line(scaled(middle, s), fill=(140, 62, 62, 255), width=2 * s)
        return
    gap = 3 + open_amount * 15
    inner_top = bezier([(mx - w + 2, my - lift + 1), (mx, my - 1), (mx + w - 2, my - lift + 1)])
    inner_bottom = bezier([(mx + w - 2, my - lift + 1), (mx, my + gap), (mx - w + 2, my - lift + 1)])
    d.polygon(scaled(inner_top + inner_bottom, s), fill=(84, 30, 34, 255))
    if open_amount > 0.25:  # top teeth
        teeth = bezier([(mx - w + 6, my - lift + 1), (mx, my + 3), (mx + w - 6, my - lift + 1)])
        d.polygon(scaled(inner_top[3:-3] + teeth[::-1], s), fill=(246, 242, 236, 255))
    if open_amount > 0.5:   # tongue
        d.ellipse(scaled([(mx - 9, my + gap - 7), (mx + 9, my + gap + 2)], s), fill=(176, 84, 90, 255))
    upper = bezier([(mx - w - 1, my - lift), (mx - 8, my - 7), (mx, my - 4), (mx + 8, my - 7), (mx + w + 1, my - lift)])
    d.polygon(scaled(upper + inner_top[::-1], s), fill=LIPS + (255,))
    lower = bezier([(mx - w - 1, my - lift), (mx, my + gap + 8), (mx + w + 1, my - lift)])
    d.polygon(scaled(inner_bottom + lower[::-1][1:], s), fill=LIPS_LIGHT + (255,))


# ---------- the face, frame by frame ----------

class Face:
    def __init__(self):
        self.static = draw_static()
        self.background = draw_background()
        self.halo = halo_mask()
        self.next_blink = 2.0
        self.blink_start = -1.0
        self.gaze = [0.0, 0.0]
        self.eyes = 1.0
        self.smile = 0.6
        self.brows = 0.0
        self.mouth = 0.0
        self.look_target = (0.0, 0.0)
        self.next_glance = 0.0

    def render(self, state, t, color, glow, mouth_target):
        """state: sleeping/listening/thinking/speaking/...  t: time in seconds
        color: (r,g,b) glow colour  glow: 0..1 brightness  mouth_target: 0..1 how open (or (open, wide))."""
        if isinstance(mouth_target, (tuple, list)):
            mouth_target = mouth_target[0]
        # what each mood looks like
        if state == "sleeping":
            eyes, smile, brows, tilt, look = 0.0, 0.5, -1.0, 0.0, (0, 0)
        elif state == "listening":
            eyes, smile, brows, tilt, look = 1.15, 0.7, 3.5, 0.0, (0, 0)
        elif state == "thinking":
            if t > self.next_glance:  # glance around while thinking
                self.look_target = random.choice([(0.8, -0.9), (-0.7, -0.8), (0.9, -0.3)])
                self.next_glance = t + random.uniform(0.8, 1.6)
            eyes, smile, brows, tilt, look = 0.95, 0.2, 2.0, 2.5, self.look_target
        elif state == "error":
            eyes, smile, brows, tilt, look = 1.0, -0.4, 1.0, -3.0, (0, 0.2)
        else:  # speaking, starting
            eyes, smile, brows, tilt, look = 1.0, 0.8, 1.0, 0.0, (0, 0)
        if state != "speaking":
            mouth_target = 0.0

        # glide towards the target expression so it looks natural
        k = 0.18
        self.eyes += (eyes - self.eyes) * k
        self.smile += (smile - self.smile) * k
        self.brows += (brows - self.brows) * k
        self.gaze[0] += (look[0] - self.gaze[0]) * 0.15
        self.gaze[1] += (look[1] - self.gaze[1]) * 0.15
        self.mouth += (mouth_target - self.mouth) * 0.45

        # blinking
        openness = self.eyes
        if state != "sleeping":
            if t > self.next_blink and self.blink_start < 0:
                self.blink_start = t
            if self.blink_start >= 0:
                p = (t - self.blink_start) / 0.16
                if p >= 1:
                    self.blink_start = -1
                    self.next_blink = t + random.uniform(2.5, 6)
                else:
                    openness *= abs(1 - 2 * p)

        # build the frame
        frame = self.background.copy()
        strength = int(90 + 120 * glow)
        frame.paste(Image.new("RGB", (W, H), color), (0, 0),
                    self.halo.point(lambda v: v * strength // 255))
        frame = frame.convert("RGBA")
        bob = math.sin(t * 1.2) * 1.5 if state == "sleeping" else 0  # gentle breathing
        frame.alpha_composite(self.static, (0, int(bob)))

        s = 2
        layer = Image.new("RGBA", (W * s, H * s), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        for ex in (CX - 32, CX + 32):
            draw_eye(layer, ex, 158 + bob, openness, self.gaze, s, closed_smile=(state == "sleeping"))
            draw_brow(d, ex, 158 + bob, self.brows, tilt, s)
        draw_mouth(d, self.mouth, self.smile, s, dy=bob)
        frame.alpha_composite(layer.resize((W, H), Image.LANCZOS))
        return frame.convert("RGB")


if __name__ == "__main__":
    # quick preview: saves a picture of each mood
    f = Face()
    colors = {"sleeping": (40, 95, 210), "listening": (0, 200, 255),
              "thinking": (150, 95, 255), "speaking": (0, 225, 160)}
    shots = []
    for st, mouth in [("sleeping", 0), ("listening", 0), ("thinking", 0), ("speaking", 0.75)]:
        f.next_blink = 1e9
        img = None
        for i in range(40):
            img = f.render(st, 10 + i * 0.05, colors[st], 0.6, mouth)
        shots.append(img)
    sheet = Image.new("RGB", (W * 4 + 30, H), (255, 255, 255))
    for i, im in enumerate(shots):
        sheet.paste(im, (i * (W + 10), 0))
    sheet.save("face_preview.png")
    print("saved face_preview.png")
