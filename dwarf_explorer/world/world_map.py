from __future__ import annotations

import asyncio
import io

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
    ("river_landing", "River Landing"),
]
_LEGEND_ICON_ENTRIES = [
    ("village",   "Village",   (200, 160, 60),  "filled_diamond"),
    ("cave",      "Cave",      (60,  40,  30),  "filled_circle"),
    ("shrine",    "Shrine",    (200, 50,  50),  "cross"),
    ("ruins",     "Ruins",     (120, 100, 80),  "outline_square"),
]

_LEGEND_SWATCH = 12
_LEGEND_ROW_H  = 14
_LEGEND_MARGIN = 6
_LEGEND_COL_W  = 110
_LEGEND_COLS   = 2

# Special tiles painted as large icons instead of plain colored squares
_ICON_TILES = {entry[0] for entry in _LEGEND_ICON_ENTRIES}
_ICON_SIZE  = 7   # pixel radius (drawn as 7×7 centred on tile centre)


def _draw_icon(draw, cx: int, cy: int, style: str, color: tuple) -> None:
    """Draw a distinctive 7-pixel icon centred at (cx, cy)."""
    r = 3   # half-size
    white = (255, 255, 255)
    if style == "filled_diamond":
        # Diamond outline + fill
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
    else:  # dot
        draw.ellipse([cx - 2, cy - 2, cx + 2, cy + 2], fill=color, outline=white)


def _generate_map_sync(seed: int, overrides: list, player_x: int, player_y: int,
                       other_players: list | None = None) -> io.BytesIO:
    from PIL import Image, ImageDraw, ImageFont

    scale = MAP_PIXEL_SCALE
    map_w = WORLD_SIZE * scale
    map_h = WORLD_SIZE * scale

    rows_per_col = (len(_LEGEND_ENTRIES) + len(_LEGEND_ICON_ENTRIES) + 1 + _LEGEND_COLS - 1) // _LEGEND_COLS
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
    icon_rows = [(wx, wy, tile_type) for wx, wy, tile_type in overrides
                 if tile_type in _ICON_TILES]
    normal_rows = [(wx, wy, tile_type) for wx, wy, tile_type in overrides
                   if tile_type not in _ICON_TILES]

    for wx, wy, tile_type in normal_rows:
        color = TILE_COLORS.get(tile_type)
        if color:
            x0, y0 = wx * scale, wy * scale
            draw.rectangle([x0, y0, x0 + scale - 1, y0 + scale - 1], fill=color)

    # Icon tiles: draw as large symbols
    _icon_style = {e[0]: (e[2], e[3]) for e in _LEGEND_ICON_ENTRIES}
    for wx, wy, tile_type in icon_rows:
        if tile_type in _icon_style:
            color, style = _icon_style[tile_type]
            cx = wx * scale + scale // 2
            cy = wy * scale + scale // 2
            _draw_icon(draw, cx, cy, style, color)

    # ── Other player markers (blue) ───────────────────────────────────────────
    if other_players:
        for ox, oy, _ in other_players:
            cx_o = ox * scale + scale // 2
            cy_o = oy * scale + scale // 2
            draw.ellipse([cx_o - 3, cy_o - 3, cx_o + 3, cy_o + 3],
                         fill=(60, 120, 255), outline=(255, 255, 255))

    # ── Player marker (red) ───────────────────────────────────────────────────
    cx_p = player_x * scale + scale // 2
    cy_p = player_y * scale + scale // 2
    draw.ellipse([cx_p - 3, cy_p - 3, cx_p + 3, cy_p + 3], fill=(255, 0, 0), outline=(255, 255, 255))

    # ── Legend ────────────────────────────────────────────────────────────────
    try:
        font = ImageFont.truetype("arial.ttf", 10)
    except Exception:
        try:
            font = ImageFont.load_default(size=10)
        except Exception:
            font = ImageFont.load_default()

    all_legend = [(k, label, TILE_COLORS.get(k, (80, 80, 80)), "square")
                  for k, label in _LEGEND_ENTRIES]
    for tile_key, label, color, style in [(e[0], e[1], e[2], e[3]) for e in _LEGEND_ICON_ENTRIES]:
        all_legend.append((tile_key, label, color, style))
    all_legend.append(("__player__", "You", (255, 0, 0), "dot_red"))
    all_legend.append(("__other__", "Other Player", (60, 120, 255), "dot_blue"))

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
        elif style in ("dot_red", "dot_blue"):
            draw.ellipse([x0 + 1, y0 + 1, x0 + _LEGEND_SWATCH - 2, y0 + _LEGEND_SWATCH - 2],
                         fill=color, outline=(255, 255, 255))
        else:
            draw.rectangle([x0, y0, x0 + _LEGEND_SWATCH - 1, y0 + _LEGEND_SWATCH - 1],
                           fill=(30, 30, 30))
            _draw_icon(draw, cx_l, cy_l, style, color)

        draw.text((x0 + _LEGEND_SWATCH + 3, y0), label, fill=(220, 220, 220), font=font)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


async def generate_world_map(seed: int, db, player_x: int, player_y: int,
                             other_players: list | None = None) -> io.BytesIO:
    rows = await db.fetch_all("SELECT world_x, world_y, tile_type FROM tile_overrides")
    overrides = [(r["world_x"], r["world_y"], r["tile_type"]) for r in rows]
    return await asyncio.to_thread(
        _generate_map_sync, seed, overrides, player_x, player_y, other_players or []
    )
