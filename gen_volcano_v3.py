from PIL import Image, ImageDraw
import random, math

W, H = 192, 144
rng = random.Random(42)

C_SKY_TOP  = (8,   8,  48)
C_SKY_MID  = (18,  42, 110)
C_SKY_HOR  = (44,  88, 168)
C_STAR     = (220, 220, 245)
C_OCN_SURF = (28,  98, 192)
C_OCN_DEEP = ( 8,  50, 130)
C_OCN_WAVE = (72, 155, 218)
C_SAND_LT  = (210, 178, 108)
C_SAND_DK  = (165, 132,  75)
C_GRS_LT   = (68, 190,  42)
C_GRS_MD   = (48, 148,  30)
C_GRS_DK   = (30, 100,  22)
C_VOL_FACE = (78,  58,  48)
C_VOL_SHAD = (44,  30,  24)
C_VOL_DARK = (26,  18,  14)
C_VOL_RIM  = (20,  14,  10)
C_TRUNK_LT = (138,  88,  48)
C_TRUNK_DK = ( 78,  48,  26)
C_FROND_LT = ( 56, 198,  38)
C_FROND_MD = ( 38, 158,  28)
C_FROND_DK = ( 22, 108,  18)
C_SMK_LT   = (198, 192, 186)
C_SMK_MD   = (148, 140, 134)
C_SMK_DK   = ( 88,  82,  78)
C_LAV_WHT  = (255, 255, 220)
C_LAV_YEL  = (255, 228,  55)
C_LAV_ORG  = (255, 138,  18)
C_LAV_RED  = (218,  48,   8)
C_GLOW_ORG = (255, 118,  28)
BLACK      = (0, 0, 0)

HORIZON_Y  = H * 54 // 100     # ~77
ISLAND_CX  = W // 2
ISLAND_CY  = HORIZON_Y + 10    # ~87
VOL_HEIGHT = 40                 # shorter = less steep
VOL_HALF_W = 48                 # wider base
VOL_TIP_Y  = ISLAND_CY - 5 - VOL_HEIGHT   # ~42
CRATER_OFFS = 10                # crater sits this far below the tip
ISLAND_BASE_Y = ISLAND_CY + 2  # approximate solid ground y

STARS = [(20,10),(52,6),(84,14),(122,8),(152,11),(172,5),
         (32,24),(98,17),(142,21),(167,28),(12,31),(64,34)]

# ── Rough volcano polygon offsets (relative to cx, tip_y) ───────────────────
# Clockwise: tip → right slope → base → left slope → tip
_VOL_POLY = [
    (  0,   0),   # tip
    (  5,   7),
    ( 12,  14),
    ( 17,  20),
    ( 21,  26),
    ( 28,  33),
    ( 32,  37),   # slight bump outward
    ( 38,  43),
    ( 44,  48),
    ( 48,  52),   # base right
    (-46,  52),   # base left
    (-44,  48),
    (-38,  43),
    (-33,  38),
    (-28,  33),
    (-22,  27),
    (-17,  21),
    (-13,  15),
    ( -6,   8),
]
# Fixed texture patches (relative dx, dy from tip — verified inside cone)
_VOL_TEX_DARK = [
    (-18, 18), (-8, 24), (-22, 30), (-5, 38), (-14, 34), (-26, 42),
    ( 10, 21), ( 20, 28), ( 8, 36), ( 15, 43), ( 5, 14), (-3, 30),
    (-20, 22), (12, 12), (-10, 44), (22, 35), (-28, 38), (6, 28),
]
_VOL_TEX_HL = [
    (12, 18), (20, 24), (16, 32), (22, 40), (8, 22), (18, 36),
    (10, 10), (24, 30), (14, 44), (6, 16),
]

# ── Lava rain particles: (vx, vy_up, launch_abs_frame) ────────────────────
# vy_up = initial upward speed (pixels/frame); gravity pulls them back
GRAVITY = 3.0
_RAIN = [
    (-5, 14, 65), ( 7, 16, 65), (-3, 11, 66), ( 9, 13, 66),
    (-6, 15, 67), ( 4, 12, 67), (-8, 13, 68), ( 6, 15, 68),
    (-4, 11, 69), ( 8, 14, 69), (-5, 16, 70), ( 3, 13, 70),
    (-7, 12, 71), ( 6, 15, 71), (-3, 14, 72), ( 9, 11, 72),
    (-6, 13, 73), ( 5, 16, 73), (-9, 12, 74), ( 4, 14, 74),
    (-5, 15, 75), ( 7, 13, 75), (-3, 11, 76), ( 8, 15, 76),
    (-6, 14, 77), ( 4, 12, 77), (-7, 13, 78), ( 6, 16, 78),
]

