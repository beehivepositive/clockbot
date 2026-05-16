from __future__ import annotations

import asyncio
import io
import time

from dwarf_explorer.config import WORLD_SIZE, MAP_PIXEL_SCALE, TILE_COLORS
from dwarf_explorer.world.terrain import get_biome

_LEGEND_ENTRIES = [
    ("deep_water",    "Deep Water"),
    ("shallow_water", "Shallow Water"),
    ("river",         "River"),
    ("bridge",        "Bridge"),
    ("sand",          "Sand"),
    ("plains",        "Plains"),
    ("grass",         "Grass"),
    ("forest",        "Forest"),
    ("dense_forest",  "Dense Forest"),
    ("hills",         "Hills"),
    ("mountain",      "Mountain"),
    ("snow",          "Snow"),
    ("path",          "Path"),
]
_LEGEND_ICON_ENTRIES = [
    ("village",    "Village",        (230, 190,  80),  "filled_diamond"),
    ("harbor",     "Harbor Village", ( 60, 120, 240),  "filled_diamond"),
    ("cave",       "Cave",           (120,  80,  50),  "filled_circle"),
    ("shrine",     "Shrine",         (220,  50,  50),  "cross"),
    ("sundial",    "Sundial",        (240, 200,  50),  "cross"),
    ("sky_temple_outer", "Outer Temple",  (  0, 220, 200), "filled_diamond"),
    ("sky_temple_main",  "Main Temple",   (255, 215,   0), "filled_diamond"),
    ("forest_entrance",  "Forest",        ( 34, 139,  34), "filled_circle"),
    ("bandit_camp",      "Bandit Camp",   (180,  60,  60), "filled_triangle"),
    ("player_house",     "Player House",  (255, 160,  50), "outline_square"),
]

# Ocean-specific legend
_OCEAN_LEGEND_ENTRIES = [
    ("deep_water",    "Deep Water"),
    ("shallow_water", "Shallow Water"),
]
_OCEAN_LEGEND_ICON_ENTRIES = [
    ("island",         "Island",         (200, 170, 80), "filled_diamond"),
    ("volcano_island", "Volcano Island", (220, 80,  20), "filled_diamond"),
    ("shipwreck",      "Shipwreck",      (100, 80,  50), "outline_square"),
]

_LEGEND_SWATCH  = 16   # px square per legend swatch
_LEGEND_ROW_H   = 20   # px per legend row
_LEGEND_MARGIN  = 8
_LEGEND_COL_W   = 120  # width per column (4 columns → 480 + margins = ~496 px wide)
_LEGEND_COLS    = 4    # horizontal layout: 4 columns = wide key image
_LEGEND_ICON_R  = 5    # radius used when drawing icons inside legend swatches

# Special tiles painted as large icons instead of plain colored squares
_ICON_TILES = {entry[0] for entry in _LEGEND_ICON_ENTRIES}

# Per-tile-type icon radius (r).  Higher = bigger icon on map.
_ICON_R: dict[str, int] = {
    "sky_temple_main":  10,  # gold diamond — most prominent landmark
    "sky_temple_outer":  8,  # teal diamond — major landmark
    "village":           6,  # tan diamond
    "harbor":            6,  # blue diamond
    "cave":              5,  # brown circle
    "shrine":            5,  # red cross
    "sundial":           5,  # yellow cross
    "forest_entrance":   5,  # green circle
    "bandit_camp":       4,  # red circle
    "player_house":      4,  # orange outline square
}
_DEFAULT_ICON_R = 5   # fallback for any unlisted icon type

# ── Base-map cache ─────────────────────────────────────────────────────────────
# Wilderness map: keyed by guild_id → (seed, n_overrides, timestamp, png_bytes)
_BASE_CACHE: dict[int, tuple[int, int, float, bytes]] = {}
# Ocean map: keyed by guild_id → (seed, timestamp, png_bytes)
_OCEAN_BASE_CACHE: dict[int, tuple[int, float, bytes]] = {}
# Key/legend image: keyed by guild_id → (seed, png_bytes)
_KEY_CACHE: dict[int, tuple[int, bytes]] = {}

_CACHE_TTL = 3600.0   # 1 hour


