"""Small island interior generation for high-seas exploration.

Islands are procedurally generated 11×11 grids stored in the DB.
Terrain types used:
  island_void   — ocean surrounding the island (impassable)
  island_sand   — beach ring
  island_grass  — interior clearing
  island_forest — dense interior
  island_chest  — treasure chest (loot once per island)
  island_dock   — dock tile to return to the boat
"""
from __future__ import annotations

import asyncio
import math
import random as _rng_module


ISLAND_SIZE = 11   # square grid
ISLAND_WALKABLE = {"island_sand", "island_grass", "island_forest", "island_tree",
                   "island_chest", "island_dock", "island_sapling"}


def _generate_island_tiles(
    island_id: int, ocean_x: int, ocean_y: int,
) -> list[tuple[int, int, str]]:
    """Return list of (local_x, local_y, tile_type) for an 11×11 island."""
    rng = _rng_module.Random(island_id ^ (ocean_x * 1_234_567) ^ (ocean_y * 7_654_321))
    W = H = ISLAND_SIZE
    cx, cy = W // 2, H // 2

    grid: list[list[str]] = [["island_void"] * W for _ in range(H)]

    # Irregular island shape: ellipse radius with per-direction noise
    radii = [2.5 + rng.uniform(-0.6, 0.6) for _ in range(8)]

    def _radius_at(angle_idx: float) -> float:
        lo = radii[int(angle_idx) % 8]
        hi = radii[(int(angle_idx) + 1) % 8]
        t = angle_idx - int(angle_idx)
        return lo + (hi - lo) * t

    for y in range(H):
        for x in range(W):
            dx, dy = x - cx, y - cy
            dist = math.hypot(dx, dy)
            if dist < 0.01:
                grid[y][x] = "island_grass"
                continue
            angle = math.atan2(dy, dx)
            sector = (angle / (2 * math.pi)) * 8
            r = _radius_at(sector)
            if dist < r - 1.2:
                grid[y][x] = "island_forest"
            elif dist < r:
                grid[y][x] = "island_grass"
            elif dist < r + 1.2:
                grid[y][x] = "island_sand"
            # else remains island_void

    # Place chest in interior (forest or grass)
    candidates = [
        (x, y) for y in range(1, H-1) for x in range(1, W-1)
        if grid[y][x] in ("island_forest", "island_grass") and (x, y) != (cx, cy)
    ]
    if candidates:
        chest_x, chest_y = rng.choice(candidates)
        grid[chest_y][chest_x] = "island_chest"

    # Place dock on the south beach edge
    dock_x = cx
    for y in range(H - 1, -1, -1):
        if grid[y][dock_x] == "island_sand":
            grid[y][dock_x] = "island_dock"
            break
    else:
        # Fallback: bottom edge
        if grid[H - 2][dock_x] != "island_void":
            grid[H - 2][dock_x] = "island_dock"
        else:
            grid[H - 3][dock_x] = "island_dock"

    return [(x, y, grid[y][x]) for y in range(H) for x in range(W)]


