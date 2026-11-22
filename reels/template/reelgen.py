#!/usr/bin/env python3
"""Branded "N app tricks" reel generator (1080x1920, 30fps, H.264 + AAC).

Usage:
    python3 reels/template/reelgen.py path/to/reel.json            # full render -> reel.mp4 next to the JSON
    python3 reels/template/reelgen.py path/to/reel.json --stills   # quick preview PNGs (one per scene)

All content comes from the JSON file (see reels/template/README.md for the schema).
Brand look (fonts, colors, K mark) comes from reels/template/brand/ (keepmesignedin.com).
Timing: hook 3s + 5s per trick + CTA 2s  (3 tricks = 20s).
"""
import functools, json, math, os, re, subprocess, sys, wave
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

W, H, FPS = 1080, 1920, 30
HERE = os.path.dirname(os.path.abspath(__file__))
BR = os.path.join(HERE, "brand") + "/"
FD = "/usr/share/fonts/opentype/inter/"

# ======================================================================= fonts
@functools.lru_cache(None)
def F(kind, size):
    """Brand: "D600" Space Grotesk / "M500" JetBrains Mono / "I500" Inter (variable weights).
    Mockup UI: reg / semi / bold / ital / mono."""
    if kind[0] in "DMI" and kind[1:].isdigit():
        f = ImageFont.truetype(BR + {"D": "space-grotesk", "M": "jetbrains-mono", "I": "inter"}[kind[0]]
                               + "-latin-wght-normal.woff2", size)
        f.set_variation_by_axes([int(kind[1:])]); return f
    path = {"bold": FD + "Inter-Bold.otf", "semi": FD + "Inter-SemiBold.otf", "reg": FD + "Inter-Regular.otf",
            "ital": FD + "Inter-Italic.otf", "mono": "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"}[kind]
    return ImageFont.truetype(path, size)

# ===================================================================== palette
def hx(s): s = s.lstrip("#"); return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))
def mix(a, b, k): return tuple(int(x + (y - x) * k) for x, y in zip(a, b))
def lum(c): return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]

# keepmesignedin.com brand tokens
BASE = (247, 245, 240); INKB = (20, 19, 15); CREAM = (242, 240, 234); MUTEDB = (110, 108, 102)
C_VIDEO = (242, 92, 84); C_IMAGE = (124, 92, 255); C_AUDIO = (20, 184, 166); C_PROD = (245, 165, 36); C_SHOP = (37, 99, 235)
TRICK_COLORS = [(C_VIDEO, INKB), (C_IMAGE, (255, 255, 255)), (C_AUDIO, INKB), (C_PROD, INKB), (C_SHOP, (255, 255, 255))]
INK = (18, 20, 28); WHITE = (255, 255, 255); MUTED = (120, 126, 140)
AV_COLS = [(84, 160, 255), (255, 159, 67), (16, 172, 132), (255, 107, 129), (238, 82, 83), (95, 39, 205)]

# App mockup theme (overridden by the JSON "app" block). Defaults = WhatsApp-like light theme.
T = {}
def set_theme(app):
    g = lambda k, d: hx(app[k]) if k in app else d
    T["header"] = g("header", (0, 128, 105))
    T["header_text"] = g("header_text", WHITE if lum(T["header"]) < 150 else INK)
    T["screen"] = g("screen_bg", (236, 229, 221))
    T["bubble_out"] = g("bubble_out", (217, 253, 211))
    T["bubble_in"] = g("bubble_in", WHITE if lum(T["screen"]) < 245 else (239, 239, 242))
    T["accent"] = g("accent", (37, 211, 102))
    T["send"] = g("send", T["header"] if lum(T["header"]) < 200 else T["accent"])
    T["field"] = g("field", WHITE if lum(T["screen"]) < 245 else (239, 239, 242))
    T["touch_dark"] = app.get("touch", "light") == "dark"

# ====================================================================== easing
def clamp(x, a=0.0, b=1.0): return max(a, min(b, x))
def prog(t, a, b): return clamp((t - a) / (b - a)) if b > a else float(t >= a)
def ease_out(x): return 1 - (1 - x) ** 3
def ease_io(x): return 4 * x ** 3 if x < .5 else 1 - (-2 * x + 2) ** 3 / 2
def back(x, s=1.9): x -= 1; return 1 + (s + 1) * x ** 3 + s * x ** 2
def lerp(a, b, x): return a + (b - a) * x

# ================================================================== background
yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
def background(t):
    img = np.broadcast_to(np.array(BASE, np.float32), (H, W, 3)).copy()
    for cx, cy, r, col, sp, amt in [(120, 380, 480, C_AUDIO, .7, .22), (980, 1560, 560, C_IMAGE, .5, .16),
                                    (1000, 300, 300, C_PROD, .9, .14)]:
        cx2 = cx + 120 * math.sin(t * sp); cy2 = cy + 90 * math.cos(t * sp * 1.3)
        d = np.exp(-(((xx - cx2) ** 2 + (yy - cy2) ** 2) / (2 * r * r)))[..., None] * amt
        img = img * (1 - d) + np.array(col, np.float32) * d
    return Image.fromarray(img.clip(0, 255).astype(np.uint8), "RGB").convert("RGBA")

# ================================================================ text helpers
FALLBACK = {"D": "bold", "M": "mono", "I": "semi"}
def has_glyph(f, ch):
    """True if font f has a real glyph for ch (missing glyphs render as the same .notdef box)."""
    try:
        return ch.isspace() or f.getmask(ch).getbbox() != f.getmask("\uffff").getbbox() or f.getlength(ch) != f.getlength("\uffff")
    except Exception:
        return False

