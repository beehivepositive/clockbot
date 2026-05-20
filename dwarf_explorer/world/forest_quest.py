"""
Forest Quest zone: ent corridor → chamber → Sokoban log puzzle → hidden grove.

Zone layout (21 wide × 42 tall):
  y  0-15  : corridor (5 tiles wide at x=8-12); ents disguised as fq_wall
  y 16-29  : chamber (21 wide); puzzle sunken area at x=5-15, y=18-28
  y 30     : stream (impassable fq_stream; fords at x=9,10 once puzzle solved)
  y 31-41  : post-stream area; grove exit at (10, 41)
"""
from __future__ import annotations

import logging

from dwarf_explorer.config import (
    VIEWPORT_SIZE,
    FQ_WIDTH, FQ_HEIGHT,
    FQ_CORRIDOR_X0, FQ_CORRIDOR_X1,
    FQ_CORRIDOR_Y0, FQ_CORRIDOR_Y1,
    FQ_CHAMBER_Y0, FQ_STREAM_Y,
    FQ_PUZZLE_X0, FQ_PUZZLE_X1,
    FQ_PUZZLE_Y0, FQ_PUZZLE_Y1,
    FQ_FORD_XA, FQ_FORD_XB,
    FQ_ENTRY_X, FQ_ENTRY_Y,
    FQ_RESET_X, FQ_RESET_Y,
    FQ_GROVE_EXIT_X, FQ_GROVE_EXIT_Y,
    FQ_LOG_A_START, FQ_LOG_B_START,
    FQ_TARGET_A, FQ_TARGET_B,
    FQ_PUZZLE_OBSTACLES,
    FQ_ENT_STARTS,
    FQ_WALKABLE,
)
from dwarf_explorer.world.generator import TileData

_log = logging.getLogger(__name__)

# Tiles that block ent movement (non-walkable from their perspective)
_ENT_BLOCKED = frozenset({"fq_wall", "fq_obstacle", "fq_stream", "fq_log"})


# ── Zone creation ─────────────────────────────────────────────────────────────

async def get_or_create_fq_area(
    db, guild_id: int,
    entry_forest_id: int | None = None,
    entry_fx: int = 0,
    entry_fy: int = 0,
) -> int:
    """Return the fq_id for this guild, generating the zone on first call.

    If this is the first call, entry_forest_id / entry_fx / entry_fy pin the
    forest tile that acts as the entrance.
    """
    row = await db.fetch_one(
        "SELECT fq_id FROM forest_quest_areas WHERE guild_id=?", (guild_id,)
    )
    if row:
        return row["fq_id"]
    cur = await db.execute(
        "INSERT INTO forest_quest_areas "
        "(guild_id, width, height, entry_forest_id, entry_fx, entry_fy) "
        "VALUES (?,?,?,?,?,?)",
        (guild_id, FQ_WIDTH, FQ_HEIGHT, entry_forest_id, entry_fx, entry_fy),
    )
    fq_id = cur.lastrowid
    await _generate_fq_zone(db, fq_id)
    return fq_id


async def get_fq_entry_info(
    db, guild_id: int
) -> tuple[int | None, int, int]:
    """Return (entry_forest_id, entry_fx, entry_fy) for this guild's FQ zone.

    Returns (None, 0, 0) if no area has been created yet.
    """
    row = await db.fetch_one(
        "SELECT entry_forest_id, entry_fx, entry_fy FROM forest_quest_areas WHERE guild_id=?",
        (guild_id,),
    )
    if not row:
        return (None, 0, 0)
    return (row["entry_forest_id"], row["entry_fx"] or 0, row["entry_fy"] or 0)


async def _generate_fq_zone(db, fq_id: int) -> None:
    """Populate forest_quest_tiles, fq_puzzle_logs, and fq_ents for a new zone."""
    tiles: list[tuple] = []

    log_positions = {FQ_LOG_A_START, FQ_LOG_B_START}

    for y in range(FQ_HEIGHT):
        for x in range(FQ_WIDTH):
            t = _tile_for(x, y, log_positions)
            tiles.append((fq_id, x, y, t))

    await db.executemany(
        "INSERT INTO forest_quest_tiles (fq_id, local_x, local_y, tile_type) VALUES (?,?,?,?)",
        tiles,
    )

    # Puzzle logs
    ax, ay = FQ_LOG_A_START
    bx, by = FQ_LOG_B_START
    await db.executemany(
        "INSERT INTO fq_puzzle_logs (fq_id, log_idx, cur_x, cur_y, start_x, start_y) "
        "VALUES (?,?,?,?,?,?)",
        [
            (fq_id, 0, ax, ay, ax, ay),
            (fq_id, 1, bx, by, bx, by),
        ],
    )

    # Ents (stored separately; rendered as fq_wall overlay in viewport)
    await db.executemany(
        "INSERT INTO fq_ents (fq_id, local_x, local_y, alive) VALUES (?,?,?,1)",
        [(fq_id, x, y) for x, y in FQ_ENT_STARTS],
    )

    await db.commit()
    _log.info("Generated forest quest zone fq_id=%d", fq_id)