def sky_band(y):
    t = min(1.0, y / HORIZON_Y)
    a, b, m = C_SKY_TOP, C_SKY_HOR, C_SKY_MID
    if t < 0.5:
        t2 = t * 2
        return tuple(int(a[i]+(m[i]-a[i])*t2) for i in range(3))
    else:
        t2 = (t-0.5)*2
        return tuple(int(m[i]+(b[i]-m[i])*t2) for i in range(3))

def draw_bg(d, sx=0, sy=0, glow=0.0):
    for y in range(max(0, HORIZON_Y+sy+1)):
        c = sky_band(y - sy)
        if glow > 0 and y > HORIZON_Y+sy-16:
            t = (y-(HORIZON_Y+sy-16))/16
            c = tuple(int(c[i]+(C_GLOW_ORG[i]-c[i])*glow*t) for i in range(3))
        d.line([(0,y),(W,y)], fill=c)
    for px, py in STARS:
        d.point([(sx+px, sy+py)], fill=C_STAR)
    for y in range(max(0,HORIZON_Y+sy), H):
        t = (y-HORIZON_Y-sy)/(H-HORIZON_Y)
        c = tuple(int(C_OCN_SURF[i]+(C_OCN_DEEP[i]-C_OCN_SURF[i])*t) for i in range(3))
        if glow > 0:
            gt = glow*(1 - t*0.85)
            c = tuple(int(c[i]+(C_GLOW_ORG[i]-c[i])*gt) for i in range(3))
        d.line([(0,y),(W,y)], fill=c)
    for wx in range(0, W, 9):
        d.line([(sx+wx,HORIZON_Y+4+sy),(sx+wx+4,HORIZON_Y+4+sy)], fill=C_OCN_WAVE)
        d.line([(sx+wx+2,HORIZON_Y+10+sy),(sx+wx+6,HORIZON_Y+10+sy)], fill=C_OCN_WAVE)

def draw_island(d, sx=0, sy=0):
    cx, cy = ISLAND_CX+sx, ISLAND_CY+sy
    d.ellipse([cx-58,cy-7,cx+58,cy+16], fill=C_SAND_LT)
    d.ellipse([cx-55,cy+6,cx+55,cy+18], fill=C_SAND_DK)
    d.ellipse([cx-52,cy-13,cx+52,cy+8], fill=C_GRS_MD)
    d.ellipse([cx-48,cy-15,cx+48,cy+5], fill=C_GRS_LT)
    d.ellipse([cx-50,cy-14,cx-18,cy+4], fill=C_GRS_DK)

def draw_volcano(d, sx=0, sy=0):
    cx  = ISLAND_CX + sx
    ty  = VOL_TIP_Y + sy
    # Full silhouette
    poly = [(cx+dx, ty+dy) for dx, dy in _VOL_POLY]
    d.polygon(poly, fill=C_VOL_FACE)
    # Shadow wedge (left face)
    shadow = [(cx,ty), (cx-46,ty+52), (cx-20,ty+52), (cx-4,ty+22)]
    d.polygon(shadow, fill=C_VOL_SHAD)
    # Dark left edge line
    left_edge = [(cx+dx,ty+dy) for dx,dy in _VOL_POLY if dx <= 0]
    for i in range(len(left_edge)-1):
        d.line([left_edge[i], left_edge[i+1]], fill=C_VOL_DARK, width=1)
    # Surface texture — dark rock patches
    for dx, dy in _VOL_TEX_DARK:
        d.rectangle([cx+dx, ty+dy, cx+dx+2, ty+dy+1], fill=C_VOL_DARK)
    # Surface highlights (right-facing rocks)
    for dx, dy in _VOL_TEX_HL:
        d.point([(cx+dx, ty+dy)], fill=(98,74,60))
    # Crater — sits CRATER_OFFS pixels below tip, well within cone
    cr_y = ty + CRATER_OFFS
    # cone half-width at cr_y ≈ VOL_HALF_W * CRATER_OFFS / VOL_HEIGHT ≈ 12px → crater 6px fits
    d.ellipse([cx-6, cr_y-3, cx+6, cr_y+3], fill=C_VOL_SHAD)
    d.ellipse([cx-4, cr_y-2, cx+4, cr_y+2], fill=C_VOL_RIM)
    d.ellipse([cx-2, cr_y-1, cx+2, cr_y+1], fill=C_VOL_DARK)

