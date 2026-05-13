"""Sky temple system — interior generation, gear puzzle, portal management."""
from __future__ import annotations
from typing import NamedTuple

from dwarf_explorer.world.generator import TileData
from dwarf_explorer.config import VIEWPORT_SIZE, VIEWPORT_CENTER

TEMPLE_SIZE = 11
TEMPLE_ENTRY_X = 5
TEMPLE_ENTRY_Y = 8   # player spawns one tile inside the entrance

# All gear-slot tile-type names (used by game_view to detect interact targets)
GEAR_SLOT_TERRAIN: frozenset[str] = frozenset({
    "gear_slot_s_empty", "gear_slot_l_empty",
    "gear_slot_s_cw", "gear_slot_s_ccw",
    "gear_slot_l_cw_tl",  "gear_slot_l_cw_tr",  "gear_slot_l_cw_bl",  "gear_slot_l_cw_br",
    "gear_slot_l_ccw_tl", "gear_slot_l_ccw_tr", "gear_slot_l_ccw_bl", "gear_slot_l_ccw_br",
})

OUTER_ALTAR_POS    = (5, 5)
OUTER_ENTRANCE_POS = (5, 9)

MAIN_PORTAL_POS       = (5, 5)
MAIN_RUNE_POSITIONS   = [(5, 4), (4, 5), (6, 5), (5, 6)]
MAIN_PILLAR_POSITIONS = [(2, 2), (8, 2), (2, 8), (8, 8)]
MAIN_ENTRANCE_POS     = (5, 9)

# Quadrant offsets for a 2×2 large gear: (dx, dy) → quadrant name
_LARGE_GEAR_QUADS = {(0, 0): "tl", (1, 0): "tr", (0, 1): "bl", (1, 1): "br"}

# ── Machine viewport layout system ────────────────────────────────────────────
# The gear machine opens as a 9×9 viewport (no border — all floor).
# Each outer temple picks one of several pre-verified layout templates based
# on (temple_id % len(MACHINE_LAYOUTS)).  Layouts vary in the direction power
# flows (left, right, top, bottom, diagonal) and path shape.
#
# Direction rule (universal): Power = CW → Slot0 = CCW → Slot1 = CW →
#   Slot2 = CCW → Slot3 = CW → Target = CCW.  Formula: is_cw = (slot_idx % 2 == 1)
#
# Partial-gear edge cuts: power/target tiles may be a subset of a 2×2 gear when
# the anchor is off-screen.  power_tiles and target_tiles each map (x,y)→quad_name
# for the visible portion; the rest is implied to be off-grid.
MACHINE_SIZE   = 9
MACHINE_CENTER = 4   # kept for API compatibility


class MachineLayout(NamedTuple):
    """Describes the visual layout of one gear machine puzzle.

    power_tiles : visible tiles of the fixed CW power-source gear  {(x,y): quad}
    slots       : player gear slots in chain order [(ax, ay, gear_type), ...]
                  slot 0 = power-adjacent (pre-filled, spins at once)
                  slot N = target-adjacent (pre-filled, still until bridged)
    target_tiles: visible tiles of the fixed CCW target gear        {(x,y): quad}
    prefilled   : slot indices that start pre-installed             frozenset[int]
    """
    power_tiles:  dict[tuple[int, int], str]
    slots:        list[tuple[int, int, str]]
    target_tiles: dict[tuple[int, int], str]
    prefilled:    frozenset[int]


# ── Six edge-to-opposite-edge layouts ─────────────────────────────────────────
# Every layout starts at one board edge and terminates at the OPPOSITE edge.
# Each path changes direction at least 3 times so it meanders visibly.
# 6 player slots each (mix of small 1×1 and large 2×2).
# prefilled = {0, 5}: slot 0 (power-adjacent, spins immediately) and
#                      slot 5 (target-adjacent, still until player bridges gap).
#
# Adjacency verification key:
#   S(x,y)        = small gear at (x,y)
#   L(ax,ay)→{tiles} = large gear anchored (ax,ay), occupying (ax,ay),(ax+1,ay),(ax,ay+1),(ax+1,ay+1)
#   "adj" = shares a non-diagonal edge