def _generate_volcano_island_tiles(
    island_id: int, ocean_x: int, ocean_y: int,
) -> list[tuple[int, int, str]]:
    """Return list of (local_x, local_y, tile_type) for a 100×100 volcano island."""
    from dwarf_explorer.config import VOLCANO_ISLAND_SIZE
    rng = _rng_module.Random(island_id ^ (ocean_x * 2_345_678) ^ (ocean_y * 8_765_432))
    W = H = VOLCANO_ISLAND_SIZE
    cx, cy = W // 2, H // 2
    CRATER_R = 12   # radius of lava crater
    VOLCANO_R = 22  # radius of volcanic rock zone
    ISLAND_R  = 42  # radius of main island body

    grid: list[list[str]] = [["vol_void"] * W for _ in range(H)]

    # Per-direction radius noise for irregular coastline
    coast_radii = [ISLAND_R + rng.uniform(-4, 4) for _ in range(16)]

    def _coast_r(angle: float) -> float:
        sector = (angle / (2 * math.pi)) * 16 % 16
        lo = coast_radii[int(sector) % 16]
        hi = coast_radii[(int(sector) + 1) % 16]
        t = sector - int(sector)
        return lo + (hi - lo) * t

    # Fill island
    for y in range(H):
        for x in range(W):
            dx, dy = x - cx, y - cy
            dist = math.hypot(dx, dy)
            angle = math.atan2(dy, dx)
            r = _coast_r(angle)

            if dist < CRATER_R:
                grid[y][x] = "vol_lava"   # lava crater
            elif dist < CRATER_R + 3:
                grid[y][x] = "vol_rock"   # crater rim
            elif dist < VOLCANO_R:
                # Volcanic rock / ash zone
                grid[y][x] = "vol_rock" if rng.random() < 0.6 else "vol_grass"
            elif dist < r - 5:
                # Main interior: mix of forest and grass
                grid[y][x] = "vol_forest" if rng.random() < 0.45 else "vol_grass"
            elif dist < r:
                # Beach ring
                grid[y][x] = "vol_sand" if rng.random() < 0.8 else "vol_grass"
            # else remains vol_void

    # Mark volcano center as crater
    grid[cy][cx] = "vol_crater"
    # A few crater rings
    for cr in range(1, 4):
        for angle_deg in range(0, 360, 15):
            angle = math.radians(angle_deg)
            lx = int(cx + math.cos(angle) * cr)
            ly = int(cy + math.sin(angle) * cr)
            if 0 <= lx < W and 0 <= ly < H:
                grid[ly][lx] = "vol_lava"

    # Lava flows from crater: 3-5 winding rivers outward
    num_flows = rng.randint(3, 5)
    for fi in range(num_flows):
        start_angle = (fi / num_flows) * 2 * math.pi + rng.uniform(-0.2, 0.2)
        fx, fy = float(cx), float(cy)
        fdx = math.cos(start_angle)
        fdy = math.sin(start_angle)
        # Walk outward until we hit the edge of the volcanic rock zone
        for step in range(ISLAND_R):
            fx += fdx + rng.uniform(-0.3, 0.3)
            fy += fdy + rng.uniform(-0.3, 0.3)
            ix, iy = int(fx), int(fy)
            if not (0 <= ix < W and 0 <= iy < H):
                break
            if math.hypot(ix - cx, iy - cy) > VOLCANO_R + 5:
                break
            if grid[iy][ix] not in ("vol_void", "vol_sand", "vol_dock"):
                grid[iy][ix] = "vol_lava"
                # 1-tile wide flow
                for off in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                    nx2, ny2 = ix + off[0], iy + off[1]
                    if (0 <= nx2 < W and 0 <= ny2 < H
                            and grid[ny2][nx2] not in ("vol_void", "vol_sand", "vol_dock")
                            and rng.random() < 0.4):
                        grid[ny2][nx2] = "vol_lava"

    # Lava bridges across lava flow gaps (3–6 bridges)
    bridge_placed = 0
    for _attempt in range(200):
        if bridge_placed >= 6:
            break
        bx = rng.randint(VOLCANO_R - 5, int(ISLAND_R * 0.8))
        by_off = rng.randint(-int(ISLAND_R * 0.7), int(ISLAND_R * 0.7))
        bx_abs = cx + bx
        by_abs = cy + by_off
        if not (2 <= bx_abs < W - 2 and 2 <= by_abs < H - 2):
            continue
        # Check if there's lava on both sides horizontally or vertically
        if (grid[by_abs][bx_abs] == "vol_lava"
                and grid[by_abs][bx_abs - 1] == "vol_lava"
                and grid[by_abs][bx_abs + 1] == "vol_lava"):
            # Bridge across a 1-wide lava gap — just mark center as bridge
            grid[by_abs][bx_abs] = "vol_lava_bridge"
            bridge_placed += 1

    # Cave entrances: 4–7 vol_cave tiles scattered on volcanic rock zone
    cave_positions: list[tuple[int, int]] = []
    for _attempt in range(300):
        if len(cave_positions) >= 7:
            break
        angle = rng.uniform(0, 2 * math.pi)
        r_pos = rng.uniform(VOLCANO_R, ISLAND_R - 6)
        ex = int(cx + math.cos(angle) * r_pos)
        ey = int(cy + math.sin(angle) * r_pos)
        if not (2 <= ex < W - 2 and 2 <= ey < H - 2):
            continue
        if grid[ey][ex] in ("vol_grass", "vol_rock", "vol_forest"):
            if all(math.hypot(ex - cpx, ey - cpy) > 8 for cpx, cpy in cave_positions):
                grid[ey][ex] = "vol_cave"
                cave_positions.append((ex, ey))

    # Outpost/trading post: 1–2 structures on coast
    outpost_placed = 0
    for _attempt in range(200):
        if outpost_placed >= 2:
            break
        angle = rng.uniform(0, 2 * math.pi)
        r_pos = rng.uniform(ISLAND_R - 10, ISLAND_R - 2)
        opx = int(cx + math.cos(angle) * r_pos)
        opy = int(cy + math.sin(angle) * r_pos)
        if not (2 <= opx < W - 2 and 2 <= opy < H - 2):
            continue
        if grid[opy][opx] in ("vol_grass", "vol_sand", "vol_forest"):
            grid[opy][opx] = "vol_outpost"
            outpost_placed += 1

    # Scattered vol_chest (2–4 chests)
    chests_placed = 0
    for _attempt in range(200):
        if chests_placed >= 4:
            break
        angle = rng.uniform(0, 2 * math.pi)
        r_pos = rng.uniform(VOLCANO_R + 2, ISLAND_R - 4)
        chx = int(cx + math.cos(angle) * r_pos)
        chy = int(cy + math.sin(angle) * r_pos)
        if not (1 <= chx < W - 1 and 1 <= chy < H - 1):
            continue
        if grid[chy][chx] in ("vol_grass", "vol_forest"):
            grid[chy][chx] = "vol_chest"
            chests_placed += 1

    # Dock: place on south coast (largest y inside island boundary)
    dock_placed = False
    for y_search in range(H - 1, cy, -1):
        if grid[y_search][cx] in ("vol_sand", "vol_grass"):
            grid[y_search][cx] = "vol_dock"
            dock_placed = True
            break
    if not dock_placed:
        # Fallback
        grid[min(H - 2, cy + int(ISLAND_R) - 2)][cx] = "vol_dock"

    return [(x, y, grid[y][x]) for y in range(H) for x in range(W)]