def _cache_valid(guild_id: int, seed: int, n_overrides: int) -> bool:
    entry = _BASE_CACHE.get(guild_id)
    if entry is None:
        return False
    c_seed, c_n, c_ts, _ = entry
    return c_seed == seed and c_n == n_overrides and (time.monotonic() - c_ts) < _CACHE_TTL


def _ocean_cache_valid(guild_id: int, seed: int) -> bool:
    entry = _OCEAN_BASE_CACHE.get(guild_id)
    if entry is None:
        return False
    c_seed, c_ts, _ = entry
    return c_seed == seed and (time.monotonic() - c_ts) < _CACHE_TTL


def invalidate_map_cache(guild_id: int) -> None:
    """Force regeneration of the base map on next /map call (e.g. after /newworld)."""
    _BASE_CACHE.pop(guild_id, None)


def invalidate_ocean_map_cache(guild_id: int) -> None:
    """Force regeneration of the ocean base map on next /map call."""
    _OCEAN_BASE_CACHE.pop(guild_id, None)


def _draw_icon(draw, cx: int, cy: int, style: str, color: tuple, r: int = 3) -> None:
    """Draw a distinctive icon centred at (cx, cy). r controls half-size (default 3)."""
    white = (255, 255, 255)
    black = (0, 0, 0)
    h = r + 2   # halo radius (dark outline for contrast against any terrain)
    if style == "filled_diamond":
        # Dark halo first, then coloured diamond on top
        halo = [(cx, cy - h), (cx + h, cy), (cx, cy + h), (cx - h, cy)]
        draw.polygon(halo, fill=black)
        pts = [(cx, cy - r), (cx + r, cy), (cx, cy + r), (cx - r, cy)]
        draw.polygon(pts, fill=color, outline=white)
    elif style == "filled_circle":
        draw.ellipse([cx - h, cy - h, cx + h, cy + h], fill=black)
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color, outline=white)
    elif style == "cross":
        draw.rectangle([cx - r, cy - 1, cx + r, cy + 1], fill=color)
        draw.rectangle([cx - 1, cy - r, cx + 1, cy + r], fill=color)
        draw.rectangle([cx - r, cy - 1, cx + r, cy + 1], outline=white)
    elif style == "outline_square":
        draw.rectangle([cx - r, cy - r, cx + r, cy + r], fill=color, outline=white)
        draw.rectangle([cx - r + 2, cy - r + 2, cx + r - 2, cy + r - 2], fill=(30, 30, 30))
    elif style == "arrow_down":
        ar = r + 1
        pts = [(cx, cy + ar), (cx - ar, cy - ar), (cx + ar, cy - ar)]
        draw.polygon(pts, fill=color, outline=white)
    elif style == "arrow_up":
        ar = r + 1
        pts = [(cx, cy - ar), (cx - ar, cy + ar), (cx + ar, cy + ar)]
        draw.polygon(pts, fill=color, outline=white)
    elif style == "filled_triangle":
        ar = r + 1
        pts = [(cx, cy - ar), (cx - ar, cy + ar), (cx + ar, cy + ar)]
        draw.polygon(pts, fill=color, outline=(255, 255, 255))
    elif style == "arrow_left":
        ar = r + 1
        pts = [(cx - ar, cy), (cx + ar, cy - ar), (cx + ar, cy + ar)]
        draw.polygon(pts, fill=color, outline=white)
    elif style == "arrow_right":
        ar = r + 1
        pts = [(cx + ar, cy), (cx - ar, cy - ar), (cx - ar, cy + ar)]
        draw.polygon(pts, fill=color, outline=white)
    else:  # dot
        draw.ellipse([cx - 2, cy - 2, cx + 2, cy + 2], fill=color, outline=white)


