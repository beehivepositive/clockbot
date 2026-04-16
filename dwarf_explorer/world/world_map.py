from __future__ import annotations

import asyncio
import io

from dwarf_explorer.config import WORLD_SIZE, MAP_PIXEL_SCALE, TILE_COLORS, STRUCTURE_TILES
from dwarf_explorer.world.terrain import get_biome


def _generate_map_sync(seed: int, overrides: list, player_x: int, player_y: int) -> io.BytesIO:
    """Generate a world map image synchronously. Returns a BytesIO PNG buffer."""
    from PIL import Image, ImageDraw

    scale = MAP_PIXEL_SCALE
    img = Image.new("RGB", (WORLD_SIZE * scale, WORLD_SIZE * scale))
    draw = ImageDraw.Draw(img)

    # Paint base terrain
    for wy in range(WORLD_SIZE):
        for wx in range(WORLD_SIZE):
            biome = get_biome(wx, wy, seed)
            color = TILE_COLORS.get(biome, (0, 0, 0))
            if scale == 1:
                img.putpixel((wx, wy), color)
            else:
                x0, y0 = wx * scale, wy * scale
                draw.rectangle([x0, y0, x0 + scale - 1, y0 + scale - 1], fill=color)

    # Paint tile overrides on top
    for row in overrides:
        wx, wy, tile_type = row
        color = TILE_COLORS.get(tile_type)
        if color:
            if scale == 1:
                img.putpixel((wx, wy), color)
            else:
                x0, y0 = wx * scale, wy * scale
                draw.rectangle([x0, y0, x0 + scale - 1, y0 + scale - 1], fill=color)

    # Draw player marker (bright red, 5x5 pixels centered on player)
    marker_color = (255, 0, 0)
    marker_half = 2
    for dy in range(-marker_half, marker_half + 1):
        for dx in range(-marker_half, marker_half + 1):
            px = player_x * scale + scale // 2 + dx
            py = player_y * scale + scale // 2 + dy
            if 0 <= px < img.width and 0 <= py < img.height:
                img.putpixel((px, py), marker_color)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


async def generate_world_map(seed: int, db, player_x: int, player_y: int) -> io.BytesIO:
    """Generate a full world map image with player marker."""
    # Fetch all tile overrides
    rows = await db.fetch_all(
        "SELECT world_x, world_y, tile_type FROM tile_overrides"
    )
    overrides = [(r["world_x"], r["world_y"], r["tile_type"]) for r in rows]

    return await asyncio.to_thread(_generate_map_sync, seed, overrides, player_x, player_y)