def _tile_for(x: int, y: int, _log_positions) -> str:
    """Return the base tile type for zone coordinate (x, y)."""
    # Corridor section
    if FQ_CORRIDOR_Y0 <= y <= FQ_CORRIDOR_Y1:
        if FQ_CORRIDOR_X0 <= x <= FQ_CORRIDOR_X1:
            if x == FQ_ENTRY_X and y == FQ_ENTRY_Y:
                return "fq_exit"
            return "fq_floor"
        return "fq_wall"

    # Stream row
    if y == FQ_STREAM_Y:
        if 1 <= x <= FQ_WIDTH - 2:
            return "fq_stream"
        return "fq_wall"

    # Post-stream
    if y > FQ_STREAM_Y:
        if 1 <= x <= FQ_WIDTH - 2:
            if x == FQ_GROVE_EXIT_X and y == FQ_GROVE_EXIT_Y:
                return "fq_grove_exit"
            return "fq_floor"
        return "fq_wall"

    # Chamber (FQ_CHAMBER_Y0 <= y < FQ_STREAM_Y)
    if 1 <= x <= FQ_WIDTH - 2:
        # Puzzle sunken area
        if FQ_PUZZLE_X0 <= x <= FQ_PUZZLE_X1 and FQ_PUZZLE_Y0 <= y <= FQ_PUZZLE_Y1:
            if (x, y) in FQ_PUZZLE_OBSTACLES:
                return "fq_obstacle"
            if (x, y) == FQ_TARGET_A or (x, y) == FQ_TARGET_B:
                return "fq_log_target"
            return "fq_puzzle_floor"
        # Reset stone
        if x == FQ_RESET_X and y == FQ_RESET_Y:
            return "fq_reset"
        return "fq_floor"

    return "fq_wall"


# ── Viewport loading ──────────────────────────────────────────────────────────

async def load_fq_viewport(
    fq_id: int, player_x: int, player_y: int, db
) -> list[list[TileData]]:
    """Return a 9×9 TileData grid centred on (player_x, player_y)."""
    half = VIEWPORT_SIZE // 2
    x_min = player_x - half
    y_min = player_y - half
    x_max = player_x + half
    y_max = player_y + half

    rows = await db.fetch_all(
        "SELECT local_x, local_y, tile_type FROM forest_quest_tiles "
        "WHERE fq_id=? AND local_x BETWEEN ? AND ? AND local_y BETWEEN ? AND ?",
        (fq_id, x_min, x_max, y_min, y_max),
    )
    tile_map: dict[tuple[int, int], str] = {
        (r["local_x"], r["local_y"]): r["tile_type"] for r in rows
    }

    # Overlay log positions
    log_rows = await db.fetch_all(
        "SELECT cur_x, cur_y FROM fq_puzzle_logs WHERE fq_id=?", (fq_id,)
    )
    log_positions: set[tuple[int, int]] = {(r["cur_x"], r["cur_y"]) for r in log_rows}

    # Overlay alive ent positions (render as fq_wall — disguised trees)
    ent_rows = await db.fetch_all(
        "SELECT local_x, local_y FROM fq_ents WHERE fq_id=? AND alive=1", (fq_id,)
    )
    ent_positions: set[tuple[int, int]] = {(r["local_x"], r["local_y"]) for r in ent_rows}

    grid: list[list[TileData]] = []
    for gy in range(VIEWPORT_SIZE):
        row: list[TileData] = []
        for gx in range(VIEWPORT_SIZE):
            wx = x_min + gx
            wy = y_min + gy
            t = tile_map.get((wx, wy), "fq_wall")
            if (wx, wy) in log_positions:
                t = "fq_log"
            elif (wx, wy) in ent_positions:
                t = "fq_wall"  # ents look like dense-forest walls until they move
            row.append(TileData(terrain=t, walkable=(t in FQ_WALKABLE), structure=None))
        grid.append(row)
    return grid


async def load_fq_single_tile(fq_id: int, x: int, y: int, db) -> TileData:
    """Load a single tile with log/ent overlays applied."""
    # Log overlay
    lrow = await db.fetch_one(
        "SELECT 1 FROM fq_puzzle_logs WHERE fq_id=? AND cur_x=? AND cur_y=?",
        (fq_id, x, y),
    )
    if lrow:
        return TileData(terrain="fq_log", walkable=False, structure=None)

    # Ent overlay
    erow = await db.fetch_one(
        "SELECT 1 FROM fq_ents WHERE fq_id=? AND local_x=? AND local_y=? AND alive=1",
        (fq_id, x, y),
    )
    if erow:
        return TileData(terrain="fq_wall", walkable=False, structure=None)

    row = await db.fetch_one(
        "SELECT tile_type FROM forest_quest_tiles WHERE fq_id=? AND local_x=? AND local_y=?",
        (fq_id, x, y),
    )
    t = row["tile_type"] if row else "fq_wall"
    return TileData(terrain=t, walkable=(t in FQ_WALKABLE), structure=None)


