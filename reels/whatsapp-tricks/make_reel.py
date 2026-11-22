"""20s vertical reel: '3 WhatsApp tricks nobody told you'. All graphics + audio generated in code."""
import math, subprocess, wave, functools, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

W, H, FPS, DUR = 1080, 1920, 30, 20.0
N = int(FPS * DUR)
OUT = sys.argv[1] if len(sys.argv) > 1 else "reel.mp4"
FD = "/usr/share/fonts/opentype/inter/"

@functools.lru_cache(None)
def F(kind, size):
    path = {"black": FD + "Inter-Black.otf", "bold": FD + "Inter-Bold.otf", "semi": FD + "Inter-SemiBold.otf",
            "reg": FD + "Inter-Regular.otf", "ital": FD + "Inter-Italic.otf",
            "mono": "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"}[kind]
    return ImageFont.truetype(path, size)

# ---------- palette ----------
INK = (18, 20, 28); WHITE = (255, 255, 255); ACC = (37, 211, 102); ACC2 = (255, 214, 10)
TEAL = (0, 128, 105); CHATBG = (236, 229, 221); OUTB = (217, 253, 211); MUTED = (120, 126, 140)

# ---------- easing ----------
def clamp(x, a=0.0, b=1.0): return max(a, min(b, x))
def prog(t, a, b): return clamp((t - a) / (b - a)) if b > a else float(t >= a)
def ease_out(x): return 1 - (1 - x) ** 3
def ease_io(x): return 4 * x ** 3 if x < .5 else 1 - (-2 * x + 2) ** 3 / 2
def back(x, s=1.9): x -= 1; return 1 + (s + 1) * x ** 3 + s * x ** 2
def lerp(a, b, x): return a + (b - a) * x

# ---------- background (animated gradient + soft blobs) ----------
yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
def background(t):
    k = (np.sin(t * 0.6) + 1) / 2
    top = np.array([lerp(12, 22, k), lerp(16, 10, k), lerp(40, 48, k)], np.float32)
    bot = np.array([lerp(6, 4, k), lerp(60, 40, k), lerp(52, 70, k)], np.float32)
    g = (yy / H)[..., None]
    img = top * (1 - g) + bot * g
    for cx, cy, r, col, sp in [(200, 400, 520, (37, 211, 102), .7), (900, 1500, 600, (0, 160, 255), .5)]:
        cx2 = cx + 120 * math.sin(t * sp); cy2 = cy + 90 * math.cos(t * sp * 1.3)
        d = np.exp(-(((xx - cx2) ** 2 + (yy - cy2) ** 2) / (2 * r * r)))[..., None] * 0.28
        img = img * (1 - d) + np.array(col, np.float32) * d
    return Image.fromarray(img.clip(0, 255).astype(np.uint8), "RGB").convert("RGBA")

