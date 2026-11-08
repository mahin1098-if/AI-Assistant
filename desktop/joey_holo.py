"""
JOEY - hologram head
A glowing holographic woman made of points and lines, like a sci-fi AI.
She faces you, blinks, glances around while thinking, and her lips form the right shape
for every sound she says (real lip sync). Her shoulders dissolve into floating light.

The face starts from a real 3D face scan (Google's open-source MediaPipe face mesh,
face_mesh.obj, Apache License 2.0), reshaped to look feminine, with hair added.
Used by joey_app.py. Needs:  pip install pillow numpy   and face_mesh.obj in the same folder.
"""

import math
import os
import random

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter

W, H = 320, 340
BG = (10, 14, 23)       # same as the app window, so the picture blends in
BASE_YAW = 0.0          # 0 = facing you. Try -0.4 to turn her a little to the side
SHOW_HAIR = False       # True adds long hair
SLIM = 0.88             # face width: 1.0 = average, lower = slimmer
MESH_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "face_mesh.obj")

# Landmark numbers in the face mesh
LIPS_OUTER = [61, 146, 91, 181, 84, 17, 314, 405, 321, 375, 291, 409, 270, 269, 267, 0, 37, 39, 40, 185]
LIPS_INNER = [78, 95, 88, 178, 87, 14, 317, 402, 318, 324, 308, 415, 310, 311, 312, 13, 82, 81, 80, 191]
UPPER_LIP = [185, 40, 39, 37, 0, 267, 269, 270, 409, 191, 80, 81, 82, 13, 312, 311, 310, 415]
LOWER_LIP = [95, 88, 178, 87, 14, 317, 402, 318, 324, 146, 91, 181, 84, 17, 314, 405, 321, 375]
EYES = {  # (outline, upper lid, lower lid)
    "right": ([33, 7, 163, 144, 145, 153, 154, 155, 133, 173, 157, 158, 159, 160, 161, 246],
              [246, 161, 160, 159, 158, 157, 173], [7, 163, 144, 145, 153, 154, 155]),
    "left": ([263, 249, 390, 373, 374, 380, 381, 382, 362, 398, 384, 385, 386, 387, 388, 466],
             [466, 388, 387, 386, 385, 384, 398], [249, 390, 373, 374, 380, 381, 382]),
}
BROWS = [[70, 63, 105, 66, 107], [300, 293, 334, 296, 336]]


# ---------- building her (done once) ----------

def load_face():
    verts, faces = [], []
    with open(MESH_FILE, encoding="utf-8") as f:
        for line in f:
            p = line.split()
            if not p:
                continue
            if p[0] == "v":
                verts.append([float(v) for v in p[1:4]])
            elif p[0] == "f":
                faces.append([int(v.split("/")[0]) - 1 for v in p[1:4]])
    return np.array(verts), np.array(faces)


def smooth(x, a, b):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


def feminise(v):
    """Reshape the average face to look more feminine."""
    v = v.copy()
    x, y, z = v[:, 0], v[:, 1], v[:, 2]
    # slimmer face, softer narrower jaw and a smaller chin
    low = smooth(-y, 1.0, 8.5)
    v[:, 0] = x * SLIM * (1 - 0.18 * low)
    v[:, 1] = y + 0.7 * smooth(-y, 6.5, 9.4)
    # smaller, slimmer nose
    nose = smooth(-np.abs(x), -2.4, -0.6) * smooth(y, -3.4, -2.6) * smooth(-y, -2.8, -1.8) * smooth(z, 4.6, 5.4)
    v[:, 2] = z - (z - 4.6) * 0.22 * nose
    v[:, 0] = v[:, 0] * (1 - 0.12 * nose)
    # fuller lips
    mouth_c = (v[13] + v[14]) / 2
    d = np.linalg.norm((v - mouth_c) * [0.55, 1.4, 1], axis=1)
    lips = smooth(-d, -1.9, -0.3)
    v[:, 1] = v[:, 1] + (v[:, 1] - mouth_c[1]) * 0.12 * lips
    v[:, 2] = v[:, 2] + 0.18 * lips
    # bigger eyes
    for outline, _, _ in EYES.values():
        c = v[outline].mean(0)
        dist = np.linalg.norm(v - c, axis=1)
        w = smooth(-dist, -2.4, -0.4)[:, None]
        v = v + (v - c) * 0.14 * w
    # higher, arched brows
    for brow in BROWS:
        c = v[brow].mean(0)
        dist = np.linalg.norm((v - c) * [0.6, 1.2, 1], axis=1)
        v[:, 1] = v[:, 1] + 0.35 * smooth(-dist, -1.8, -0.2)
    # gently hollow under the cheekbones (less round)
    cheek = smooth(-np.abs(np.abs(v[:, 0]) - 3.6), -1.6, 0) * smooth(-np.abs(v[:, 1] + 3.2), -1.8, 0)
    v[:, 2] = v[:, 2] - 0.25 * cheek
    return v