def _legend_block(draw, all_legend: list, map_w: int, font) -> None:
    """Render a legend panel to the right of map_w."""
    for i, (tile_key, label, color, style) in enumerate(all_legend):
        col = i % _LEGEND_COLS
        row = i // _LEGEND_COLS
        x0 = map_w + _LEGEND_MARGIN + col * _LEGEND_COL_W
        y0 = _LEGEND_MARGIN + row * _LEGEND_ROW_H
        cx_l = x0 + _LEGEND_SWATCH // 2
        cy_l = y0 + _LEGEND_SWATCH // 2

        if style == "square":
            draw.rectangle([x0, y0, x0 + _LEGEND_SWATCH - 1, y0 + _LEGEND_SWATCH - 1],
                           fill=color, outline=(180, 180, 180))
        elif style in ("dot_red", "dot_blue", "dot_green"):
            draw.ellipse([x0 + 1, y0 + 1, x0 + _LEGEND_SWATCH - 2, y0 + _LEGEND_SWATCH - 2],
                         fill=color, outline=(255, 255, 255))
        else:
            draw.rectangle([x0, y0, x0 + _LEGEND_SWATCH - 1, y0 + _LEGEND_SWATCH - 1],
                           fill=(30, 30, 30))
            _draw_icon(draw, cx_l, cy_l, style, color, r=_LEGEND_ICON_R)

        # Vertically centre the text within the swatch height
        text_y = y0 + (_LEGEND_SWATCH - 11) // 2
        draw.text((x0 + _LEGEND_SWATCH + 4, text_y), label, fill=(220, 220, 220), font=font)


# ── Coordinate helpers ────────────────────────────────────────────────────────

def _world_to_pixel_y(wy: int) -> int:
    """Convert world y to pixel y.

    y=0 is at the TOP of the image (north). Pressing 'up' (north) decreases y,
    so lower y → lower pixel_y → higher on screen → north is at top.
    """
    return wy * MAP_PIXEL_SCALE


def _draw_coord_rulers(draw, map_w: int, map_h: int, font) -> None:
    """Draw tick marks + labels along the left (Y) and bottom (X) edges of the map.

    Y-axis labels: 0 at BOTTOM (south), increasing upward (north).
      Terrain is rendered with internal y=0 at pixel-top; we flip only the labels
      so the displayed coordinate matches the game's north=high convention.
    X-axis: x=0 at left (west), increasing rightward (east).
    Minor ticks every 50 tiles; major ticks every 100 tiles.
    """
    white  = (255, 255, 255)
    shadow = (0, 0, 0)
    scale  = MAP_PIXEL_SCALE

    minor_len = 5
    major_len = 11

    for display_coord in range(0, WORLD_SIZE + 1, 50):
        display_coord = min(display_coord, WORLD_SIZE)
        is_major = (display_coord % 100 == 0)
        tick = major_len if is_major else minor_len
        lw   = 2      if is_major else 1
        label = str(display_coord)
        show_label = True   # show all labels including 0

        # ── Y-axis ruler (left edge): label 0 at BOTTOM (south) ──────────────
        # Flip: coordinate 0 → pixel bottom, coordinate WORLD_SIZE → pixel top
        py = (WORLD_SIZE - display_coord) * scale
        py = max(0, min(py, map_h - 1))
        draw.line([(0, py), (tick, py)], fill=white, width=lw)
        if show_label:
            if is_major:
                draw.text((tick + 3, py - 5), label, fill=shadow, font=font)
                draw.text((tick + 2, py - 6), label, fill=white,  font=font)
            else:
                draw.text((tick + 2, py - 5), label, fill=(180, 180, 180), font=font)

        # ── X-axis ruler (bottom edge): x=0 at left ─────────────────────────
        px2 = min(display_coord * scale, map_w - 1)
        draw.line([(px2, map_h - tick), (px2, map_h - 1)], fill=white, width=lw)
        if show_label:
            if is_major:
                draw.text((px2 + 2, map_h - tick - 12), label, fill=shadow, font=font)
                draw.text((px2 + 1, map_h - tick - 13), label, fill=white,  font=font)
            else:
                draw.text((px2 + 1, map_h - tick - 11), label, fill=(180, 180, 180), font=font)

    # ── Diagonal origin marker at (0,0) — bottom-left corner (south-west) ────
    ox = 2
    oy = map_h - 4   # start near very bottom edge, diagonal goes upward
    marker_color = (255, 220, 50)
    for d in range(8):
        draw.point((ox + d, oy - d), fill=marker_color)
        draw.point((ox + d + 1, oy - d), fill=marker_color)
    draw.text((ox + 2, oy - 14), "0,0", fill=shadow, font=font)
    draw.text((ox + 1, oy - 15), "0,0", fill=marker_color, font=font)