# ── L0: LEFT edge → RIGHT edge ──────────────────────────────────────────────
# power(0,4)tr,(0,5)br  → S(1,4) ↑ L(1,2) → L(3,1) → S(5,2) → L(6,2) ↓ S(7,4) → target(8,3-4)
# Directions: R → UP → R → R → R → DOWN → R  (4 bends)
# Adjacency: power(0,4)→S(1,4)  S(1,4)→L(1,3)  L(2,2)→L(3,2)  L(4,2)→S(5,2)
#            S(5,2)→L(6,2)  L(7,3)→S(7,4)  S(7,4)→target(8,4)
_L0 = MachineLayout(
    power_tiles  = {(0, 4): "tr", (0, 5): "br"},        # left edge — right half of off-screen gear
    slots = [
        (1, 4, "small_gear"),    # S0 — adj to power(0,4) right
        (1, 2, "large_gear"),    # L1 — adj to S0(1,4) via up to (1,3)
        (3, 1, "large_gear"),    # L2 — adj to L1(2,2) right to (3,2)
        (5, 2, "small_gear"),    # S3 — adj to L2(4,2) right
        (6, 2, "large_gear"),    # L4 — adj to S3(5,2) right to (6,2)
        (7, 4, "small_gear"),    # S5 — adj to L4(7,3) down; touches target
    ],
    target_tiles = {(8, 3): "tl", (8, 4): "bl"},        # right edge — left half of off-screen gear
    prefilled    = frozenset({0, 5}),
)

# ── L1: RIGHT edge → LEFT edge ──────────────────────────────────────────────
# power(8,4)tl,(8,5)bl  → S(7,5) ← L(5,4) ↑ S(5,3) ← L(3,2) ↓ L(2,4) ← S(1,4) → target(0,3-4)
# Directions: L → L → UP → L → DOWN → L → L  (4 bends)
# Adjacency: power(8,5)→S(7,5)  S(7,5)→L(6,5)  L(5,4)→S(5,3) up  S(5,3)→L(4,3) left
#            L(3,3)→L(3,4) down  L(2,4)→S(1,4)  S(1,4)→target(0,4)
_L1 = MachineLayout(
    power_tiles  = {(8, 4): "tl", (8, 5): "bl"},        # right edge — left half
    slots = [
        (7, 5, "small_gear"),    # S0 — adj to power(8,5) left
        (5, 4, "large_gear"),    # L1 — adj to S0(7,5) via left to (6,5)
        (5, 3, "small_gear"),    # S2 — adj to L1(5,4) up
        (3, 2, "large_gear"),    # L3 — adj to S2(5,3) via left to (4,3)
        (2, 4, "large_gear"),    # L4 — adj to L3(3,3) down to (3,4)
        (1, 4, "small_gear"),    # S5 — adj to L4(2,4) left; touches target
    ],
    target_tiles = {(0, 3): "tr", (0, 4): "br"},        # left edge — right half
    prefilled    = frozenset({0, 5}),
)

# ── L2: TOP edge → BOTTOM edge ──────────────────────────────────────────────
# power(3,0)bl,(4,0)br  → S(4,1) ↓ L(4,2) → S(6,3) ↓ L(6,4) ← S(5,5) ↓ L(4,6) → target(4-5,8)
# Directions: D → D → R → D → L → D → D  (4 bends)
# Adjacency: power(4,0)→S(4,1)  S(4,1)→L(4,2) down  L(5,3)→S(6,3) right
#            S(6,3)→L(6,4) down  L(6,5)→S(5,5) left  S(5,5)→L(5,6) down  L(4,7)→target(4,8)
_L2 = MachineLayout(
    power_tiles  = {(3, 0): "bl", (4, 0): "br"},        # top edge — bottom half
    slots = [
        (4, 1, "small_gear"),    # S0 — adj to power(4,0) down
        (4, 2, "large_gear"),    # L1 — adj to S0(4,1) down to (4,2)
        (6, 3, "small_gear"),    # S2 — adj to L1(5,3) right
        (6, 4, "large_gear"),    # L3 — adj to S2(6,3) down to (6,4)
        (5, 5, "small_gear"),    # S4 — adj to L3(6,5) left
        (4, 6, "large_gear"),    # L5 — adj to S4(5,5) down to (5,6); (4,7)→target
    ],
    target_tiles = {(4, 8): "tl", (5, 8): "tr"},        # bottom edge — top half
    prefilled    = frozenset({0, 5}),
)