def build(seed=5):
    rng = np.random.default_rng(seed)
    face, tris = load_face()
    face = feminise(face)
    n_face = len(face)

    normals = np.zeros_like(face)
    for a, b, c in tris:
        normals[[a, b, c]] += np.cross(face[b] - face[a], face[c] - face[a])
    normals /= np.linalg.norm(normals, axis=1, keepdims=True) + 1e-9
    if np.mean(np.sum(normals * (face - [0, 0, -3]), 1)) < 0:
        normals = -normals
    edges, count = set(), {}
    for a, b, c in tris:
        for u, v in ((a, b), (b, c), (c, a)):
            k = (min(u, v), max(u, v))
            edges.add(k)
            count[k] = count.get(k, 0) + 1
    nbrs = [[] for _ in range(n_face)]
    for u, v in edges:
        nbrs[u].append(v)
        nbrs[v].append(u)
    relief = np.array([np.dot(face[i] - face[nb].mean(0), normals[i]) for i, nb in enumerate(nbrs)])
    relief /= np.std(relief) + 1e-9
    border = sorted({i for e, c in count.items() if c == 1 for i in e})

    pts, nrm, kind = [face], [normals], [np.zeros(n_face)]   # kind: 0 face, 1 head, 2 hair, 3 neck/shoulders
    sculpt = [np.clip(1 + 0.45 * relief, 0.35, 2.4)]

    # back of the head (mostly hidden under the hair)
    centre, radii = np.array([0.0, 2.2, -2.2]), np.array([7.9 * SLIM, 10.4, 9.4])
    shell, shell_n, grid = [], [], {}
    for i in range(14):
        ph = -0.45 + (math.pi / 2 + 0.45) * i / 13
        for j in range(26):
            if ph > 1.3 and j % 3:
                continue
            th = 2 * math.pi * j / 26 + rng.uniform(-0.04, 0.04)
            d = np.array([math.cos(ph) * math.sin(th), math.sin(ph), math.cos(ph) * math.cos(th)])
            p = centre + radii * d
            if (p[2] > -1.2 and p[1] < 8.6) or np.min(np.linalg.norm(face - p, axis=1)) < 1.8:
                continue
            grid[(i, j)] = n_face + len(shell)
            shell.append(p)
            shell_n.append(d / np.linalg.norm(d))
    for (i, j), a in grid.items():
        for di, dj in ((0, 1), (1, 0)):
            b = grid.get((i + di, (j + dj) % 26))
            if b is not None:
                edges.add((a, b))
    shell = np.array(shell)
    for i in border:
        dist = np.linalg.norm(shell - face[i], axis=1)
        k = int(np.argmin(dist))
        if dist[k] < 4.0:
            edges.add((i, n_face + k))
    pts.append(shell); nrm.append(np.array(shell_n)); kind.append(np.ones(len(shell)))
    sculpt.append(np.full(len(shell), 0.6))

    # long hair: strands from a side parting, over the head and down past the shoulders
    base = n_face + len(shell)
    hair, hair_n, strand_edges = [], [], []
    part = np.array([-1.6, 12.4, 0.5])
    n_strands, seg = (70 if SHOW_HAIR else 0), 16
    for s in range(n_strands):
        a = -math.pi + 2 * math.pi * (s + 0.5) / n_strands + rng.uniform(-0.03, 0.03)
        front = math.cos(a) > 0.35
        side = 1 if math.sin(a) >= 0 else -1
        if front:
            # fringe: sweeps from the parting to the side of the face, framing it
            e = np.array([side * rng.uniform(7.4, 8.8), rng.uniform(1.5, 7.0), rng.uniform(0.8, 3.6)])
            ctrl = np.array([side * rng.uniform(3.0, 6.5), rng.uniform(12.0, 13.2), 4.0 + rng.uniform(-0.8, 0.8)])
        else:
            e = centre + radii * 1.07 * np.array([math.sin(a), 0.05, math.cos(a)])
            ctrl = centre + radii * 1.12 * np.array([math.sin(a) * 0.85, 0.75, math.cos(a) * 0.85])
        bottom = e + np.array([side * rng.uniform(0.6, 2.2), -rng.uniform(13.5, 17.5), rng.uniform(-1.5, 0.5)])
        mid = e + np.array([side * rng.uniform(0.6, 1.4), -6.5, 0])
        path = []
        for k in range(seg):
            t = k / (seg - 1)
            if t < 0.45:  # over the head
                u = t / 0.45
                q = (1 - u) ** 2 * part + 2 * (1 - u) * u * ctrl + u ** 2 * e
            else:         # falling down
                u = (t - 0.45) / 0.55
                q = (1 - u) ** 2 * e + 2 * (1 - u) * u * mid + u ** 2 * bottom
                q = q + np.array([math.sin(u * 3 + s) * 0.35, 0, 0])
            path.append(q)
        start = base + len(hair)
        for k, q in enumerate(path):
            hair.append(q)
            out = q - np.array([0, q[1] * 0.3, -2.2])
            hair_n.append(out / (np.linalg.norm(out) + 1e-9))
            if k:
                strand_edges.append((start + k - 1, start + k))
    hair = np.array(hair).reshape(-1, 3)
    for e in strand_edges:
        edges.add(e)
    # a few cross links so the hair reads as a surface
    for s in range(n_strands):
        for k in range(2, seg, 3):
            a_ = base + s * seg + k
            b_ = base + ((s + 1) % n_strands) * seg + k
            if np.linalg.norm(hair[a_ - base] - hair[b_ - base]) < 3.5:
                edges.add((a_, b_))
    hair_fade = np.tile(np.linspace(1.0, 0.25, seg), n_strands)
    pts.append(hair); nrm.append(np.array(hair_n).reshape(-1, 3)); kind.append(np.full(len(hair), 2))
    sculpt.append(1.15 * hair_fade)

    # slender neck and shoulders, as a jittered mesh that breaks up at the bottom
    base2 = base + len(hair)
    body, body_n = [], []
    rows, cols = 9, 20
    for r in range(rows):
        y = -5.5 - r * 1.75
        shoulder = smooth(np.array(-y), 9.5, 14.0)
        half_w = 3.6 + 11.5 * float(shoulder)
        depth = 3.6 + 1.2 * float(shoulder)
        for c in range(cols):
            a = -math.pi * 0.5 + math.pi * c / (cols - 1)   # front half only
            x = half_w * math.sin(a) + rng.uniform(-0.3, 0.3)
            z = -2.6 + depth * math.cos(a) * (1 - 0.35 * float(shoulder)) + rng.uniform(-0.2, 0.2)
            slope = 3.2 * float(shoulder) * abs(math.sin(a)) ** 1.6
            body.append([x, y + rng.uniform(-0.5, 0.5) - slope, z])
            body_n.append([math.sin(a), 0.2 * float(shoulder), math.cos(a)])
            i = base2 + r * cols + c
            broken = r >= rows - 4 and rng.random() < (r - rows + 5) * 0.22   # bottom breaks apart
            if c and not broken:
                edges.add((i - 1, i))
            if r and not broken:
                edges.add((i - cols, i))
                if c and (r + c) % 2:
                    edges.add((i - cols - 1, i))
    body = np.array(body)
    fade = np.repeat(np.linspace(0.7, 0.08, rows), cols)
    pts.append(body); nrm.append(np.array(body_n)); kind.append(np.full(len(body), 3))
    sculpt.append(fade)

    pts = np.vstack(pts)
    nrm = np.vstack(nrm)
    kind = np.concatenate(kind)
    sculpt = np.concatenate(sculpt)

    # how strongly each face point follows the jaw / lips
    jaw = np.zeros(len(pts))
    corner_y = face[61, 1]
    fx, fy = face[:, 0], face[:, 1]
    jaw[:n_face] = np.clip((corner_y - 0.2 - fy) / 1.4, 0, 1) * np.clip(1 - (np.abs(fx) / 6.8) ** 2, 0, 1)
    jaw[LOWER_LIP] = 1.0
    jaw[[61, 291, 78, 308]] = 0.4
    mouth_c = (face[13] + face[14]) / 2
    dist = np.linalg.norm((face - mouth_c) * [0.6, 1.0, 1.0], axis=1)
    near_mouth = np.zeros(len(pts))
    near_mouth[:n_face] = smooth(-dist, -3.6, -0.6)
    upper = np.zeros(len(pts))
    upper[UPPER_LIP] = 1.0

    edges = np.array(sorted(edges))
    face_edges = edges[(edges[:, 0] < n_face) & (edges[:, 1] < n_face)]
    extra = np.column_stack([face_edges, rng.uniform(0.3, 0.7, len(face_edges))])
    return dict(pts=pts, nrm=nrm, kind=kind, sculpt=sculpt, edges=edges, extra=extra, jaw=jaw,
                near_mouth=near_mouth, upper=upper, mouth_c=mouth_c, sparkle=rng.random(len(pts)),
                body_rows=(base2, rows, cols))


