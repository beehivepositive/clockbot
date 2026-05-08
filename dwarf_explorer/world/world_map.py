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
    ("village",   "Village",        (200, 160, 60),  "filled_diamond"),
    ("harbor",    "Harbor Village", (40,  80,  200), "filled_diamond"),
    ("cave",      "Cave",           (60,  40,  30),  "filled_circle"),
    ("shrine",    "Shrine",         (200, 50,  50),  "cross"),
    ("sundial",   "Sundial",        (220, 180, 60),  "cross"),
]

# Ocean-specific legend
_OCEAN_LEGEND_ENTRIES = [
    ("deep_water",    "Deep Water"),
    ("shallow_water", "Shallow Water"),
]
_OCEAN_LEGEND_ICON_ENTRIES = [
    ("island",    "Island",    (200, 170, 80), "filled_diamond"),
    ("shipwreck", "Shipwreck", (100, 80,  50), "outline_square"),
]

_LEGEND_SWATCH = 12
_LEGEND_ROW_H  = 14
_LEGEND_MARGIN = 6
_LEGEND_COL_W  = 120
_LEGEND_COLS   = 2

# Special tiles painted as large icons instead of plain colored squares
_ICON_TILES = {entry[0] for entry in _LEGEND_ICON_ENTRIES}
_ICON_SIZE  = 7   # pixel radius (drawn as 7×7 centred on tile centre)

# ── Base-map cache ─────────────────────────────────────────────────────────────
# Wilderness map: keyed by guild_id → (seed, n_overrides, timestamp, png_bytes)
_BASE_CACHE: dict[int, tuple[int, int, float, bytes]] = {}
# Ocean map: keyed by guild_id → (seed, timestamp, png_bytes)
_OCEAN_BASE_CACHE: dict[int, tuple[int, float, bytes]] = {}

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


def _draw_icon(draw, cx: int, cy: int, style: str, color: tuple) -> None:
    """Draw a distinctive icon centred at (cx, cy)."""
    r = 3   # half-size
    white = (255, 255, 255)
    if style == "filled_diamond":
        pts = [(cx, cy - r), (cx + r, cy), (cx, cy + r), (cx - r, cy)]
        draw.polygon(pts, fill=color, outline=white)
    elif style == "filled_circle":
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color, outline=white)
    elif style == "cross":
        draw.rectangle([cx - r, cy - 1, cx + r, cy + 1], fill=color)
        draw.rectangle([cx - 1, cy - r, cx + 1, cy + r], fill=color)
        draw.rectangle([cx - r, cy - 1, cx + r, cy + 1], outline=white)
    elif style == "outline_square":
        draw.rectangle([cx - r, cy - r, cx + r, cy + r], fill=color, outline=white)
        draw.rectangle([cx - r + 2, cy - r + 2, cx + r - 2, cy + r - 2], fill=(30, 30, 30))
    elif style == "arrow_down":
        ar = 4
        pts = [(cx, cy + ar), (cx - ar, cy - ar), (cx + ar, cy - ar)]
        draw.polygon(pts, fill=color, outline=white)
    elif style == "arrow_up":
        ar = 4
        pts = [(cx, cy - ar), (cx - ar, cy + ar), (cx + ar, cy + ar)]
        draw.polygon(pts, fill=color, outline=white)
    elif style == "arrow_left":
        ar = 4
        pts = [(cx - ar, cy), (cx + ar, cy - ar), (cx + ar, cy + ar)]
        draw.polygon(pts, fill=color, outline=white)
    elif style == "arrow_right":
        ar = 4
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
            _draw_icon(draw, cx_l, cy_l, style, color)

        draw.text((x0 + _LEGEND_SWATCH + 3, y0), label, fill=(220, 220, 220), font=font)


# ── Wilderness base-map renderer ──────────────────────────────────────────────