@functools.lru_cache(4096)
def text_img(s, kind, size, color, ls=0.0):
    f = F(kind, size)
    missing = {ch for ch in set(s) if not has_glyph(f, ch)}
    if missing and kind[0] in FALLBACK:  # per-glyph fallback (e.g. "→" is not in the site's Space Grotesk subset)
        fb = F(FALLBACK[kind[0]], size); asc, desc = f.getmetrics(); trk = ls * size
        fx = lambda ch: fb if ch in missing else f
        im = Image.new("RGBA", (int(sum(fx(ch).getlength(ch) for ch in s) + abs(trk) * len(s)) + 12, asc + desc + 8), (0, 0, 0, 0))
        d = ImageDraw.Draw(im); x = 6
        for ch in s:
            ff = fx(ch); d.text((x, 2 + asc), ch, font=ff, fill=color, anchor="ls"); x += ff.getlength(ch) + trk
        return im.crop(im.getbbox() or (0, 0, 1, 1))
    if ls:
        asc, desc = f.getmetrics(); trk = ls * size
        im = Image.new("RGBA", (int(f.getlength(s) + abs(trk) * len(s)) + 12, asc + desc + 4), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        for i, ch in enumerate(s):
            d.text((6 + f.getlength(s[:i]) + trk * i, 2), ch, font=f, fill=color)
        return im.crop(im.getbbox() or (0, 0, 1, 1))
    l, t_, r, b = f.getbbox(s)
    im = Image.new("RGBA", (r - l + 4, b - t_ + 4), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((2 - l, 2 - t_), s, font=f, fill=color)
    return im

def fit_text(s, kind, size, color, maxw, ls=0.0, min_size=24):
    """Largest text_img <= maxw wide."""
    while True:
        im = text_img(s, kind, size, color, ls)
        if im.width <= maxw or size <= min_size: return im
        size -= 2

def paste(canvas, im, cx, cy, scale=1.0, alpha=1.0):
    if scale <= 0.01 or alpha <= 0.01: return
    if abs(scale - 1) > 1e-3:
        im = im.resize((max(1, int(im.width * scale)), max(1, int(im.height * scale))), Image.LANCZOS)
    if alpha < 1:
        im = im.copy(); im.putalpha(im.getchannel("A").point(lambda v: int(v * alpha)))
    canvas.paste(im, (int(cx - im.width / 2), int(cy - im.height / 2)), im)

def shadowed(canvas, box, radius, fill, blur=30, off=18, sh_alpha=110):
    x0, y0, x1, y1 = map(int, box); pad = blur * 2
    sh = Image.new("RGBA", (x1 - x0 + pad * 2, y1 - y0 + pad * 2), (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle((pad, pad, pad + x1 - x0, pad + y1 - y0), radius, fill=(0, 0, 0, sh_alpha))
    sh = sh.filter(ImageFilter.GaussianBlur(blur))
    canvas.paste(sh, (x0 - pad, y0 - pad + off), sh)
    ImageDraw.Draw(canvas).rounded_rectangle(box, radius, fill=fill)

MARKUP = re.compile(r"(```[^`]+```|`[^`]+`|\*[^*]+\*|_[^_]+_|~[^~]+~)")
def parse_markup(s):
    """'*bold* _italic_ ~strike~ `mono`' -> [(text, style)]"""
    runs = []
    for part in MARKUP.split(s):
        if not part: continue
        if part.startswith("```"): runs.append((part[3:-3], "mono"))
        elif part[0] == "`": runs.append((part[1:-1], "mono"))
        elif part[0] == "*": runs.append((part[1:-1], "bold"))
        elif part[0] == "_": runs.append((part[1:-1], "ital"))
        elif part[0] == "~": runs.append((part[1:-1], "strike"))
        else: runs.append((part, "reg"))
    return runs

def wrap(s, font, maxw):
    lines, cur = [], ""
    for w_ in s.split():
        if font.getlength((cur + " " + w_).strip()) <= maxw: cur = (cur + " " + w_).strip()
        else: lines.append(cur); cur = w_
    return lines + [cur] if cur else lines

# ============================================================== phone mockup
PW, PH = 780, 1240
def phone(canvas, cx, cy):
    x0, y0 = cx - PW / 2, cy - PH / 2
    shadowed(canvas, (x0, y0, x0 + PW, y0 + PH), 90, (14, 14, 18), blur=44, off=34, sh_alpha=85)
    ImageDraw.Draw(canvas).rounded_rectangle((x0 + 3, y0 + 3, x0 + PW - 3, y0 + PH - 3), 87, outline=(70, 72, 82), width=3)
    return Image.new("RGBA", (PW - 44, PH - 44), T["screen"] + (255,)), (int(x0 + 22), int(y0 + 22))

def new_screen(): return Image.new("RGBA", (PW - 44, PH - 44), T["screen"] + (255,))

def finish_phone(canvas, scr, pos):
    mask = Image.new("L", scr.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, scr.width - 1, scr.height - 1), 68, fill=255)
    canvas.paste(scr, pos, mask)
    cx = pos[0] + scr.width / 2
    ImageDraw.Draw(canvas).rounded_rectangle((cx - 80, pos[1] + 18, cx + 80, pos[1] + 58), 20, fill=(8, 8, 10))

def status_bar(s, col):
    d = ImageDraw.Draw(s)
    d.text((60, 22), "9:41", font=F("semi", 30), fill=col)
    for i in range(4): d.rectangle((s.width - 170 + i * 14, 48 - i * 7, s.width - 160 + i * 14, 52), fill=col)
    d.rounded_rectangle((s.width - 100, 26, s.width - 50, 50), 7, outline=col, width=3)
    d.rectangle((s.width - 96, 30, s.width - 64, 46), fill=col)

def back_arrow(d, col, y=135):
    d.line((40, y, 58, y - 18), fill=col, width=6); d.line((40, y, 58, y + 18), fill=col, width=6)

def header_rule(s, h):
    if lum(T["header"]) > 235: ImageDraw.Draw(s).line((0, h - 1, s.width, h - 1), fill=(225, 225, 228), width=2)

def chat_header(s, title, sub="online"):
    d = ImageDraw.Draw(s); ht = T["header_text"]
    d.rectangle((0, 0, s.width, 190), fill=T["header"]); header_rule(s, 190)
    status_bar(s, ht); back_arrow(d, ht)
    d.ellipse((80, 100, 150, 170), fill=mix(T["header"], WHITE, 0.6))
    d.text((115, 135), title[0], font=F("bold", 34), fill=T["header"] if lum(T["header"]) < 200 else INK, anchor="mm")
    d.text((170, 102), title, font=F("semi", 36), fill=ht)
    d.text((170, 146), sub, font=F("reg", 26), fill=mix(ht, T["header"], 0.25))

def list_header(s, title):
    d = ImageDraw.Draw(s); ht = T["header_text"]
    d.rectangle((0, 0, s.width, 210), fill=T["header"]); header_rule(s, 210)
    status_bar(s, ht)
    d.text((40, 120), title, font=F("bold", 52), fill=ht)
    d.ellipse((s.width - 170, 125, s.width - 130, 165), outline=ht, width=5)
    d.line((s.width - 136, 159, s.width - 116, 179), fill=ht, width=6)
    for i in range(3): d.ellipse((s.width - 70, 128 + i * 18, s.width - 60, 138 + i * 18), fill=ht)

def page_header(s, title):
    d = ImageDraw.Draw(s); ht = T["header_text"]
    d.rectangle((0, 0, s.width, 200), fill=T["header"]); header_rule(s, 200)
    status_bar(s, ht); back_arrow(d, ht, 140)
    d.text((90, 140), title, font=fit_font("semi", 40, title, s.width - 130), fill=ht, anchor="lm")

def fit_font(kind, size, s, maxw):
    while F(kind, size).getlength(s) > maxw and size > 20: size -= 2
    return F(kind, size)

def chat_row(s, y, name, msg, time_, col, pinned=False, highlight=0.0):
    d = ImageDraw.Draw(s)
    if highlight > 0: d.rectangle((0, y, s.width, y + 140), fill=mix(T["screen"], T["accent"], 0.3 * highlight))
    d.ellipse((36, y + 25, 126, y + 115), fill=col)
    d.text((81, y + 70), name[0], font=F("bold", 40), fill=WHITE, anchor="mm")
    d.text((156, y + 30), name, font=fit_font("semi", 36, name, s.width - 330), fill=INK)
    d.text((156, y + 82), msg, font=fit_font("reg", 28, msg, s.width - 260), fill=MUTED)
    d.text((s.width - 40, y + 36), time_, font=F("reg", 24), fill=MUTED, anchor="ra")
    if pinned: pin_icon(d, s.width - 70, y + 98, 16, MUTED)
    d.line((156, y + 139, s.width, y + 139), fill=(225, 225, 228), width=2)

def pin_icon(d, cx, cy, r, col, angle=-35):
    a = math.radians(angle)
    def rot(px, py): return (cx + px * math.cos(a) - py * math.sin(a), cy + px * math.sin(a) + py * math.cos(a))
    d.polygon([rot(-r * .7, -r * 1.2), rot(r * .7, -r * 1.2), rot(r * .5, -r * .2), rot(r * 1.1, r * .25),
               rot(-r * 1.1, r * .25), rot(-r * .5, -r * .2)], fill=col)
    d.line([rot(0, r * .25), rot(0, r * 1.5)], fill=col, width=max(3, r // 4))

def run_font(st, size): return F({"strike": "reg"}.get(st, st), size if st != "mono" else size - 3)

def bubble(s, y, runs, out=True, scale=1.0, time_="9:41"):
    maxw = s.width - 230; size = 34
    while sum(run_font(st, size).getlength(tx) for tx, st in runs) > maxw and size > 22: size -= 2
    widths = [run_font(st, size).getlength(tx) for tx, st in runs]
    bw, bh = sum(widths) + 140, 96
    x1 = s.width - 30 if out else 30 + bw
    layer = Image.new("RGBA", (int(bw) + 40, bh + 40), (0, 0, 0, 0)); d = ImageDraw.Draw(layer)
    d.rounded_rectangle((10, 10, 10 + bw, 10 + bh), 26, fill=(T["bubble_out"] if out else T["bubble_in"]) + (255,))
    x = 34
    for (tx, st), w_ in zip(runs, widths):
        d.text((x, 10 + bh / 2), tx, font=run_font(st, size), fill=INK, anchor="lm")
        if st == "strike": d.line((x, 10 + bh / 2 + 2, x + w_, 10 + bh / 2 + 2), fill=INK, width=3)
        x += w_
    d.text((10 + bw - 22, 10 + bh - 16), time_, font=F("reg", 20), fill=MUTED, anchor="rb")
    if scale <= 0.02: return
    if scale < 1: layer = layer.resize((max(1, int(layer.width * scale)), max(1, int(layer.height * scale))), Image.LANCZOS)
    px = int((x1 + 10) - layer.width) if out else int(x1 - bw - 10)
    s.alpha_composite(layer, (max(0, px), max(0, int(y + (bh + 40) * (1 - scale) / 2) - 10)))

def input_bar(s, typed, cursor_on, send_press=0.0):
    d = ImageDraw.Draw(s); y = s.height - 140
    d.rounded_rectangle((24, y, s.width - 140, y + 100), 50, fill=T["field"])
    f = F("reg", 32); shown = typed
    while f.getlength(shown) > s.width - 240 and len(shown) > 1: shown = shown[1:]
    d.text((64, y + 50), shown, font=f, fill=INK, anchor="lm")
    if cursor_on:
        cx = 64 + f.getlength(shown) + 4; d.rectangle((cx, y + 28, cx + 3, y + 72), fill=T["send"])
    r = 50 * (1 - 0.15 * send_press); cx, cy = s.width - 74, y + 50
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=T["send"])
    d.polygon([(cx - 18, cy - 20), (cx + 24, cy), (cx - 18, cy + 20), (cx - 10, cy)], fill=WHITE)

def finger(canvas, x, y, press=0.0, alpha=1.0):
    d = ImageDraw.Draw(canvas, "RGBA")
    base = (20, 19, 15) if T["touch_dark"] else (255, 255, 255)
    if press > 0:
        r = 40 + 70 * press
        d.ellipse((x - r, y - r, x + r, y + r), outline=base + (int(200 * (1 - press) * alpha),), width=6)
    r = 34
    d.ellipse((x - r, y - r, x + r, y + r), fill=base + (int((60 if T["touch_dark"] else 150) * alpha),),
              outline=base + (int(230 * alpha),), width=4)

def toggle(d, x, y, on):
    """iOS-style switch, top-left (x, y), on in [0,1]."""
    d.rounded_rectangle((x, y, x + 100, y + 58), 29, fill=mix((205, 205, 210), T["accent"], on))
    kx = x + 29 + 42 * on
    d.ellipse((kx - 25, y + 4, kx + 25, y + 54), fill=WHITE, outline=(0, 0, 0, 25), width=1)

# ============================================================== brand overlays
@functools.lru_cache(64)
def pill_img(txt, col, txtcol=INKB, kind="M600", size=34, ls=0.08, padx=40, pady=20):
    t = text_img(txt, kind, size, txtcol, ls)
    im = Image.new("RGBA", (t.width + padx * 2, t.height + pady * 2), (0, 0, 0, 0))
    ImageDraw.Draw(im).rounded_rectangle((0, 0, im.width - 1, im.height - 1), im.height // 2, fill=col)
    im.alpha_composite(t, (padx, pady)); return im

def top_title(canvas, t, t0, badge, title, col, txtcol):
    p = prog(t, t0, t0 + 0.45)
    paste(canvas, pill_img(badge, col, txtcol), W / 2, 150, back(p) if p < 1 else 1, min(1, p * 2))
    p2 = prog(t, t0 + 0.12, t0 + 0.6)
    paste(canvas, fit_text(title, "D600", 86, INKB, 980, -0.03), W / 2, 268 + 40 * (1 - ease_out(p2)), 1, p2)

def caption(canvas, t, t0, t1, cap):
    if not cap or not (t0 <= t < t1 + 0.3): return
    line1, line2 = (cap + [None])[:2] if isinstance(cap, list) else (cap, None)
    a = ease_out(prog(t, t0, t0 + 0.35)) * (1 - prog(t, t1, t1 + 0.25)); p = ease_out(prog(t, t0, t0 + 0.35))
    lines = [fit_text(line1, "D600", 50, CREAM, 900, -0.02)]
    if line2: lines.append(fit_text(line2, "D600", 50, C_PROD, 900, -0.02))
    box_w = max(l.width for l in lines) + 90
    bh = 30 + sum(l.height + 14 for l in lines) + 16
    layer = Image.new("RGBA", (int(box_w), int(bh)), (0, 0, 0, 0))
    ImageDraw.Draw(layer).rounded_rectangle((0, 0, box_w - 1, bh - 1), 26, fill=INKB + (242,))
    y_ = 26
    for l in lines: layer.alpha_composite(l, (int((box_w - l.width) / 2), y_)); y_ += l.height + 14
    paste(canvas, layer, W / 2, 1690 + 30 * (1 - p), 1, a)

def progress(canvas, t, segs, total):
    d = ImageDraw.Draw(canvas, "RGBA")
    gap, x = 10, 40; tot = W - 80 - gap * (len(segs) - 1)
    for a, b in segs:
        w_ = tot * (b - a) / total
        d.rounded_rectangle((x, 44, x + w_, 52), 4, fill=INKB + (38,))
        fw = w_ * prog(t, a, b)
        if fw > 2: d.rounded_rectangle((x, 44, x + fw, 52), 4, fill=INKB + (230,))
        x += w_ + gap

@functools.lru_cache(16)
def kmark(h, col):
    m = Image.open(BR + "k-mark.png").convert("RGBA").getchannel("A")
    m = m.resize((int(m.width * h / m.height), h), Image.LANCZOS)
    im = Image.new("RGBA", m.size, col + (255,)); im.putalpha(m); return im

def slide_offset(t, t0, t1):
    return (1 - ease_io(prog(t, t0, t0 + 0.4))) * W * 0.9 - ease_io(prog(t, t1 - 0.35, t1)) * W * 0.9

# ===================================================================== scenes
# Each trick scene is 5s long; lt = local time. CAPS = caption windows (before / after the "action").
def scene_hook(c, t, cfg):
    h = cfg["hook"]
    p = prog(t, 0.0, 0.5)
    s3 = back(p, 2.4) if p < 1 else 1 + 0.03 * math.sin(t * 6)
    paste(c, fit_text(h.get("kicker", ""), "M500", 34, MUTEDB, 960, 0.1), W / 2, 330, 1, prog(t, 0.0, 0.35)) if h.get("kicker") else None
    n3 = text_img(str(h.get("number", len(cfg["tricks"]))), "D700", 470, INKB)
    tw = max(440, n3.width + 120)
    tile = Image.new("RGBA", (tw, 520), (0, 0, 0, 0))
    ImageDraw.Draw(tile).rounded_rectangle((0, 0, tw - 1, 519), 56, fill=C_VIDEO)
    tile.alpha_composite(n3, ((tw - n3.width) // 2, (520 - n3.height) // 2))
    tile = tile.rotate(-4 * (1 - ease_out(p)) + 3, resample=Image.BICUBIC, expand=True)
    paste(c, tile, W / 2, 720, s3 * (1.0 + 0.6 * (1 - p)), min(1, p * 3))
    l1 = fit_text(h["line1"], "D700", 118, INKB, 1000, -0.035)
    l2 = fit_text(h.get("line2", ""), "D500", 96, INKB, 1000, -0.035) if h.get("line2") else None
    y1 = 1150; y2 = y1 + l1.height / 2 + 40 + (l2.height / 2 if l2 else 0)
    if l2:  # amber highlighter behind line 2
        q = ease_out(prog(t, 1.15, 1.7)); hw = l2.width / 2 + 10
        ImageDraw.Draw(c).rounded_rectangle((W / 2 - hw, y2 + l2.height * 0.05, W / 2 - hw + 2 * hw * q, y2 + l2.height * 0.42), 10, fill=C_PROD)
    for i, (im, y, t0) in enumerate([(l1, y1, 0.45), (l2, y2, 0.7)]):
        if im is None: continue
        q = prog(t, t0, t0 + 0.4)
        paste(c, im, W / 2 + 300 * (1 - ease_out(q)) * (1 if i % 2 else -1), y, 1, q)
    if h.get("teaser"):
        paste(c, fit_text(h["teaser"], "I500", 40, MUTEDB, 960), W / 2, 1460, 1, prog(t, 1.6, 2.0))
    out = prog(t, 2.7, 3.0)
    if out > 0: c.alpha_composite(Image.new("RGBA", (W, H), BASE + (int(255 * out),)))

def screen_chat_send(c, scr, pos, lt, sc):
    chat_header(scr, sc.get("contact", "Alex"), sc.get("contact_sub", "online"))
    y = 230
    for msg in sc.get("incoming", []):
        bubble(scr, y, parse_markup(msg), out=False, time_="9:38"); y += 120
    full = sc["type_text"]; tp = prog(lt, 0.7, 2.6); n = int(len(full) * tp)
    if lt <= 2.95:
        input_bar(scr, full[:n], int(lt * 3) % 2 == 0 or tp < 1, send_press=prog(lt, 2.75, 2.95))
    else:
        input_bar(scr, "", int(lt * 3) % 2 == 0)
        bubble(scr, y + 30, parse_markup(sc.get("sent", full)), out=True, scale=back(prog(lt, 2.95, 3.35)))
    finish_phone(c, scr, pos)
    if 2.55 < lt < 3.1:
        finger(c, pos[0] + scr.width - 74, pos[1] + scr.height - 90, prog(lt, 2.75, 3.05), 1 - prog(lt, 2.95, 3.1))

def screen_search_open(c, scr, pos, lt, sc):
    if lt <= 2.3:
        d = ImageDraw.Draw(scr); list_header(scr, sc.get("list_title", "Chats"))
        d.rounded_rectangle((30, 230, scr.width - 30, 320), 45, fill=T["field"])
        q = sc["query"]; n = int(len(q) * prog(lt, 0.7, 1.1))
        d.text((80, 275), q[:n] if n else "Search…", font=F("reg", 34), fill=INK if n else MUTED, anchor="lm")
        res = sc["result"]
        rows = [(res[0], res[1], "", T["accent"])] + [(r[0], r[1], r[2], AV_COLS[i % 6]) for i, r in enumerate(sc.get("others", []))]
        filt = prog(lt, 1.1, 1.5); y = 340
        for i, r in enumerate(rows[:6]):
            if i == 0: chat_row(scr, y, *r, highlight=prog(lt, 1.6, 1.9))
            else:
                chat_row(scr, y, *r)
                if filt > 0:
                    ov = Image.new("RGBA", scr.size, (0, 0, 0, 0))
                    ImageDraw.Draw(ov).rectangle((0, y, scr.width, y + 140), fill=T["screen"] + (int(255 * filt),))
                    scr.alpha_composite(ov)
            y += 140
    else:
        chat_header(scr, sc.get("open_title", sc["result"][0]), sc.get("open_sub", ""))
        y = 230
        for i, it in enumerate(sc.get("items", [])[:6]):
            bubble(scr, y, parse_markup(it), out=True, scale=back(prog(lt, 2.4 + i * 0.4, 2.75 + i * 0.4))); y += 120
        input_bar(scr, "", int(lt * 3) % 2 == 0)
    finish_phone(c, scr, pos)
    if 1.45 < lt < 2.3:
        finger(c, pos[0] + 330, pos[1] + 410, prog(lt, 1.6, 2.1), 1 - prog(lt, 2.05, 2.3))

def screen_long_press_pin(c, scr, pos, lt, sc):
    list_header(scr, sc.get("list_title", "Chats"))
    rows = [(r[0], r[1], r[2], AV_COLS[i % 6]) for i, r in enumerate(sc["rows"][:6])]
    tgt = sc.get("target", len(rows) - 2)
    press = prog(lt, 0.8, 1.6); toolbar = prog(lt, 1.6, 1.9)
    move = ease_io(prog(lt, 2.5, 3.2)); base_y = 230
    for i, r in enumerate(rows):
        if i == tgt: continue
        chat_row(scr, base_y + i * 140 + (140 * move if i < tgt else 0), *r)
    hl = toolbar * (1 - prog(lt, 3.3, 3.8))
    chat_row(scr, base_y + tgt * 140 * (1 - move), *rows[tgt], pinned=lt > 2.5, highlight=max(hl, press * 0.6))
    if toolbar > 0 and lt < 2.6:
        d = ImageDraw.Draw(scr); dark = mix(T["header"], (0, 0, 0), 0.28) if lum(T["header"]) < 200 else mix(T["header"], T["accent"], 0.15)
        d.rectangle((0, 0, scr.width, 210), fill=mix(T["header"], dark, toolbar))
        status_bar(scr, T["header_text"]); ht = T["header_text"]
        d.text((40, 120), "1", font=F("bold", 48), fill=ht)
        pp = prog(lt, 2.0, 2.4)
        pin_icon(d, scr.width - 260, 150, int(22 * (1 + 0.25 * math.sin(pp * math.pi))), ht)
        d.rectangle((scr.width - 180, 132, scr.width - 140, 168), outline=ht, width=4)
        d.rectangle((scr.width - 100, 132, scr.width - 60, 168), fill=ht)
    finish_phone(c, scr, pos)
    if 0.6 < lt < 1.8:
        finger(c, pos[0] + 400, pos[1] + base_y + tgt * 140 + 70, press if press < 1 else 0, 1 - prog(lt, 1.6, 1.8))
    if 1.9 < lt < 2.6:
        finger(c, pos[0] + scr.width - 260, pos[1] + 150, prog(lt, 2.0, 2.4), 1 - prog(lt, 2.4, 2.6))

def screen_settings_toggle(c, scr, pos, lt, sc):
    """Settings list -> tap a row -> detail page -> flip a switch on."""
    rows = sc["rows"][:7]; tap = sc.get("tap", 0)
    # --- list page
    a = new_screen(); d = ImageDraw.Draw(a)
    page_header(a, sc.get("title", "Settings"))
    hl = prog(lt, 1.05, 1.25) * (1 - prog(lt, 1.8, 2.0))
    for i, label in enumerate(rows):
        y = 220 + i * 124
        if i == tap and hl > 0: d.rectangle((0, y, a.width, y + 124), fill=mix(T["screen"], T["accent"], 0.18 * hl))
        d.rounded_rectangle((40, y + 34, 96, y + 90), 16, fill=mix(T["screen"], AV_COLS[i % 6], 0.85))
        d.text((68, y + 62), label[0].upper(), font=F("bold", 28), fill=WHITE, anchor="mm")
        d.text((124, y + 62), label, font=fit_font("reg", 34, label, a.width - 220), fill=INK, anchor="lm")
        d.line((a.width - 60, y + 50, a.width - 48, y + 62), fill=MUTED, width=4)
        d.line((a.width - 48, y + 62, a.width - 60, y + 74), fill=MUTED, width=4)
        d.line((124, y + 123, a.width, y + 123), fill=(225, 225, 228), width=2)
    # --- detail page
    b = new_screen(); d = ImageDraw.Draw(b)
    page_header(b, sc.get("detail_title", rows[tap]))
    y = 240
    if sc.get("detail_text"):
        for ln in wrap(sc["detail_text"], F("reg", 30), b.width - 90)[:4]:
            d.text((44, y), ln, font=F("reg", 30), fill=MUTED); y += 44
        y += 26
    card_y = y; on = ease_io(prog(lt, 2.75, 3.0))
    d.rounded_rectangle((24, card_y, b.width - 24, card_y + 150), 24, fill=T["field"] if lum(T["screen"]) < 245 else (246, 246, 248))
    lbl = sc["toggle_label"]
    d.text((56, card_y + 52), lbl, font=fit_font("semi", 34, lbl, b.width - 250), fill=INK, anchor="lm")
    if sc.get("toggle_sub"):
        d.text((56, card_y + 102), sc["toggle_sub"], font=fit_font("reg", 26, sc["toggle_sub"], b.width - 250), fill=MUTED, anchor="lm")
    toggle(d, b.width - 150, card_y + 46, on if not sc.get("start_on") else 1 - on)
    # --- compose with a push transition
    k = ease_io(prog(lt, 1.5, 1.85))
    if k <= 0: scr.paste(a, (0, 0))
    elif k >= 1: scr.paste(b, (0, 0))
    else:
        scr.paste(a, (int(-k * scr.width * 0.3), 0))
        sh = Image.new("RGBA", scr.size, (0, 0, 0, int(60 * k))); scr.alpha_composite(sh)
        scr.paste(b, (int((1 - k) * scr.width), 0))
    finish_phone(c, scr, pos)
    if 0.75 < lt < 1.5:
        finger(c, pos[0] + 300, pos[1] + 220 + tap * 124 + 62, prog(lt, 1.0, 1.4), 1 - prog(lt, 1.35, 1.5))
    if 2.45 < lt < 3.15:
        finger(c, pos[0] + b.width - 100, pos[1] + card_y + 75, prog(lt, 2.7, 3.05), 1 - prog(lt, 3.0, 3.15))

# ---------------------------------------------------------- mail-style widgets
def star(d, cx, cy, r, col):
    pts = [(cx + (r if k % 2 == 0 else r * .45) * math.sin(k * math.pi / 5), cy - (r if k % 2 == 0 else r * .45) * math.cos(k * math.pi / 5)) for k in range(10)]
    d.polygon(pts, outline=col, width=3)

def kebab(d, x, y, col):
    for i in (-1, 0, 1): d.ellipse((x - 5, y + i * 16 - 5, x + 5, y + i * 16 + 5), fill=col)

def email_row(s, y, sender, subject, snippet, time_, col, unread=True):
    d = ImageDraw.Draw(s)
    d.ellipse((32, y + 30, 112, y + 110), fill=col)
    d.text((72, y + 70), sender[0].upper(), font=F("bold", 36), fill=WHITE, anchor="mm")
    d.text((140, y + 24), sender, font=fit_font("bold" if unread else "semi", 32, sender, s.width - 330), fill=INK)
    d.text((s.width - 36, y + 30), time_, font=F("bold" if unread else "reg", 24), fill=INK if unread else MUTED, anchor="ra")
    d.text((140, y + 68), subject, font=fit_font("semi" if unread else "reg", 28, subject, s.width - 200), fill=INK)
    d.text((140, y + 108), snippet, font=fit_font("reg", 26, snippet, s.width - 230), fill=MUTED)
    star(d, s.width - 56, y + 122, 17, MUTED)

def snackbar(s, text, action, appear):
    if appear <= 0: return
    d = ImageDraw.Draw(s); y = s.height - 150 + (1 - appear) * 220
    d.rounded_rectangle((24, y, s.width - 24, y + 104), 18, fill=(48, 48, 50))
    act_f = F("semi", 30); aw = act_f.getlength(action) if action else 0
    d.text((56, y + 52), text, font=fit_font("reg", 30, text, s.width - 160 - aw), fill=WHITE, anchor="lm")
    if action: d.text((s.width - 56, y + 52), action, font=act_f, fill=mix(T["accent"], WHITE, 0.55), anchor="rm")

def mail_header(s, title="", icons=()):
    d = ImageDraw.Draw(s); ht = T["header_text"]
    d.rectangle((0, 0, s.width, 200), fill=T["header"]); header_rule(s, 200)
    status_bar(s, ht); back_arrow(d, ht, 140)
    if title: d.text((90, 140), title, font=F("semi", 38), fill=ht, anchor="lm")
    x = s.width - 150
    for ic in icons:
        if ic == "send": d.polygon([(x - 20, 120), (x + 24, 140), (x - 20, 160), (x - 12, 140)], fill=ht)
        elif ic == "clip":
            d.arc((x - 12, 116, x + 12, 164), 200, 160, fill=ht, width=4)
        elif ic == "archive":
            d.rectangle((x - 22, 122, x + 22, 134), outline=ht, width=4); d.rectangle((x - 18, 134, x + 18, 160), outline=ht, width=4)
            d.line((x - 7, 145, x + 7, 145), fill=ht, width=4)
        elif ic == "trash":
            d.line((x - 22, 126, x + 22, 126), fill=ht, width=4); d.rectangle((x - 16, 130, x + 16, 162), outline=ht, width=4)
            d.line((x - 6, 120, x + 6, 120), fill=ht, width=4)
        x -= 90
    kebab(d, s.width - 60, 140, ht)

def base_compose(s, sc):
    mail_header(s, "Compose", ("send",)); d = ImageDraw.Draw(s); y = 210
    for lab, val in [("From", sc.get("from", "me@example.com")), ("To", sc.get("to", "")), ("", sc.get("subject", ""))]:
        vx = 130 if lab else 40
        if lab: d.text((40, y + 45), lab, font=F("reg", 30), fill=MUTED, anchor="lm")
        if lab == "To" and val:
            w_ = F("reg", 28).getlength(val) + 80
            d.rounded_rectangle((vx, y + 18, vx + w_, y + 72), 27, outline=(205, 205, 210), width=2)
            d.ellipse((vx + 6, y + 24, vx + 48, y + 66), fill=AV_COLS[0])
            d.text((vx + 27, y + 45), val[0].upper(), font=F("bold", 22), fill=WHITE, anchor="mm")
            d.text((vx + 58, y + 45), val, font=F("reg", 28), fill=INK, anchor="lm")
        else:
            d.text((vx, y + 45), val, font=fit_font("reg" if lab else "semi", 30, val, s.width - vx - 40), fill=INK, anchor="lm")
        d.line((0, y + 90, s.width, y + 90), fill=(228, 228, 232), width=2); y += 90
    y += 34
    for para in sc.get("body", []):
        for ln in wrap(para, F("reg", 30), s.width - 80): d.text((40, y), ln, font=F("reg", 30), fill=INK); y += 46
        y += 22

def base_email(s, sc):
    mail_header(s, "", ("trash", "archive")); d = ImageDraw.Draw(s); y = 230
    for ln in wrap(sc.get("subject", ""), F("semi", 40), s.width - 80)[:3]:
        d.text((40, y), ln, font=F("semi", 40), fill=INK); y += 56
    y += 30; snd = sc.get("sender", "Sender")
    d.ellipse((40, y, 120, y + 80), fill=AV_COLS[2])
    d.text((80, y + 40), snd[0].upper(), font=F("bold", 34), fill=WHITE, anchor="mm")
    d.text((144, y + 6), snd, font=fit_font("semi", 32, snd, s.width - 330), fill=INK)
    d.text((144, y + 48), "to me", font=F("reg", 26), fill=MUTED)
    d.text((s.width - 40, y + 10), sc.get("time", "9:14 AM"), font=F("reg", 24), fill=MUTED, anchor="ra")
    y += 130
    for para in sc.get("body", []):
        for ln in wrap(para, F("reg", 30), s.width - 80): d.text((40, y), ln, font=F("reg", 30), fill=INK); y += 46
        y += 22

MENU_W, MENU_IH = 460, 88
def menu_geom(s, n):
    lw, lh = MENU_W + 60, MENU_IH * n + 24 + 60
    return s.width - 10 - lw, 120, lw, lh   # x, y, w, h of the menu layer

def popup_menu(s, items, appear, hi_idx=None, hi=0.0):
    if appear <= 0.01: return
    mx, my, lw, lh = menu_geom(s, len(items))
    layer = Image.new("RGBA", (lw, lh), (0, 0, 0, 0))
    shadowed(layer, (30, 20, 30 + MENU_W, 20 + MENU_IH * len(items) + 24), 22, WHITE, blur=14, off=8, sh_alpha=120)
    d = ImageDraw.Draw(layer)
    d.rounded_rectangle((30, 20, 30 + MENU_W, 20 + MENU_IH * len(items) + 24), 22, outline=(222, 222, 228), width=2)
    for i, it in enumerate(items):
        y = 32 + i * MENU_IH
        if i == hi_idx and hi > 0: d.rectangle((30, y, 30 + MENU_W, y + MENU_IH), fill=mix(WHITE, T["accent"], 0.14 * hi))
        d.text((66, y + MENU_IH / 2), it, font=fit_font("reg", 32, it, MENU_W - 70), fill=INK, anchor="lm")
    sc_ = max(0.05, appear)
    if sc_ < 1: layer = layer.resize((max(1, int(lw * sc_)), max(1, int(lh * sc_))), Image.LANCZOS)
    s.paste(layer, (int(mx + lw - layer.width), my), layer)

SHEET_RH = 104
def sheet_top(s, n): return s.height - (130 + SHEET_RH * n + 70)

def bottom_sheet(s, title, opts, appear, hi_idx=None, hi=0.0):
    if appear <= 0.01: return
    s.alpha_composite(Image.new("RGBA", s.size, (0, 0, 0, int(90 * appear))))
    full = s.height - sheet_top(s, len(opts)); y0 = s.height - full * appear
    d = ImageDraw.Draw(s)
    d.rounded_rectangle((0, y0, s.width, s.height + 60), 36, fill=WHITE)
    d.rounded_rectangle((s.width / 2 - 40, y0 + 16, s.width / 2 + 40, y0 + 24), 4, fill=(205, 205, 210))
    d.text((40, y0 + 72), title, font=F("semi", 34), fill=INK, anchor="lm")
    for i, (lab, det) in enumerate(opts):
        y = y0 + 120 + i * SHEET_RH
        if i == hi_idx and hi > 0: d.rectangle((0, y, s.width, y + SHEET_RH), fill=mix(WHITE, T["accent"], 0.14 * hi))
        d.text((40, y + SHEET_RH / 2), lab, font=fit_font("reg", 32, lab, s.width - 330), fill=INK, anchor="lm")
        if det: d.text((s.width - 40, y + SHEET_RH / 2), det, font=F("reg", 26), fill=MUTED, anchor="rm")

def screen_menu_pick(c, scr, pos, lt, sc):
    """Tap the 3-dot menu -> pick an item -> (optional) bottom sheet option -> snackbar confirmation."""
    (base_email if sc.get("base") == "email" else base_compose)(scr, sc)
    items = sc["menu"]; pick = sc.get("pick", 0); opts = [tuple(o) for o in sc.get("sheet", [])]; sp = sc.get("sheet_pick", 0)
    popup_menu(scr, items, ease_out(prog(lt, 0.95, 1.15)) * (1 - prog(lt, 1.75, 1.85)), pick, prog(lt, 1.45, 1.6))
    if opts:
        bottom_sheet(scr, sc.get("sheet_title", items[pick]), opts,
                     ease_out(prog(lt, 1.85, 2.2)) * (1 - ease_io(prog(lt, 2.85, 3.1))), sp, prog(lt, 2.5, 2.65))
    if sc.get("toast") and lt > 3.0:
        snackbar(scr, sc["toast"], sc.get("toast_action", "Undo"), ease_out(prog(lt, 3.05, 3.3)))
    finish_phone(c, scr, pos)
    if 0.45 < lt < 1.0:
        finger(c, pos[0] + scr.width - 60, pos[1] + 140, prog(lt, 0.65, 0.95), 1 - prog(lt, 0.9, 1.0))
    mx, my, lw, lh = menu_geom(scr, len(items))
    if 1.2 < lt < 1.8:
        finger(c, pos[0] + mx + 30 + MENU_W * 0.4, pos[1] + my + 32 + pick * MENU_IH + MENU_IH / 2,
               prog(lt, 1.4, 1.7), 1 - prog(lt, 1.65, 1.8))
    if opts and 2.25 < lt < 2.9:
        finger(c, pos[0] + scr.width * 0.4, pos[1] + sheet_top(scr, len(opts)) + 120 + sp * SHEET_RH + SHEET_RH / 2,
               prog(lt, 2.45, 2.8), 1 - prog(lt, 2.75, 2.9))

def screen_swipe_action(c, scr, pos, lt, sc):
    """Inbox-style list -> swipe one row away revealing the action -> list closes the gap -> snackbar."""
    list_header(scr, sc.get("list_title", "Inbox")); d = ImageDraw.Draw(scr)
    d.text((40, 236), sc.get("section", "Primary"), font=F("semi", 26), fill=MUTED)
    rows = sc["rows"][:5]; tgt = sc.get("target", 0); y0, RH = 280, 170
    dirn = -1 if sc.get("direction", "left") == "left" else 1
    sw = ease_io(prog(lt, 1.0, 1.9)); collapse = ease_io(prog(lt, 2.0, 2.4))
    acol = hx(sc.get("action_color", "#1E8E3E"))
    for i, r in enumerate(rows):
        y = y0 + i * RH - (RH * collapse if i > tgt else 0)
        if i != tgt:
            email_row(scr, int(y), *r[:4], AV_COLS[i % 6], unread=i % 3 != 2); continue
        if collapse >= 1: continue
        strip = Image.new("RGBA", (scr.width, RH), acol + (255,)); sd = ImageDraw.Draw(strip)
        lab = sc.get("action_label", "Archive")
        if dirn < 0: sd.text((scr.width - 56, RH / 2), lab, font=F("semi", 32), fill=WHITE, anchor="rm")
        else: sd.text((56, RH / 2), lab, font=F("semi", 32), fill=WHITE, anchor="lm")
        row = Image.new("RGBA", (scr.width, RH), T["screen"] + (255,))
        email_row(row, 0, *r[:4], AV_COLS[i % 6])
        strip.paste(row, (int(dirn * sw * scr.width), 0), row)
        h = max(1, int(RH * (1 - collapse)))
        scr.paste(strip.crop((0, 0, scr.width, h)), (0, int(y)))
    if sc.get("toast") and lt > 2.2:
        snackbar(scr, sc["toast"], sc.get("toast_action", "Undo"), ease_out(prog(lt, 2.3, 2.55)))
    finish_phone(c, scr, pos)
    if 0.7 < lt < 2.0:
        fx = scr.width - 160 if dirn < 0 else 160
        fx += dirn * sw * (scr.width - 320)
        finger(c, pos[0] + fx, pos[1] + y0 + tgt * RH + RH / 2, prog(lt, 0.8, 1.0) if lt < 1.0 else 0, 1 - prog(lt, 1.8, 2.0))

SCREENS = {"chat_send": (screen_chat_send, (0.6, 2.9), (3.0, 4.7)),
           "search_open": (screen_search_open, (0.5, 2.3), (2.4, 4.7)),
           "long_press_pin": (screen_long_press_pin, (0.5, 2.4), (2.5, 4.7)),
           "settings_toggle": (screen_settings_toggle, (0.5, 2.6), (2.7, 4.7)),
           "menu_pick": (screen_menu_pick, (0.4, 2.8), (2.95, 4.7)),
           "swipe_action": (screen_swipe_action, (0.5, 2.2), (2.35, 4.7))}
ACTION_AT = {"chat_send": 2.95, "search_open": 2.4, "long_press_pin": 2.5, "settings_toggle": 2.8,
             "menu_pick": 3.0, "swipe_action": 2.0}

def scene_trick(c, t, cfg, i, t0):
    tr = cfg["tricks"][i]; lt = t - t0
    col, tcol = TRICK_COLORS[i % len(TRICK_COLORS)]
    top_title(c, t, t0, f'{cfg.get("badge", "TRICK")} #{i + 1}', tr["title"], col, tcol)
    fn, capA, capB = SCREENS[tr["screen"]["type"]]
    scr, pos = phone(c, W / 2, 1010)
    fn(c, scr, pos, lt, tr["screen"])
    caps = tr.get("captions", [])
    if len(caps) > 0: caption(c, lt, *capA, caps[0])
    if len(caps) > 1: caption(c, lt, *capB, caps[1])

def scene_cta(c, t, cfg, t0):
    cta = cfg.get("cta", {}); lt = t - t0; p = prog(lt, 0, 0.45)
    paste(c, fit_text(cta.get("line1", "Which trick"), "D700", 110, INKB, 1000, -0.035), W / 2, 560, back(p) if p < 1 else 1, p)
    paste(c, fit_text(cta.get("line2", "was new to you?"), "D500", 96, INKB, 1000, -0.035), W / 2, 700,
          back(prog(lt, .1, .55)) if lt < .55 else 1, prog(lt, .1, .4))
    chips = cta.get("chips") or [tr.get("chip", tr["title"].split()[0]) for tr in cfg["tricks"]]
    step = 125 if len(chips) <= 3 else 105
    for i, lab in enumerate(chips):
        q = prog(lt, 0.3 + i * 0.12, 0.65 + i * 0.12)
        col, tcol = TRICK_COLORS[i % len(TRICK_COLORS)]
        paste(c, pill_img(f"{i + 1}  {lab}", col, tcol, "D600", 46, -0.01, 46, 22), W / 2, 880 + i * step,
              back(q) if q < 1 else 1, min(1, q * 2))
    paste(c, fit_text(cta.get("prompt", "COMMENT THE NUMBER"), "M500", 36, MUTEDB, 960, 0.08), W / 2,
          880 + len(chips) * step + 30, 1, prog(lt, 0.8, 1.2))
    b = prog(lt, 1.0, 1.4)
    btn = Image.new("RGBA", (800, 140), (0, 0, 0, 0))
    ImageDraw.Draw(btn).rounded_rectangle((0, 0, 799, 140 - 1), 70, fill=INKB)
    btn.alpha_composite(kmark(64, CREAM), (64, 38))
    lab = fit_text(cta.get("button", f'Follow {cfg.get("handle", "")}'), "D600", 46, CREAM, 560, -0.01)
    btn.alpha_composite(lab, (int(160 + (800 - 160 - 50 - lab.width) / 2), int(70 - lab.height / 2)))
    pulse = 1 + 0.04 * math.sin(lt * 10) * (lt > 1.4)
    paste(c, btn, W / 2, 1560, (back(b) if b < 1 else 1) * pulse, b)

# ===================================================================== timeline
HOOK, TRICK, CTA = 3.0, 5.0, 2.0
def timeline(cfg):
    n = len(cfg["tricks"])
    segs = [(0, HOOK)] + [(HOOK + i * TRICK, HOOK + (i + 1) * TRICK) for i in range(n)]
    segs.append((segs[-1][1], segs[-1][1] + CTA))
    return segs, segs[-1][1]

def frame(cfg, i):
    segs, total = timeline(cfg); t = i / FPS
    bg = background(t)
    for k, (a, b) in enumerate(segs):
        if not (a - 0.01 <= t < b): continue
        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        if k == 0: scene_hook(layer, t, cfg); off = 0
        elif k == len(segs) - 1: scene_cta(layer, t, cfg, a); off = slide_offset(t, a, b + 1)
        else: scene_trick(layer, t, cfg, k - 1, a); off = slide_offset(t, a, b)
        if abs(off) < 1: bg.alpha_composite(layer)
        else: bg.paste(layer, (int(off), 0), layer)
    progress(bg, t, segs, total)
    handle = cfg.get("handle")
    if handle:
        wm = text_img(handle, "M500", 28, INKB + (150,), 0.02)
        paste(bg, wm, W - 56 - wm.width / 2, H - 78)
        km = kmark(36, INKB).copy(); km.putalpha(km.getchannel("A").point(lambda v: v * 150 // 255))
        bg.alpha_composite(km, (int(W - 56 - wm.width - 16 - km.width), int(H - 78 - km.height / 2)))
    return bg.convert("RGB")

# ======================================================================= audio
SR = 44100
def make_audio(path, cfg):
    segs, dur = timeline(cfg)
    n = int(SR * dur); a = np.zeros(n, np.float32); tt = np.arange(n) / SR
    beat = 60 / 120
    def add(sig, t0, gain=1.0):
        s = int(t0 * SR); e = min(n, s + len(sig))
        if 0 <= s < n: a[s:e] += sig[:e - s] * gain
    kl = int(0.35 * SR); kt = np.arange(kl) / SR
    kick = np.sin(2 * np.pi * (50 * kt + 90 * (1 - np.exp(-kt * 30)) / 30)) * np.exp(-kt * 9)
    hl = int(0.06 * SR); hat = np.diff(np.random.default_rng(1).standard_normal(hl) * np.exp(-np.arange(hl) / SR * 70), prepend=0)
    sl = int(0.2 * SR); snare = np.random.default_rng(2).standard_normal(sl) * np.exp(-np.arange(sl) / SR * 22)
    cta0 = segs[-1][0]
    for b in range(int(dur / beat)):
        t0 = b * beat
        if t0 < cta0 or b % 2 == 0: add(kick, t0, 0.9)
        if b % 2 == 1: add(snare, t0, 0.25)
        add(hat, t0 + beat / 2, 0.18); add(hat, t0, 0.08)
    roots = [55.0, 43.65, 65.41, 49.0]; chords = [[220, 261.6, 329.6], [174.6, 220, 261.6], [261.6, 329.6, 392], [196, 246.9, 293.7]]
    bar = beat * 2
    for k in range(int(math.ceil(dur / bar))):
        t0 = k * bar; s = int(t0 * SR); e = min(n, int((t0 + bar) * SR)); seg = tt[s:e] - t0
        env = np.minimum(1, seg * 30) * np.exp(-seg * 1.2); r = roots[k % 4]
        a[s:e] += (np.sign(np.sin(2 * np.pi * r * seg)) * 0.5 + np.sin(2 * np.pi * r * seg)) * env * 0.12
        pad_env = np.minimum(1, seg * 4) * np.minimum(1, (bar - seg) * 6)
        for f in chords[k % 4]:
            a[s:e] += (np.sin(2 * np.pi * f * seg) + 0.3 * np.sin(2 * np.pi * f * 2.003 * seg)) * pad_env * 0.035
    for _, b in segs[:-1]:  # whoosh into each new scene
        wl = int(0.5 * SR); w_ = np.random.default_rng(int(b * 10)).standard_normal(wl)
        add(np.convolve(w_, np.ones(12) / 12, "same") * np.sin(np.linspace(0, np.pi, wl)) ** 2, b - 0.15, 0.5)
    pl = int(0.12 * SR); pt = np.arange(pl) / SR
    pop = np.sin(2 * np.pi * (900 * pt - 2500 * pt ** 2)) * np.exp(-pt * 35)
    pops = [0.05, cta0, cta0 + 0.3, cta0 + 0.42, cta0 + 0.54]
    for i, (s0, _) in enumerate(segs[1:-1]):
        pops += [s0, s0 + ACTION_AT[cfg["tricks"][i]["screen"]["type"]]]
    for t0 in pops: add(pop, t0, 0.35)
    a *= np.minimum(1, (dur - tt) / 0.8)
    pcm = (np.tanh(a * 1.3) * 0.85 * 32767).astype(np.int16)
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(SR); wf.writeframes(pcm.tobytes())

# ========================================================================= main
def load(path):
    cfg = json.load(open(path))
    assert 1 <= len(cfg["tricks"]) <= 5, "use 1-5 tricks"
    for tr in cfg["tricks"]:
        assert tr["screen"]["type"] in SCREENS, f'unknown screen type {tr["screen"]["type"]!r}; use one of {list(SCREENS)}'
    set_theme(cfg.get("app", {}))
    return cfg

def write_extras(cfg, outdir):
    """cover.png (hook at full reveal, for the Reels/TikTok cover) + post.txt (caption + hashtags)."""
    frame(cfg, int(2.3 * FPS)).save(os.path.join(outdir, "cover.png"))
    post = cfg.get("post")
    if post:
        txt = post.get("caption", "").strip() + "\n\n" + " ".join("#" + h.lstrip("#") for h in post.get("hashtags", []))
        open(os.path.join(outdir, "post.txt"), "w").write(txt.strip() + "\n")

def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args: sys.exit(__doc__)
    cfg_path = os.path.abspath(args[0]); cfg = load(cfg_path)
    outdir = os.path.dirname(cfg_path)
    out = os.path.join(outdir, cfg.get("output", "reel.mp4"))
    segs, dur = timeline(cfg)
    write_extras(cfg, outdir)
    if "--stills" in sys.argv:
        times = [1.6] + [a + 2.0 for a, _ in segs[1:-1]] + [a + 4.0 for a, _ in segs[1:-1]] + [dur - 0.5]
        os.makedirs(os.path.join(outdir, "stills"), exist_ok=True)
        for t in sorted(times):
            frame(cfg, int(t * FPS)).save(os.path.join(outdir, "stills", f"t{t:05.2f}.png"))
        print("stills ->", os.path.join(outdir, "stills")); return
    wav = os.path.splitext(out)[0] + ".wav"; make_audio(wav, cfg)
    ff = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                           "-r", str(FPS), "-i", "-", "-i", wav, "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                           "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", out],
                          stdin=subprocess.PIPE)
    N = int(round(dur * FPS))
    for i in range(N):
        ff.stdin.write(frame(cfg, i).tobytes())
        if i % 90 == 0: print(f"frame {i}/{N}", flush=True)
    ff.stdin.close(); ff.wait(); os.remove(wav)
    print(f"done {out} ({dur:.0f}s)")

if __name__ == "__main__":
    main()