# ── Wilderness base-map renderer ──────────────────────────────────────────────

def _generate_base_map_sync(seed: int, overrides: list) -> bytes:
    """Render terrain + overrides + rulers.  Returns raw PNG bytes (no legend, no players)."""
    from PIL import Image, ImageDraw, ImageFont

    scale = MAP_PIXEL_SCALE
    map_w = WORLD_SIZE * scale
    map_h = WORLD_SIZE * scale

    img = Image.new("RGB", (map_w, map_h), (30, 30, 30))
    draw = ImageDraw.Draw(img)

    # ── Base terrain (y=0 internal = north = top of image rendered at bottom) ─
    # Display convention: y=0 is SOUTH (bottom), increasing northward.
    for wy in range(WORLD_SIZE):
        for wx in range(WORLD_SIZE):
            biome = get_biome(wx, wy, seed)
            color = TILE_COLORS.get(biome, (0, 0, 0))
            x0 = wx * scale
            y0 = _world_to_pixel_y(wy)
            draw.rectangle([x0, y0, x0 + scale - 1, y0 + scale - 1], fill=color)

    # ── Tile overrides: normal tiles first, then icons on top ─────────────────
    _icon_style = {e[0]: (e[2], e[3]) for e in _LEGEND_ICON_ENTRIES}
    icon_rows   = [(wx, wy, tt) for wx, wy, tt in overrides if tt in _ICON_TILES]
    normal_rows = [(wx, wy, tt) for wx, wy, tt in overrides if tt not in _ICON_TILES]

    for wx, wy, tile_type in normal_rows:
        color = TILE_COLORS.get(tile_type)
        if color:
            x0 = wx * scale
            y0 = _world_to_pixel_y(wy)
            draw.rectangle([x0, y0, x0 + scale - 1, y0 + scale - 1], fill=color)

    for wx, wy, tile_type in icon_rows:
        if tile_type in _icon_style:
            color, style = _icon_style[tile_type]
            cx = wx * scale + scale // 2
            cy = _world_to_pixel_y(wy) + scale // 2
            icon_r = _ICON_R.get(tile_type, _DEFAULT_ICON_R)
            _draw_icon(draw, cx, cy, style, color, r=icon_r)

    # ── Coordinate rulers ─────────────────────────────────────────────────────
    try:
        font = ImageFont.truetype("arial.ttf", 11)
    except Exception:
        try:
            font = ImageFont.load_default(size=11)
        except Exception:
            font = ImageFont.load_default()

    _draw_coord_rulers(draw, map_w, map_h, font)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _generate_key_sync(all_legend_entries: list) -> bytes:
    """Render map legend as a standalone PNG (no terrain). Returns raw PNG bytes."""
    from PIL import Image, ImageDraw, ImageFont

    rows_per_col = (len(all_legend_entries) + _LEGEND_COLS - 1) // _LEGEND_COLS
    legend_h = rows_per_col * _LEGEND_ROW_H + _LEGEND_MARGIN * 2
    legend_w = _LEGEND_COLS * _LEGEND_COL_W + _LEGEND_MARGIN * 2

    img = Image.new("RGB", (legend_w, legend_h), (30, 30, 30))
    draw = ImageDraw.Draw(img)

    try:
        font = ImageFont.truetype("arial.ttf", 11)
    except Exception:
        try:
            font = ImageFont.load_default(size=11)
        except Exception:
            font = ImageFont.load_default()

    # Pass map_w=0 so items render starting at x=_LEGEND_MARGIN
    _legend_block(draw, all_legend_entries, 0, font)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ── Avatar helper ─────────────────────────────────────────────────────────────