def _find_dock_pos(tiles: list[tuple[int, int, str]]) -> tuple[int, int]:
    for lx, ly, tt in tiles:
        if tt in ("island_dock", "vol_dock"):
            return lx, ly
    return ISLAND_SIZE // 2, ISLAND_SIZE // 2


async def get_or_create_island_data(
    db, ocean_x: int, ocean_y: int, seed: int,
    island_type: str = "regular",
) -> tuple[int, list[tuple[int, int, str]], tuple[int, int]]:
    """Return (island_id, tiles, (dock_x, dock_y)). Creates DB record if needed."""
    from dwarf_explorer.database.repositories import (
        get_or_create_island, store_island_tiles, get_island_tiles, get_island_type,
    )
    island_id = await get_or_create_island(db, ocean_x, ocean_y, island_type)
    # Use actual stored type (may differ if island was created earlier)
    actual_type = await get_island_type(db, ocean_x, ocean_y)
    existing = await get_island_tiles(db, island_id)
    if existing:
        tiles = existing
    else:
        if actual_type == "volcano":
            from dwarf_explorer.config import VOLCANO_ISLAND_SIZE
            tiles = await asyncio.to_thread(
                _generate_volcano_island_tiles, island_id, ocean_x, ocean_y
            )
        else:
            tiles = await asyncio.to_thread(
                _generate_island_tiles, island_id, ocean_x, ocean_y
            )
        await store_island_tiles(db, island_id, tiles)
    dock_pos = _find_dock_pos(tiles)
    return island_id, tiles, dock_pos


def load_island_viewport(
    tiles: list[tuple[int, int, str]],
    player_x: int,
    player_y: int,
    size: int = 9,
) -> list[list]:
    """Return a size×size list of TileData rows centred on (player_x, player_y)."""
    from dwarf_explorer.world.generator import TileData

    tile_map = {(lx, ly): tt for lx, ly, tt in tiles}
    half = size // 2
    rows: list[list] = []
    for dy in range(-half, half + 1):
        row: list = []
        for dx in range(-half, half + 1):
            nx, ny = player_x + dx, player_y + dy
            terrain = tile_map.get((nx, ny), "island_void")
            row.append(TileData(terrain=terrain, world_x=nx, world_y=ny))
        rows.append(row)
    return rows