# ---------- drawing ----------

LIGHT = np.array([-0.35, 0.55, 0.75])
LIGHT = LIGHT / np.linalg.norm(LIGHT)


class HoloHead:
    def __init__(self):
        m = build()
        self.__dict__.update(m)
        self.extra_sparkle = np.random.default_rng(3).random(len(self.extra))
        self.yaw, self.pitch = BASE_YAW, 0.03
        self.target_yaw, self.target_pitch = BASE_YAW, 0.03
        self.gaze, self.target_gaze = np.zeros(2), np.zeros(2)
        self.next_move = 0.0
        self.open, self.wide = 0.0, 0.0
        self.bright = 0.6
        self.next_blink, self.blink_start = 2.5, -1.0
        self.background = Image.new("RGB", (W, H), BG)
        # floating light triangles where the shoulders dissolve
        rng = np.random.default_rng(9)
        n = 46
        self.flakes = dict(
            pos=np.column_stack([rng.uniform(-18, 18, n), rng.uniform(-25, -15, n), rng.uniform(-3, 3, n)]),
            vel=np.column_stack([rng.uniform(-0.25, 0.25, n), rng.uniform(0.15, 0.5, n), np.zeros(n)]),
            size=rng.uniform(0.5, 1.4, n), spin=rng.uniform(0, 6.28, n), phase=rng.uniform(0, 1, n))

    def _turn(self, v, shift):
        cy, sy = math.cos(self.yaw), math.sin(self.yaw)
        cp, sp = math.cos(self.pitch), math.sin(self.pitch)
        x, y, z = v[:, 0], v[:, 1], v[:, 2] + shift
        x, z = x * cy + z * sy, -x * sy + z * cy
        y, z = y * cp - z * sp, y * sp + z * cp
        return np.stack([x, y, z], -1)

    def _project(self, v):
        r = self._turn(v, 2.2)
        persp = 50 / (50 - r[:, 2])
        scale = 8.7
        return np.stack([W / 2 + r[:, 0] * scale * persp, 136 - r[:, 1] * scale * persp], -1)

    def render(self, state, t, color, glow, mouth_target):
        """mouth_target: (open, wide) from lip sync, or just a number for how open."""
        if not isinstance(mouth_target, (tuple, list)):
            mouth_target = (float(mouth_target), 0.15)
        if state != "speaking":
            mouth_target = (0.0, 0.0)

        # head and eye movement for each mood
        if t > self.next_move:
            if state == "thinking":
                self.target_yaw = BASE_YAW + random.choice([-0.22, 0.18])
                self.target_pitch = random.choice([-0.1, -0.03])
                self.target_gaze = np.array(random.choice([(0.7, 0.6), (-0.7, 0.6), (0.6, 0.2)]))
                self.next_move = t + random.uniform(0.9, 1.6)
            elif state == "listening":
                self.target_yaw, self.target_pitch, self.target_gaze = BASE_YAW + 0.04, 0.0, np.zeros(2)
                self.next_move = t + 1.0
            elif state == "speaking":
                self.target_yaw = BASE_YAW + random.uniform(-0.1, 0.1)
                self.target_pitch = random.uniform(-0.03, 0.05)
                self.target_gaze = np.array([random.uniform(-0.15, 0.15), 0.0])
                self.next_move = t + random.uniform(1.2, 2.2)
            else:
                self.target_yaw = BASE_YAW + 0.06 * math.sin(t * 0.3)
                self.target_pitch, self.target_gaze = 0.1, np.zeros(2)
                self.next_move = t + 0.5
        self.yaw += (self.target_yaw - self.yaw) * 0.05
        self.pitch += (self.target_pitch - self.pitch) * 0.05
        self.gaze += (self.target_gaze - self.gaze) * 0.15
        target_bright = {"sleeping": 0.5, "listening": 1.0, "thinking": 0.85, "speaking": 0.95}.get(state, 0.6)
        self.bright += (target_bright - self.bright) * 0.08
        # mouth follows the lip-sync shape quickly but smoothly, like real muscles
        # lips close faster than they open, like real lips (so m/b/p shut fully)
        rate = 0.85 if mouth_target[0] < self.open else 0.55
        self.open += (mouth_target[0] - self.open) * rate
        self.wide += (mouth_target[1] - self.wide) * 0.45

        closed = 0.95 if state == "sleeping" else 0.0
        if state != "sleeping":
            if t > self.next_blink and self.blink_start < 0:
                self.blink_start = t
            if self.blink_start >= 0:
                q = (t - self.blink_start) / 0.17
                if q >= 1:
                    self.blink_start, self.next_blink = -1, t + random.uniform(2.5, 6)
                else:
                    closed = 0.92 * (1 - abs(1 - 2 * q))

        # shape the mouth, jaw and eyelids
        p = self.pts.copy()
        o, w = self.open, self.wide
        p[:, 1] -= self.jaw * o * 1.5                                  # jaw drops
        p[:, 1] += self.upper * o * 0.22                               # upper lip lifts a little
        p[:, 2] -= self.jaw * o * 0.35
        dx = p[:, 0] - self.mouth_c[0]
        p[:, 0] += dx * self.near_mouth * w * 0.16                     # spread (ee) or purse (oo)
        p[:, 2] += self.near_mouth * max(0.0, -w) * 0.55               # lips push forward for oo/sh
        for outline, upper, lower in EYES.values():
            p[upper] += (p[lower] - p[upper]) * closed
        # gentle breathing and hair sway
        sway = math.sin(t * 0.9) * 0.15
        hair = self.kind == 2
        p[hair, 0] += sway * np.clip(-(p[hair, 1] - 4) / 14, 0, 1)
        p[:, 1] += math.sin(t * 1.3) * 0.08
        xy = self._project(p)

        # lighting: raised parts glow, edges get a rim light, the back fades away
        n = self._turn(self.nrm, 0.0)
        facing = n[:, 2]
        rim = np.clip(1 - np.abs(facing), 0, 1) ** 2
        lit = np.clip(n @ LIGHT, 0, 1)
        shade = np.where(facing > -0.15, (0.12 + 0.5 * lit) * self.sculpt + 0.35 * rim * self.sculpt, 0.03)
        level = self.bright * (0.82 + 0.18 * glow)
        c = np.array(color, dtype=float)

        lines = Image.new("RGB", (W, H))
        d = ImageDraw.Draw(lines)
        e0, e1 = self.edges[:, 0], self.edges[:, 1]
        eb = (shade[e0] + shade[e1]) / 2 * level
        keep = eb > 0.045
        for a, b, f in zip(e0[keep], e1[keep], eb[keep]):
            d.line([(xy[a, 0], xy[a, 1]), (xy[b, 0], xy[b, 1])],
                   fill=(int(c[0] * f), int(c[1] * f), int(c[2] * f)))

        # glowing dots
        acc = np.zeros((H, W, 3), dtype=np.float32)
        twinkle = 0.55 + 0.45 * np.sin(t * 2.5 + self.sparkle * 50)
        db = shade * level * twinkle * (0.5 + 1.1 * (self.sparkle > 0.78))
        ok = (db > 0.05) & (xy[:, 0] >= 1) & (xy[:, 0] < W - 2) & (xy[:, 1] >= 1) & (xy[:, 1] < H - 2)
        px = xy[ok].astype(int)
        vals = db[ok][:, None] * np.minimum(255, c + 110)[None, :]
        for ox, oy, k in ((0, 0, 1.0), (1, 0, 0.35), (0, 1, 0.35), (1, 1, 0.2)):
            np.add.at(acc, (px[:, 1] + oy, px[:, 0] + ox), vals * k)
        ia, ib, f = self.extra[:, 0].astype(int), self.extra[:, 1].astype(int), self.extra[:, 2]
        mxy = xy[ia] + (xy[ib] - xy[ia]) * f[:, None]
        mb = (shade[ia] + shade[ib]) / 2 * level * (0.3 + 0.5 * np.sin(t * 3.1 + self.extra_sparkle * 60) ** 2)
        ok = (mb > 0.06) & (mxy[:, 0] >= 0) & (mxy[:, 0] < W - 1) & (mxy[:, 1] >= 0) & (mxy[:, 1] < H - 1)
        mp = mxy[ok].astype(int)
        np.add.at(acc, (mp[:, 1], mp[:, 0]), mb[ok][:, None] * np.minimum(255, c + 90)[None, :])
        dots = Image.fromarray(np.clip(acc, 0, 255).astype(np.uint8))

        fd = ImageDraw.Draw(dots)
        hi = tuple(int(min(255, v + 120) * level * 0.9) for v in color)
        soft = tuple(int(v * 0.65) for v in hi)

        # floating triangles where the shoulders dissolve
        fl = self.flakes
        life = (fl["phase"] + t * 0.08) % 1.0
        fpos = fl["pos"] + fl["vel"] * (life[:, None] * 12)
        fxy = self._project(fpos)
        for i in range(len(life)):
            alpha = math.sin(life[i] * math.pi) * level
            r = fl["size"][i] * 9.4 * 0.5
            ang = fl["spin"][i] + t * 0.6
            tri = [(fxy[i, 0] + r * math.cos(ang + k * 2.094), fxy[i, 1] + r * math.sin(ang + k * 2.094))
                   for k in range(3)]
            col = tuple(int(v * 0.55 * alpha) for v in hi)
            fd.line(tri + [tri[0]], fill=col)
            fd.point([tri[0]], fill=tuple(int(v * alpha) for v in hi))

        # eyes: glowing, with lashes; brows; lips
        for outline, upper, lower in EYES.values():
            fd.line([tuple(xy[i]) for i in outline] + [tuple(xy[outline[0]])], fill=hi)
            span = np.ptp(xy[outline][:, 0])
            side = 1 if xy[outline[0], 0] > W / 2 else -1
            for k, idx in enumerate(upper[:4] if side < 0 else upper[:4]):
                x0, y0 = xy[idx]
                ln = span * (0.12 + 0.05 * k) * (1 - 0.6 * closed)
                fd.line([(x0, y0), (x0 + side * ln * 0.5, y0 - ln)], fill=soft)
            if closed < 0.5:
                cx, cy = xy[outline].mean(0)
                gx, gy = cx + self.gaze[0] * span * 0.16, cy - self.gaze[1] * span * 0.06
                rr = max(2.0, span * 0.19)
                fd.ellipse([gx - rr, gy - rr, gx + rr, gy + rr], outline=hi)
                fd.ellipse([gx - rr * 0.55, gy - rr * 0.55, gx + rr * 0.55, gy + rr * 0.55],
                           fill=tuple(min(255, int(v * 1.1) + 40) for v in hi))
        for brow in BROWS:
            fd.line([tuple(xy[i]) for i in brow], fill=soft)
        fd.line([tuple(xy[i]) for i in LIPS_OUTER] + [tuple(xy[LIPS_OUTER[0]])], fill=soft)
        if self.open > 0.1:
            k = min(1.0, (self.open - 0.1) * 4)
            fd.line([tuple(xy[i]) for i in LIPS_INNER] + [tuple(xy[LIPS_INNER[0]])],
                    fill=tuple(int(v * 0.85 * k) for v in soft))

        # glow, made by blurring small copies (fast), then combine
        art = ImageChops.add(lines, dots)
        bloom = art.resize((W // 2, H // 2), Image.BILINEAR).filter(ImageFilter.GaussianBlur(2.5)) \
            .resize((W, H), Image.BILINEAR)
        haze = art.resize((W // 6, H // 6), Image.BILINEAR).filter(ImageFilter.GaussianBlur(2.5)) \
            .resize((W, H), Image.BILINEAR)
        frame = ImageChops.add(ImageChops.add(self.background, haze), bloom)
        return ImageChops.add(frame, art)


if __name__ == "__main__":
    import time as _t
    h = HoloHead()
    t0 = _t.time()
    for i in range(30):
        h.render("speaking", i / 30, (70, 185, 255), 0.6, (abs(math.sin(i)), math.cos(i)))
    print(f"{(_t.time() - t0) / 30 * 1000:.1f} ms per frame, {len(h.pts)} points, {len(h.edges)} lines")
    shots = []
    for st, m in [("sleeping", (0, 0)), ("listening", (0, 0)), ("speaking", (0.9, 0.2)), ("speaking", (0.3, -1.0))]:
        h2 = HoloHead()
        h2.next_blink = 1e9
        random.seed(2)
        img = None
        for i in range(40):
            img = h2.render(st, 5 + i * 0.05, (70, 185, 255), 0.6, m)
        shots.append(img)
    sheet = Image.new("RGB", (W * 4 + 30, H), (255, 255, 255))
    for i, im in enumerate(shots):
        sheet.paste(im, (i * (W + 10), 0))
    sheet.save("holo_preview.png")
