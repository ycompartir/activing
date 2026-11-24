#!/usr/bin/env python3
"""MotivationDeeply reel generator: cinematic black-and-white scenes, handwritten caps, one red key word.

Usage:
    python3 reels/motivation-template/motivegen.py path/to/reel.json            # full render -> reel.mp4 next to the JSON
    python3 reels/motivation-template/motivegen.py path/to/reel.json --stills   # preview PNGs
    python3 reels/motivation-template/motivegen.py path/to/reel.json --meta     # only cover.png, post.txt, youtube.txt

Structure: hook (3.5s) + N items (7.5s each) + CTA (3s). 3 items = 29s.
Brand: MotivationDeeply logo, Architects Daughter (handwritten caps), red #D44545 key words.
"""
import functools, hashlib, json, math, os, re, subprocess, sys, urllib.parse, urllib.request, wave
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

W, H, FPS = 1080, 1920, 30
HERE = os.path.dirname(os.path.abspath(__file__))
BR = os.path.join(HERE, "brand") + "/"
RED = (212, 69, 69); WHITE = (246, 244, 240); SOFT = (205, 203, 198)
SW, SH = 1188, 2112          # scene canvas (10% larger than the frame, for the slow zoom)

# ===================================================================== utils
def clamp(x, a=0.0, b=1.0): return max(a, min(b, x))
def prog(t, a, b): return clamp((t - a) / (b - a)) if b > a else float(t >= a)
def ease_out(x): return 1 - (1 - x) ** 3
def ease_io(x): return 4 * x ** 3 if x < .5 else 1 - (-2 * x + 2) ** 3 / 2

# Channel font. Patrick Hand (SIL OFL, see brand/PatrickHand-OFL.txt) is the default since Nov 2026; reels made earlier pin
# "font": "architects-daughter" in reel.json so they re-render exactly as published. "tracking" = extra letter spacing (x size).
# name: (file, tracking, size scale, word-space factor, line height x size)
FONTS = {"patrick-hand": ("PatrickHand-Regular.ttf", 0.09, 1.12, 1.8, 1.85), "architects-daughter": ("architects-daughter-latin-400-normal.woff2", 0.0, 1.0, 1.1, 1.42)}
FONT_FILE, TRACK, FSCALE, WSPACE, LEADING = FONTS["patrick-hand"]

def set_font(cfg):
    global FONT_FILE, TRACK, FSCALE, WSPACE, LEADING
    FONT_FILE, TRACK, FSCALE, WSPACE, LEADING = FONTS[cfg.get("font", "patrick-hand")]
    TRACK = cfg.get("tracking", TRACK); LEADING = cfg.get("leading", LEADING)

@functools.lru_cache(None)
def _F(file, size): return ImageFont.truetype(BR + file, size)
def F(size): return _F(FONT_FILE, int(round(size * FSCALE)))   # FSCALE evens out the x-height between fonts
def wlen(f, w, size): return f.getlength(w) + TRACK * size * max(0, len(w) - 1)

@functools.lru_cache(None)
def logo(width):
    im = Image.open(BR + "logo-dark-bg.webp").convert("RGBA")
    bb = im.getbbox(); im = im.crop(bb)
    return im.resize((width, int(im.height * width / im.width)), Image.LANCZOS)

def paste(canvas, im, cx, cy, alpha=1.0, scale=1.0):
    if alpha <= 0.01: return
    if abs(scale - 1) > 1e-3: im = im.resize((max(1, int(im.width * scale)), max(1, int(im.height * scale))), Image.LANCZOS)
    if alpha < 1: im = im.copy(); im.putalpha(im.getchannel("A").point(lambda v: int(v * alpha)))
    canvas.alpha_composite(im, (int(cx - im.width / 2), int(cy - im.height / 2))) if (cx - im.width / 2 >= 0 and cy - im.height / 2 >= 0 and cx + im.width / 2 <= W and cy + im.height / 2 <= H) else canvas.paste(im, (int(cx - im.width / 2), int(cy - im.height / 2)), im)

@functools.lru_cache(4096)
def word_img(word, size, color, ls=None):
    """Word with a soft dark shadow for readability on any background."""
    f = F(size); trk = (TRACK if ls is None else ls) * size
    wd = int(f.getlength(word) + trk * max(0, len(word) - 1)) + 40
    asc, desc = f.getmetrics(); hh = asc + desc + 40
    txt = Image.new("RGBA", (wd, hh), (0, 0, 0, 0)); d = ImageDraw.Draw(txt)
    x = 20
    for ch in word:
        d.text((x, 20), ch, font=f, fill=color + (255,)); x += f.getlength(ch) + trk
    sh = Image.new("RGBA", txt.size, (0, 0, 0, 0)); sh.putalpha(txt.getchannel("A").point(lambda v: int(min(255, v * 0.95))))
    sh = sh.filter(ImageFilter.GaussianBlur(9))
    out = Image.new("RGBA", txt.size, (0, 0, 0, 0)); out.alpha_composite(sh, (0, 4)); out.alpha_composite(txt)
    return out

def parse_words(text):
    """'3 STOIC RULES FOR *HARD* DAYS' -> [(word, is_red)]"""
    out, red = [], False
    for w in text.split():
        s = w.startswith("*"); e = w.rstrip(".,!?;:").endswith("*")
        clean = w.replace("*", "")
        out.append((clean, red or s)); red = (red or s) and not e
    return out

