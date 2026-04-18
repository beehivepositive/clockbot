from __future__ import annotations

import asyncio
import io

from dwarf_explorer.config import WORLD_SIZE, MAP_PIXEL_SCALE, TILE_COLORS, STRUCTURE_TILES
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
    ("village",       "Village"),
    ("cave",          "Cave"),
    ("ruins",         "Ruins"),
    ("shrine",        "Shrine"),
    ("campfire",      "Campfire"),
]

_LEGEND_SWATCH  = 12   # px square per colour swatch
_LEGEND_ROW_H   = 14   # px height per legend row
_LEGEND_MARGIN  = 6    # px left/right padding inside legend panel
_LEGEND_COL_W   = 110  # px width of one legend column (swatch + label)
_LEGEND_COLS    = 2    # number of columns in legend


def _generate_map_sync(seed: int, overrides: list, player_x: int, player_y: int) -> io.BytesIO:
    """Generate a world map image synchronously. Returns a BytesIO PNG buffer."""
    from PIL import Image, ImageDraw, ImageFont

    scale = MAP_PIXEL_SCALE
    map_w = WORLD_SIZE * scale
    map_h = WORLD_SIZE * scale

    # ── Legend dimensions ─────────────────────────────────────────────────────
    rows_per_col = (len(_LEGEND_ENTRIES) + _LEGEND_COLS - 1) // _LEGEND_COLS
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

    # ── Tile overrides ────────────────────────────────────────────────────────
    for row in overrides:
        wx, wy, tile_type = row
        color = TILE_COLORS.get(tile_type)
        if color:
            x0, y0 = wx * scale, wy * scale
            draw.rectangle([x0, y0, x0 + scale - 1, y0 + scale - 1], fill=color)

    # ── Player marker ─────────────────────────────────────────────────────────
    marker_color = (255, 0, 0)
    for dy in range(-2, 3):
        for dx in range(-2, 3):
            px = player_x * scale + scale // 2 + dx
            py = player_y * scale + scale // 2 + dy
            if 0 <= px < map_w and 0 <= py < map_h:
                img.putpixel((px, py), marker_color)

    # ── Legend panel ──────────────────────────────────────────────────────────
    # Try to load a small bitmap font; fall back to default
    try:
        font = ImageFont.truetype("arial.ttf", 10)
    except Exception:
        try:
            font = ImageFont.load_default(size=10)
        except Exception:
            font = ImageFont.load_default()

    for i, (tile_key, label) in enumerate(_LEGEND_ENTRIES):
        col = i % _LEGEND_COLS
        row = i // _LEGEND_COLS
        x0 = map_w + _LEGEND_MARGIN + col * _LEGEND_COL_W
        y0 = _LEGEND_MARGIN + row * _LEGEND_ROW_H

        color = TILE_COLORS.get(tile_key, (80, 80, 80))
        draw.rectangle([x0, y0, x0 + _LEGEND_SWATCH - 1, y0 + _LEGEND_SWATCH - 1], fill=color,
                       outline=(180, 180, 180))
        draw.text((x0 + _LEGEND_SWATCH + 3, y0), label, fill=(220, 220, 220), font=font)

    # Player dot legend entry
    last_row = len(_LEGEND_ENTRIES) // _LEGEND_COLS
    x0 = map_w + _LEGEND_MARGIN
    y0 = _LEGEND_MARGIN + last_row * _LEGEND_ROW_H
    draw.rectangle([x0, y0, x0 + _LEGEND_SWATCH - 1, y0 + _LEGEND_SWATCH - 1],
                   fill=(255, 0, 0), outline=(180, 180, 180))
    draw.text((x0 + _LEGEND_SWATCH + 3, y0), "You", fill=(220, 220, 220), font=font)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


async def generate_world_map(seed: int, db, player_x: int, player_y: int) -> io.BytesIO:
    """Generate a full world map image with player marker and legend."""
    rows = await db.fetch_all(
        "SELECT world_x, world_y, tile_type FROM tile_overrides"
    )
    overrides = [(r["world_x"], r["world_y"], r["tile_type"]) for r in rows]
    return await asyncio.to_thread(_generate_map_sync, seed, overrides, player_x, player_y)