def draw_palm(d, tx, ty, size=1.0, sx=0, sy=0):
    tx, ty = int(tx+sx), int(ty+sy)
    th = int(13*size)   # shorter trunk
    for i in range(th):
        lean = i//8
        px = tx+lean
        col = C_TRUNK_LT if i > th*0.55 else C_TRUNK_DK
        d.line([(px, ty-i),(px+1, ty-i)], fill=col)
    top_x = tx + th//8
    top_y = ty - th
    fl = int(9*size)    # shorter fronds
    for angle in [-90, -50, -18, 16, 48]:
        rad = math.radians(angle)
        for j in range(fl):
            t = j/fl
            lx = int(top_x + math.cos(rad)*j)
            ly = int(top_y + math.sin(rad)*j)
            col = C_FROND_LT if t < 0.4 else (C_FROND_MD if t < 0.7 else C_FROND_DK)
            d.point([(lx, ly)], fill=col)
            if j % 3 == 0:
                d.point([(lx, ly-1)], fill=C_FROND_LT)

def draw_trees(d, sx=0, sy=0):
    cy = ISLAND_CY
    cx = ISLAND_CX
    for tx, ty, sz in [
        (cx-53, cy,    0.52),
        (cx-42, cy-6,  0.60),
        (cx-28, cy-7,  0.55),
        (cx-12, cy-7,  0.50),
        (cx+ 8, cy-7,  0.53),
        (cx+24, cy-7,  0.58),
        (cx+40, cy-6,  0.60),
        (cx+52, cy,    0.50),
    ]:
        draw_palm(d, tx, ty, sz, sx, sy)

def crater_pos(sx=0, sy=0):
    return ISLAND_CX+sx, VOL_TIP_Y + CRATER_OFFS + sy