# ── Puzzle helpers ────────────────────────────────────────────────────────────

async def get_fq_log_positions(db, fq_id: int) -> list[tuple[int, int]]:
    rows = await db.fetch_all(
        "SELECT cur_x, cur_y FROM fq_puzzle_logs WHERE fq_id=? ORDER BY log_idx",
        (fq_id,),
    )
    return [(r["cur_x"], r["cur_y"]) for r in rows]


async def move_fq_log(db, fq_id: int, from_x: int, from_y: int,
                      to_x: int, to_y: int) -> None:
    """Move the log at (from_x, from_y) to (to_x, to_y)."""
    await db.execute(
        "UPDATE fq_puzzle_logs SET cur_x=?, cur_y=? WHERE fq_id=? AND cur_x=? AND cur_y=?",
        (to_x, to_y, fq_id, from_x, from_y),
    )
    await db.commit()


async def reset_fq_logs(db, fq_id: int) -> None:
    """Return all logs to their starting positions."""
    await db.execute(
        "UPDATE fq_puzzle_logs SET cur_x=start_x, cur_y=start_y WHERE fq_id=?",
        (fq_id,),
    )
    await db.commit()


async def check_and_solve_puzzle(db, fq_id: int) -> bool:
    """If both logs are on their targets, activate the stream fords and return True."""
    logs = await db.fetch_all(
        "SELECT cur_x, cur_y FROM fq_puzzle_logs WHERE fq_id=?", (fq_id,)
    )
    positions = {(r["cur_x"], r["cur_y"]) for r in logs}
    if FQ_TARGET_A in positions and FQ_TARGET_B in positions:
        # Activate fords
        for fx in (FQ_FORD_XA, FQ_FORD_XB):
            await db.execute(
                "UPDATE forest_quest_tiles SET tile_type='fq_stream_ford' "
                "WHERE fq_id=? AND local_x=? AND local_y=?",
                (fq_id, fx, FQ_STREAM_Y),
            )
        await db.execute(
            "UPDATE forest_quest_areas SET solved=1 WHERE fq_id=?", (fq_id,)
        )
        await db.commit()
        return True
    return False


# ── Ent movement ──────────────────────────────────────────────────────────────

async def step_ents_toward_player(
    db, fq_id: int, player_x: int, player_y: int
) -> list[tuple[int, int]]:
    """
    Move each alive ent one step closer to the player (Manhattan, no diagonal).
    Ents are blocked by walls, obstacles, other ents, and cannot enter the chamber.
    Returns a list of (x, y) positions where an ent reached the player's tile
    (= combat triggers).
    """
    ents = await db.fetch_all(
        "SELECT id, local_x, local_y FROM fq_ents WHERE fq_id=? AND alive=1",
        (fq_id,),
    )
    # Collect all current ent positions to avoid collisions
    ent_pos_set: set[tuple[int, int]] = {(e["local_x"], e["local_y"]) for e in ents}
    combat_triggers: list[tuple[int, int]] = []

    for ent in ents:
        eid, ex, ey = ent["id"], ent["local_x"], ent["local_y"]

        # Ents never enter the chamber (y >= FQ_CHAMBER_Y0)
        if ey >= FQ_CHAMBER_Y0:
            continue

        dx = player_x - ex
        dy = player_y - ey

        # Prefer the axis with the larger gap; ties go to x
        candidates: list[tuple[int, int]] = []
        if abs(dx) >= abs(dy):
            if dx != 0:
                candidates.append((1 if dx > 0 else -1, 0))
            if dy != 0:
                candidates.append((0, 1 if dy > 0 else -1))
        else:
            if dy != 0:
                candidates.append((0, 1 if dy > 0 else -1))
            if dx != 0:
                candidates.append((1 if dx > 0 else -1, 0))

        moved = False
        for sdx, sdy in candidates:
            nx, ny = ex + sdx, ey + sdy
            if ny >= FQ_CHAMBER_Y0:
                continue
            if (nx, ny) in ent_pos_set:
                continue
            tile = await load_fq_single_tile(fq_id, nx, ny, db)
            if tile.terrain in _ENT_BLOCKED:
                continue
            # Move ent
            ent_pos_set.discard((ex, ey))
            ent_pos_set.add((nx, ny))
            await db.execute(
                "UPDATE fq_ents SET local_x=?, local_y=? WHERE id=?",
                (nx, ny, eid),
            )
            ex, ey = nx, ny
            moved = True
            break

        if ex == player_x and ey == player_y:
            combat_triggers.append((ex, ey))

    await db.commit()
    return combat_triggers