# ── L3: BOTTOM edge → TOP edge ──────────────────────────────────────────────
# power(4,8)tl,(5,8)tr  → S(4,7) ↑ L(4,5) ← S(3,5) ↑ L(2,3) → S(4,3) ↑ L(4,1) → target(3-4,0)
# Directions: U → U → L → U → R → U → U  (4 bends)
# Adjacency: power(4,8)→S(4,7)  S(4,7)→L(4,6) up  L(4,5)→S(3,5) left
#            S(3,5)→L(3,4) up  L(3,3)→S(4,3) right  S(4,3)→L(4,2) up  L(4,1)→target(4,0)
_L3 = MachineLayout(
    power_tiles  = {(4, 8): "tl", (5, 8): "tr"},        # bottom edge — top half
    slots = [
        (4, 7, "small_gear"),    # S0 — adj to power(4,8) up
        (4, 5, "large_gear"),    # L1 — adj to S0(4,7) via up to (4,6)
        (3, 5, "small_gear"),    # S2 — adj to L1(4,5) left
        (2, 3, "large_gear"),    # L3 — adj to S2(3,5) via up to (3,4)
        (4, 3, "small_gear"),    # S4 — adj to L3(3,3) right
        (4, 1, "large_gear"),    # L5 — adj to S4(4,3) via up to (4,2); (4,1)→target(4,0)
    ],
    target_tiles = {(3, 0): "bl", (4, 0): "br"},        # top edge — bottom half
    prefilled    = frozenset({0, 5}),
)

# ── L4: TOP-RIGHT → BOTTOM-LEFT ─────────────────────────────────────────────
# power(6,0)bl,(7,0)br  → S(6,1) ← L(4,1) ↓ L(4,3) ← S(3,4) ↓ L(2,5) ↓ S(2,7) → target(1-2,8)
# Directions: D → L → D → L → D → D → D  (3 bends)
# Adjacency: power(6,0)→S(6,1)  S(6,1)→L(5,1) left  L(4,2)→L(4,3) down
#            L(4,4)→S(3,4) left  S(3,4)→L(3,5) down  L(2,6)→S(2,7)  S(2,7)→target(2,8)
_L4 = MachineLayout(
    power_tiles  = {(6, 0): "bl", (7, 0): "br"},        # top edge right side
    slots = [
        (6, 1, "small_gear"),    # S0 — adj to power(6,0) down
        (4, 1, "large_gear"),    # L1 — adj to S0(6,1) via left to (5,1)
        (4, 3, "large_gear"),    # L2 — adj to L1(4,2) down to (4,3)
        (3, 4, "small_gear"),    # S3 — adj to L2(4,4) left
        (2, 5, "large_gear"),    # L4 — adj to S3(3,4) down to (3,5)
        (2, 7, "small_gear"),    # S5 — adj to L4(2,6) down; touches target
    ],
    target_tiles = {(1, 8): "tl", (2, 8): "tr"},        # bottom edge left side
    prefilled    = frozenset({0, 5}),
)

