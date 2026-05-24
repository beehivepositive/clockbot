"""
Forest Quest zone: ent corridor → Sokoban chamber → stream → post-stream corridor →
shop section → Thornwarden boss chamber → (Y-fork / puzzle gauntlet / final room — TBD).

Zone layout (21 wide × 200 tall):
  y   0-15  : corridor (5 wide at x=8-12); ents disguised as fq_wall
  y  16-28  : Sokoban chamber (21 wide); puzzle sunken area at x=5-15, y=18-28
  y  29-30  : stream (2-wide; push logs into stream to build bridge — no orange targets)
  y  31-40  : post-stream corridor (3 wide at x=9-11, same as shop corridor)
  y  41-53  : shop section (3-wide corridor x=9-11; 2-wide wall x=7-8; side room x=3-6, y=44-50; 1-tile opening at y=47; shopkeeper at x=6, y=47)
  y  54-57  : boss approach (corridor widens to full room width)
  y  58-79  : Thornwarden boss chamber (19 wide at x=1-19)
               Warden body: x=8-12, y=65-67; eyes at corners
               Boss door at (10, 79) — locked until warden defeated
  y  80-87  : post-boss corridor (7 wide at x=7-13)
  y  88+    : future sections (Y-fork, puzzle gauntlet, final room)
"""
from __future__ import annotations

import logging