def _paste_avatar(
    img,
    avatar_bytes: bytes,
    cx: int, cy: int,
    size: int,
    border_color: tuple,
):
    """Paste a circular cropped avatar centred at (cx, cy) with a coloured border.

    Falls back silently if the image can't be decoded.
    """
    try:
        from PIL import Image, ImageDraw
        av = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA").resize(
            (size, size), Image.LANCZOS
        )
        # Circular mask for the avatar
        mask = Image.new("L", (size, size), 0)
        ImageDraw.Draw(mask).ellipse([0, 0, size - 1, size - 1], fill=255)

        border = 2
        # Draw border circle on the base image
        base_draw = ImageDraw.Draw(img)
        bx0 = cx - size // 2 - border
        by0 = cy - size // 2 - border
        bx1 = cx + size // 2 + border
        by1 = cy + size // 2 + border
        base_draw.ellipse([bx0, by0, bx1, by1], fill=border_color)

        # Composite the circular avatar
        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        overlay.paste(av, (cx - size // 2, cy - size // 2), mask)
        base_rgba = img.convert("RGBA")
        img = Image.alpha_composite(base_rgba, overlay).convert("RGB")
    except Exception:
        pass  # fall back to whatever was drawn before (the border circle)
    return img


# ── Wilderness player-dot compositor ─────────────────────────────────────────

def _composite_players_sync(
    base_png: bytes,
    player_x: int, player_y: int,
    other_players: list,
    quest_markers: list | None = None,
    ocean_quest_markers: list | None = None,
    harbor_positions: list | None = None,
    coast_edge: int = 0,
    player_avatar: bytes | None = None,
    other_avatars: list[bytes | None] | None = None,
) -> io.BytesIO:
    """Load the cached base PNG and stamp player/quest dots on top.

    coast_edge: 0=south, 1=north, 2=west, 3=east — which edge the ocean is on.
    player_avatar: PNG/JPEG bytes for the current player's profile picture.
    other_avatars: parallel list to other_players with avatar bytes (or None).
    """
    from PIL import Image, ImageDraw

    scale = MAP_PIXEL_SCALE
    map_w = WORLD_SIZE * scale
    map_h = WORLD_SIZE * scale
    img  = Image.open(io.BytesIO(base_png)).copy()
    draw = ImageDraw.Draw(img)

    # Overworld quest markers — red diamonds (use _world_to_pixel_y for flipped coords)
    if quest_markers:
        for qx, qy, _ in quest_markers:
            cx_q = qx * scale + scale // 2
            cy_q = _world_to_pixel_y(qy) + scale // 2
            _draw_icon(draw, cx_q, cy_q, "filled_diamond", (220, 30, 30), r=6)

    # Ocean quest edge markers — arrow + diamond at the ocean-facing edge
    if ocean_quest_markers:
        _ac = (255, 140, 0)
        # Arrow style points toward the ocean edge
        _astyle = {0: "arrow_down", 1: "arrow_up", 2: "arrow_left", 3: "arrow_right"}
        astyle = _astyle.get(coast_edge, "arrow_down")
        candidates = harbor_positions or []
        if not candidates:
            if coast_edge in (0, 1):
                candidates = [(WORLD_SIZE // 2, 0)]
            else:
                candidates = [(0, WORLD_SIZE // 2)]
        single = [candidates[len(candidates) // 2]]
        for hx, hy in single:
            if coast_edge == 0:          # south edge (internal y=WORLD_SIZE-1 = pixel y top)
                px = hx * scale + scale // 2
                _draw_icon(draw, px, map_h - 14, "filled_diamond", _ac)
                _draw_icon(draw, px, map_h - 5,  astyle, _ac)
            elif coast_edge == 1:        # north edge
                px = hx * scale + scale // 2
                _draw_icon(draw, px, 14, "filled_diamond", _ac)
                _draw_icon(draw, px, 5,  astyle, _ac)
            elif coast_edge == 2:        # west edge
                py = _world_to_pixel_y(hy) + scale // 2
                _draw_icon(draw, 14, py, "filled_diamond", _ac)
                _draw_icon(draw, 5,  py, astyle, _ac)
            elif coast_edge == 3:        # east edge
                py = _world_to_pixel_y(hy) + scale // 2
                _draw_icon(draw, map_w - 14, py, "filled_diamond", _ac)
                _draw_icon(draw, map_w - 5,  py, astyle, _ac)

    # Other players — avatar (16 px) or blue dot fallback
    _other_avs = other_avatars or []
    for i, player_entry in enumerate(other_players):
        ox, oy = player_entry[0], player_entry[1]
        cx_o = ox * scale + scale // 2
        cy_o = _world_to_pixel_y(oy) + scale // 2
        av_bytes = _other_avs[i] if i < len(_other_avs) else None
        if av_bytes:
            img = _paste_avatar(img, av_bytes, cx_o, cy_o, 16, (60, 120, 255))
            draw = ImageDraw.Draw(img)  # re-acquire draw after img replace
        else:
            draw.ellipse([cx_o - 4, cy_o - 4, cx_o + 4, cy_o + 4],
                         fill=(60, 120, 255), outline=(255, 255, 255))

    # Current player — avatar (20 px) or red dot fallback
    cx_p = player_x * scale + scale // 2
    cy_p = _world_to_pixel_y(player_y) + scale // 2
    if player_avatar:
        img = _paste_avatar(img, player_avatar, cx_p, cy_p, 20, (255, 50, 50))
        draw = ImageDraw.Draw(img)
    else:
        draw.ellipse([cx_p - 5, cy_p - 5, cx_p + 5, cy_p + 5],
                     fill=(255, 0, 0), outline=(255, 255, 255))

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


# ── Ocean base-map renderer ───────────────────────────────────────────────────

def _generate_ocean_base_map_sync(seed: int) -> bytes:
    """Render 200×200 ocean terrain + structures (no legend). Returns raw PNG bytes."""
    from PIL import Image, ImageDraw
    from dwarf_explorer.config import OCEAN_SIZE
    from dwarf_explorer.world.ocean import get_ocean_tile, get_ocean_structure

    scale = MAP_PIXEL_SCALE
    map_w = OCEAN_SIZE * scale
    map_h = OCEAN_SIZE * scale

    img = Image.new("RGB", (map_w, map_h), (30, 30, 30))
    draw = ImageDraw.Draw(img)

    # ── Base terrain ──────────────────────────────────────────────────────────
    for oy in range(OCEAN_SIZE):
        for ox in range(OCEAN_SIZE):
            terrain = get_ocean_tile(ox, oy, seed)
            color = TILE_COLORS.get(terrain, (0, 20, 80))
            x0, y0 = ox * scale, oy * scale
            draw.rectangle([x0, y0, x0 + scale - 1, y0 + scale - 1], fill=color)

    # ── Structure icons ───────────────────────────────────────────────────────
    _ocean_icon_style = {e[0]: (e[2], e[3]) for e in _OCEAN_LEGEND_ICON_ENTRIES}
    for oy in range(OCEAN_SIZE):
        for ox in range(OCEAN_SIZE):
            struct = get_ocean_structure(ox, oy, seed)
            if struct and struct in _ocean_icon_style:
                color, style = _ocean_icon_style[struct]
                cx = ox * scale + scale // 2
                cy = oy * scale + scale // 2
                _draw_icon(draw, cx, cy, style, color)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ── Ocean player-dot compositor ───────────────────────────────────────────────

def _composite_ocean_sync(
    base_png: bytes,
    player_ox: int, player_oy: int,
    ocean_quest_markers: list | None = None,
    has_wilderness_quests: bool = False,
    coast_edge: int = 0,
    player_avatar: bytes | None = None,
) -> io.BytesIO:
    """coast_edge is the same value as for the wilderness map (0=south etc.).
    The exit from the ocean is on the *opposite* side of the ocean grid:
      coast_edge 0 (ocean south of wilderness): exit at oy=0, arrow UP
      coast_edge 1 (ocean north of wilderness): exit at oy=OCEAN_SIZE-1, arrow DOWN
      coast_edge 2 (ocean west of wilderness):  exit at ox=OCEAN_SIZE-1, arrow RIGHT
      coast_edge 3 (ocean east of wilderness):  exit at ox=0, arrow LEFT
    """
    from PIL import Image, ImageDraw
    from dwarf_explorer.config import OCEAN_SIZE

    scale = MAP_PIXEL_SCALE
    map_w = OCEAN_SIZE * scale
    map_h = OCEAN_SIZE * scale
    img  = Image.open(io.BytesIO(base_png)).copy()
    draw = ImageDraw.Draw(img)

    # Ocean quest markers — orange diamonds at their ocean coordinates
    if ocean_quest_markers:
        for ox, oy, _ in ocean_quest_markers:
            cx_q = ox * scale + scale // 2
            cy_q = oy * scale + scale // 2
            _draw_icon(draw, cx_q, cy_q, "filled_diamond", (255, 140, 0))

    # Wilderness exit marker — green arrow at the exit edge of the ocean grid
    if has_wilderness_quests:
        _ec = (200, 255, 100)
        _dc = (255, 140, 0)
        mid = (OCEAN_SIZE // 2) * scale + scale // 2
        if coast_edge == 0:          # exit: north edge (oy=0), go up
            _draw_icon(draw, mid, 14, "filled_diamond", _dc)
            _draw_icon(draw, mid, 5,  "arrow_up",   _ec)
        elif coast_edge == 1:        # exit: south edge (oy=max), go down
            _draw_icon(draw, mid, map_h - 14, "filled_diamond", _dc)
            _draw_icon(draw, mid, map_h - 5,  "arrow_down", _ec)
        elif coast_edge == 2:        # exit: east edge (ox=max), go right
            _draw_icon(draw, map_w - 14, mid, "filled_diamond", _dc)
            _draw_icon(draw, map_w - 5,  mid, "arrow_right", _ec)
        elif coast_edge == 3:        # exit: west edge (ox=0), go left
            _draw_icon(draw, 14, mid, "filled_diamond", _dc)
            _draw_icon(draw, 5,  mid, "arrow_left", _ec)

    # Current player — avatar (20 px) or red dot fallback
    cx_p = player_ox * scale + scale // 2
    cy_p = player_oy * scale + scale // 2
    if player_avatar:
        img = _paste_avatar(img, player_avatar, cx_p, cy_p, 20, (255, 50, 50))
        draw = ImageDraw.Draw(img)
    else:
        draw.ellipse([cx_p - 3, cy_p - 3, cx_p + 3, cy_p + 3],
                     fill=(255, 0, 0), outline=(255, 255, 255))

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


# ── Public API ────────────────────────────────────────────────────────────────

def _build_wilderness_legend_entries() -> list:
    """Return the full list of (key, label, color, style) tuples for the wilderness legend."""
    return (
        [(k, label, TILE_COLORS.get(k, (80, 80, 80)), "square") for k, label in _LEGEND_ENTRIES]
        + [(e[0], e[1], e[2], e[3]) for e in _LEGEND_ICON_ENTRIES]
        + [
            ("__player__", "You",           (255,  40,  40), "dot_red"),
            ("__other__",  "Other Player",  ( 60, 120, 255), "dot_blue"),
            ("__quest__",  "Quest Target",  (220,  30,  30), "filled_diamond"),
        ]
    )


async def generate_world_map_key(guild_id: int, seed: int) -> io.BytesIO:
    """Return a BytesIO PNG of the wilderness map legend (terrain key + icon key, no map)."""
    entry = _KEY_CACHE.get(guild_id)
    if entry is not None and entry[0] == seed:
        _, png_bytes = entry
    else:
        all_legend_entries = _build_wilderness_legend_entries()
        png_bytes = await asyncio.to_thread(_generate_key_sync, all_legend_entries)
        _KEY_CACHE[guild_id] = (seed, png_bytes)

    buf = io.BytesIO(png_bytes)
    buf.seek(0)
    return buf


def _stitch_map_and_key_sync(map_png: bytes, key_png: bytes) -> io.BytesIO:
    """Composite the key legend above the map image and return a combined BytesIO PNG."""
    from PIL import Image

    map_img = Image.open(io.BytesIO(map_png))
    key_img = Image.open(io.BytesIO(key_png))
    map_w, map_h = map_img.size
    key_w, key_h = key_img.size

    # Place key centred horizontally above the map on a dark background
    combined = Image.new("RGB", (map_w, key_h + map_h), (30, 30, 30))
    key_x = max(0, (map_w - key_w) // 2)
    combined.paste(key_img, (key_x, 0))
    combined.paste(map_img, (0, key_h))

    buf = io.BytesIO()
    combined.save(buf, format="PNG")
    buf.seek(0)
    return buf


async def generate_world_map_with_key(
    seed: int, db, guild_id: int,
    player_x: int, player_y: int,
    other_players: list | None = None,
    quest_markers: list | None = None,
    ocean_quest_markers: list | None = None,
    player_avatar: bytes | None = None,
    other_avatars: list[bytes | None] | None = None,
) -> io.BytesIO:
    """Generate world map with the legend key stitched above it as one combined PNG."""
    # Ensure key bytes are cached
    key_entry = _KEY_CACHE.get(guild_id)
    if key_entry is not None and key_entry[0] == seed:
        key_bytes = key_entry[1]
    else:
        all_legend_entries = _build_wilderness_legend_entries()
        key_bytes = await asyncio.to_thread(_generate_key_sync, all_legend_entries)
        _KEY_CACHE[guild_id] = (seed, key_bytes)

    map_buf = await generate_world_map(
        seed, db, guild_id, player_x, player_y,
        other_players, quest_markers, ocean_quest_markers,
        player_avatar, other_avatars,
    )
    map_bytes = map_buf.getvalue()
    return await asyncio.to_thread(_stitch_map_and_key_sync, map_bytes, key_bytes)


async def generate_world_map(
    seed: int, db, guild_id: int,
    player_x: int, player_y: int,
    other_players: list | None = None,
    quest_markers: list | None = None,
    ocean_quest_markers: list | None = None,
    player_avatar: bytes | None = None,
    other_avatars: list[bytes | None] | None = None,
) -> io.BytesIO:
    """Return a BytesIO PNG of the wilderness world map with player dots composited.

    quest_markers: [(world_x, world_y, target_id)] — orange diamonds on map.
    ocean_quest_markers: if non-empty, draws edge arrows toward ocean (harbors).
    player_avatar: PNG/JPEG bytes for the current player's profile picture.
    other_avatars: parallel list to other_players with avatar bytes (or None).
    """
    rows = await db.fetch_all("SELECT world_x, world_y, tile_type FROM tile_overrides")
    overrides = [(r["world_x"], r["world_y"], r["tile_type"]) for r in rows]
    n_overrides = len(overrides)

    if not _cache_valid(guild_id, seed, n_overrides):
        base_png = await asyncio.to_thread(_generate_base_map_sync, seed, overrides)
        _BASE_CACHE[guild_id] = (seed, n_overrides, time.monotonic(), base_png)
    else:
        _, _, _, base_png = _BASE_CACHE[guild_id]

    harbor_positions = [(wx, wy) for wx, wy, tt in overrides if tt == "harbor"]

    from dwarf_explorer.world.terrain import get_coast_boundary
    coast_edge, _ = get_coast_boundary(seed)

    return await asyncio.to_thread(
        _composite_players_sync, base_png, player_x, player_y,
        other_players or [], quest_markers or [],
        ocean_quest_markers or [], harbor_positions, coast_edge,
        player_avatar, other_avatars,
    )


async def generate_ocean_map(
    seed: int, guild_id: int,
    player_ox: int, player_oy: int,
    ocean_quest_markers: list | None = None,
    has_wilderness_quests: bool = False,
    player_avatar: bytes | None = None,
) -> io.BytesIO:
    """Return a BytesIO PNG of the ocean map with player dot composited.

    ocean_quest_markers: [(ocean_x, ocean_y, target_id)] — orange diamonds.
    has_wilderness_quests: if True, draws a green arrow at the north exit edge.
    player_avatar: PNG/JPEG bytes for the current player's profile picture.
    """
    if not _ocean_cache_valid(guild_id, seed):
        base_png = await asyncio.to_thread(_generate_ocean_base_map_sync, seed)
        _OCEAN_BASE_CACHE[guild_id] = (seed, time.monotonic(), base_png)
    else:
        _, _, base_png = _OCEAN_BASE_CACHE[guild_id]

    from dwarf_explorer.world.terrain import get_coast_boundary
    coast_edge, _ = get_coast_boundary(seed)

    return await asyncio.to_thread(
        _composite_ocean_sync, base_png, player_ox, player_oy,
        ocean_quest_markers or [], has_wilderness_quests, coast_edge,
        player_avatar,
    )