# ── L5: TOP-LEFT → BOTTOM-RIGHT ─────────────────────────────────────────────
# power(1,0)bl,(2,0)br  → S(2,1) → L(3,1) ↓ L(4,3) → S(6,4) ↓ L(6,5) ↓ S(7,7) → target(6-7,8)
# Directions: D → R → D → R → D → D → D  (3 bends)
# Adjacency: power(2,0)→S(2,1)  S(2,1)→L(3,1) right  L(4,2)→L(4,3) down
#            L(5,4)→S(6,4) right  S(6,4)→L(6,5) down  L(7,6)→S(7,7)  S(7,7)→target(7,8)
_L5 = MachineLayout(
    power_tiles  = {(1, 0): "bl", (2, 0): "br"},        # top edge left side
    slots = [
        (2, 1, "small_gear"),    # S0 — adj to power(2,0) down
        (3, 1, "large_gear"),    # L1 — adj to S0(2,1) right to (3,1)
        (4, 3, "large_gear"),    # L2 — adj to L1(4,2) down to (4,3)
        (6, 4, "small_gear"),    # S3 — adj to L2(5,4) right
        (6, 5, "large_gear"),    # L4 — adj to S3(6,4) down to (6,5)
        (7, 7, "small_gear"),    # S5 — adj to L4(7,6) down; touches target
    ],
    target_tiles = {(6, 8): "tl", (7, 8): "tr"},        # bottom edge right side
    prefilled    = frozenset({0, 5}),
)

MACHINE_LAYOUTS: list[MachineLayout] = [_L0, _L1, _L2, _L3, _L4, _L5]


def get_machine_layout(temple_id: int) -> MachineLayout:
    """Return the layout template for a given outer temple."""
    return MACHINE_LAYOUTS[temple_id % len(MACHINE_LAYOUTS)]


def get_layout_gear_slots(temple_id: int) -> list[tuple[int, int, str]]:
    """Return [(ax, ay, gear_type), ...] in chain order for the given temple's layout.

    Use this instead of the old OUTER_GEAR_SLOTS constant — slot count and
    positions vary per layout.
    """
    return list(get_machine_layout(temple_id).slots)


def _large_gear_tiles(ax: int, ay: int) -> list[tuple[int, int, str]]:
    """Return [(x, y, quad), ...] for all 4 tiles of a large gear anchored at (ax, ay)."""
    return [(ax + dx, ay + dy, q) for (dx, dy), q in _LARGE_GEAR_QUADS.items()]


def _slot_tile_positions(required: str, ax: int, ay: int) -> set[tuple[int, int]]:
    """Return all in-bounds machine-grid positions occupied by this slot."""
    if required == "large_gear":
        return {
            (ax + dx, ay + dy)
            for dx in range(2) for dy in range(2)
            if 0 <= ax + dx < MACHINE_SIZE and 0 <= ay + dy < MACHINE_SIZE
        }
    return {(ax, ay)} if 0 <= ax < MACHINE_SIZE and 0 <= ay < MACHINE_SIZE else set()


def _compute_powered_slots(
    slot_states: list[tuple[str, bool]],
    layout: MachineLayout,
) -> tuple[set[int], dict[int, set[tuple[int, int]]]]:
    """BFS from the fixed power source tiles.

    Returns (powered_slot_indices, slot_tile_map).
    Only *filled* slots propagate power.
    """
    tile_to_slot: dict[tuple[int, int], int] = {}
    slot_tile_map: dict[int, set[tuple[int, int]]] = {}
    for slot_idx, (ax, ay, required) in enumerate(layout.slots):
        _, is_filled = slot_states[slot_idx]
        if not is_filled:
            continue
        tset = _slot_tile_positions(required, ax, ay)
        slot_tile_map[slot_idx] = tset
        for pos in tset:
            tile_to_slot[pos] = slot_idx

    # Seed: filled slots directly adjacent to any power tile
    visited: set[int] = set()
    queue:   list[int] = []
    for px, py in layout.power_tiles:
        for nx, ny in ((px - 1, py), (px + 1, py), (px, py - 1), (px, py + 1)):
            if (nx, ny) in tile_to_slot:
                sidx = tile_to_slot[(nx, ny)]
                if sidx not in visited:
                    visited.add(sidx)
                    queue.append(sidx)

    # BFS: spread through touching filled slots
    while queue:
        sidx = queue.pop(0)
        for tx, ty in slot_tile_map.get(sidx, set()):
            for nx, ny in ((tx - 1, ty), (tx + 1, ty), (tx, ty - 1), (tx, ty + 1)):
                if (nx, ny) in tile_to_slot:
                    nidx = tile_to_slot[(nx, ny)]
                    if nidx not in visited:
                        visited.add(nidx)
                        queue.append(nidx)

    return visited, slot_tile_map