def layout(text, size, maxw):
    words = parse_words(text); f = F(size); sp = f.getlength(" ") * WSPACE
    lines, cur, cw = [], [], 0
    for w, r in words:
        ww = wlen(f, w, size)
        if cur and cw + sp + ww > maxw: lines.append(cur); cur, cw = [], 0
        cw += (sp if cur else 0) + ww; cur.append((w, r))
    if cur: lines.append(cur)
    placed = []   # (word, red, x_center, line_index)
    for li, ln in enumerate(lines):
        tw = sum(wlen(f, w, size) for w, _ in ln) + sp * (len(ln) - 1); x = W / 2 - tw / 2
        for w, r in ln:
            placed.append((w, r, x + wlen(f, w, size) / 2, li)); x += wlen(f, w, size) + sp
    return placed, len(lines), size * LEADING

def draw_text(canvas, text, size, cy, t, t0, stagger=0.11, fade_out=None, maxw=880):
    """Word-by-word reveal (fade + rise). Returns (top, bottom, end_time)."""
    placed, n, lh = layout(text, size, maxw)
    top = cy - (n - 1) * lh / 2
    out_a = 1.0 if fade_out is None else 1 - ease_io(prog(t, fade_out, fade_out + 0.45))
    for i, (w, r, x, li) in enumerate(placed):
        p = prog(t, t0 + i * stagger, t0 + i * stagger + 0.55)
        if p <= 0: continue
        e = ease_out(p)
        paste(canvas, word_img(w, size, RED if r else WHITE), x, top + li * lh + 22 * (1 - e) - 10 * (1 - out_a), e * out_a)
    return top - lh / 2, top + (n - 1) * lh + lh / 2, t0 + len(placed) * stagger + 0.55