def _generate_base_map_sync(seed: int, overrides: list) -> bytes:
    """Render terrain + overrides + legend.  Returns raw PNG bytes (no players)."""
    from PIL import Image, ImageDraw, ImageFont

    scale = MAP_PIXEL_SCALE
    map_w = WORLD_SIZE * scale
    map_h = WORLD_SIZE * scale

    all_legend_entries = (
        [(k, label, TILE_COLORS.get(k, (80, 80, 80)), "square") for k, label in _LEGEND_ENTRIES]
        + [(e[0], e[1], e[2], e[3]) for e in _LEGEND_ICON_ENTRIES]
        + [
            ("__player__", "You",           (255, 0,   0),   "dot_red"),
            ("__other__",  "Other Player",  (60,  120, 255), "dot_blue"),
            ("__quest__",  "Quest Target",  (255, 140, 0),   "filled_diamond"),
            ("__ocean__",  "Ocean Quest ▸",  (255, 140, 0),   "arrow_right"),
        ]
    )

    rows_per_col = (len(all_legend_entries) + _LEGEND_COLS - 1) // _LEGEND_COLS
    legend_h = rows_per_col * _LEGEND_ROW_H + _LEGEND_MARGIN * 2
    legend_w = _LEGEND_COLS * _LEGEND_COL_W + _LEGEND_MARGIN * 2
    panel_h  = max(map_h, legend_h)

    img = Image.new("RGB", (map_w + legend_w, panel_h), (30, 30, 30))
    draw = ImageDraw.Draw(img)

    # ── Base terrain ──────────────────────────────────────────────────────────
    for wy in range(WORLD_SIZE):
        for wx in range(WORLD_SIZE):
            biome = get_biome(wx, wy, seed)
            color = TILE_COLORS.get(biome, (0, 0, 0))
            x0, y0 = wx * scale, wy * scale
            draw.rectangle([x0, y0, x0 + scale - 1, y0 + scale - 1], fill=color)

    # ── Tile overrides: normal tiles first, then icons on top ─────────────────
    _icon_style = {e[0]: (e[2], e[3]) for e in _LEGEND_ICON_ENTRIES}
    icon_rows   = [(wx, wy, tt) for wx, wy, tt in overrides if tt in _ICON_TILES]
    normal_rows = [(wx, wy, tt) for wx, wy, tt in overrides if tt not in _ICON_TILES]

    for wx, wy, tile_type in normal_rows:
        color = TILE_COLORS.get(tile_type)
        if color:
            x0, y0 = wx * scale, wy * scale
            draw.rectangle([x0, y0, x0 + scale - 1, y0 + scale - 1], fill=color)

    for wx, wy, tile_type in icon_rows:
        if tile_type in _icon_style:
            color, style = _icon_style[tile_type]
            cx = wx * scale + scale // 2
            cy = wy * scale + scale // 2
            _draw_icon(draw, cx, cy, style, color)

    # ── Legend ────────────────────────────────────────────────────────────────
    try:
        font = ImageFont.truetype("arial.ttf", 10)
    except Exception:
        try:
            font = ImageFont.load_default(size=10)
        except Exception:
            font = ImageFont.load_default()

    _legend_block(draw, all_legend_entries, map_w, font)

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

    # Overworld quest markers — orange diamonds
    if quest_markers:
        for qx, qy, _ in quest_markers:
            cx_q = qx * scale + scale // 2
            cy_q = qy * scale + scale // 2
            _draw_icon(draw, cx_q, cy_q, "filled_diamond", (255, 140, 0))

    # Ocean quest edge markers — arrow + diamond at the ocean-facing edge
    if ocean_quest_markers:
        _ac = (255, 140, 0)
        # Arrow style points toward the ocean edge
        _astyle = {0: "arrow_down", 1: "arrow_up", 2: "arrow_left", 3: "arrow_right"}
        astyle = _astyle.get(coast_edge, "arrow_down")
        # Candidate positions: use one harbor tile (the middle one) to place the
        # single edge indicator — we only want ONE marker regardless of how many
        # harbors exist.
        candidates = harbor_positions or []
        if not candidates:
            # synthetic centre candidate
            if coast_edge in (0, 1):
                candidates = [(WORLD_SIZE // 2, 0)]
            else:
                candidates = [(0, WORLD_SIZE // 2)]
        # Pick the middle harbour so the arrow sits near the centre of the coastline
        single = [candidates[len(candidates) // 2]]
        for hx, hy in single:
            if coast_edge == 0:          # south edge
                px = hx * scale + scale // 2
                _draw_icon(draw, px, map_h - 14, "filled_diamond", _ac)
                _draw_icon(draw, px, map_h - 5,  astyle, _ac)
            elif coast_edge == 1:        # north edge
                px = hx * scale + scale // 2
                _draw_icon(draw, px, 14, "filled_diamond", _ac)
                _draw_icon(draw, px, 5,  astyle, _ac)
            elif coast_edge == 2:        # west edge
                py = hy * scale + scale // 2
                _draw_icon(draw, 14, py, "filled_diamond", _ac)
                _draw_icon(draw, 5,  py, astyle, _ac)
            elif coast_edge == 3:        # east edge
                py = hy * scale + scale // 2
                _draw_icon(draw, map_w - 14, py, "filled_diamond", _ac)
                _draw_icon(draw, map_w - 5,  py, astyle, _ac)

    # Other players — avatar (16 px) or blue dot fallback
    _other_avs = other_avatars or []
    for i, player_entry in enumerate(other_players):
        ox, oy = player_entry[0], player_entry[1]
        cx_o = ox * scale + scale // 2
        cy_o = oy * scale + scale // 2
        av_bytes = _other_avs[i] if i < len(_other_avs) else None
        if av_bytes:
            img = _paste_avatar(img, av_bytes, cx_o, cy_o, 16, (60, 120, 255))
            draw = ImageDraw.Draw(img)  # re-acquire draw after img replace
        else:
            draw.ellipse([cx_o - 4, cy_o - 4, cx_o + 4, cy_o + 4],
                         fill=(60, 120, 255), outline=(255, 255, 255))

    # Current player — avatar (20 px) or red dot fallback
    cx_p = player_x * scale + scale // 2
    cy_p = player_y * scale + scale // 2
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
    """Render 200×200 ocean terrain + structures + legend. Returns raw PNG bytes."""
    from PIL import Image, ImageDraw, ImageFont
    from dwarf_explorer.config import OCEAN_SIZE
    from dwarf_explorer.world.ocean import get_ocean_tile, get_ocean_structure

    scale = MAP_PIXEL_SCALE
    map_w = OCEAN_SIZE * scale
    map_h = OCEAN_SIZE * scale

    all_legend_entries = (
        [(k, label, TILE_COLORS.get(k, (0, 40, 100)), "square") for k, label in _OCEAN_LEGEND_ENTRIES]
        + [(e[0], e[1], e[2], e[3]) for e in _OCEAN_LEGEND_ICON_ENTRIES]
        + [
            ("__player__", "You",              (255, 0,   0),   "dot_red"),
            ("__quest__",  "Quest Target",     (255, 140, 0),   "filled_diamond"),
            ("__exit__",   "Wilderness Quest", (200, 255, 100), "arrow_up"),
        ]
    )

    rows_per_col = (len(all_legend_entries) + _LEGEND_COLS - 1) // _LEGEND_COLS
    legend_h = rows_per_col * _LEGEND_ROW_H + _LEGEND_MARGIN * 2
    legend_w = _LEGEND_COLS * _LEGEND_COL_W + _LEGEND_MARGIN * 2
    panel_h  = max(map_h, legend_h)

    img = Image.new("RGB", (map_w + legend_w, panel_h), (30, 30, 30))
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

    # ── Legend ────────────────────────────────────────────────────────────────
    try:
        font = ImageFont.truetype("arial.ttf", 10)
    except Exception:
        try:
            font = ImageFont.load_default(size=10)
        except Exception:
            font = ImageFont.load_default()

    _legend_block(draw, all_legend_entries, map_w, font)

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

    # Current player (red)
    cx_p = player_ox * scale + scale // 2
    cy_p = player_oy * scale + scale // 2
    draw.ellipse([cx_p - 3, cy_p - 3, cx_p + 3, cy_p + 3],
                 fill=(255, 0, 0), outline=(255, 255, 255))

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


# ── Public API ────────────────────────────────────────────────────────────────

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
) -> io.BytesIO:
    """Return a BytesIO PNG of the ocean map with player dot composited.

    ocean_quest_markers: [(ocean_x, ocean_y, target_id)] — orange diamonds.
    has_wilderness_quests: if True, draws a green arrow at the north exit edge.
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
    )