def build_machine_grid(
    slot_states: list[tuple[str, bool]],
    temple_id: int = 0,
) -> list[list["TileData"]]:
    """Build the 9×9 TileData grid for the gear machine viewport.

    Picks a layout template from MACHINE_LAYOUTS based on temple_id.
    All floor — no border.  Only gears connected to the power source spin;
    isolated filled gears show their still variant.
    """
    layout = get_machine_layout(temple_id)

    # All floor — no border
    tiles: dict[tuple[int, int], str] = {
        (x, y): "temple_floor"
        for y in range(MACHINE_SIZE)
        for x in range(MACHINE_SIZE)
    }

    # ── Fixed power source (always CW) ───────────────────────────────────────
    for (px, py), quad in layout.power_tiles.items():
        tiles[(px, py)] = f"gear_slot_l_cw_{quad}"

    # ── Compute powered connectivity ──────────────────────────────────────────
    powered_indices, slot_tile_map = _compute_powered_slots(slot_states, layout)

    # ── Player slots ──────────────────────────────────────────────────────────
    # Direction: Power=CW → slot0=CCW → slot1=CW → slot2=CCW → …
    for slot_idx, (ax, ay, required) in enumerate(layout.slots):
        _, is_filled = slot_states[slot_idx]
        is_large  = (required == "large_gear")
        is_cw     = (slot_idx % 2 == 1)   # 0=CCW, 1=CW, 2=CCW, 3=CW
        dir_s     = "cw" if is_cw else "ccw"
        powered   = slot_idx in powered_indices

        if is_large:
            for gx, gy, quad in _large_gear_tiles(ax, ay):
                if 0 <= gx < MACHINE_SIZE and 0 <= gy < MACHINE_SIZE:
                    if is_filled:
                        t = f"gear_slot_l_{dir_s}_{quad}" if powered else f"gear_slot_l_still_{quad}"
                    else:
                        t = "gear_slot_l_empty"
                    tiles[(gx, gy)] = t
        else:
            if 0 <= ax < MACHINE_SIZE and 0 <= ay < MACHINE_SIZE:
                if is_filled:
                    tiles[(ax, ay)] = f"gear_slot_s_{dir_s}" if powered else "gear_slot_s_still"
                else:
                    tiles[(ax, ay)] = "gear_slot_s_empty"

    # ── Fixed target gear (CCW; spins when a powered slot is adjacent) ────────
    target_tile_set = set(layout.target_tiles.keys())
    target_powered = False
    for sidx, stiles in slot_tile_map.items():
        if sidx not in powered_indices:
            continue
        for tx, ty in stiles:
            for nx, ny in ((tx - 1, ty), (tx + 1, ty), (tx, ty - 1), (tx, ty + 1)):
                if (nx, ny) in target_tile_set:
                    target_powered = True
                    break
        if target_powered:
            break
    for (tx, ty), quad in layout.target_tiles.items():
        t = f"gear_slot_l_ccw_{quad}" if target_powered else f"gear_slot_l_still_{quad}"
        tiles[(tx, ty)] = t

    # ── Assemble TileData grid ────────────────────────────────────────────────
    grid: list[list[TileData]] = []
    for y in range(MACHINE_SIZE):
        row: list[TileData] = []
        for x in range(MACHINE_SIZE):
            row.append(TileData(terrain=tiles.get((x, y), "temple_floor"), world_x=x, world_y=y))
        grid.append(row)
    return grid


GEAR_MACHINE_POS = (5, 1)   # centre of north interior row — the interactable machine panel