from dwarf_explorer.config import (
    VIEWPORT_SIZE,
    FQ_WIDTH, FQ_HEIGHT,
    FQ_CORRIDOR_X0, FQ_CORRIDOR_X1,
    FQ_CORRIDOR_Y0, FQ_CORRIDOR_Y1,
    FQ_CHAMBER_Y0, FQ_STREAM_Y, FQ_STREAM_Y2,
    FQ_PUZZLE_X0, FQ_PUZZLE_X1,
    FQ_PUZZLE_Y0, FQ_PUZZLE_Y1,
    FQ_FORD_XA, FQ_FORD_XB,
    FQ_ENTRY_X, FQ_ENTRY_Y,
    FQ_RESET_X, FQ_RESET_Y,
    FQ_LOG_A_START, FQ_LOG_B_START,
    FQ_PUZZLE_OBSTACLES,
    FQ_ENT_STARTS,
    FQ_WALKABLE,
    # Post-stream / shop
    FQ_POST_STREAM_X0, FQ_POST_STREAM_X1,
    FQ_SHOP_Y0, FQ_SHOP_Y1,
    FQ_SHOP_ROOM_Y0, FQ_SHOP_ROOM_Y1,
    FQ_SHOP_OPENING_Y,
    FQ_SHOPKEEPER_X, FQ_SHOPKEEPER_Y,
    # Boss approach + chamber
    FQ_BOSS_APPROACH_Y0, FQ_BOSS_APPROACH_Y1,
    FQ_BOSS_CHAMBER_Y0, FQ_BOSS_CHAMBER_Y1,
    FQ_BOSS_CHAMBER_CX, FQ_BOSS_CHAMBER_CY, FQ_BOSS_CHAMBER_R,
    FQ_WARDEN_X0, FQ_WARDEN_X1,
    FQ_WARDEN_Y0, FQ_WARDEN_Y1,
    FQ_WARDEN_EYE_NW, FQ_WARDEN_EYE_NE,
    FQ_WARDEN_EYE_SW, FQ_WARDEN_EYE_SE,
    FQ_WARDEN_EYE_POSITIONS, FQ_WARDEN_EYE_BY_POS, FQ_WARDEN_EYE_CYCLE,
    FQ_BOSS_DOOR_X, FQ_BOSS_DOOR_Y,
    FQ_BOSS_CHEST_X, FQ_BOSS_CHEST_Y,
    FQ_POST_BOSS_Y0, FQ_POST_BOSS_Y1,
    # Y-fork
    FQ_FORK_Y0, FQ_FORK_LOBBY_Y,
    FQ_FORK_BRANCH_Y0, FQ_FORK_BRANCH_Y1, FQ_FORK_Y1,
    FQ_FORK_LEFT_WALL_X, FQ_FORK_RIGHT_WALL_X,
    FQ_FORK_CHEST_L, FQ_FORK_CHEST_R,
    # Canal puzzle
    FQ_CANAL_Y0, FQ_CANAL_ROOM_Y0, FQ_CANAL_ROOM_Y1,
    FQ_CANAL_TARGET_A, FQ_CANAL_TARGET_B,
    FQ_CANAL_BLOCK_A_START, FQ_CANAL_BLOCK_B_START,
    FQ_CANAL_GATE_X, FQ_CANAL_GATE_Y,
    FQ_CANAL_RESET_X, FQ_CANAL_RESET_Y,
    FQ_CANAL_Y1,
    # Final room
    FQ_FINAL_Y0, FQ_FINAL_ROOM_Y0, FQ_FINAL_Y1,
    FQ_ANCIENT_TREE_X, FQ_ANCIENT_TREE_Y,
    FQ_ANCIENT_TREE_CHEST_X, FQ_ANCIENT_TREE_CHEST_Y,
    FQ_ANCIENT_ENT_1, FQ_ANCIENT_ENT_2, FQ_ANCIENT_ENT_POSITIONS,
    FQ_FINAL_EXIT_X, FQ_FINAL_EXIT_Y,
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
    """Return the fq_id for this guild, generating the zone on first call."""
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
    """Return (entry_forest_id, entry_fx, entry_fy) for this guild's FQ zone."""
    row = await db.fetch_one(
        "SELECT entry_forest_id, entry_fx, entry_fy FROM forest_quest_areas WHERE guild_id=?",
        (guild_id,),
    )
    if not row:
        return (None, 0, 0)
    return (row["entry_forest_id"], row["entry_fx"] or 0, row["entry_fy"] or 0)


async def get_warden_defeated(db, fq_id: int) -> bool:
    """Return True if the Thornwarden has been defeated in this zone."""
    row = await db.fetch_one(
        "SELECT warden_defeated FROM forest_quest_areas WHERE fq_id=?", (fq_id,)
    )
    return bool(row and row["warden_defeated"])


async def defeat_warden(db, fq_id: int) -> None:
    """
    Called when all 4 eyes are destroyed.
    - Collapses remaining warden tiles to fq_warden_dead
    - Opens the boss door
    - Spawns a loot chest at the chamber centre
    - Marks warden_defeated = 1
    """
    # Collapse all living warden tiles
    await db.execute(
        "UPDATE forest_quest_tiles SET tile_type='fq_warden_dead' "
        "WHERE fq_id=? AND tile_type IN "
        "('fq_warden_body','fq_warden_eye_nw','fq_warden_eye_ne',"
        "'fq_warden_eye_sw','fq_warden_eye_se')",
        (fq_id,),
    )
    # Open the boss door
    await db.execute(
        "UPDATE forest_quest_tiles SET tile_type='fq_boss_door_open' "
        "WHERE fq_id=? AND tile_type='fq_boss_door'",
        (fq_id,),
    )
    # Spawn chest at centre (replace the fq_warden_dead tile there with chest)
    await db.execute(
        "UPDATE forest_quest_tiles SET tile_type='fq_boss_chest' "
        "WHERE fq_id=? AND local_x=? AND local_y=?",
        (fq_id, FQ_BOSS_CHEST_X, FQ_BOSS_CHEST_Y),
    )
    # Mark zone
    await db.execute(
        "UPDATE forest_quest_areas SET warden_defeated=1 WHERE fq_id=?", (fq_id,)
    )
    await db.commit()
    _log.info("Thornwarden defeated in fq_id=%d", fq_id)


# ── Zone tile generation ───────────────────────────────────────────────────────

async def _generate_fq_zone(db, fq_id: int) -> None:
    """Populate forest_quest_tiles, fq_puzzle_logs, and fq_ents for a new zone."""
    log_positions = {FQ_LOG_A_START, FQ_LOG_B_START}

    tiles: list[tuple] = []
    for y in range(FQ_HEIGHT):
        for x in range(FQ_WIDTH):
            t = _tile_for(x, y, log_positions)
            tiles.append((fq_id, x, y, t))

    await db.executemany(
        "INSERT INTO forest_quest_tiles (fq_id, local_x, local_y, tile_type) VALUES (?,?,?,?)",
        tiles,
    )

    # Sokoban puzzle logs (indices 0, 1)
    ax, ay = FQ_LOG_A_START
    bx, by = FQ_LOG_B_START
    # Canal puzzle logs (indices 2, 3)
    cax, cay = FQ_CANAL_BLOCK_A_START
    cbx, cby = FQ_CANAL_BLOCK_B_START
    await db.executemany(
        "INSERT INTO fq_puzzle_logs (fq_id, log_idx, cur_x, cur_y, start_x, start_y) "
        "VALUES (?,?,?,?,?,?)",
        [
            (fq_id, 0, ax,  ay,  ax,  ay),
            (fq_id, 1, bx,  by,  bx,  by),
            (fq_id, 2, cax, cay, cax, cay),
            (fq_id, 3, cbx, cby, cbx, cby),
        ],
    )

    # Regular ents in corridor (rendered as fq_wall overlay until they move)
    await db.executemany(
        "INSERT INTO fq_ents (fq_id, local_x, local_y, alive, ent_type) VALUES (?,?,?,1,'regular')",
        [(fq_id, x, y) for x, y in FQ_ENT_STARTS],
    )

    # Ancient ents in final room
    await db.executemany(
        "INSERT INTO fq_ents (fq_id, local_x, local_y, alive, ent_type) VALUES (?,?,?,1,'ancient')",
        [(fq_id, x, y) for x, y in FQ_ANCIENT_ENT_POSITIONS],
    )

    await db.commit()
    _log.info("Generated forest quest zone fq_id=%d", fq_id)


def _tile_for(x: int, y: int, _log_positions) -> str:
    """Return the base tile type for zone coordinate (x, y)."""

    # ── Corridor (y 0-15) ──────────────────────────────────────────────────
    if FQ_CORRIDOR_Y0 <= y <= FQ_CORRIDOR_Y1:
        if FQ_CORRIDOR_X0 <= x <= FQ_CORRIDOR_X1:
            if x == FQ_ENTRY_X and y == FQ_ENTRY_Y:
                return "fq_exit"
            return "fq_floor"
        return "fq_wall"

    # ── Sokoban chamber (y 16-29) ──────────────────────────────────────────
    if FQ_CHAMBER_Y0 <= y < FQ_STREAM_Y:
        if 1 <= x <= FQ_WIDTH - 2:
            if FQ_PUZZLE_X0 <= x <= FQ_PUZZLE_X1 and FQ_PUZZLE_Y0 <= y <= FQ_PUZZLE_Y1:
                if (x, y) in FQ_PUZZLE_OBSTACLES:
                    return "fq_obstacle"
                return "fq_puzzle_floor"
            if x == FQ_RESET_X and y == FQ_RESET_Y:
                return "fq_reset"
            return "fq_floor"
        return "fq_wall"

    # ── Stream rows (y 29-30) — near ford + far deep channel ─────────────
    if FQ_STREAM_Y <= y <= FQ_STREAM_Y2:
        if 1 <= x <= FQ_WIDTH - 2:
            return "fq_stream"
        return "fq_wall"

    # ── Post-stream corridor (y 31-40) ────────────────────────────────────
    if FQ_STREAM_Y2 < y <= 40:
        if FQ_POST_STREAM_X0 <= x <= FQ_POST_STREAM_X1:
            return "fq_floor"
        return "fq_wall"

    # ── Shop section (y 41-53): narrow corridor + separate side room ─────────
    if FQ_SHOP_Y0 <= y <= FQ_SHOP_Y1:
        # Narrow 3-wide corridor (always open, connects approach above/below)
        if 9 <= x <= 11:
            return "fq_floor"
        # 1-wide opening through the 2-wide wall (x=7-8) at the shopkeeper row
        if y == FQ_SHOP_OPENING_Y and 7 <= x <= 8:
            return "fq_floor"
        # Left side room (x=3-6, separated from corridor by the 2-wide wall)
        if 3 <= x <= 6 and FQ_SHOP_ROOM_Y0 <= y <= FQ_SHOP_ROOM_Y1:
            if x == FQ_SHOPKEEPER_X and y == FQ_SHOPKEEPER_Y:
                return "fq_shopkeeper"
            return "fq_floor"
        return "fq_wall"

    # ── Boss approach (y 54-57): funnel narrows to single-tile entrance ───
    if FQ_BOSS_APPROACH_Y0 <= y <= FQ_BOSS_APPROACH_Y1:
        step     = y - FQ_BOSS_APPROACH_Y0          # 0 → 3
        half_w   = (2, 1, 1, 0)[step]               # widths: 5, 3, 3, 1
        if abs(x - FQ_BOSS_CHAMBER_CX) <= half_w:
            return "fq_floor"
        return "fq_wall"

    # ── Boss chamber (y 58-68): circular arena, radius 5 ─────────────────
    if FQ_BOSS_CHAMBER_Y0 <= y <= FQ_BOSS_CHAMBER_Y1:
        dist_sq = (x - FQ_BOSS_CHAMBER_CX) ** 2 + (y - FQ_BOSS_CHAMBER_CY) ** 2
        if dist_sq <= FQ_BOSS_CHAMBER_R ** 2:
            # Warden body region
            if FQ_WARDEN_X0 <= x <= FQ_WARDEN_X1 and FQ_WARDEN_Y0 <= y <= FQ_WARDEN_Y1:
                if (x, y) == FQ_WARDEN_EYE_NW:
                    return "fq_warden_eye_nw"
                if (x, y) == FQ_WARDEN_EYE_NE:
                    return "fq_warden_eye_ne"
                if (x, y) == FQ_WARDEN_EYE_SW:
                    return "fq_warden_eye_sw"
                if (x, y) == FQ_WARDEN_EYE_SE:
                    return "fq_warden_eye_se"
                return "fq_warden_body"
            # Boss door at southernmost circle point
            if x == FQ_BOSS_DOOR_X and y == FQ_BOSS_DOOR_Y:
                return "fq_boss_door"
            return "fq_floor"
        return "fq_wall"

    # ── Post-boss corridor (y 69-87) ──────────────────────────────────────
    if FQ_POST_BOSS_Y0 <= y <= FQ_POST_BOSS_Y1:
        if 7 <= x <= 13:
            return "fq_floor"
        return "fq_wall"

    # ── Y-fork gauntlet (y 88-108) ────────────────────────────────────────
    if FQ_FORK_Y0 <= y <= FQ_FORK_Y1:
        if y < FQ_FORK_LOBBY_Y:
            # Approach corridor (x=7-13)
            if 7 <= x <= 13:
                return "fq_floor"
            return "fq_wall"
        if y == FQ_FORK_LOBBY_Y:
            # Wide lobby — all of x=2-18 open so all branches are visible
            if 2 <= x <= 18:
                return "fq_floor"
            return "fq_wall"
        if FQ_FORK_BRANCH_Y0 <= y <= FQ_FORK_BRANCH_Y1:
            # Three distinct branches separated by single-tile dividers
            if x == FQ_FORK_LEFT_WALL_X or x == FQ_FORK_RIGHT_WALL_X:
                return "fq_wall"
            if 2 <= x <= 5:   # left branch
                if (x, y) == FQ_FORK_CHEST_L:
                    return "fq_fork_chest"
                return "fq_floor"
            if 7 <= x <= 13:  # centre branch (continues straight through)
                return "fq_floor"
            if 15 <= x <= 18: # right branch
                if (x, y) == FQ_FORK_CHEST_R:
                    return "fq_fork_chest"
                return "fq_floor"
            return "fq_wall"
        # y > FQ_FORK_BRANCH_Y1: centre corridor resumes (x=7-13)
        if 7 <= x <= 13:
            return "fq_floor"
        return "fq_wall"

    # ── Canal puzzle (y 109-152) ──────────────────────────────────────────
    if FQ_CANAL_Y0 <= y <= FQ_CANAL_Y1:
        if y < FQ_CANAL_ROOM_Y0:
            # Approach corridor (x=7-13)
            if 7 <= x <= 13:
                return "fq_floor"
            return "fq_wall"
        if FQ_CANAL_ROOM_Y0 <= y <= FQ_CANAL_ROOM_Y1:
            # Wide puzzle room (x=2-18 open interior)
            if 2 <= x <= 18:
                if x == FQ_CANAL_RESET_X and y == FQ_CANAL_RESET_Y:
                    return "fq_canal_reset"
                if (x, y) == FQ_CANAL_TARGET_A or (x, y) == FQ_CANAL_TARGET_B:
                    return "fq_canal_target"
                return "fq_canal_floor"
            return "fq_wall"
        if y == FQ_CANAL_GATE_Y:
            # Single-tile chokepoint row — only x=10 passable (as the gate)
            if x == FQ_CANAL_GATE_X:
                return "fq_canal_gate"
            return "fq_wall"
        # y > FQ_CANAL_GATE_Y: exit corridor (x=7-13)
        if 7 <= x <= 13:
            return "fq_canal_floor"
        return "fq_wall"

    # ── Final room (y 153-180) ────────────────────────────────────────────
    if FQ_FINAL_Y0 <= y <= FQ_FINAL_Y1:
        if y < FQ_FINAL_ROOM_Y0:
            # Transition corridor (x=7-13)
            if 7 <= x <= 13:
                return "fq_canal_floor"
            return "fq_wall"
        # Wide final room (x=1-19)
        if 1 <= x <= FQ_WIDTH - 2:
            if x == FQ_ANCIENT_TREE_X and y == FQ_ANCIENT_TREE_Y:
                return "fq_ancient_tree"
            if x == FQ_ANCIENT_TREE_CHEST_X and y == FQ_ANCIENT_TREE_CHEST_Y:
                return "fq_ancient_chest"
            if x == FQ_FINAL_EXIT_X and y == FQ_FINAL_EXIT_Y:
                return "fq_exit"
            return "fq_floor"
        return "fq_wall"

    # Everything else: wall
    return "fq_wall"


# ── Viewport loading ──────────────────────────────────────────────────────────

async def load_fq_viewport(
    fq_id: int,
    player_x: int,
    player_y: int,
    db,
    boss_state: dict | None = None,
    aim_cursor: tuple[int, int] | None = None,
) -> list[list[TileData]]:
    """
    Return a 9×9 TileData grid centred on (player_x, player_y).

    boss_state (optional) dict keys:
      "eyes"     : str e.g. "1011" (NW|NE|SE|SW alive mask)
      "warn_eye" : str|None  e.g. "NW" — the eye currently in warning phase
      "open_eye" : str|None  e.g. "NW" — the eye currently open/attacking

    aim_cursor (optional): (cx, cy) zone position for the slingshot aim overlay.
    """
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

    # Overlay alive ent positions (regular = disguised wall; ancient = darker tree)
    ent_rows = await db.fetch_all(
        "SELECT local_x, local_y, ent_type FROM fq_ents WHERE fq_id=? AND alive=1", (fq_id,)
    )
    ent_positions: dict[tuple[int, int], str] = {
        (r["local_x"], r["local_y"]): r["ent_type"] for r in ent_rows
    }

    grid: list[list[TileData]] = []
    for gy in range(VIEWPORT_SIZE):
        row: list[TileData] = []
        for gx in range(VIEWPORT_SIZE):
            wx = x_min + gx
            wy = y_min + gy
            t = tile_map.get((wx, wy), "fq_wall")

            # Log / ent overlays
            if (wx, wy) in log_positions:
                t = "fq_log"
            elif (wx, wy) in ent_positions:
                # Regular ents disguised as trees; ancient ents look slightly different
                t = "fq_ancient_ent" if ent_positions[(wx, wy)] == "ancient" else "fq_wall"

            # Boss-state eye overlays
            elif boss_state and (wx, wy) in FQ_WARDEN_EYE_BY_POS:
                eye_name = FQ_WARDEN_EYE_BY_POS[(wx, wy)]
                eye_idx  = FQ_WARDEN_EYE_CYCLE.index(eye_name)
                eyes_mask = boss_state.get("eyes", "1111")
                if eye_idx < len(eyes_mask) and eyes_mask[eye_idx] == "0":
                    t = "fq_warden_dead"
                elif eye_name == boss_state.get("warn_eye"):
                    t = "fq_warden_eye_warn"
                elif eye_name == boss_state.get("open_eye"):
                    t = "fq_warden_eye_open"
                # else: keep the stored tile type (closed eye)

            # Aim cursor overlay (drawn on top of everything)
            if aim_cursor and (wx, wy) == aim_cursor:
                t = "fq_aim_cursor"

            row.append(TileData(terrain=t, structure=None))
        grid.append(row)
    return grid


async def load_fq_single_tile(fq_id: int, x: int, y: int, db) -> TileData:
    """Load a single tile with log/ent overlays applied."""
    lrow = await db.fetch_one(
        "SELECT 1 FROM fq_puzzle_logs WHERE fq_id=? AND cur_x=? AND cur_y=?",
        (fq_id, x, y),
    )
    if lrow:
        return TileData(terrain="fq_log", structure=None)

    erow = await db.fetch_one(
        "SELECT 1 FROM fq_ents WHERE fq_id=? AND local_x=? AND local_y=? AND alive=1",
        (fq_id, x, y),
    )
    if erow:
        return TileData(terrain="fq_wall", structure=None)

    row = await db.fetch_one(
        "SELECT tile_type FROM forest_quest_tiles WHERE fq_id=? AND local_x=? AND local_y=?",
        (fq_id, x, y),
    )
    t = row["tile_type"] if row else "fq_wall"
    return TileData(terrain=t, structure=None)


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
    """Return Sokoban logs (indices 0, 1) to their starting positions.

    Also resets any fq_stream_ford tiles in the stream rows back to fq_stream
    and clears the solved flag so the puzzle can be attempted again.
    """
    await db.execute(
        "UPDATE fq_puzzle_logs SET cur_x=start_x, cur_y=start_y "
        "WHERE fq_id=? AND log_idx IN (0, 1)",
        (fq_id,),
    )
    # Revert any ford tiles created by pushing logs into the stream
    await db.execute(
        "UPDATE forest_quest_tiles SET tile_type='fq_stream' "
        "WHERE fq_id=? AND tile_type='fq_stream_ford' AND local_y IN (?, ?)",
        (fq_id, FQ_STREAM_Y, FQ_STREAM_Y2),
    )
    # Re-open the solved flag so the bridge can be rebuilt
    await db.execute(
        "UPDATE forest_quest_areas SET solved=0 WHERE fq_id=?", (fq_id,)
    )
    await db.commit()


async def check_and_solve_puzzle(db, fq_id: int) -> bool:
    """Bridge is complete when one Sokoban log is in each stream row. Return True if solved."""
    # Already solved?
    row = await db.fetch_one(
        "SELECT solved FROM forest_quest_areas WHERE fq_id=?", (fq_id,)
    )
    if row and row["solved"]:
        return True

    logs = await db.fetch_all(
        "SELECT cur_y FROM fq_puzzle_logs WHERE fq_id=? AND log_idx IN (0, 1)", (fq_id,)
    )
    y_positions = {r["cur_y"] for r in logs}
    if FQ_STREAM_Y in y_positions and FQ_STREAM_Y2 in y_positions:
        await db.execute(
            "UPDATE forest_quest_areas SET solved=1 WHERE fq_id=?", (fq_id,)
        )
        await db.commit()
        return True
    return False


# ── Ent movement ──────────────────────────────────────────────────────────────

async def reset_ent_positions(db, fq_id: int) -> None:
    """Reset all alive regular ents to their spawn positions.

    Called every time a player enters (or re-enters) the FQ zone so that ents
    which drifted toward the entry point during a previous session cannot
    trigger instant combat on arrival.
    """
    ents = await db.fetch_all(
        "SELECT id FROM fq_ents WHERE fq_id=? AND ent_type='regular' AND alive=1 ORDER BY id",
        (fq_id,),
    )
    for i, ent in enumerate(ents):
        if i < len(FQ_ENT_STARTS):
            sx, sy = FQ_ENT_STARTS[i]
            await db.execute(
                "UPDATE fq_ents SET local_x=?, local_y=? WHERE id=?",
                (sx, sy, ent["id"]),
            )
    await db.commit()


async def step_ents_toward_player(
    db, fq_id: int, player_x: int, player_y: int
) -> list[tuple[int, int]]:
    """
    Move each alive *regular* ent one step closer to the player (Manhattan, no diagonal).
    Ents are blocked by walls, obstacles, other ents, and cannot enter the chamber.
    Returns a list of (x, y) positions where an ent reached the player's tile.
    """
    ents = await db.fetch_all(
        "SELECT id, local_x, local_y FROM fq_ents WHERE fq_id=? AND alive=1 AND ent_type='regular'",
        (fq_id,),
    )
    ent_pos_set: set[tuple[int, int]] = {(e["local_x"], e["local_y"]) for e in ents}
    combat_triggers: list[tuple[int, int]] = []

    for ent in ents:
        eid, ex, ey = ent["id"], ent["local_x"], ent["local_y"]

        if ey >= FQ_CHAMBER_Y0:
            continue

        dx = player_x - ex
        dy = player_y - ey

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

        for sdx, sdy in candidates:
            nx, ny = ex + sdx, ey + sdy
            if ny >= FQ_CHAMBER_Y0:
                continue
            if (nx, ny) in ent_pos_set:
                continue
            tile = await load_fq_single_tile(fq_id, nx, ny, db)
            if tile.terrain in _ENT_BLOCKED:
                continue
            ent_pos_set.discard((ex, ey))
            ent_pos_set.add((nx, ny))
            await db.execute(
                "UPDATE fq_ents SET local_x=?, local_y=? WHERE id=?",
                (nx, ny, eid),
            )
            ex, ey = nx, ny
            break

        if ex == player_x and ey == player_y:
            combat_triggers.append((ex, ey))

    await db.commit()
    return combat_triggers


# ── Canal puzzle helpers ──────────────────────────────────────────────────────

async def check_and_solve_canal(db, fq_id: int) -> bool:
    """Return True if both canal logs are on their targets and open the gate."""
    # Already solved?
    row = await db.fetch_one(
        "SELECT canal_solved FROM forest_quest_areas WHERE fq_id=?", (fq_id,)
    )
    if row and row["canal_solved"]:
        return True

    logs = await db.fetch_all(
        "SELECT cur_x, cur_y FROM fq_puzzle_logs WHERE fq_id=?", (fq_id,)
    )
    positions = {(r["cur_x"], r["cur_y"]) for r in logs}
    if FQ_CANAL_TARGET_A not in positions or FQ_CANAL_TARGET_B not in positions:
        return False

    # Open the gate
    await db.execute(
        "UPDATE forest_quest_tiles SET tile_type='fq_canal_gate_open' "
        "WHERE fq_id=? AND local_x=? AND local_y=?",
        (fq_id, FQ_CANAL_GATE_X, FQ_CANAL_GATE_Y),
    )
    await db.execute(
        "UPDATE forest_quest_areas SET canal_solved=1 WHERE fq_id=?", (fq_id,)
    )
    await db.commit()
    return True


async def reset_canal_logs(db, fq_id: int) -> None:
    """Return canal logs (indices 2, 3) to starting positions and re-close the gate."""
    await db.execute(
        "UPDATE fq_puzzle_logs SET cur_x=start_x, cur_y=start_y "
        "WHERE fq_id=? AND log_idx IN (2, 3)",
        (fq_id,),
    )
    # Re-close the gate tile if it was opened
    await db.execute(
        "UPDATE forest_quest_tiles SET tile_type='fq_canal_gate' "
        "WHERE fq_id=? AND local_x=? AND local_y=? AND tile_type='fq_canal_gate_open'",
        (fq_id, FQ_CANAL_GATE_X, FQ_CANAL_GATE_Y),
    )
    await db.execute(
        "UPDATE forest_quest_areas SET canal_solved=0 WHERE fq_id=?", (fq_id,)
    )
    await db.commit()


# ── Ancient ent helpers ───────────────────────────────────────────────────────

async def step_ancient_ents(
    db, fq_id: int, player_x: int, player_y: int
) -> list[tuple[int, int]]:
    """
    Move each alive ancient ent one step closer to the player (Manhattan, no diagonal).
    Ancient ents roam only within y >= FQ_FINAL_ROOM_Y0.
    Returns a list of (x, y) positions where an ent reached the player's tile.
    """
    ents = await db.fetch_all(
        "SELECT id, local_x, local_y FROM fq_ents "
        "WHERE fq_id=? AND alive=1 AND ent_type='ancient'",
        (fq_id,),
    )
    ent_pos_set: set[tuple[int, int]] = {(e["local_x"], e["local_y"]) for e in ents}
    combat_triggers: list[tuple[int, int]] = []

    for ent in ents:
        eid, ex, ey = ent["id"], ent["local_x"], ent["local_y"]

        dx = player_x - ex
        dy = player_y - ey

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

        for sdx, sdy in candidates:
            nx, ny = ex + sdx, ey + sdy
            # Keep ancient ents within the final room
            if ny < FQ_FINAL_ROOM_Y0:
                continue
            if (nx, ny) in ent_pos_set:
                continue
            tile = await load_fq_single_tile(fq_id, nx, ny, db)
            if tile.terrain in _ENT_BLOCKED:
                continue
            ent_pos_set.discard((ex, ey))
            ent_pos_set.add((nx, ny))
            await db.execute(
                "UPDATE fq_ents SET local_x=?, local_y=? WHERE id=?",
                (nx, ny, eid),
            )
            ex, ey = nx, ny
            break

        if ex == player_x and ey == player_y:
            combat_triggers.append((ex, ey))

    await db.commit()
    return combat_triggers