def draw_smoke(d, lvl, sx=0, sy=0):
    if lvl <= 0:
        return
    cx, cy = crater_pos(sx, sy)
    for i in range(min(lvl, 7)):
        py = cy - 4 - i*8
        pr = 3 + i*2
        drift = i*2
        a = max(0.15, 1.0-i*0.14)
        oc = tuple(int(c*a) for c in C_SMK_DK)
        mc = tuple(int(c*a) for c in C_SMK_MD)
        lc = tuple(int(c*a) for c in C_SMK_LT)
        d.ellipse([cx-pr-drift,py-pr,cx+pr-drift,py+pr], fill=oc)
        d.ellipse([cx-pr//2-drift,py-pr//2,cx+pr//2-drift,py+pr//2], fill=mc)
        if pr > 4:
            d.ellipse([cx-2-drift,py-2,cx+2-drift,py+2], fill=lc)

def draw_lava(d, h, sx=0, sy=0, frm=0):
    if h <= 0:
        return
    cx, cy = crater_pos(sx, sy)
    mh = min(h, 76)
    # Glow ring at crater mouth
    for r in range(12, 0, -2):
        t = r/12
        gc = tuple(int(C_VOL_DARK[i]+(C_LAV_ORG[i]-C_VOL_DARK[i])*(1-t)*0.75) for i in range(3))
        d.ellipse([cx-r, cy-r//2, cx+r, cy+r//2], fill=gc)
    # Lava column
    for ly in range(mh):
        t = ly/mh
        y = cy - ly
        cw = max(1, int((1-t*0.68)*5))
        if   t < 0.12: col = C_LAV_WHT
        elif t < 0.32: col = C_LAV_YEL
        elif t < 0.58: col = C_LAV_ORG
        else:          col = C_LAV_RED
        d.line([(cx-cw,y),(cx+cw,y)], fill=col)
    # Ballistic debris (random per-frame)
    dr = random.Random(frm*17+3)
    for _ in range(6):
        ang = dr.uniform(-70, 70)
        spd = dr.uniform(8, 20)
        rad = math.radians(ang - 90)
        dbx = cx + int(math.cos(rad)*spd)
        dby = cy + int(math.sin(rad)*spd)
        col = C_LAV_ORG if dr.random() > 0.4 else C_LAV_YEL
        d.ellipse([dbx-1,dby-1,dbx+2,dby+2], fill=col)

def draw_lava_rain(d, frm, sx=0, sy=0):
    """Arcing lava blobs launched at various absolute frames."""
    cx, cy = crater_pos(sx, sy)
    base_y = ISLAND_BASE_Y + sy
    for (vx, vy_up, lf) in _RAIN:
        if frm < lf:
            continue
        t = frm - lf
        px = int(cx + vx * t)
        py = int(cy - vy_up * t + 0.5 * GRAVITY * t * t)
        if py > base_y + 12:
            continue
        if py >= base_y - 1:   # impact splat
            d.ellipse([px-2, py-1, px+3, py+2], fill=C_LAV_RED)
        else:
            col = C_LAV_ORG if (px+py) % 2 == 0 else C_LAV_YEL
            d.ellipse([px-1, py-1, px+2, py+2], fill=col)

def make_frame(sx=0, sy=0, smoke=0, lava_h=0, glow=0.0, frm=0, rain=False):
    img = Image.new("RGB", (W,H), BLACK)
    d = ImageDraw.Draw(img)
    draw_bg(d, sx, sy, glow)
    draw_island(d, sx, sy)
    draw_trees(d, sx, sy)
    draw_volcano(d, sx, sy)
    if lava_h > 0:
        draw_lava(d, lava_h, sx, sy, frm)
        if rain:
            draw_lava_rain(d, frm, sx, sy)
    elif smoke > 0:
        draw_smoke(d, smoke, sx, sy)
    return img

def blend_to_black(img, alpha):
    black = Image.new("RGB", (W,H), BLACK)
    return Image.blend(black, img, max(0.0, min(1.0, alpha)))

rgb_frames = []
durations  = []

def add(img, ms):
    rgb_frames.append(img)
    durations.append(ms)

# fade in (8 frames)
for i in range(8):
    add(blend_to_black(make_frame(smoke=1, frm=i), (i+1)/8), 100)

# calm (24 frames)
for i in range(24):
    sm = 1 + (1 if i%6==0 else 0)
    add(make_frame(smoke=sm, frm=i+8), 160)

# pre-tremor (6 frames)
for i in range(6):
    sx = rng.randint(-1,1)
    add(make_frame(sx=sx, smoke=2+i//2, frm=i+32), 130)

# heavy shake (14 frames)
for i in range(14):
    sx = rng.randint(-3,3)
    sy = rng.randint(-1,1)
    add(make_frame(sx=sx, sy=sy, smoke=4+i//3, frm=i+38), 80)

# lava buildup (7 frames)
for i in range(7):
    sx = rng.randint(-2,2)
    add(make_frame(sx=sx, lava_h=(i+1)*6, glow=i*0.06, frm=i+52), 65)

# full eruption first half — column growing, rain starts at frm>=65 (i>=6)
for i in range(26):
    sx = rng.randint(-1,1) if i<8 else 0
    lh = 42 + min(i*3, 40)
    gl = min(0.55+i*0.018, 0.92)
    add(make_frame(sx=sx, lava_h=lh, glow=gl, frm=i+59, rain=(i>=6)), 80)

# fade out — rain continues, column dies
for i in range(8):
    lh = max(0, 55-i*8)
    gl = max(0, 0.7-i*0.09)
    add(blend_to_black(make_frame(lava_h=lh, glow=gl, frm=i+85, rain=True), 1-(i+1)/8), 100)

# ── global palette ───────────────────────────────────────────────────────────
step = max(1, len(rgb_frames)//20)
sample = rgb_frames[::step]
col_w = len(sample) * W
collage = Image.new("RGB", (col_w, H))
for idx, sf in enumerate(sample):
    collage.paste(sf, (idx*W, 0))
global_pal = collage.quantize(colors=64, dither=0)

quantized = [img.quantize(colors=64, palette=global_pal, dither=0) for img in rgb_frames]

quantized[0].save(
    "C:/ClaudeCode/volcano_eruption_v3.gif",
    save_all=True, append_images=quantized[1:],
    loop=0, duration=durations, optimize=False,
)

# Peak eruption preview (frm=72, with rain)
peak_rgb = make_frame(lava_h=78, glow=0.9, frm=72, rain=True)
peak_rgb.save("C:/ClaudeCode/volcano_preview_v3.png")
print(f"Done — {len(quantized)} frames")