def _make_outer_temple_tiles() -> list[tuple[int, int, str]]:
    """Generate the static tile layout for an outer (puzzle) temple."""
    tiles: dict[tuple[int, int], str] = {}
    for y in range(TEMPLE_SIZE):
        for x in range(TEMPLE_SIZE):
            if x == 0 or x == TEMPLE_SIZE - 1 or y == 0 or y == TEMPLE_SIZE - 1:
                tiles[(x, y)] = "temple_wall"
            else:
                tiles[(x, y)] = "temple_floor"

    # Entrance (south wall opening)
    ex, ey = OUTER_ENTRANCE_POS
    tiles[(ex, ey)] = "temple_entrance"

    # Gear machine panel on the north interior wall (walkable — opens machine UI)
    mx, my = GEAR_MACHINE_POS
    tiles[(mx, my)] = "gear_machine"

    # Altar centre
    ax, ay = OUTER_ALTAR_POS
    tiles[(ax, ay)] = "temple_altar"

    # Rune stones flanking the altar
    tiles[(ax - 2, ay)] = "temple_rune"
    tiles[(ax + 2, ay)] = "temple_rune"

    return [(x, y, t) for (x, y), t in tiles.items()]


def _make_main_temple_tiles() -> list[tuple[int, int, str]]:
    """Generate the static tile layout for the main (portal) temple."""
    tiles: dict[tuple[int, int], str] = {}
    for y in range(TEMPLE_SIZE):
        for x in range(TEMPLE_SIZE):
            if x == 0 or x == TEMPLE_SIZE - 1 or y == 0 or y == TEMPLE_SIZE - 1:
                tiles[(x, y)] = "temple_wall"
            else:
                tiles[(x, y)] = "temple_floor"
    ex, ey = MAIN_ENTRANCE_POS
    tiles[(ex, ey)] = "temple_entrance"
    # Portal (locked by default — unlocked dynamically)
    px, py = MAIN_PORTAL_POS
    tiles[(px, py)] = "temple_portal_locked"
    # Rune stones
    for rx, ry in MAIN_RUNE_POSITIONS:
        tiles[(rx, ry)] = "temple_rune"
    # Pillars
    for ppx, ppy in MAIN_PILLAR_POSITIONS:
        tiles[(ppx, ppy)] = "temple_pillar"
    return [(x, y, t) for (x, y), t in tiles.items()]


_OLD_GEAR_SLOT_TILES = frozenset({
    "gear_slot_s_empty", "gear_slot_l_empty",
    "gear_slot_s_cw", "gear_slot_s_ccw",
    "gear_slot_l_cw_tl",  "gear_slot_l_cw_tr",  "gear_slot_l_cw_bl",  "gear_slot_l_cw_br",
    "gear_slot_l_ccw_tl", "gear_slot_l_ccw_tr", "gear_slot_l_ccw_bl", "gear_slot_l_ccw_br",
})


