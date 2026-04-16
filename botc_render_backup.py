"""botc_render.py — render a BotC grimoire image from game state."""
import math, os, io
from PIL import Image, ImageDraw, ImageFont, ImageEnhance
import botc_assets as BA

W, H    = 1200, 1200
BG      = (18, 18, 28)
TOKEN_D = 175
REM_D   = 78
CIRCLE_R= 450
CX, CY  = W // 2, H // 2
C_LABEL = (240, 240, 240)
C_DEAD  = (130, 130, 130)

def _make_vote_icon(size,color):
    S=size*4; cx=S//2
    W=(255,255,255,255); A=(0,0,0,0)
    gap=max(2,S//28)
    bw=int(S*0.56); bh=int(S*0.46)
    bx0=cx-bw//2; bx1=cx+bw//2
    by0=int(S*0.40); by1=by0+bh
    aw=int(S*0.13)
    sx0=bx0-aw; sx1=bx1+aw
    at=int(S*0.07); sy_b=by1+int(S*0.05)
    tk=aw//3; iy=by0-gap
    saddle=[(sx0,sy_b),(sx1,sy_b),
            (sx1,at+tk),(sx1-tk,at),(bx1+gap,iy),
            (bx0-gap,iy),(sx0+tk,at),(sx0,at+tk)]
    img=Image.new('RGBA',(S,S),(0,0,0,0))
    d=ImageDraw.Draw(img)
    d.polygon(saddle,fill=W)
    d.rectangle([bx0-gap,iy,bx1+gap,by1],fill=A)
    d.rectangle([bx0,by0,bx1,by1],fill=W)
    ck=int(S*0.11); cy2=(by0+by1)//2
    lw=max(3,S//15)
    pts=[(cx-ck,cy2),(cx-ck//3,cy2+ck),(cx+ck,cy2-int(ck*0.75))]
    d.line(pts,fill=A,width=lw)
    return img.resize((size,size),Image.LANCZOS)



_FA_PATHS = {
    'users':       (640,512,'M96 224c35.3 0 64-28.7 64-64s-28.7-64-64-64-64 28.7-64 64 28.7 64 64 64zm448 0c35.3 0 64-28.7 64-64s-28.7-64-64-64-64 28.7-64 64 28.7 64 64 64zm32 32h-64c-17.6 0-33.5 7.1-45.1 18.6 40.3 22.1 68.9 62 75.1 109.4h66c17.7 0 32-14.3 32-32v-32c0-35.3-28.7-64-64-64zm-256 0c61.9 0 112-50.1 112-112S381.9 32 320 32 208 82.1 208 144s50.1 112 112 112zm76.8 32h-8.3c-20.8 10-43.9 16-68.5 16s-47.6-6-68.5-16h-8.3C179.6 288 128 339.6 128 403.2V432c0 26.5 21.5 48 48 48h288c26.5 0 48-21.5 48-48v-28.8c0-63.6-51.6-115.2-115.2-115.2zm-223.7-13.4C161.5 263.1 145.6 256 128 256H64c-35.3 0-64 28.7-64 64v32c0 17.7 14.3 32 32 32h65.9c6.3-47.4 34.9-87.3 75.2-109.4z'),
    'heartbeat':   (512,512,'M320.2 243.8l-49.7 99.4c-6 12.1-23.4 11.7-28.9-.6l-56.9-126.3-30 71.7H60.6l182.5 186.5c7.1 7.3 18.6 7.3 25.7 0L451.4 288H342.3l-22.1-44.2zM473.7 73.9l-2.4-2.5c-51.5-52.6-135.8-52.6-187.4 0L256 100l-27.9-28.5c-51.5-52.7-135.9-52.7-187.4 0l-2.4 2.4C-10.4 123.7-12.5 203 31 256h10.6l214.5 219.6c7.1 7.3 18.6 7.3 25.7 0L496 256h16.4c43.5-53 41.4-132.1-38.7-182.1z'),
    'vote-yea':    (640,512,'M608 320h-64v64h22.4c5.3 0 9.6 3.6 9.6 8v16c0 4.4-4.3 8-9.6 8H73.6c-5.3 0-9.6-3.6-9.6-8v-16c0-4.4 4.3-8 9.6-8H96v-64H32c-17.7 0-32 14.3-32 32v96c0 17.7 14.3 32 32 32h576c17.7 0 32-14.3 32-32v-96c0-17.7-14.3-32-32-32zm-64 64H96v-64h448v64zM218.7 200.3l-9.6 3.2 9.2 5.2c12.3 6.9 17.3 21.7 11.7 34.6l-3.5 8.2c-6.3 14.8-23.5 21.4-38.1 14.8l-78.3-35.2c-14.8-6.6-21.3-24-14.5-38.7l.5-1c6.7-14.4 23.8-20.7 38.3-14.2l.6.3-3.5-10.4c-5-14.8 3-30.9 17.8-35.9l8.3-2.8c15.4-5.2 32 2.9 37.7 18.1L218.7 200.3zM493.3 200.3l29.4-53.8c5.7-15.2 22.3-23.3 37.7-18.1l8.3 2.8c14.8 5 22.8 21.1 17.8 35.9l-3.5 10.4.6-.3c14.5-6.5 31.6-.2 38.3 14.2l.5 1c6.8 14.7.3 32.1-14.5 38.7l-78.3 35.2c-14.6 6.6-31.8 0-38.1-14.8l-3.5-8.2c-5.6-12.9-.6-27.7 11.7-34.6l9.2-5.2-9.6-3.2zM352 256c-17.7 0-32-14.3-32-32V32c0-17.7 14.3-32 32-32s32 14.3 32 32v192c0 17.7-14.3 32-32 32zm-96-114.2V128h-48c-26.5 0-48 21.5-48 48v256h384V176c0-26.5-21.5-48-48-48h-48v13.8c18.6 6.6 32 24.3 32 45.2V224c0 26.5-21.5 48-48 48h-128c-26.5 0-48-21.5-48-48v-37c0-20.9 13.4-38.6 32-45.2z'),
    'user-friends':(640,512,'M192 256c61.9 0 112-50.1 112-112S253.9 32 192 32 80 82.1 80 144s50.1 112 112 112zm76.8 32h-8.3c-20.8 10-43.9 16-68.5 16s-47.6-6-68.5-16h-8.3C51.6 288 0 339.6 0 403.2V432c0 26.5 21.5 48 48 48h288c26.5 0 48-21.5 48-48v-28.8c0-63.6-51.6-115.2-115.2-115.2zM480 256c53 0 96-43 96-96s-43-96-96-96-96 43-96 96 43 96 96 96zm48 32h-3.8c-13.9 4.8-28.6 8-44.2 8s-30.3-3.2-44.2-8H432c-20.1 0-39.2 5.9-55.7 15.4 24.4 26.3 39.7 61.2 39.7 99.8v38.4c0 2.2-.5 4.3-.6 6.4H592c26.5 0 48-21.5 48-48v-25.6c0-63.6-51.6-115.2-115.2-115.2z'),
    'user':        (448,512,'M224 256c70.7 0 128-57.3 128-128S294.7 0 224 0 96 57.3 96 128s57.3 128 128 128zm89.6 32h-16.7c-22.2 10.2-46.9 16-72.9 16s-50.6-5.8-72.9-16h-16.7C60.2 288 0 348.2 0 422.4V464c0 26.5 21.5 48 48 48h352c26.5 0 48-21.5 48-48v-41.6c0-74.2-60.2-134.4-134.4-134.4z'),
}
_icon_cache = {}

def _fa_icon(name, size, color):
    key = (name, size, color)
    if key in _icon_cache: return _icon_cache[key]
    vw, vh, d = _FA_PATHS[name]
    r, g, b = color
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {vw} {vh}">'
           f'<path fill="rgb({r},{g},{b})" d="{d}"/></svg>')
    import cairosvg
    if name=='vote-yea':
        img=_make_vote_icon(size,color); _icon_cache[key]=img; return img
    wo=size; ho=max(1,int(size*vh/vw))
    png=cairosvg.svg2png(bytestring=svg.encode(),output_width=wo,output_height=ho)
    raw=Image.open(io.BytesIO(png)).convert('RGBA')
    img=Image.new('RGBA',(size,size),(0,0,0,0))
    img.paste(raw,((size-wo)//2,(size-ho)//2),raw)
    _icon_cache[key]=img; return img

_DIST = {
    5:(3,0,1,1), 6:(3,1,1,1), 7:(5,0,1,1), 8:(5,1,1,1), 9:(5,2,1,1),
    10:(7,0,2,1), 11:(7,1,2,1), 12:(7,2,2,1),
    13:(9,0,3,1), 14:(9,1,3,1), 15:(9,2,3,1),
}
def _base_dist(n):
    return _DIST.get(max(5, min(15, n)), (n-3, 0, 1, 2))

def _load(path, size):
    if not path or not os.path.exists(path):
        return Image.new('RGBA', size, (80, 80, 80, 200))
    return Image.open(path).convert('RGBA').resize(size, Image.LANCZOS)

def _circle_mask(size):
    m = Image.new('L', size, 0)
    ImageDraw.Draw(m).ellipse([0, 0, size[0]-1, size[1]-1], fill=255)
    return m

_FONT_DIR = os.path.join(os.path.dirname(__file__), 'fonts')

_N={"alhadikhia":"Al-Hadikhia","alsaahir":"Al-Saahir","bonecollector":"Bone Collector","boomdandy":"Boom Dandy","bountyhunter":"Bounty Hunter","cacklejack":"Cackle Jack","choirboy":"Choir Boy","cultleader":"Cult Leader","devilsadvocate":"Devil's Advocate","deusexfiasco":"Deus Ex Fiasco","eviltwin":"Evil Twin","fanggu":"Fang Gu","fearmonger":"Fearmonger","flowergirl":"Flower Girl","fortuneteller":"Fortune Teller","gunslinger":"Gunslinger","hellslibrarian":"Hell's Librarian","highpriestess":"High Priestess","lilmonsta":"Lil' Monsta","lordoftyphon":"Lord Of Typhon","mastermind":"Mastermind","mathematician":"Mathematician","nightwatchman":"Night Watchman","nodashii":"No Dashii","organgrinder":"Organ Grinder","pithag":"Pit-Hag","plaguedoctor":"Plague Doctor","poppygrower":"Poppy Grower","puzzlemaster":"Puzzle Master","ravenkeeper":"Ravenkeeper","scarletwoman":"Scarlet Woman","snakecharmer":"Snake Charmer","spiritofivory":"Spirit Of Ivory","stormcatcher":"Storm Catcher","tealady":"Tea Lady","towncrier":"Town Crier","villageidiot":"Village Idiot","vigormortis":"Vigormortis","ventriloquist":"Ventriloquist",}
def _char_display(r):
    k=r.lower().replace(" ","").replace("_","").replace("-","")
    return _N.get(k," ".join(w.capitalize() for w in r.replace("_"," ").split()))

_EVIL_ROLES={'poisoner','spy','scarletwoman','imp','baron','assassin','godfather','evil_twin','witch','cerenovus','fang_gu','vigormortis','no_dashii','vortox','zombuul','pukka','shabaloth','po','lleech','kazali','riot','legion'}


def _char_font(size):
    for p in (os.path.join(_FONT_DIR,"papyrus.ttf"),
              os.path.join(_FONT_DIR,"Cinzel-Bold.ttf"),
              os.path.join(_FONT_DIR,"piratesbay.ttf")):
        if os.path.exists(p):
            try: return ImageFont.truetype(p,size)
            except: pass
    return ImageFont.load_default()
def _name_font(size):
    for p in (os.path.join(_FONT_DIR,'RobotoCondensed-Regular.ttf'),
              os.path.join(_FONT_DIR,'RobotoCondensed-Light.ttf'),
              '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'):
        if os.path.exists(p):
            try: return ImageFont.truetype(p,size)
            except: pass
    return ImageFont.load_default()
def _try_font(size): return _char_font(size)

def _paste_centered(canvas, img, cx, cy):
    canvas.paste(img, (cx - img.width // 2, cy - img.height // 2), img)

def _wrap_text(text, font, draw, max_w):
    words = text.split()
    lines, line = [], ''
    for word in words:
        test = (line + ' ' + word).strip()
        bb = draw.textbbox((0, 0), test, font=font)
        if bb[2] - bb[0] > max_w and line:
            lines.append(line); line = word
        else:
            line = test
    if line: lines.append(line)
    return lines or ['']

def _draw_arc_text(img, text, cx, cy, radius, font_size, fill=(15,10,5),
                   stroke_color=None, stroke_width=2, letter_spacing=0.25):
    """Draw text curved along the bottom arc. Baseline on arc, left-to-right."""
    if not text: return
    text = ' '.join(w.capitalize() for w in text.split())
    fn = _char_font(font_size)

    # Measure with baseline anchor
    char_data = []
    for ch in text:
        try:
            bb = fn.getbbox(ch, anchor='ls')
        except TypeError:
            bb = fn.getbbox(ch)
        _gl=getattr(fn,"getlength",None)
        cw = int(_gl(ch)) if _gl else max(bb[2]-bb[0],1)
        if cw < font_size*0.4: cw=int(font_size*0.4)
        char_data.append((ch, bb, cw))

    sp = font_size * letter_spacing
    total_w = sum(d[2] for d in char_data) + sp * (len(char_data) - 1)
    arc_span = total_w / radius

    # Start from LEFT of arc (high angle in screen coords), go right (decreasing)
    cur = math.pi / 2 + arc_span / 2

    for ch, bb, cw in char_data:
        if ch == ' ':
            cur -= (font_size * 0.55 + sp) / radius
            continue
        mid = cur - cw / (2 * radius)
        px_c = cx + radius * math.cos(mid)
        py_c = cy + radius * math.sin(mid)
        rot_deg = math.degrees(mid) - 90
        rot_rad = rot_deg * math.pi / 180

        w2 = max(bb[2] - bb[0], 1)
        h2 = max(bb[3] - bb[1], 1)
        pad = max(stroke_width + 2, 3) if stroke_color else 3
        ci = Image.new("RGBA", (w2 + pad * 2, h2 + pad * 2), (0, 0, 0, 0))
        draw_ci = ImageDraw.Draw(ci)
        x_draw = -bb[0] + pad
        y_draw = -bb[1] + pad  # baseline is at y_draw in ci

        # Stroke
        if stroke_color and stroke_width > 0:
            for dx in range(-stroke_width, stroke_width + 1):
                for dy in range(-stroke_width, stroke_width + 1):
                    if dx == 0 and dy == 0:
                        continue
                    if dx*dx+dy*dy <= stroke_width*stroke_width+1:
                        try:
                            draw_ci.text((x_draw+dx,y_draw+dy),ch,font=fn,
                                         fill=stroke_color,anchor='ls')
                        except TypeError:
                            draw_ci.text((x_draw+dx,y_draw+dy),ch,font=fn,
                                         fill=stroke_color)
        # Fill (drawn twice at +1x to simulate bold weight)
        for _bx in (0,1):
            try:
                draw_ci.text((x_draw+_bx,y_draw),ch,font=fn,fill=fill,anchor='ls')
            except TypeError:
                draw_ci.text((x_draw+_bx,y_draw),ch,font=fn,fill=fill)

        rot=ci.rotate(-rot_deg,expand=True,resample=Image.BICUBIC)

        # Baseline offset from center of ci
        dy_from_center = y_draw - ci.height / 2
        # After clockwise rotation by rot_deg, find where baseline lands
        anchor_x_in_rot=rot.width/2+dy_from_center*math.sin(rot_rad)
        anchor_y_in_rot=rot.height/2+dy_from_center*math.cos(rot_rad)

        ox = int(px_c - anchor_x_in_rot)
        oy = int(py_c - anchor_y_in_rot)
        img.paste(rot, (ox, oy), rot)
        cur -= (cw + sp) / radius
def _make_token(role_id, use_evil, diameter, dead=False, char_name=""):
    sz    = (diameter, diameter)
    inner = int(diameter * 0.92)
    off   = (diameter - inner) // 2
    icx   = inner // 2
    icy   = inner // 2
    inner_img = Image.new("RGBA", (inner, inner), (0, 0, 0, 0))

    art_sz  = int(inner * 0.80)
    art_off = (inner - art_sz) // 2
    char_art = _load(BA.get_token_path(role_id, use_evil), (art_sz, art_sz))
    if dead:
        char_art = ImageEnhance.Color(char_art).enhance(0.0)
    art_m = Image.new("RGBA", (art_sz, art_sz), (0, 0, 0, 0))
    art_m.paste(char_art, (0, 0), _circle_mask((art_sz, art_sz)))
    art_y=max(0,art_off-int(inner*0.04))
    inner_img.paste(art_m,(art_off,art_y),art_m)

    if char_name:
        nlen=len(char_name)
        fn_sz=(max(24,inner//5) if nlen<=6 else max(20,inner//6) if nlen<=10 else max(16,inner//7))
        ls=0.26 if nlen<=8 else 0.20
        text_r=inner//2-fn_sz//2-2
        for _t in range(8):
            _fn=_char_font(fn_sz); _sp=fn_sz*ls
            _tw=sum((getattr(_fn,"getlength",None) and _fn.getlength(c)) or max(_fn.getbbox(c)[2]-_fn.getbbox(c)[0],1) for c in char_name if c!=" ")
            if _tw/max(text_r,1)<=3.0 or fn_sz<=11: break
            fn_sz-=1; text_r=inner//2-fn_sz//2-2
        _draw_arc_text(inner_img,char_name,icx,icy,text_r,fn_sz,
                       fill=(0,0,0),stroke_color=(255,255,255),
                       stroke_width=2,letter_spacing=ls)

    inner_masked=Image.new("RGBA",(inner,inner),(0,0,0,0))
    inner_masked.paste(inner_img,(0,0),_circle_mask((inner,inner)))

    out=Image.new("RGBA",sz,(0,0,0,0))
    out.paste(_load(BA.get_base_path("token"),sz),(0,0),_circle_mask(sz))

    tmp=Image.new("RGBA",sz,(0,0,0,0))
    tmp.paste(inner_masked,(off,off),inner_masked)
    result=Image.alpha_composite(out,tmp)

    if dead:
        dark=Image.new("RGBA",sz,(0,0,12,95))
        dark_c=Image.new("RGBA",sz,(0,0,0,0))
        dark_c.paste(dark,(0,0),_circle_mask(sz))
        result=Image.alpha_composite(result,dark_c)

    return result

def _make_reminder(role_id, text, diam, use_evil=None):
    sz=(diam,diam); mask=_circle_mask(sz)
    out=Image.new("RGBA",sz,(0,0,0,0))
    bg=_load(BA.get_base_path("reminder"),sz)
    out.paste(bg,(0,0),mask)
    icon_sz=int(diam*0.58); ix=(diam-icon_sz)//2; iy=int(diam*0.06)
    _ev=use_evil if use_evil is not None else (role_id in _EVIL_ROLES)
    ci=_load(BA.get_token_path(role_id,_ev),(icon_sz,icon_sz))
    im=Image.new("RGBA",(icon_sz,icon_sz),(0,0,0,0))
    im.paste(ci,(0,0),_circle_mask((icon_sz,icon_sz)))
    out.paste(im,(ix,iy),im)
    fn=_char_font(max(12,diam//6))
    dr=ImageDraw.Draw(out)
    lb=' '.join(w.capitalize() for w in text.split())
    bb=dr.textbbox((0,0),lb,font=fn)
    tx=(diam-(bb[2]-bb[0]))//2; ty=int(diam*0.62)
    sc=(246,223,189)
    sc=(246,223,189)
    for ox,oy in [(-1,0),(1,0),(0,-1),(0,1)]:
        dr.text((tx+ox,ty+oy),lb,font=fn,fill=sc)
    for bx in (0,1):
        dr.text((tx+bx,ty),lb,font=fn,fill=(0,0,0))
    f=Image.new("RGBA",sz,(0,0,0,0)); f.paste(out,(0,0),mask); return f


def _player_positions(n):
    return [(int(CX + CIRCLE_R * math.cos(2 * math.pi * i / n - math.pi / 2)),
             int(CY + CIRCLE_R * math.sin(2 * math.pi * i / n - math.pi / 2)))
            for i in range(n)]

def _reminder_offsets(px, py, count):
    """Place reminders facing inward toward the center."""
    if count == 0: return []
    r      = TOKEN_D // 2 + REM_D + REM_D // 2 + 8
    inward = math.atan2(CY - py, CX - px)
    spread = 0.30
    start  = inward - spread * (count - 1) / 2
    return [(int(px + r * math.cos(start + i * spread)),
             int(py + r * math.sin(start + i * spread)))
            for i in range(count)]

def _draw_center(canvas, g):
    pl    = g['players']
    total = len(pl)
    alive = sum(1 for p in pl if p.get('alive', True))
    votes = sum(1 for p in pl
                if p.get('alive', True) or p.get('tokens', {}).get('ghost_vote_available'))
    tf, out, mn, dem = _base_dist(total)
    draw = ImageDraw.Draw(canvas)
    fn_c = _name_font(26)

    row1 = [
        ('users',        (  0, 247,   0), total),
        ('heartbeat',    (255,  74,  80), alive),
        ('vote-yea',     (255, 255, 255), votes),
    ]
    row2 = [
        ('user-friends', ( 31, 101, 255), tf),
        ('user-friends', ( 70, 213, 255), out),
        ('user-friends', (230, 140,  50), mn),
        ('user',         (220,  55,  55), dem),
    ]
    isz1, isz2 = 34, 29
    cw1,  cw2  = 90, 80
    row1_y = CY - 90
    x = CX - len(row1) * cw1 // 2 + cw1 // 2
    for icon, col, val in row1:
        ic = _fa_icon(icon, isz1, col)
        label = str(val)
        tw = isz1 + 8 + fn_c.getbbox(label)[2]
        ox = x - tw // 2
        _paste_centered(canvas, ic, ox + isz1 // 2, row1_y)
        draw.text((ox + isz1 + 8, row1_y - isz1 // 2 + 2), label, font=fn_c, fill=C_LABEL)
        x += cw1
    row2_y = CY - 10
    x = CX - len(row2) * cw2 // 2 + cw2 // 2
    for icon, col, val in row2:
        ic = _fa_icon(icon, int(isz2*0.82) if icon=="user" else isz2, col)
        label = str(val)
        tw = isz2 + 7 + fn_c.getbbox(label)[2]
        ox = x - tw // 2
        _paste_centered(canvas, ic, ox + isz2 // 2, row2_y)
        draw.text((ox + isz2 + 7, row2_y - isz2 // 2 + 2), label, font=fn_c, fill=C_LABEL)
        x += cw2

    bluffs=[b for b in g.get('_demon_bluffs',[]) if b]
    if bluffs:
        fn_lbl=_name_font(15);bd=66;by=row2_y+52
        bb=draw.textbbox((0,0),'DEMON BLUFFS',font=fn_lbl)
        draw.text((CX-(bb[2]-bb[0])//2,by),'DEMON BLUFFS',font=fn_lbl,fill=(190,55,55))
        by+=22;nb=min(3,len(bluffs));gap=bd+12;bx0=CX-(nb*gap-12)//2
        for ii2,bc in enumerate(bluffs[:3]):
            bx=bx0+ii2*gap+bd//2
            _paste_centered(canvas,_make_token(bc,False,bd,char_name=""),bx,by+bd//2)
            dn=_char_display(bc)
            fn_bn=_name_font(13)
            bb2=draw.textbbox((0,0),dn,font=fn_bn)
            draw.text((bx-(bb2[2]-bb2[0])//2,by+bd+4),dn,font=fn_bn,fill=(200,160,160))

def render_grimoire(g, out_path='/tmp/grim.png'):
    canvas    = Image.new('RGBA', (W, H), BG + (255,))
    players   = g['players']
    positions = _player_positions(len(players))
    fn_name = _name_font(26)
    draw      = ImageDraw.Draw(canvas)

    for player, (px, py) in zip(players, positions):
        role     = player.get('character', '')
        ctype    = player.get('char_type', 'townsfolk')
        alive    = player.get('alive', True)
        use_evil = ctype in ('minion', 'demon')

        tok = _make_token(role, use_evil, TOKEN_D, dead=not alive, char_name=_char_display(role))
        _paste_centered(canvas, tok, px, py)

        reminders = player.get('_reminders', [])[:6]
        for (rx, ry), rem in zip(_reminder_offsets(px, py, len(reminders)), reminders):
            r_role = rem['role'] if isinstance(rem, dict) else rem
            r_text = rem['name'] if isinstance(rem, dict) else r_role.replace('_',' ').title()
            _paste_centered(canvas, _make_reminder(r_role, r_text, REM_D), rx, ry)

        name = player.get('name', '?')
        col  = C_DEAD if not alive else C_LABEL
        bb   = draw.textbbox((0, 0), name, font=fn_name)
        draw.text((px - (bb[2] - bb[0]) // 2, py + TOKEN_D // 2 + 18),
                  name, font=fn_name, fill=col)
    _draw_center(canvas, g)
    canvas.convert('RGB').save(out_path)
    return out_path

def build_grimoire_reminders(g):
    """Populate _reminders list on each player dict."""
    import botc_logic as BL
    players = g['players']
    id_map  = {p['id']: p for p in players}
    for p in players:
        p['_reminders'] = []

    def _rem(role, name):
        return {'role': role, 'name': name}

    ft = BL.get_character(g, 'Fortune Teller')
    if ft:
        rh = ft.get('tokens', {}).get('red_herring')
        if rh and rh in id_map:
            id_map[rh]['_reminders'].append(_rem('fortuneteller', 'Red Herring'))

    for p in players:
        if p.get('tokens', {}).get('poisoned_by_poisoner'):
            p['_reminders'].append(_rem('poisoner', 'Poisoned'))

    drunk = BL.get_character(g, 'Drunk')
    if drunk:
        drunk['_reminders'].append(_rem('drunk', 'Is The Drunk'))

    vi_id = g.get('_vi_drunk_id')
    if vi_id and vi_id in id_map:
        id_map[vi_id]['_reminders'].append(_rem('drunk', 'Is The Drunk'))

    for p in players:
        for rem in p.get('_raw_reminders', []):
            if isinstance(rem,str): rem={'name':rem,'role':''}
            role_raw = rem.get('role', '') or ''
            import re as _re
            role_key = _re.sub(r'[^a-z0-9]', '', role_raw.lower())
            name     = rem.get('name', '') or role_raw.replace('_', ' ').title()
            p['_reminders'].append(_rem(role_key, name))