# ---------- text helpers ----------
@functools.lru_cache(4096)
def text_img(s, kind, size, color, stroke=0, stroke_col=(0, 0, 0)):
    f = F(kind, size)
    l, t_, r, b = f.getbbox(s, stroke_width=stroke)
    im = Image.new("RGBA", (r - l + 4, b - t_ + 4), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((2 - l, 2 - t_), s, font=f, fill=color, stroke_width=stroke, stroke_fill=stroke_col)
    return im

def paste(canvas, im, cx, cy, scale=1.0, alpha=1.0, anchor="c"):
    if scale <= 0.01 or alpha <= 0.01: return
    if abs(scale - 1) > 1e-3:
        im = im.resize((max(1, int(im.width * scale)), max(1, int(im.height * scale))), Image.LANCZOS)
    if alpha < 1:
        im = im.copy(); a = im.getchannel("A").point(lambda v: int(v * alpha)); im.putalpha(a)
    x = int(cx - im.width / 2) if anchor == "c" else int(cx)
    y = int(cy - im.height / 2)
    canvas.alpha_composite(im, (x, y)) if 0 <= x and 0 <= y and x + im.width <= W and y + im.height <= H else canvas.paste(im, (x, y), im)

def shadowed(canvas, box, radius, fill, blur=30, off=18, sh_alpha=110):
    x0, y0, x1, y1 = map(int, box)
    pad = blur * 2
    sh = Image.new("RGBA", (x1 - x0 + pad * 2, y1 - y0 + pad * 2), (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle((pad, pad, pad + x1 - x0, pad + y1 - y0), radius, fill=(0, 0, 0, sh_alpha))
    sh = sh.filter(ImageFilter.GaussianBlur(blur))
    canvas.paste(sh, (x0 - pad, y0 - pad + off), sh)
    ImageDraw.Draw(canvas).rounded_rectangle(box, radius, fill=fill)

# ---------- phone mockup ----------
PW, PH = 780, 1240
def phone(canvas, cx, cy, scale=1.0):
    """Draws the phone frame and returns an RGBA 'screen' image + its paste position; caller draws into screen."""
    x0, y0 = cx - PW / 2, cy - PH / 2
    shadowed(canvas, (x0, y0, x0 + PW, y0 + PH), 90, (14, 14, 18), blur=40, off=30, sh_alpha=150)
    d = ImageDraw.Draw(canvas)
    d.rounded_rectangle((x0 + 3, y0 + 3, x0 + PW - 3, y0 + PH - 3), 87, outline=(70, 72, 82), width=3)
    scr = Image.new("RGBA", (PW - 44, PH - 44), CHATBG + (255,))
    return scr, (int(x0 + 22), int(y0 + 22))

def finish_phone(canvas, scr, pos):
    mask = Image.new("L", scr.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, scr.width - 1, scr.height - 1), 68, fill=255)
    canvas.paste(scr, pos, mask)
    d = ImageDraw.Draw(canvas)
    cx = pos[0] + scr.width / 2
    d.rounded_rectangle((cx - 80, pos[1] + 18, cx + 80, pos[1] + 58), 20, fill=(8, 8, 10))  # notch pill

def status_bar(s, dark=True):
    d = ImageDraw.Draw(s); col = WHITE if dark else INK
    d.text((60, 22), "9:41", font=F("semi", 30), fill=col)
    for i in range(4): d.rectangle((s.width - 170 + i * 14, 48 - i * 7, s.width - 160 + i * 14, 52), fill=col)
    d.rounded_rectangle((s.width - 100, 26, s.width - 50, 50), 7, outline=col, width=3)
    d.rectangle((s.width - 96, 30, s.width - 64, 46), fill=col)

def chat_header(s, title, sub="online"):
    d = ImageDraw.Draw(s)
    d.rectangle((0, 0, s.width, 190), fill=TEAL)
    status_bar(s)
    d.line((40, 135, 58, 117), fill=WHITE, width=6); d.line((40, 135, 58, 153), fill=WHITE, width=6)
    d.ellipse((80, 100, 150, 170), fill=(160, 200, 190))
    d.text((115, 135), title[0], font=F("bold", 34), fill=TEAL, anchor="mm")
    d.text((170, 102), title, font=F("semi", 36), fill=WHITE)
    d.text((170, 146), sub, font=F("reg", 26), fill=(200, 235, 225))

def list_header(s, title="Chats"):
    d = ImageDraw.Draw(s)
    d.rectangle((0, 0, s.width, 210), fill=TEAL)
    status_bar(s)
    d.text((40, 120), title, font=F("bold", 52), fill=WHITE)
    # search icon
    d.ellipse((s.width - 170, 125, s.width - 130, 165), outline=WHITE, width=5)
    d.line((s.width - 136, 159, s.width - 116, 179), fill=WHITE, width=6)
    for i in range(3): d.ellipse((s.width - 70, 128 + i * 18, s.width - 60, 138 + i * 18), fill=WHITE)

AV_COLS = [(255, 159, 67), (84, 160, 255), (255, 107, 129), (95, 39, 205), (16, 172, 132), (238, 82, 83)]
def chat_row(s, y, name, msg, time_, col, pinned=False, highlight=0.0):
    d = ImageDraw.Draw(s, "RGBA")
    if highlight > 0:
        k = 0.3 * highlight
        d.rectangle((0, y, s.width, y + 140), fill=tuple(int(lerp(c0, c1, k)) for c0, c1 in zip(CHATBG, ACC)))
    d.rectangle((0, y, s.width, y + 140), outline=None)
    d.ellipse((36, y + 25, 126, y + 115), fill=col)
    d.text((81, y + 70), name[0], font=F("bold", 40), fill=WHITE, anchor="mm")
    d.text((156, y + 30), name, font=F("semi", 36), fill=INK)
    d.text((156, y + 82), msg, font=F("reg", 28), fill=MUTED)
    d.text((s.width - 40, y + 36), time_, font=F("reg", 24), fill=MUTED, anchor="ra")
    if pinned: pin_icon(d, s.width - 70, y + 98, 16, MUTED)
    d.line((156, y + 139, s.width, y + 139), fill=(225, 225, 228), width=2)

def pin_icon(d, cx, cy, r, col, angle=-35):
    a = math.radians(angle)
    def rot(px, py): return (cx + px * math.cos(a) - py * math.sin(a), cy + px * math.sin(a) + py * math.cos(a))
    d.polygon([rot(-r * .7, -r * 1.2), rot(r * .7, -r * 1.2), rot(r * .5, -r * .2), rot(r * 1.1, r * .25),
               rot(-r * 1.1, r * .25), rot(-r * .5, -r * .2)], fill=col)
    d.line([rot(0, r * .25), rot(0, r * 1.5)], fill=col, width=max(3, r // 4))

def bubble(s, y, text_runs, out=True, scale=1.0, time_="9:41"):
    """text_runs: list of (str, style) style in reg/bold/ital/strike/mono. Returns bubble height."""
    widths = []
    for txt, st in text_runs:
        f = F({"strike": "reg"}.get(st, st), 34 if st != "mono" else 31)
        widths.append(f.getlength(txt))
    tw = sum(widths)
    bw, bh = tw + 140, 96
    x1 = s.width - 30 if out else 30 + bw
    x0 = x1 - bw
    layer = Image.new("RGBA", (int(bw) + 40, bh + 40), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.rounded_rectangle((10, 10, 10 + bw, 10 + bh), 26, fill=(OUTB if out else WHITE) + (255,))
    x = 34
    for (txt, st), w_ in zip(text_runs, widths):
        f = F({"strike": "reg"}.get(st, st), 34 if st != "mono" else 31)
        d.text((x, 10 + bh / 2), txt, font=f, fill=INK, anchor="lm")
        if st == "strike": d.line((x, 10 + bh / 2 + 2, x + w_, 10 + bh / 2 + 2), fill=INK, width=3)
        x += w_
    d.text((10 + bw - 22, 10 + bh - 16), time_ + (" ✓✓" if False else ""), font=F("reg", 20), fill=MUTED, anchor="rb")
    if out:  # double tick
        tx, ty = 10 + bw - 22 - F("reg", 20).getlength(time_) - 46, 10 + bh - 24
    sc = scale
    if sc < 1:
        if sc <= 0.02: return bh
        layer = layer.resize((max(1, int(layer.width * sc)), max(1, int(layer.height * sc))), Image.LANCZOS)
    px = int((x1 + 10) - layer.width) if out else int(x0 - 10)
    py = int(y + (bh + 40) * (1 - sc) / 2) - 10
    s.alpha_composite(layer, (max(0, px), max(0, py)))
    return bh

def input_bar(s, typed, cursor_on, send_press=0.0):
    d = ImageDraw.Draw(s)
    y = s.height - 140
    d.rounded_rectangle((24, y, s.width - 140, y + 100), 50, fill=WHITE)
    f = F("reg", 32)
    shown = typed
    while f.getlength(shown) > s.width - 240 and len(shown) > 1: shown = shown[1:]
    d.text((64, y + 50), shown, font=f, fill=INK, anchor="lm")
    if cursor_on:
        cx = 64 + f.getlength(shown) + 4
        d.rectangle((cx, y + 28, cx + 3, y + 72), fill=TEAL)
    r = 50 * (1 - 0.15 * send_press)
    cx, cy = s.width - 74, y + 50
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=TEAL)
    d.polygon([(cx - 18, cy - 20), (cx + 24, cy), (cx - 18, cy + 20), (cx - 10, cy)], fill=WHITE)

def finger(canvas, x, y, press=0.0, alpha=1.0):
    d = ImageDraw.Draw(canvas, "RGBA")
    if press > 0:
        r = 40 + 70 * press
        d.ellipse((x - r, y - r, x + r, y + r), outline=(255, 255, 255, int(200 * (1 - press) * alpha)), width=6)
    r = 34
    d.ellipse((x - r, y - r, x + r, y + r), fill=(255, 255, 255, int(150 * alpha)), outline=(255, 255, 255, int(230 * alpha)), width=4)

# ---------- overlays ----------
def top_title(canvas, t, t0, badge, title, col=ACC):
    p = prog(t, t0, t0 + 0.45)
    paste(canvas, pill_img(badge, col), W / 2, 150, back(p) if p < 1 else 1, min(1, p * 2))
    p2 = prog(t, t0 + 0.12, t0 + 0.6)
    paste(canvas, text_img(title, "black", 76, WHITE), W / 2, 265 + 40 * (1 - ease_out(p2)), 1, p2)

@functools.lru_cache(64)
def pill_img(txt, col):
    t = text_img(txt, "black", 40, INK)
    im = Image.new("RGBA", (t.width + 70, t.height + 36), (0, 0, 0, 0))
    ImageDraw.Draw(im).rounded_rectangle((0, 0, im.width - 1, im.height - 1), im.height // 2, fill=col)
    im.alpha_composite(t, (35, 18)); return im

def caption(canvas, t, t0, t1, line1, line2=None):
    if not (t0 <= t < t1 + 0.3): return
    p = ease_out(prog(t, t0, t0 + 0.35)); q = 1 - prog(t, t1, t1 + 0.25)
    a = p * q
    im = text_img(line1, "bold", 50, WHITE, 0)
    box_w = im.width + 80; lines = [im]
    if line2:
        im2 = text_img(line2, "bold", 50, ACC2); lines.append(im2); box_w = max(box_w, im2.width + 80)
    bh = 30 + sum(l.height + 14 for l in lines) + 16
    y0 = 1690 - bh / 2 + 30 * (1 - p)
    layer = Image.new("RGBA", (int(box_w), int(bh)), (0, 0, 0, 0))
    ImageDraw.Draw(layer).rounded_rectangle((0, 0, box_w - 1, bh - 1), 28, fill=(10, 10, 14, 215))
    yy_ = 26
    for l in lines: layer.alpha_composite(l, (int((box_w - l.width) / 2), yy_)); yy_ += l.height + 14
    paste(canvas, layer, W / 2, y0 + bh / 2, 1, a)

def progress(canvas, t):
    d = ImageDraw.Draw(canvas, "RGBA")
    segs = [(0, 3), (3, 8), (8, 13), (13, 18), (18, 20)]
    gap, x = 10, 40; tot = W - 80 - gap * 4
    for a, b in segs:
        w_ = tot * (b - a) / 20
        d.rounded_rectangle((x, 44, x + w_, 52), 4, fill=(255, 255, 255, 70))
        fw = w_ * prog(t, a, b)
        if fw > 2: d.rounded_rectangle((x, 44, x + fw, 52), 4, fill=(255, 255, 255, 235))
        x += w_ + gap

def slide_offset(t, t0, t1):
    """x-offset for scene enter/exit."""
    pin = ease_io(prog(t, t0, t0 + 0.4)); pout = ease_io(prog(t, t1 - 0.35, t1))
    return (1 - pin) * W * 0.9 - pout * W * 0.9

# ---------- scenes ----------
def scene_hook(c, t):
    # big "3" slam, then title words cascade
    p = prog(t, 0.0, 0.5)
    s3 = back(p, 2.4) if p < 1 else 1 + 0.03 * math.sin(t * 6)
    glow = text_img("3", "black", 560, ACC, 0)
    paste(c, glow, W / 2, 720, s3 * (1.0 + 0.6 * (1 - p)), min(1, p * 3))
    words = [("WHATSAPP", WHITE, 0.45), ("TRICKS", ACC2, 0.65), ("nobody told you", WHITE, 0.85)]
    y = 1130
    for i, (w_, col, t0) in enumerate(words):
        q = prog(t, t0, t0 + 0.4)
        kind, size = ("black", 120) if i < 2 else ("bold", 70)
        im = text_img(w_, kind, size, col)
        paste(c, im, W / 2 + 300 * (1 - ease_out(q)) * (1 if i % 2 else -1), y, 1, q)
        y += im.height + 34
    # ticking underline
    q = ease_out(prog(t, 1.2, 1.8))
    d = ImageDraw.Draw(c); d.rounded_rectangle((W / 2 - 330 * q, 1520, W / 2 + 330 * q, 1534), 7, fill=ACC)
    q2 = prog(t, 1.6, 2.0)
    paste(c, text_img("#2 will change how you take notes", "semi", 40, (200, 205, 215)), W / 2, 1610, 1, q2)
    # exit: zoom + fade
    out = prog(t, 2.7, 3.0)
    if out > 0:
        ov = Image.new("RGBA", (W, H), (10, 12, 20, int(255 * out))); c.alpha_composite(ov)

def scene_format(c, t):
    lt = t - 3
    top_title(c, t, 3.0, "TRICK #1", "Format your texts")
    scr, pos = phone(c, W / 2, 1010)
    chat_header(scr, "Alex")
    bubble(scr, 230, [("See you at 8?", "reg")], out=False, time_="9:38")
    full = "*Bold* _italic_ ~strike~ ```mono```"
    tp = prog(lt, 0.7, 2.6)
    n = int(len(full) * tp)
    sent = lt > 2.95
    if not sent:
        input_bar(scr, full[:n], int(lt * 3) % 2 == 0 or tp < 1, send_press=prog(lt, 2.75, 2.95))
    else:
        input_bar(scr, "", int(lt * 3) % 2 == 0)
        sc = back(prog(lt, 2.95, 3.35))
        bubble(scr, 380, [("Bold ", "bold"), ("italic ", "ital"), ("strike", "strike"), (" ", "reg"), ("mono", "mono")], out=True, scale=sc)
    finish_phone(c, scr, pos)
    if 2.55 < lt < 3.1:  # finger tapping send
        fp = prog(lt, 2.75, 3.05)
        finger(c, pos[0] + scr.width - 74, pos[1] + scr.height - 90, fp, 1 - prog(lt, 2.95, 3.1))
    caption(c, lt, 0.6, 2.9, "Wrap words in symbols:", "*bold*  _italic_  ~strike~")
    caption(c, lt, 3.0, 4.7, "Works in any chat.", "No extra app needed.")

def scene_self(c, t):
    lt = t - 8
    top_title(c, t, 8.0, "TRICK #2", "Message yourself")
    scr, pos = phone(c, W / 2, 1010)
    opened = lt > 2.3
    if not opened:
        d = ImageDraw.Draw(scr)
        list_header(scr)
        # search bar typing
        d.rounded_rectangle((30, 230, scr.width - 30, 320), 45, fill=WHITE)
        q = "Me"; n = int(len(q) * prog(lt, 0.7, 1.1))
        d.text((80, 275), q[:n] if n else "Search…", font=F("reg", 34), fill=INK if n else MUTED, anchor="lm")
        rows = [("Me (You)", "Message yourself", "", ACC), ("Mom", "Call me when you land", "9:12", AV_COLS[2]),
                ("Team", "Deck is ready", "8:47", AV_COLS[1]), ("Sam", "haha yes", "Yesterday", AV_COLS[0])]
        filt = prog(lt, 1.1, 1.5)
        y = 340
        for i, r in enumerate(rows):
            if i > 0 and filt > 0:
                # other rows fade away
                ov_y = y
                chat_row(scr, y, *r)
                ov = Image.new("RGBA", scr.size, (0, 0, 0, 0))
                ImageDraw.Draw(ov).rectangle((0, ov_y, scr.width, ov_y + 140), fill=CHATBG + (int(255 * filt),))
                scr.alpha_composite(ov)
            else:
                chat_row(scr, y, *r, highlight=prog(lt, 1.6, 1.9))
            y += 140
    else:
        chat_header(scr, "Me (You)", "Message yourself")
        items = [[("Wi-Fi: ", "bold"), ("Blue-Fox-42", "mono")], [("Groceries: ", "bold"), ("milk, eggs, coffee", "reg")],
                 [("Read later: ", "bold"), ("bit.ly/app-tips", "ital")], [("Gift idea for Mom ", "reg"), ("!!", "bold")]]
        y = 230
        for i, it in enumerate(items):
            sc = back(prog(lt, 2.4 + i * 0.4, 2.75 + i * 0.4))
            bubble(scr, y, it, out=True, scale=sc); y += 120
        input_bar(scr, "", int(lt * 3) % 2 == 0)
    finish_phone(c, scr, pos)
    if 1.45 < lt < 2.3:
        fp = prog(lt, 1.6, 2.1)
        finger(c, pos[0] + 330, pos[1] + 410, fp, 1 - prog(lt, 2.05, 2.3))
    caption(c, lt, 0.5, 2.3, "Search your own name", "or tap your number")
    caption(c, lt, 2.4, 4.7, "Your private notepad,", "synced on every device")

def scene_pin(c, t):
    lt = t - 13
    top_title(c, t, 13.0, "TRICK #3", "Pin your top chats")
    scr, pos = phone(c, W / 2, 1010)
    list_header(scr)
    rows = [("Team", "Deck is ready", "9:30", AV_COLS[1]), ("Sam", "haha yes", "9:02", AV_COLS[0]),
            ("Gym crew", "Leg day tomorrow", "8:15", AV_COLS[4]), ("Mom", "Call me when you land", "Yesterday", AV_COLS[2]),
            ("Dentist", "Reminder: Thu 10am", "Mon", AV_COLS[5])]
    MOM = 3
    press = prog(lt, 0.8, 1.6)           # long press
    toolbar = prog(lt, 1.6, 1.9)
    pinned = lt > 2.5
    move = ease_io(prog(lt, 2.5, 3.2))
    base_y = 230
    # selection toolbar overlays header
    for i, r in enumerate(rows):
        if i == MOM: continue
        slot = i if i < MOM else i
        y = base_y + slot * 140
        if i < MOM: y += 140 * move
        chat_row(scr, y, *r)
    my = base_y + MOM * 140 * (1 - move)
    hl = toolbar * (1 - prog(lt, 3.3, 3.8))
    chat_row(scr, my, *rows[MOM], pinned=pinned, highlight=max(hl, press * 0.6))
    if toolbar > 0 and lt < 2.6:
        d = ImageDraw.Draw(scr, "RGBA")
        d.rectangle((0, 0, scr.width, 210), fill=tuple(int(lerp(a_, b_, toolbar)) for a_, b_ in zip(TEAL, (0, 92, 75))))
        status_bar(scr)
        d.text((40, 120), "1", font=F("bold", 48), fill=WHITE)
        pp = prog(lt, 2.0, 2.4)
        pin_icon(d, scr.width - 260, 150, int(22 * (1 + 0.25 * math.sin(pp * math.pi))), WHITE)
        d.rectangle((scr.width - 180, 132, scr.width - 140, 168), outline=WHITE, width=4)
        d.rectangle((scr.width - 100, 132, scr.width - 60, 168), fill=WHITE)
    finish_phone(c, scr, pos)
    if 0.6 < lt < 1.8:
        finger(c, pos[0] + 400, pos[1] + base_y + MOM * 140 + 70, press if press < 1 else 0, 1 - prog(lt, 1.6, 1.8))
    if 1.9 < lt < 2.6:
        fp = prog(lt, 2.0, 2.4)
        finger(c, pos[0] + scr.width - 260, pos[1] + 150, fp, 1 - prog(lt, 2.4, 2.6))
    caption(c, lt, 0.5, 2.4, "Long-press a chat,", "then tap the pin")
    caption(c, lt, 2.5, 4.7, "Up to 3 chats stay", "on top. Always.")

def scene_cta(c, t):
    lt = t - 18
    p = prog(lt, 0, 0.45)
    paste(c, text_img("Which trick", "black", 104, WHITE), W / 2, 560, back(p) if p < 1 else 1, p)
    paste(c, text_img("was new to you?", "black", 104, ACC2), W / 2, 700, back(prog(lt, .1, .55)) if lt < .55 else 1, prog(lt, .1, .4))
    # three numbered chips
    for i, lab in enumerate(["1  Format", "2  Notes", "3  Pin"]):
        q = prog(lt, 0.3 + i * 0.12, 0.65 + i * 0.12)
        im = pill_img(lab, [ACC, ACC2, (120, 200, 255)][i])
        paste(c, im, W / 2, 900 + i * 125, back(q) if q < 1 else 1, min(1, q * 2))
    q = prog(lt, 0.8, 1.2)
    paste(c, text_img("Comment the number", "semi", 52, WHITE), W / 2, 1320, 1, q)
    # save + follow buttons
    b = prog(lt, 1.0, 1.4)
    btn = Image.new("RGBA", (760, 140), (0, 0, 0, 0))
    bd = ImageDraw.Draw(btn); bd.rounded_rectangle((0, 0, 759, 139), 70, fill=WHITE)
    # bookmark glyph
    bd.polygon([(70, 35), (110, 35), (110, 105), (90, 88), (70, 105)], fill=INK)
    bd.text((420, 70), "Save + Follow for more", font=F("black", 44), fill=INK, anchor="mm")
    pulse = 1 + 0.04 * math.sin(lt * 10) * (lt > 1.4)
    paste(c, btn, W / 2, 1520, (back(b) if b < 1 else 1) * pulse, b)

SCENES = [(0, 3, scene_hook), (3, 8, scene_format), (8, 13, scene_self), (13, 18, scene_pin), (18, 20, scene_cta)]

def frame(i):
    t = i / FPS
    bg = background(t)
    for a, b, fn in SCENES:
        if a - 0.01 <= t < b:
            layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            fn(layer, t)
            off = slide_offset(t, a, b) if fn not in (scene_hook,) else 0
            if fn is scene_cta: off = slide_offset(t, a, b + 1)
            bg.alpha_composite(layer, (0, 0)) if abs(off) < 1 else bg.paste(layer, (int(off), 0), layer)
    progress(bg, t)
    # handle tag
    paste(bg, text_img("@app.tips", "semi", 30, (255, 255, 255, 150)), W - 140, H - 80)
    return bg.convert("RGB")

# ---------- audio ----------
SR = 44100
def make_audio(path):
    n = int(SR * DUR); a = np.zeros(n, np.float32); tt = np.arange(n) / SR
    bpm = 120; beat = 60 / bpm
    def add(sig, t0, gain=1.0):
        s = int(t0 * SR); e = min(n, s + len(sig)); a[s:e] += sig[:e - s] * gain
    kl = int(0.35 * SR); kt = np.arange(kl) / SR
    kick = np.sin(2 * np.pi * (50 * kt + 90 * (1 - np.exp(-kt * 30)) / 30)) * np.exp(-kt * 9)
    hl = int(0.06 * SR); hat = np.random.default_rng(1).standard_normal(hl) * np.exp(-np.arange(hl) / SR * 70)
    hat = np.diff(hat, prepend=0)
    sl = int(0.2 * SR); snare = np.random.default_rng(2).standard_normal(sl) * np.exp(-np.arange(sl) / SR * 22)
    nb = int(DUR / beat)
    for b in range(nb):
        t0 = b * beat
        if t0 < 18.0 or b % 2 == 0: add(kick, t0, 0.9)
        if b % 2 == 1: add(snare, t0, 0.25)
        add(hat, t0 + beat / 2, 0.18); add(hat, t0, 0.08)
    # bass + pad chord progression (Am F C G), 2 beats each
    roots = [55.0, 43.65, 65.41, 49.0]; chords = [[220, 261.6, 329.6], [174.6, 220, 261.6], [261.6, 329.6, 392], [196, 246.9, 293.7]]
    bar = beat * 2
    for k in range(int(DUR / bar)):
        t0 = k * bar; s = int(t0 * SR); e = min(n, int((t0 + bar) * SR)); seg = tt[s:e] - t0
        env = np.minimum(1, seg * 30) * np.exp(-seg * 1.2)
        r = roots[k % 4]
        a[s:e] += (np.sign(np.sin(2 * np.pi * r * seg)) * 0.5 + np.sin(2 * np.pi * r * seg)) * env * 0.12
        pad_env = np.minimum(1, seg * 4) * np.minimum(1, (bar - seg) * 6)
        for f in chords[k % 4]:
            a[s:e] += (np.sin(2 * np.pi * f * seg) + 0.3 * np.sin(2 * np.pi * f * 2.003 * seg)) * pad_env * 0.035
    # whooshes at transitions, pops on events
    for t0 in [2.85, 7.75, 12.75, 17.75]:
        wl = int(0.5 * SR); w_ = np.random.default_rng(int(t0 * 10)).standard_normal(wl)
        env = np.sin(np.linspace(0, np.pi, wl)) ** 2
        w_ = np.convolve(w_, np.ones(12) / 12, "same") * env
        add(w_, t0, 0.5)
    pl = int(0.12 * SR); pt = np.arange(pl) / SR
    pop = np.sin(2 * np.pi * (900 * pt - 2500 * pt ** 2)) * np.exp(-pt * 35)
    for t0 in [0.05, 3.0, 5.95, 8.0, 10.4, 10.8, 11.2, 11.6, 13.0, 15.5, 18.0, 18.3, 18.42, 18.54]:
        add(pop, t0, 0.35)
    # master: fade out, soft clip
    a *= np.minimum(1, (DUR - tt) / 0.8)
    a = np.tanh(a * 1.3) * 0.85
    pcm = (a * 32767).astype(np.int16)
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(SR); wf.writeframes(pcm.tobytes())

if __name__ == "__main__":
    import os
    wav = os.path.splitext(OUT)[0] + ".wav"
    make_audio(wav)
    if "--stills" in sys.argv:
        for t in [1.5, 5.0, 6.8, 9.5, 11.5, 14.5, 16.5, 19.5]:
            frame(int(t * FPS)).save(os.path.join(os.path.dirname(OUT) or ".", f"still_{t:04.1f}.png"))
        sys.exit()
    ff = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                           "-r", str(FPS), "-i", "-", "-i", wav, "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                           "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", OUT],
                          stdin=subprocess.PIPE)
    for i in range(N):
        ff.stdin.write(frame(i).tobytes())
        if i % 60 == 0: print(f"frame {i}/{N}", flush=True)
    ff.stdin.close(); ff.wait()
    print("done", OUT)