async def get_or_create_outer_temple(db, world_x: int, world_y: int) -> int:
    """Return temple_id for the outer temple at (world_x, world_y), creating it if needed.

    Also migrates legacy temples that still have floor gear-slot tiles by replacing
    them with the new gear_machine panel layout.
    """
    row = await db.fetch_one(
        "SELECT id FROM sky_temples WHERE world_x=? AND world_y=? AND temple_type='outer'",
        (world_x, world_y),
    )
    if row:
        temple_id = row["id"]
        # ── Migrate legacy floor gear-slot tiles ─────────────────────────────
        legacy = await db.fetch_all(
            "SELECT local_x, local_y FROM temple_tiles WHERE temple_id=? AND tile_type IN ({})".format(
                ",".join("?" * len(_OLD_GEAR_SLOT_TILES))
            ),
            (temple_id, *_OLD_GEAR_SLOT_TILES),
        )
        if legacy:
            await db.execute(
                "DELETE FROM temple_tiles WHERE temple_id=? AND tile_type IN ({})".format(
                    ",".join("?" * len(_OLD_GEAR_SLOT_TILES))
                ),
                (temple_id, *_OLD_GEAR_SLOT_TILES),
            )
            mx, my = GEAR_MACHINE_POS
            await db.execute(
                "INSERT OR REPLACE INTO temple_tiles (temple_id, local_x, local_y, tile_type) VALUES (?,?,?,'gear_machine')",
                (temple_id, mx, my),
            )
        # ── Reconcile gear slots with current layout ──────────────────────────
        layout = get_machine_layout(temple_id)
        layout_positions = {(ax, ay) for ax, ay, _ in layout.slots}
        existing = await db.fetch_all(
            "SELECT slot_x, slot_y FROM temple_gear_slots WHERE temple_id=?",
            (temple_id,),
        )
        existing_positions = {(r["slot_x"], r["slot_y"]) for r in existing}
        # Remove stale slots no longer in this layout
        for sx, sy in existing_positions - layout_positions:
            await db.execute(
                "DELETE FROM temple_gear_slots WHERE temple_id=? AND slot_x=? AND slot_y=?",
                (temple_id, sx, sy),
            )
        # Add any slots that are missing
        for i, (ax, ay, req) in enumerate(layout.slots):
            if (ax, ay) not in existing_positions:
                await db.execute(
                    "INSERT OR IGNORE INTO temple_gear_slots"
                    " (temple_id, slot_x, slot_y, required_gear, is_filled) VALUES (?,?,?,?,?)",
                    (temple_id, ax, ay, req, 1 if i in layout.prefilled else 0),
                )
        return temple_id

    cur = await db.execute(
        "INSERT INTO sky_temples (world_x, world_y, temple_type) VALUES (?, ?, 'outer')",
        (world_x, world_y),
    )
    temple_id = cur.lastrowid
    tile_list = _make_outer_temple_tiles()
    await db.executemany(
        "INSERT OR IGNORE INTO temple_tiles (temple_id, local_x, local_y, tile_type) VALUES (?,?,?,?)",
        [(temple_id, x, y, t) for x, y, t in tile_list],
    )
    # Insert gear slots from the layout chosen for this temple_id
    layout = get_machine_layout(temple_id)
    await db.executemany(
        "INSERT OR IGNORE INTO temple_gear_slots"
        " (temple_id, slot_x, slot_y, required_gear, is_filled) VALUES (?,?,?,?,?)",
        [
            (temple_id, ax, ay, req, 1 if i in layout.prefilled else 0)
            for i, (ax, ay, req) in enumerate(layout.slots)
        ],
    )
    return temple_id


async def get_or_create_main_temple(db, world_x: int, world_y: int, world_seed: int) -> tuple[int, int, int]:
    """Return (temple_id, entry_x, entry_y) for the main temple, creating if needed."""
    row = await db.fetch_one(
        "SELECT id, sky_id FROM sky_temples WHERE world_x=? AND world_y=? AND temple_type='main'",
        (world_x, world_y),
    )
    if row:
        return row["id"], TEMPLE_ENTRY_X, TEMPLE_ENTRY_Y
    cur = await db.execute(
        "INSERT INTO sky_temples (world_x, world_y, temple_type) VALUES (?, ?, 'main')",
        (world_x, world_y),
    )
    temple_id = cur.lastrowid
    tile_list = _make_main_temple_tiles()
    await db.executemany(
        "INSERT OR IGNORE INTO temple_tiles (temple_id, local_x, local_y, tile_type) VALUES (?,?,?,?)",
        [(temple_id, x, y, t) for x, y, t in tile_list],
    )
    return temple_id, TEMPLE_ENTRY_X, TEMPLE_ENTRY_Y


async def load_temple_viewport(
    temple_id: int, center_x: int, center_y: int, db, is_main: bool = False
) -> list[list[TileData]]:
    """Load a 9×9 viewport centred at (center_x, center_y) inside the temple."""
    half  = VIEWPORT_CENTER
    x_min = center_x - half
    y_min = center_y - half

    rows = await db.fetch_all(
        "SELECT local_x, local_y, tile_type FROM temple_tiles"
        " WHERE temple_id=? AND local_x>=? AND local_x<=? AND local_y>=? AND local_y<=?",
        (temple_id, x_min, center_x + half, y_min, center_y + half),
    )
    tile_map = {(r["local_x"], r["local_y"]): r["tile_type"] for r in rows}

    if is_main:
        # Main temple: overlay portal open/locked based on puzzle completion
        all_solved = await are_all_outer_temples_solved(db)
        px, py = MAIN_PORTAL_POS
        tile_map[(px, py)] = "temple_portal_open" if all_solved else "temple_portal_locked"

    grid: list[list[TileData]] = []
    for local_y in range(VIEWPORT_SIZE):
        row_tiles: list[TileData] = []
        for local_x in range(VIEWPORT_SIZE):
            cx = x_min + local_x
            cy = y_min + local_y
            row_tiles.append(TileData(
                terrain=tile_map.get((cx, cy), "temple_wall"),
                world_x=cx, world_y=cy,
            ))
        grid.append(row_tiles)
    return grid