@functools.lru_cache(16)
def brush(width, thick):
    """Tapered red brush stroke like the logo's underline (thick rounded start, thin tail)."""
    S = 3; w, h = width * S, int(thick * 3 * S)
    im = Image.new("RGBA", (w + 40 * S, h), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    top, bot = [], []
    for k in range(60):
        s = k / 59; x = 20 * S + s * w; y = h * 0.62 - s * h * 0.28
        hw = (thick * (1 - 0.88 * s) + 1) * S / 2
        top.append((x, y - hw)); bot.append((x, y + hw))
    d.polygon(top + bot[::-1], fill=RED + (255,))
    r = thick * S / 2; d.ellipse((20 * S - r, h * 0.62 - r, 20 * S + r, h * 0.62 + r), fill=RED + (255,))
    return im.resize((im.width // S, im.height // S), Image.LANCZOS)

def draw_brush(canvas, cx, cy, width, thick, p, alpha=1.0):
    if p <= 0 or alpha <= 0: return
    b = brush(width, thick); cut = b.crop((0, 0, max(1, int(b.width * p)), b.height))
    if alpha < 1: cut = cut.copy(); cut.putalpha(cut.getchannel("A").point(lambda v: int(v * alpha)))
    canvas.alpha_composite(cut, (int(cx - b.width / 2), int(cy - b.height / 2)))

# =================================================================== scenes
def norm(a): return (a - a.min()) / (a.max() - a.min() + 1e-6)

@functools.lru_cache(32)
def fbm(w, h, seed, octaves=6, base=3):
    rng = np.random.default_rng(seed); out = np.zeros((h, w), np.float32); amp, tot = 1.0, 0.0
    for o in range(octaves):
        gw = base * 2 ** o; gh = max(2, int(gw * h / w) + 1)
        g = rng.random((gh, gw)).astype(np.float32)
        out += np.asarray(Image.fromarray((g * 255).astype(np.uint8)).resize((w, h), Image.BICUBIC), np.float32) / 255 * amp
        tot += amp; amp *= 0.55
    return norm(out / tot)

YY = np.linspace(0, 1, SH, dtype=np.float32)[:, None]; XX = np.linspace(0, 1, SW, dtype=np.float32)[None, :]

def grad(top, bot, y0=0.0, y1=1.0):
    k = ((YY - y0) / (y1 - y0)).clip(0, 1)
    return np.broadcast_to(top * (1 - k) + bot * k, (SH, SW)).astype(np.float32)

def ridge(seed, base, amp, freq):
    """Fractal mountain ridge (1D fBm), y in pixels for every column."""
    rng = np.random.default_rng(seed); x = np.linspace(0, 1, SW); n = np.zeros(SW); a, tot = 1.0, 0.0
    for o in range(7):
        pts = int(freq * 2 ** o) + 2
        n += np.interp(x, np.linspace(0, 1, pts), rng.random(pts)) * a; tot += a; a *= 0.5
    n = n / tot; n = (n - n.min()) / (n.max() - n.min())
    return ((base - amp * n) * SH).astype(np.float32)

class Scene:
    """Grayscale scene, value range 0..255 as float32 (SH x SW). render(lt, dur) -> array."""
    tint = (1.0, 1.0, 1.0)
    def __init__(self, opts): self.o = opts or {}

class Storm(Scene):
    tint = (0.96, 0.99, 1.05)
    def __init__(self, o):
        super().__init__(o); hz = 0.74
        self.sky = grad(4, 34, 0, hz)
        self.sea = grad(34, 8, hz, 1.0); self.hz = hz
        c = fbm(SW * 2, int(SH * hz), 11, octaves=7, base=2); self.cloud = ((c - 0.3).clip(0, 1) * 1.6).clip(0, 1) ** 0.8
        self.shade = fbm(SW * 2, int(SH * hz), 12)
        rng = np.random.default_rng(5); pts = [(SW * 0.88, 0)]
        while pts[-1][1] < SH * hz * 0.92:   # keep the bolt on the right edge, clear of logo and text
            x, y = pts[-1]; pts.append((float(np.clip(x + rng.normal(0, 34), SW * 0.80, SW * 0.97)), y + 40 + rng.random() * 50))
        bolt = Image.new("L", (SW, SH), 0); d = ImageDraw.Draw(bolt); d.line(pts, fill=255, width=5)
        for k in range(4, 10):   # side branch
            x, y = pts[k]; br = [(x, y)]
            for _ in range(5): br.append((br[-1][0] - 20 - rng.random() * 20, br[-1][1] + 35))
            d.line(br, fill=170, width=3); break
        self.bolt = np.asarray(bolt.filter(ImageFilter.GaussianBlur(2)), np.float32) / 255
        self.glow = np.asarray(bolt.filter(ImageFilter.GaussianBlur(60)), np.float32) / 255
        self.flashes = self.o.get("flashes", [0.35, 2.15])
    def render(self, lt, dur):
        hzp = int(SH * self.hz); off = int(lt * 28)
        cl = np.roll(self.cloud, -off, axis=1)[:, :SW]; sh = np.roll(self.shade, -off // 2, axis=1)[:, :SW]
        img = self.sky.copy(); top = img[:hzp]
        top[:] = top * (1 - cl) + (26 + 150 * sh ** 1.6 * (1 - YY[:hzp] * 0.6)) * cl
        img[hzp:] = self.sea[hzp:] * (0.9 + 0.1 * np.sin(np.arange(SH - hzp)[:, None] * 0.9 + lt * 3))
        fl = 0.0
        for tf in self.flashes:
            if lt >= tf: fl = max(fl, math.exp(-(lt - tf) * 7) * (0.6 + 0.4 * (int((lt - tf) * 30) % 2 == 0)))
        if fl > 0.02:
            img = img + fl * (60 + 140 * self.glow) + fl * 255 * self.bolt
            img[:hzp] += fl * 55 * cl
        return img

class NightSea(Scene):
    tint = (0.93, 0.97, 1.06)
    def __init__(self, o):
        super().__init__(o); hz = 0.83; self.hz = hz
        sky = grad(6, 38, 0, hz); rng = np.random.default_rng(3)
        for _ in range(260):
            x, y = int(rng.random() * SW), int(rng.random() * SH * hz * 0.8); sky[y, x] = 120 + rng.random() * 135
        self.mx, self.my, self.mr = SW * 0.5, SH * 0.755, 58
        dist = np.sqrt((XX * SW - self.mx) ** 2 + (YY * SH - self.my) ** 2)
        sky = sky + 120 * np.exp(-(dist / 260) ** 2) + 40 * np.exp(-(dist / 700) ** 2)
        sky[dist < self.mr] = 236
        self.sky = sky; self.cl = (fbm(SW * 2, int(SH * hz), 21) - 0.5).clip(0, 1) * 1.4
        self.sea = grad(30, 6, hz, 1.0)
        A = np.zeros((SH, SW), np.float32); B = np.zeros((SH, SW), np.float32)
        for L in (A, B):
            for _ in range(500):
                y = int(SH * hz + 3 + (rng.random() ** 1.3) * SH * (1 - hz) * 0.97); spread = 40 + (y - SH * hz) * 0.5
                x = int(self.mx + rng.normal(0, spread)); ln = int(10 + rng.random() * 50 * (1 + (y - SH * hz) / 300))
                L[y:y + 2, max(0, x - ln // 2):min(SW, x + ln // 2)] = 140 + rng.random() * 100
        self.A, self.B = A, B
    def render(self, lt, dur):
        hzp = int(SH * self.hz); img = self.sky.copy()
        cl = np.roll(self.cl, -int(lt * 10), axis=1)[:, :SW]
        img[:hzp] = img[:hzp] * (1 - cl * 0.6) + 28 * cl * 0.6
        w = 0.5 + 0.5 * math.sin(lt * 2.4)
        img[hzp:] = np.maximum(self.sea[hzp:], self.A[hzp:] * w + self.B[hzp:] * (1 - w))
        return img

class FogMountains(Scene):
    tint = (0.98, 0.99, 1.02)
    def __init__(self, o):
        super().__init__(o)
        img = grad(52, 168, 0, 0.62); Y = YY * SH
        layers = [(0.70, 0.12, 2, 150), (0.76, 0.10, 3, 118), (0.83, 0.09, 3, 82), (0.91, 0.07, 2, 30)]
        for k, (b, a, f, v) in enumerate(layers):
            r = ridge(40 + k, b, a, f)[None, :]
            m = Y >= r; img = np.where(m, v, img)
            haze = np.exp(-((Y - r) / 60).clip(0, None) ** 1) * (Y >= r) * 0.0
            img = img + 0 * haze
            if k < 3:  # fog band above next ridge
                img = img + 55 * np.exp(-((Y - (b + 0.05) * SH) / 70) ** 2) * (1 - k * 0.25)
        r = ridge(43, 0.91, 0.07, 2)
        fx = int(np.argmin(r[int(SW * 0.55):int(SW * 0.75)])) + int(SW * 0.55); fy = int(r[fx]) + 4
        fig = Image.new("L", (SW, SH), 0); d = ImageDraw.Draw(fig)
        d.ellipse((fx - 9, fy - 92, fx + 9, fy - 74), fill=255)
        d.polygon([(fx - 14, fy - 72), (fx + 14, fy - 72), (fx + 18, fy - 30), (fx + 9, fy), (fx - 9, fy), (fx - 18, fy - 30)], fill=255)
        self.fig = np.asarray(fig, np.float32) / 255
        self.img = img; self.fog = fbm(SW * 2, SH, 31, base=2)
    def render(self, lt, dur):
        img = self.img * (1 - self.fig) + 18 * self.fig
        fg = np.roll(self.fog, -int(lt * 22), axis=1)[:, :SW]
        band = np.exp(-((YY - 0.80) / 0.10) ** 2)
        return img * (1 - fg * band * 0.45) + 190 * fg * band * 0.45

class LightBreak(Scene):
    tint = (1.06, 1.0, 0.9)
    def __init__(self, o):
        super().__init__(o); self.start = self.o.get("start", 0.0)
        self.sx, self.sy = SW * 0.5, SH * 0.80
        dx, dy = XX * SW - self.sx, YY * SH - self.sy
        self.dist = np.sqrt(dx ** 2 + dy ** 2); ang = np.arctan2(dy, dx)
        rng = np.random.default_rng(8); n = rng.random(90).astype(np.float32)
        idx = ((ang + math.pi) / (2 * math.pi) * 90).astype(int) % 90
        rays = (n[idx] ** 3) * np.exp(-self.dist / 1000) * (dy < 0)
        self.rays = np.asarray(Image.fromarray((rays * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(10)), np.float32) / 255
        self.cloud = fbm(SW * 2, SH, 51); self.sky = grad(40, 120, 0, 0.7)
        r1 = ridge(61, 0.86, 0.10, 2)[None, :]; r2 = ridge(62, 0.93, 0.06, 3)[None, :]
        Y = YY * SH; self.m1 = (Y >= r1).astype(np.float32); self.m2 = (Y >= r2).astype(np.float32)
    def render(self, lt, dur):
        op = clamp(self.start + lt / max(dur, 1e-3) * (1 - self.start) * 1.0)
        cl = np.roll(self.cloud, -int(lt * 14), axis=1)[:, :SW]
        hole = np.exp(-(self.dist / (180 + 520 * op)) ** 2)
        cover = ((cl - 0.35) * 2).clip(0, 1) * (1 - hole)
        img = self.sky + 150 * np.exp(-(self.dist / (240 + 200 * op)) ** 2) * (0.4 + 0.6 * op)
        img = img * (1 - cover * 0.85) + (40 + 60 * cl) * cover * 0.85
        img = img + self.rays * (70 + 130 * op) * (1 - cover * 0.6)
        img = img * (1 - self.m1) + (58 + 30 * op) * self.m1
        return img * (1 - self.m2) + 22 * self.m2

# ============================================================ stock scenes
# {"name": "stock", "query": "rain window", "kind": "video"|"photo", "id": <pixabay id>, "tint": "cool"|"warm"|"neutral"|[r,g,b],
#  "focus": 0..1 (horizontal crop position), "speed": 1.0, "level": 1.0 (brightness), "gamma": 1.1, "start": seconds into the clip}
# Assets come from Pixabay (key in $PIXABAY_API_KEY, never printed or stored) with Openverse CC0/PDM photos as the fallback.
# Downloads are cached in cache/ (gitignored). The chosen id/source/page are written back into reel.json for reproducible renders.
CACHE = os.path.join(HERE, "cache"); UA = {"User-Agent": "Mozilla/5.0 (motivegen reel generator)"}
TINTS = {"cool": (0.93, 0.97, 1.06), "warm": (1.06, 1.0, 0.9), "neutral": (1.0, 1.0, 1.0), "silver": (0.98, 0.99, 1.02)}

def _get(url, binary=False):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r: data = r.read()
    return data if binary else json.loads(data)

def pixabay(kind, **params):
    key = os.environ.get("PIXABAY_API_KEY")
    if not key: raise RuntimeError("PIXABAY_API_KEY is not set")
    os.makedirs(CACHE, exist_ok=True)
    tag = hashlib.sha1(json.dumps([kind, params], sort_keys=True).encode()).hexdigest()[:16]
    cp = os.path.join(CACHE, f"api-{kind}-{tag}.json")
    if os.path.exists(cp): return json.load(open(cp))
    ep = "https://pixabay.com/api/videos/" if kind == "video" else "https://pixabay.com/api/"
    q = dict(params, safesearch="true"); q.setdefault("per_page", 50)
    try: d = _get(ep + "?" + urllib.parse.urlencode(dict(q, key=key)))
    except Exception as e: raise RuntimeError(f"Pixabay {kind} request failed: {type(e).__name__} {getattr(e, 'code', '')}") from None
    json.dump(d, open(cp, "w")); return d

def video_rendition(hit, need_w=SW, need_h=SH, cap=80e6):
    """Smallest rendition that still covers the scene canvas after a cover-crop, else the largest under the size cap."""
    rs = [v for v in hit["videos"].values() if v.get("url") and v.get("width")]
    covers = lambda v: max(need_w / v["width"], need_h / v["height"]) <= 1.0
    ok = sorted([v for v in rs if covers(v) and v.get("size", 0) <= cap], key=lambda v: v["width"] * v["height"])
    return ok[0] if ok else max([v for v in rs if v.get("size", 0) <= cap] or rs, key=lambda v: v["width"] * v["height"])

def score_hit(hit, kind, need):
    if hit.get("isAiGenerated"): return -1e9
    if kind == "video":
        v = video_rendition(hit); s = math.log1p(hit.get("downloads", 0)) + 2 * math.log1p(hit.get("likes", 0))
        s += 6 if v["height"] > v["width"] else 0                         # vertical first
        s -= 8 if hit.get("duration", 0) < need else 0                    # long enough to avoid a loop seam
        return s
    s = math.log1p(hit.get("downloads", 0)) + 2 * math.log1p(hit.get("likes", 0))
    return s + (6 if hit["imageHeight"] > hit["imageWidth"] else 0) - (10 if hit["imageWidth"] < 1600 else 0)

def resolve_stock(spec, need=9.0):
    """Fill in id/source/page/src for a stock spec (mutates and returns it)."""
    kind = spec.get("kind", "video")
    if spec.get("source") == "openverse": return spec
    if spec.get("id"):
        hits = pixabay(kind, id=str(spec["id"]))["hits"]
    else:
        hits = pixabay(kind, q=spec["query"], **({"video_type": "film"} if kind == "video" else {"image_type": "photo"}))["hits"]
        hits = sorted(hits, key=lambda h: -score_hit(h, kind, need))[:1]
    if not hits:
        if kind == "photo" or spec.get("fallback", True):
            return resolve_openverse(spec)
        raise RuntimeError(f"no Pixabay result for {spec}")
    h = hits[0]; spec.update(source="pixabay", id=h["id"], page=h["pageURL"], kind=kind)
    if kind == "video":
        v = video_rendition(h); spec.update(src=v["url"], size=[v["width"], v["height"]], duration=h.get("duration"))
    else:
        spec.update(size=[h["imageWidth"], h["imageHeight"]])
    return spec

def resolve_openverse(spec):
    q = urllib.parse.urlencode({"q": spec["query"], "license": "cc0,pdm", "page_size": 20, "aspect_ratio": "tall"})
    res = [r for r in _get("https://api.openverse.org/v1/images/?" + q).get("results", []) if (r.get("height") or 0) >= 1600]
    if not res: raise RuntimeError(f"no stock image for {spec['query']!r}")
    r = res[0]; spec.update(source="openverse", kind="photo", id=r["id"], page=r.get("foreign_landing_url"), src=r["url"], license=r.get("license"))
    return spec

def stock_file(spec):
    os.makedirs(CACHE, exist_ok=True); kind = spec.get("kind", "video")
    ext = ".mp4" if kind == "video" else ".jpg"
    path = os.path.join(CACHE, f"{spec.get('source', 'pixabay')}-{kind}-{spec['id']}{ext}")
    if os.path.exists(path): return path
    url = spec.get("src")
    if spec.get("source", "pixabay") == "pixabay" and kind == "photo":   # photo URLs expire: ask the API for a fresh one
        h = pixabay("photo", id=str(spec["id"]))["hits"][0]; url = h.get("fullHDURL") or h["largeImageURL"]
    data = _get(url, binary=True); open(path + ".part", "wb").write(data); os.replace(path + ".part", path)
    return path

def grade(g, lo, hi, gamma, level):
    """Map the clip's own black/white points to the channel's dark, cinematic range."""
    return (((g - lo) / max(hi - lo, 1)).clip(0, 1) ** gamma) * 205 * level + 4

class Stock(Scene):
    def __init__(self, o):
        super().__init__(o); o = self.o
        t = o.get("tint", "silver"); self.tint = TINTS[t] if isinstance(t, str) else tuple(t)
        self.kind = o.get("kind", "video"); self.path = stock_file(o)
        self.gamma, self.level = o.get("gamma", 1.1), o.get("level", 1.0)
        fx = clamp(o.get("focus", 0.5))
        vf = (f"scale={SW}:{SH}:force_original_aspect_ratio=increase:flags=lanczos,"
              f"crop={SW}:{SH}:(iw-{SW})*{fx:.3f}:(ih-{SH})/2,format=gray")
        if self.kind == "photo":
            im = Image.open(self.path).convert("L"); s = max(SW / im.width, SH / im.height)
            im = im.resize((math.ceil(im.width * s), math.ceil(im.height * s)), Image.LANCZOS)
            x0 = int((im.width - SW) * fx); y0 = (im.height - SH) // 2
            g = np.asarray(im.crop((x0, y0, x0 + SW, y0 + SH)), np.float32)
            lo, hi = np.percentile(g, [1, 99.5]); self.img = grade(g, lo, hi, self.gamma, self.level); return
        secs = o.get("seconds", 9.0); n = int(secs * FPS); sp = o.get("speed", 1.0)
        key = hashlib.sha1(json.dumps([self.path, vf, n, sp, o.get("start", 0)]).encode()).hexdigest()[:12]
        raw = os.path.join(CACHE, f"frames-{o['id']}-{key}.u8")
        if not os.path.exists(raw):
            cmd = ["ffmpeg", "-y", "-loglevel", "error", "-stream_loop", "-1", "-ss", str(o.get("start", 0)), "-i", self.path,
                   "-vf", f"setpts={1 / sp:.4f}*PTS,fps={FPS}," + vf, "-frames:v", str(n), "-f", "rawvideo", raw + ".part"]
            subprocess.run(cmd, check=True); os.replace(raw + ".part", raw)
        self.frames = np.memmap(raw, np.uint8, "r").reshape(-1, SH, SW); self.n = len(self.frames)
        sample = self.frames[:: max(1, self.n // 6)].astype(np.float32)
        self.lo, self.hi = np.percentile(sample, [1, 99.5])
    def render(self, lt, dur):
        if self.kind == "photo": return self.img
        i = int(max(lt, 0) * FPS) % self.n
        return grade(self.frames[i].astype(np.float32), self.lo, self.hi, self.gamma, self.level)

SCENES = {"storm": Storm, "night_sea": NightSea, "fog_mountains": FogMountains, "light_break": LightBreak, "stock": Stock}

@functools.lru_cache(None)
def scene_obj(name, opts_json):
    return SCENES[name](json.loads(opts_json))

def render_scene(spec, lt, dur):
    name = spec if isinstance(spec, str) else spec["name"]; opts = {} if isinstance(spec, str) else spec
    sc = scene_obj(name, json.dumps(opts, sort_keys=True))
    g = sc.render(lt, dur).clip(0, 255)
    rgb = np.stack([g * sc.tint[0], g * sc.tint[1], g * sc.tint[2]], -1).clip(0, 255).astype(np.uint8)
    im = Image.fromarray(rgb, "RGB")
    z = 1.0 + 0.06 * clamp(lt / max(dur, 1e-3))
    cw, ch = SW / z / 1.1, SH / z / 1.1
    return im.crop((int((SW - cw) / 2), int((SH - ch) / 2), int((SW + cw) / 2), int((SH + ch) / 2))).resize((W, H), Image.BILINEAR)

# vignette + center darkening for text + grain
_y = np.linspace(-1, 1, H, dtype=np.float32)[:, None]; _x = np.linspace(-1, 1, W, dtype=np.float32)[None, :]
VIGN = (1 - 0.55 * ((_x ** 2) * 0.8 + (_y ** 2) * 0.6).clip(0, 1) ** 1.3)[..., None]
TEXTBAND = (1 - 0.32 * np.exp(-((_y + 0.08) / 0.40) ** 2))[..., None]
# soft grain: generated at half resolution and upscaled, so it reads as film texture but still compresses well
GRAIN = [np.asarray(Image.fromarray(np.random.default_rng(100 + k).normal(128, 40, (H // 2, W // 2)).clip(0, 255).astype(np.uint8))
                    .resize((W, H), Image.BILINEAR), np.float32)[..., None] / 40 * 3.2 - 128 / 40 * 3.2 for k in range(4)]

# =================================================================== timeline
def timeline(cfg):
    p = cfg.get("pace", {}); hk, it, ct = p.get("hook", 3.5), p.get("item", 7.5), p.get("cta", 3.0)
    segs = [("hook", 0, hk, cfg["hook"].get("scene", "storm"))]; t = hk
    for i, item in enumerate(cfg["items"]):
        segs.append((f"item{i}", t, t + it, item.get("scene", "night_sea"))); t += it
    segs.append(("cta", t, t + ct, cfg["cta"].get("scene", {"name": "light_break", "start": 0.7}))); t += ct
    return segs, t

ROMAN = ["I", "II", "III", "IV", "V"]
XF = 0.35   # half crossfade

def frame(cfg, i):
    segs, total = timeline(cfg); t = i / FPS
    k = next(j for j, s in enumerate(segs) if t < s[2] or j == len(segs) - 1)
    _, a, b, spec = segs[k]
    bg = render_scene(spec, t - a, b - a)
    if k > 0 and t - a < XF:
        _, pa, pb, pspec = segs[k - 1]; m = 0.5 + 0.5 * (t - a) / XF
        bg = Image.blend(render_scene(pspec, t - pa, pb - pa), bg, ease_io(m))
    elif k < len(segs) - 1 and b - t < XF:
        _, na, nb, nspec = segs[k + 1]; m = 0.5 * (1 - (b - t) / XF)
        bg = Image.blend(bg, render_scene(nspec, t - na if t >= na else 0, nb - na), ease_io(m))
    arr = np.asarray(bg, np.float32) * VIGN * TEXTBAND + GRAIN[(i // 2) % len(GRAIN)]
    canvas = Image.fromarray(arr.clip(0, 255).astype(np.uint8), "RGB").convert("RGBA")
    name = segs[k][0]; lt = t - a
    # top logo (hidden during CTA, where the big logo takes over)
    la = prog(t, 0.0, 0.7) * (1 - prog(t, segs[-1][1] - 0.2, segs[-1][1] + 0.3))
    paste(canvas, logo(cfg.get("logo_width", 560)), W / 2, 235, la)
    if name == "hook":
        h = cfg["hook"]
        if h.get("kicker"):
            paste(canvas, word_img(h["kicker"], 36, SOFT, 0.14), W / 2, 700, prog(lt, 0.2, 0.7) * (1 - prog(lt, b - a - 0.45, b - a)))
        draw_text(canvas, h["text"], h.get("size", 96), 930, lt, 0.5, 0.14, fade_out=b - a - 0.5, maxw=900)
    elif name.startswith("item"):
        n = int(name[4:]); it = cfg["items"][n]; dur = b - a; fo = dur - 0.55
        size = it.get("size", 74 if len(it["text"]) < 90 else 66)
        placed, nl, lh = layout(it["text"], size, 880)
        cy = 900; top = cy - (nl - 1) * lh / 2 - lh / 2
        la_ = prog(lt, 0.25, 0.7) * (1 - ease_io(prog(lt, fo, fo + 0.45)))
        lab = word_img(it.get("label", f'{cfg.get("label", "RULE")} {ROMAN[n]}'), 44, WHITE, 0.2)
        paste(canvas, lab, W / 2, top - 120, la_)
        draw_brush(canvas, W / 2 + 10, top - 62, 250, 13, ease_out(prog(lt, 0.55, 1.05)), la_)
        _, bot, tend = draw_text(canvas, it["text"], size, cy, lt, 1.0, it.get("stagger", 0.13), fade_out=fo)
        if it.get("author"):
            aa = prog(lt, tend + 0.15, tend + 0.7) * (1 - ease_io(prog(lt, fo, fo + 0.45)))
            paste(canvas, word_img(it["author"], 38, SOFT, 0.16), W / 2, bot + 70, aa)
    else:
        c = cfg["cta"]
        draw_text(canvas, c["text"], c.get("size", 72), 720, lt, 0.15, 0.07, maxw=880)
        lp = prog(lt, 0.8, 1.5)
        paste(canvas, logo(cfg.get("cta_logo_width", 860)), W / 2, 1080, ease_out(lp), 0.9 + 0.1 * ease_out(lp))
        paste(canvas, word_img(c.get("follow", "FOLLOW @MOTIVATIONDEEPLY"), 40, WHITE, 0.14), W / 2, 1290, prog(lt, 1.4, 1.9))
    return canvas.convert("RGB")

# ===================================================================== audio
SR = 44100
def lowpass(x, fc, order=4):
    X = np.fft.rfft(x); f = np.fft.rfftfreq(len(x), 1 / SR); X *= 1 / (1 + (f / fc) ** order); return np.fft.irfft(X, len(x)).astype(np.float32)
def highpass(x, fc): return (x - lowpass(x, fc, 2)).astype(np.float32)

def make_audio(path, cfg):
    segs, dur = timeline(cfg); n = int(SR * dur); rng = np.random.default_rng(7)
    music = np.zeros(n, np.float32); sfx = np.zeros(n, np.float32); tt = np.arange(n) / SR
    def add(buf, sig, t0, g=1.0):
        s = int(t0 * SR); e = min(n, s + len(sig))
        if 0 <= s < n: buf[s:e] += sig[:e - s] * g
    hk = segs[0][2]; cta0 = segs[-1][1]
    # --- harmony: A minor, one chord per half item
    NOTE = lambda m: 440 * 2 ** ((m - 69) / 12)
    prog_ = [(57, [0, 3, 7]), (53, [0, 4, 7]), (48, [0, 4, 7]), (55, [0, 4, 7])]   # Am F C G
    times = [hk + k * (segs[1][2] - segs[1][1]) / 2 for k in range(2 * len(cfg["items"]))]
    # drone under the hook
    hl = int(hk * SR); ht = np.arange(hl) / SR
    add(music, (np.sin(2 * np.pi * NOTE(33) * ht) + 0.5 * np.sin(2 * np.pi * NOTE(45) * ht)) * np.minimum(1, ht / 1.5) * 0.18, 0)
    def pad(root, ints, t0, d, g):
        L = int((d + 1.2) * SR); x = np.arange(L) / SR; env = np.minimum(1, x / 0.9) * np.minimum(1, ((d + 1.2) - x) / 1.2)
        s = np.zeros(L, np.float32)
        for iv in ints:
            f = NOTE(root + iv)
            for det in (-0.12, 0.12): s += np.sin(2 * np.pi * f * (1 + det / 100) * x) * 0.5
            s += 0.25 * np.sin(2 * np.pi * f * 2 * x)
        add(music, s * env * g, t0)
    def piano(m, t0, g):
        f = NOTE(m); L = int(2.8 * SR); x = np.arange(L) / SR; s = np.zeros(L, np.float32)
        for k in range(1, 7): s += np.sin(2 * np.pi * f * k * x * (1 + 0.0004 * k * k)) * (0.55 ** k) * np.exp(-x * (1.2 + k * 0.9))
        add(music, s * np.minimum(1, x / 0.004) * g, t0)
    seq = times + [cta0]
    for k, t0 in enumerate(seq):
        root, ints = prog_[k % 4] if t0 < cta0 else (48, [0, 4, 7])
        d = (seq[k + 1] - t0) if k + 1 < len(seq) else (dur - t0)
        pad(root - 12, ints, t0, d, 0.035 + 0.02 * (t0 / dur))
        piano(root - 12, t0, 0.32)
        arp = [root + ints[0], root + ints[1], root + ints[2], root + 12, root + ints[2], root + ints[1]]
        step = 0.47
        for j in range(int(d / step)):
            piano(arp[j % len(arp)] + 12, t0 + j * step, 0.13 + 0.05 * (t0 / dur))
    # --- SFX
    for tf in cfg["hook"].get("flashes", [0.35, 2.15]):       # thunder synced to lightning
        L = int(3.2 * SR); x = np.arange(L) / SR
        crack = highpass(rng.normal(0, 1, L).astype(np.float32), 1500) * np.exp(-x * 18)
        rumble = lowpass(rng.normal(0, 1, L).astype(np.float32), 160) * (np.minimum(1, x / 0.08) * np.exp(-x * 1.1)) * (1 + 0.5 * np.sin(x * 9))
        add(sfx, crack * 0.35 + rumble * 2.2, tf)
    add(sfx, lowpass(rng.normal(0, 1, int(hk * SR)).astype(np.float32), 5000) * 0.03 * np.minimum(1, np.arange(int(hk * SR)) / SR / 0.5), 0)  # rain hiss
    for _, a, _, _ in segs[1:]:                                 # reverse swell into each scene
        L = int(0.9 * SR); x = np.arange(L) / SR
        w = lowpass(rng.normal(0, 1, L).astype(np.float32), 1800) * (x / 0.9) ** 2.5 * np.minimum(1, (0.9 - x) / 0.05)
        add(sfx, w * 0.45, a - 0.85)
    for _, a, _, _ in segs[1:-1]:                               # deep boom when the rule label lands
        L = int(1.6 * SR); x = np.arange(L) / SR
        f = 58 * np.exp(-x * 1.4) + 30; ph = 2 * np.pi * np.cumsum(f) / SR
        add(sfx, (np.sin(ph) * np.exp(-x * 2.2) + lowpass(rng.normal(0, 1, L).astype(np.float32), 120) * np.exp(-x * 6) * 0.8) * 0.55, a + 0.3)
    L = int(3 * SR); x = np.arange(L) / SR                     # bell on the CTA logo
    bell = sum(np.sin(2 * np.pi * f * x) * g * np.exp(-x * dcy) for f, g, dcy in [(1046.5, .5, 1.6), (1568, .3, 2.2), (2093, .2, 2.8), (2637, .1, 3.5)])
    add(sfx, bell * 0.22, cta0 + 0.8)
    wind = lowpass(rng.normal(0, 1, n).astype(np.float32), 380) * (0.5 + 0.5 * np.sin(tt * 0.7)) * 0.05
    sfx += wind * (tt > hk)
    # --- reverb + master
    IRl = int(2.4 * SR); ir = (rng.normal(0, 1, IRl) * np.exp(-np.arange(IRl) / SR / 0.75)).astype(np.float32); ir /= np.sqrt((ir ** 2).sum())
    dry = music + sfx * 0.8
    N = 1 << int(math.ceil(math.log2(n + IRl)))
    wet = np.fft.irfft(np.fft.rfft(dry, N) * np.fft.rfft(ir, N), N)[:n].astype(np.float32)
    mix = dry * 0.75 + wet * 0.45 + sfx * 0.35
    mix *= np.minimum(1, tt / 0.05) * np.minimum(1, (dur - tt) / 1.2)
    mix = np.tanh(mix / (np.abs(mix).max() + 1e-6) * 1.6) * 0.9
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(SR); wf.writeframes((mix * 32767).astype(np.int16).tobytes())

# ================================================================== extras
def uses_stock(cfg): return any(isinstance(p.get("scene"), dict) and p["scene"].get("name") == "stock" for p in [cfg["hook"], *cfg["items"], cfg["cta"]])

def tags_len(tags): return sum(len(t) + (2 if " " in t else 0) for t in tags) + max(0, len(tags) - 1)

def write_extras(cfg, outdir):
    frame(cfg, int(cfg.get("cover_at", 2.6) * FPS)).save(os.path.join(outdir, "cover.png"))
    if cfg.get("post"):
        p = cfg["post"]; txt = p["caption"].strip() + "\n\n" + " ".join("#" + h.lstrip("#") for h in p.get("hashtags", []))
        open(os.path.join(outdir, "post.txt"), "w").write(txt + "\n")
    if cfg.get("youtube"):
        yt = cfg["youtube"]; title, desc, tags = yt["title"], yt["description"], yt.get("tags", [])
        hashtags = ["#" + h.lstrip("#") for h in yt.get("hashtags", [])]; rule = "=" * 60; warn = []
        if len(title) > 100: warn.append(f"TITLE TOO LONG ({len(title)}/100)")
        if len(desc) > 5000: warn.append(f"DESCRIPTION TOO LONG ({len(desc)}/5000)")
        if tags_len(tags) > 500: warn.append(f"TAGS TOO LONG ({tags_len(tags)}/500)")
        for w_ in warn: print("WARNING:", w_)
        out = [f"YOUTUBE SHORTS METADATA: MotivationDeeply ({cfg.get('output', 'reel.mp4')})", rule, f"TITLE ({len(title)}/100)", title]
        if yt.get("alt_titles"): out += ["", "ALTERNATIVE TITLES (A/B test)"] + [f"- {x}" for x in yt["alt_titles"]]
        out += ["", rule, f"DESCRIPTION ({len(desc)}/5000)", desc, "", rule, f"TAGS ({tags_len(tags)}/500), paste into the Tags field",
                ", ".join(tags), "", rule, "HASHTAGS (the first 3 appear above the title)", " ".join(hashtags[:3]), "", rule, "UPLOAD SETTINGS",
                "Audience: No, it's not made for kids", f'Category: {yt.get("category", "People & Blogs")}', "Video language: English (United States)",
                "Altered or synthetic content: No (licensed stock footage and generated scenery, nothing realistic was altered or faked)" if uses_stock(cfg) else "Altered or synthetic content: No (generated abstract scenery, no realistic people or events)", "Comments: On",
                f'Pinned comment: {yt.get("pinned_comment", "")}', "Thumbnail: in the YouTube mobile app, pick the frame at ~0:02"]
        if warn: out += ["", "WARNINGS"] + warn
        open(os.path.join(outdir, "youtube.txt"), "w").write("\n".join(out) + "\n")

def resolve_all(cfg):
    """Pick and record a stock asset for every stock scene that has no id yet. Returns True if reel.json changed."""
    changed = False; it = cfg.get("pace", {}).get("item", 7.5)
    for part in [cfg["hook"], *cfg["items"], cfg["cta"]]:
        sc = part.get("scene")
        if isinstance(sc, dict) and sc.get("name") == "stock":
            sc.setdefault("seconds", round(it + 1.0, 2))
            if not sc.get("id") or not sc.get("page"): resolve_stock(sc, need=sc["seconds"]); changed = True
    return changed

def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args: sys.exit(__doc__)
    path = os.path.abspath(args[0]); cfg = json.load(open(path)); outdir = os.path.dirname(path); set_font(cfg)
    if resolve_all(cfg): json.dump(cfg, open(path, "w"), indent=2, ensure_ascii=False); open(path, "a").write("\n"); print("recorded stock ids in", path)
    out = os.path.join(outdir, cfg.get("output", "reel.mp4")); segs, dur = timeline(cfg)
    write_extras(cfg, outdir)
    if "--meta" in sys.argv: print("metadata ->", outdir); return
    if "--stills" in sys.argv:
        os.makedirs(os.path.join(outdir, "stills"), exist_ok=True)
        ts = [1.0, 2.4] + [a + d for _, a, _, _ in segs[1:-1] for d in (1.6, 4.5, 6.6)] + [dur - 0.4]
        for t in ts: frame(cfg, int(t * FPS)).save(os.path.join(outdir, "stills", f"t{t:05.2f}.png"))
        print("stills ->", os.path.join(outdir, "stills")); return
    wav = os.path.splitext(out)[0] + ".wav"; make_audio(wav, cfg)
    ff = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
                           "-i", wav, "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-maxrate", "10M", "-bufsize", "20M", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
                           "-shortest", "-movflags", "+faststart", out], stdin=subprocess.PIPE)
    N = int(round(dur * FPS))
    for i in range(N):
        ff.stdin.write(frame(cfg, i).tobytes())
        if i % 90 == 0: print(f"frame {i}/{N}", flush=True)
    ff.stdin.close(); ff.wait(); os.remove(wav); print(f"done {out} ({dur:.0f}s)")

if __name__ == "__main__":
    main()