async def load_temple_single_tile(
    temple_id: int, local_x: int, local_y: int, db, is_main: bool = False
) -> TileData:
    row = await db.fetch_one(
        "SELECT tile_type FROM temple_tiles WHERE temple_id=? AND local_x=? AND local_y=?",
        (temple_id, local_x, local_y),
    )
    tile_type = row["tile_type"] if row else "temple_wall"

    if is_main and tile_type in ("temple_portal_locked", "temple_portal_open"):
        all_solved = await are_all_outer_temples_solved(db)
        tile_type = "temple_portal_open" if all_solved else "temple_portal_locked"

    return TileData(terrain=tile_type, world_x=local_x, world_y=local_y)


async def fill_gear_slot(db, temple_id: int, slot_x: int, slot_y: int, user_id: int) -> str | None:
    """Fill a gear slot (by anchor position).

    Returns the required_gear type on success, None if slot not found or already filled.
    """
    row = await db.fetch_one(
        "SELECT required_gear, is_filled FROM temple_gear_slots"
        " WHERE temple_id=? AND slot_x=? AND slot_y=?",
        (temple_id, slot_x, slot_y),
    )
    if not row or row["is_filled"]:
        return None
    await db.execute(
        "UPDATE temple_gear_slots SET is_filled=1, filled_by=?"
        " WHERE temple_id=? AND slot_x=? AND slot_y=?",
        (user_id, temple_id, slot_x, slot_y),
    )
    return row["required_gear"]


async def remove_gear_slot(db, temple_id: int, slot_x: int, slot_y: int) -> str | None:
    """Remove a gear from a filled slot (by anchor position).

    Returns gear type removed, or None if not filled.
    """
    row = await db.fetch_one(
        "SELECT required_gear, is_filled FROM temple_gear_slots"
        " WHERE temple_id=? AND slot_x=? AND slot_y=?",
        (temple_id, slot_x, slot_y),
    )
    if not row or not row["is_filled"]:
        return None
    await db.execute(
        "UPDATE temple_gear_slots SET is_filled=0, filled_by=NULL"
        " WHERE temple_id=? AND slot_x=? AND slot_y=?",
        (temple_id, slot_x, slot_y),
    )
    return row["required_gear"]


async def is_outer_temple_solved(db, temple_id: int) -> bool:
    """Return True if all gear slots in this outer temple are filled."""
    row = await db.fetch_one(
        "SELECT COUNT(*) AS total, SUM(is_filled) AS filled FROM temple_gear_slots WHERE temple_id=?",
        (temple_id,),
    )
    if not row or not row["total"]:
        return False
    return row["total"] == row["filled"]


async def are_all_outer_temples_solved(db) -> bool:
    """Return True if every outer temple has its puzzle completed."""
    temples = await db.fetch_all(
        "SELECT id FROM sky_temples WHERE temple_type='outer'"
    )
    if not temples:
        return False
    for t in temples:
        if not await is_outer_temple_solved(db, t["id"]):
            return False
    return True


async def get_main_temple_sky_id(db, temple_id: int, world_seed: int) -> int:
    """Get or create the sky biome linked to the main temple."""
    row = await db.fetch_one("SELECT sky_id FROM sky_temples WHERE id=?", (temple_id,))
    if row and row["sky_id"]:
        return row["sky_id"]
    # Create new sky biome
    cur = await db.execute("INSERT INTO sky_biomes (width, height) VALUES (1, 1)")
    sky_id = cur.lastrowid
    await db.execute("UPDATE sky_temples SET sky_id=? WHERE id=?", (sky_id, temple_id))
    from dwarf_explorer.world.sky import create_sky_biome
    await create_sky_biome(sky_id, world_seed, db)
    return sky_id
