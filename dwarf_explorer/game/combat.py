"""Turn-based arena combat system.

Arena state is stored in _ui_state (memory) for the active session.
Player combat position, enemy type/HP, and moves left are persisted to DB.
"""
from __future__ import annotations

import math
import random

from dwarf_explorer.config import ENEMY_STATS, ENEMY_ABILITIES, ARENA_IMPASSABLE, COMBAT_MOVES_DEFAULT

ARENA_SIZE = 9


def _passable(grid: list[list[str]], x: int, y: int) -> bool:
    if not (0 <= x < ARENA_SIZE and 0 <= y < ARENA_SIZE):
        return False
    return grid[y][x] not in ARENA_IMPASSABLE


def _adjacent(ax: int, ay: int, bx: int, by: int) -> bool:
    return abs(ax - bx) <= 1 and abs(ay - by) <= 1 and (ax, ay) != (bx, by)


def _step_toward(
    fx: int, fy: int, tx: int, ty: int,
    grid: list[list[str]],
    avoid: tuple[int, int],
) -> tuple[int, int]:
    """Move (fx,fy) one step toward (tx,ty), avoiding impassable tiles and avoid pos."""
    best = (fx, fy)
    best_d = math.hypot(fx - tx, fy - ty)
    for ddx in (-1, 0, 1):
        for ddy in (-1, 0, 1):
            if ddx == 0 and ddy == 0:
                continue
            nx, ny = fx + ddx, fy + ddy
            if not _passable(grid, nx, ny):
                continue
            if (nx, ny) == avoid:
                continue
            d = math.hypot(nx - tx, ny - ty)
            if d < best_d:
                best_d = d
                best = (nx, ny)
    return best


# ── Arena generation ──────────────────────────────────────────────────────────

def build_arena_from_viewport(
    viewport,  # list[list[TileData]]
    enemy_type: str,
    rng: random.Random,
) -> tuple[dict, int, int]:
    """Build fresh arena state from a 9×9 viewport snapshot.

    Returns (arena_state, enemy_x, enemy_y).
    arena_state keys:
      grid        - 9×9 list of terrain type strings
      objects     - {(x,y): "cobweb"} arena objects
      player_trapped - bool
      poison_turns  - int
      golem_slam_used - bool
      combat_log  - list[str]  last 3 messages
    """
    grid = [[tile.terrain for tile in row] for row in viewport]

    # Place enemy 2-3 tiles from center, on a passable tile
    center = ARENA_SIZE // 2
    ex, ey = center + 2, center
    for _ in range(40):
        angle = rng.uniform(0, 2 * math.pi)
        dist = rng.uniform(2.0, 3.5)
        cx = int(round(center + math.cos(angle) * dist))
        cy = int(round(center + math.sin(angle) * dist))
        cx = max(1, min(ARENA_SIZE - 2, cx))
        cy = max(1, min(ARENA_SIZE - 2, cy))
        if _passable(grid, cx, cy) and (cx, cy) != (center, center):
            ex, ey = cx, cy
            break

    arena = {
        "grid": grid,
        "objects": {},
        "player_trapped": False,
        "poison_turns": 0,
        "golem_slam_used": False,
        "combat_log": [],
        "extra_enemies": [],   # list of {"x","y","hp","type"} for simultaneous enemies
    }
    return arena, ex, ey


def spawn_extra_enemies(
    arena: dict,
    rng: random.Random,
    enemy_type: str,
    count: int,
    primary_x: int,
    primary_y: int,
    player_center: tuple[int, int],
) -> None:
    """Add `count` extra enemies of the same type to arena["extra_enemies"].

    Each is placed at a random passable tile 2-4 tiles from the primary enemy,
    avoiding the player start position and any already-placed enemies.
    """
    from dwarf_explorer.config import ENEMY_STATS
    base_hp = ENEMY_STATS[enemy_type][0]
    px, py = player_center
    for _ in range(count):
        occupied = {(px, py), (primary_x, primary_y)}
        occupied.update((e["x"], e["y"]) for e in arena["extra_enemies"])
        placed = False
        for _attempt in range(60):
            angle = rng.uniform(0, 2 * math.pi)
            dist = rng.uniform(2.0, 4.0)
            cx = max(1, min(ARENA_SIZE - 2, int(round(primary_x + math.cos(angle) * dist))))
            cy = max(1, min(ARENA_SIZE - 2, int(round(primary_y + math.sin(angle) * dist))))
            if _passable(arena["grid"], cx, cy) and (cx, cy) not in occupied:
                arena["extra_enemies"].append(
                    {"x": cx, "y": cy, "hp": base_hp, "type": enemy_type}
                )
                placed = True
                break
        if not placed:
            # Fallback: place anywhere passable not occupied
            for fy in range(1, ARENA_SIZE - 1):
                for fx in range(1, ARENA_SIZE - 1):
                    if _passable(arena["grid"], fx, fy) and (fx, fy) not in occupied:
                        arena["extra_enemies"].append(
                            {"x": fx, "y": fy, "hp": base_hp, "type": enemy_type}
                        )
                        placed = True
                        break
                if placed:
                    break


def promote_extra_enemy(arena: dict, player) -> bool:
    """Promote the first living extra enemy to primary. Returns True if promoted."""
    # Purge dead extras
    arena["extra_enemies"] = [
        e for e in arena.get("extra_enemies", []) if e["hp"] > 0
    ]
    extras = arena["extra_enemies"]
    if not extras:
        return False
    next_e = extras.pop(0)
    player.combat_enemy_hp = next_e["hp"]
    player.combat_enemy_x = next_e["x"]
    player.combat_enemy_y = next_e["y"]
    # type stays the same (swarm of same enemy type)
    return True


# ── Player actions ────────────────────────────────────────────────────────────

_DIR_DELTA = {
    "up":        (0, -1),
    "down":      (0,  1),
    "left":      (-1, 0),
    "right":     (1,  0),
    "upleft":    (-1, -1),
    "upright":   (1, -1),
    "downleft":  (-1, 1),
    "downright": (1,  1),
}


def action_move(arena: dict, player, direction: str, rng: random.Random) -> str:
    """Move player one tile. If trapped, attempt 50% escape instead. Costs 1 move."""
    if arena["player_trapped"]:
        player.combat_moves_left -= 1
        if rng.random() < 0.50:
            arena["player_trapped"] = False
            arena["objects"].pop((player.combat_player_x, player.combat_player_y), None)
            return "You struggle free from the cobweb! ✅"
        return "You thrash against the cobweb but can't break free! 🕸️"

    dx, dy = _DIR_DELTA.get(direction, (0, 0))
    nx, ny = player.combat_player_x + dx, player.combat_player_y + dy

    if not _passable(arena["grid"], nx, ny):
        player.combat_moves_left -= 1
        return "Something blocks your path."

    occupied_by_enemy = {(player.combat_enemy_x, player.combat_enemy_y)}
    occupied_by_enemy.update(
        (e["x"], e["y"]) for e in arena.get("extra_enemies", []) if e["hp"] > 0
    )
    if (nx, ny) in occupied_by_enemy:
        player.combat_moves_left -= 1
        return "An enemy is standing there!"

    player.combat_player_x = nx
    player.combat_player_y = ny
    player.combat_moves_left -= 1

    if arena["objects"].get((nx, ny)) == "cobweb":
        arena["player_trapped"] = True
        return "You step into a cobweb and get tangled! 🕸️"

    return "You move."


def action_attack(arena: dict, player, rng: random.Random, has_slingshot: bool = False) -> str:
    """Attack the enemy. Costs 1 move. Slingshot bypasses adjacency requirement."""
    if arena["player_trapped"]:
        player.combat_moves_left -= 1
        return "You can't attack while tangled in a cobweb! 🕸️"

    player.combat_moves_left -= 1
    is_ranged = has_slingshot
    if not is_ranged and not _adjacent(player.combat_player_x, player.combat_player_y,
                                       player.combat_enemy_x, player.combat_enemy_y):
        return "The enemy is too far away! Move closer first."

    _hp, _atk, defn, _xp, _gold = ENEMY_STATS[player.combat_enemy_type]
    dmg = max(1, player.attack - defn)
    player.combat_enemy_hp -= dmg
    name = _enemy_name(player.combat_enemy_type)
    prefix = "🪃 You sling a rock at" if is_ranged else "⚔️ You strike"
    return f"{prefix} the {name} for **{dmg}** damage! ({player.combat_enemy_hp} HP left)"


def action_flee(arena: dict, player, rng: random.Random) -> tuple[str, bool]:
    """Attempt to flee. Uses all remaining moves. Returns (message, success)."""
    px, py = player.combat_player_x, player.combat_player_y
    dist_from_enemy = math.hypot(px - player.combat_enemy_x, py - player.combat_enemy_y)
    edge_dist = min(px, py, ARENA_SIZE - 1 - px, ARENA_SIZE - 1 - py)
    chance = 0.35 + min(dist_from_enemy * 0.05, 0.25) + max(0, 2 - edge_dist) * 0.05
    player.combat_moves_left = 0

    if rng.random() < chance:
        # Successful escape — enemy lands a parting blow for half their attack
        _hp, enemy_atk, _, _, _ = ENEMY_STATS.get(player.combat_enemy_type, (0, 6, 0, 0, 0))
        player_def = getattr(player, "defense", 5)
        flee_dmg = max(1, enemy_atk // 2 - player_def)
        is_naval = getattr(player, "in_high_seas", False) or getattr(player, "in_ocean", False)
        if is_naval:
            player.ship_hp = max(1, player.ship_hp - flee_dmg)
            return f"🏃 You escape, but the enemy lands a parting blow for **{flee_dmg}** hull damage! ({player.ship_hp} HP)", True
        else:
            player.hp = max(1, player.hp - flee_dmg)  # fleeing can't kill you
            return f"🏃 You escape, but take a parting blow for **{flee_dmg}** damage! ({player.hp} HP)", True
    return "🏃 You try to flee but can't get away!", False



def action_use_potion(arena: dict, player) -> str:
    """Use a potion. Heals 30 HP. Costs 1 move. Caller removes potion from inventory."""
    heal = min(30, player.max_hp - player.hp)
    player.hp += heal
    player.combat_moves_left -= 1
    return f"🧪 You drink a potion! Restored **{heal}** HP. ({player.hp}/{player.max_hp})"


# ── Enemy AI ──────────────────────────────────────────────────────────────────

def resolve_enemy_turn(arena: dict, player, rng: random.Random, naval: bool = False) -> str:
    """Run the enemy's turn. Returns combined message string.

    If naval=True, enemy attacks damage player.ship_hp instead of player.hp
    (the creature is attacking the ship, not the player directly).
    """
    enemy_type = player.combat_enemy_type
    abilities = ENEMY_ABILITIES.get(enemy_type, {})
    hp_entry, atk, defn, _xp, _gold = ENEMY_STATS[enemy_type]
    name = _enemy_name(enemy_type)
    msgs: list[str] = []

    def _deal_damage(dmg: int) -> str:
        """Apply damage to ship_hp (naval) or player hp, return status string."""
        if naval:
            player.ship_hp = max(0, player.ship_hp - dmg)
            return f"({player.ship_hp}/{player.ship_max_hp} hull)"
        else:
            player.hp = max(0, player.hp - dmg)
            return f"({player.hp}/{player.max_hp} HP)"

    # ── Temporal Echo: custom AI ──────────────────────────────────────────────
    if enemy_type == "temporal_echo":
        ex, ey = player.combat_enemy_x, player.combat_enemy_y
        px, py = player.combat_player_x, player.combat_player_y

        # 1. Clear old deposits (gives window at start of player's next round)
        arena["echo_deposits"] = set()

        # 2. Rewind — regain HP every 2 turns
        arena["echo_rewind_counter"] = arena.get("echo_rewind_counter", 0) + 1
        if arena["echo_rewind_counter"] % 2 == 0:
            rewind_hp = 30
            max_hp = ENEMY_STATS["temporal_echo"][0]
            old_hp = player.combat_enemy_hp
            player.combat_enemy_hp = min(player.combat_enemy_hp + rewind_hp, max_hp)
            actual = player.combat_enemy_hp - old_hp
            if actual > 0:
                msgs.append(
                    f"⏪ The Echo **rewinds**, restoring **{actual}** HP!"
                    f" ({player.combat_enemy_hp}/{max_hp} HP)"
                )

        # 3. Move toward player
        new_ex, new_ey = _step_toward(ex, ey, px, py, arena["grid"], (px, py))
        player.combat_enemy_x = new_ex
        player.combat_enemy_y = new_ey

        # 4. Attack if adjacent
        if _adjacent(new_ex, new_ey, px, py):
            dmg = max(1, atk - player.defense // 2)
            player.hp = max(0, player.hp - dmg)
            msgs.append(
                f"👻 The Echo strikes for **{dmg}** damage! ({player.hp}/{player.max_hp} HP)"
            )

        if not msgs:
            msgs.append("👻 The Echo shifts through time, watching you...")

        if not naval and arena.get("poison_turns", 0) > 0:
            player.hp = max(0, player.hp - 2)
            arena["poison_turns"] -= 1
            msgs.append(f"🟢 Poison deals **2** damage. ({player.hp}/{player.max_hp} HP)")

        return " ".join(msgs)

    # Enemy gets 1 action (cave_bat gets 2 for hit-and-run feel)
    num_actions = 2 if enemy_type == "cave_bat" else 1

    for _ in range(num_actions):
        ex, ey = player.combat_enemy_x, player.combat_enemy_y
        px, py = player.combat_player_x, player.combat_player_y

        # ── Spider: lay cobweb before moving ──
        if abilities.get("cobweb"):
            lay_chance = 0.40 if enemy_type == "cave_spider" else 0.30
            if rng.random() < lay_chance:
                arena["objects"][(ex, ey)] = "cobweb"
                msgs.append(f"The {name} leaves a sticky cobweb behind! 🕸️")
                # 30% chance: extra cobweb on a random adjacent tile
                if rng.random() < 0.30:
                    neighbors = [(ex+dx, ey+dy) for dx, dy in ((0,1),(0,-1),(1,0),(-1,0))
                                 if 0 <= ex+dx < ARENA_SIZE and 0 <= ey+dy < ARENA_SIZE
                                 and (ex+dx, ey+dy) != (px, py)]
                    if neighbors:
                        arena["objects"][rng.choice(neighbors)] = "cobweb"

        # ── Golem slam ──
        if abilities.get("slam") and not arena["golem_slam_used"] and rng.random() < 0.25:
            arena["golem_slam_used"] = True
            sdx = (1 if px > ex else (-1 if px < ex else 0))
            sdy = (1 if py > ey else (-1 if py < ey else 0))
            line = [(ex + sdx * t, ey + sdy * t) for t in range(1, 5)]
            if (px, py) in line:
                slam_dmg = max(1, atk * 2 - player.defense)
                status = _deal_damage(slam_dmg)
                msgs.append(f"💥 The {name} SLAMS! **{slam_dmg}** damage! {status}")
            else:
                msgs.append(f"💥 The {name} slams! You barely dodge!")
            continue

        # ── Bear roar ──
        if abilities.get("roar") and rng.random() < 0.20:
            msgs.append(f"🐻 The {name} lets out a terrifying ROAR!")
            continue

        # ── Ranged attack: fire from up to 3 tiles (Chebyshev) without closing ──
        if abilities.get("ranged"):
            dist = max(abs(ex - px), abs(ey - py))
            if dist <= 3:
                # Fire a projectile — deal slightly reduced damage
                dmg = max(1, atk - player.defense // 3)
                status = _deal_damage(dmg)
                msgs.append(f"🎯 The {name} fires at you for **{dmg}** damage! {status}")
                # Hit-and-run: back off after shooting
                if abilities.get("hit_run") and rng.random() < 0.50:
                    away = _step_toward(ex, ey,
                                        ARENA_SIZE - 1 - px, ARENA_SIZE - 1 - py,
                                        arena["grid"], (px, py))
                    player.combat_enemy_x, player.combat_enemy_y = away
                    msgs.append(f"💨 The {name} darts away!")
            else:
                # Out of range — step closer
                new_ex, new_ey = _step_toward(ex, ey, px, py, arena["grid"], (px, py))
                player.combat_enemy_x = new_ex
                player.combat_enemy_y = new_ey
            continue

        # ── Move toward player ──
        new_ex, new_ey = _step_toward(ex, ey, px, py, arena["grid"], (px, py))
        player.combat_enemy_x = new_ex
        player.combat_enemy_y = new_ey

        # ── Attack if adjacent ──
        if _adjacent(new_ex, new_ey, px, py):
            dmg = max(1, atk - player.defense // 2)
            status = _deal_damage(dmg)

            # Cave spider poison (not applicable in naval — ship can't be poisoned)
            if abilities.get("poison") and not naval and rng.random() < 0.35:
                arena["poison_turns"] = max(arena["poison_turns"], 3)
                msgs.append(f"🕷️ The {name} bites and **poisons** you!")

            prefix = "⚓" if naval else "💢"
            msgs.append(f"{prefix} {name} attacks for **{dmg}** damage! {status}")

            # Bat hit-and-run: retreat after attacking
            if abilities.get("hit_run") and rng.random() < 0.50:
                away = _step_toward(new_ex, new_ey,
                                    ARENA_SIZE - 1 - px, ARENA_SIZE - 1 - py,
                                    arena["grid"], (px, py))
                player.combat_enemy_x, player.combat_enemy_y = away
                msgs.append(f"🦇 The {name} darts away!")

    # ── Extra simultaneous enemies act ───────────────────────────────────────
    for extra in arena.get("extra_enemies", []):
        if extra["hp"] <= 0:
            continue
        if player.hp <= 0:
            break
        ex_type = extra["type"]
        _ex_hp, ex_atk, ex_def, _, _ = ENEMY_STATS[ex_type]
        ex_actions = 2 if ex_type == "cave_bat" else 1
        ex_abilities = ENEMY_ABILITIES.get(ex_type, {})
        ex_x, ex_y = extra["x"], extra["y"]
        px2, py2 = player.combat_player_x, player.combat_player_y
        for _ea in range(ex_actions):
            new_ex_x, new_ex_y = _step_toward(ex_x, ex_y, px2, py2, arena["grid"], (px2, py2))
            extra["x"], extra["y"] = new_ex_x, new_ex_y
            ex_x, ex_y = new_ex_x, new_ex_y
            if _adjacent(ex_x, ex_y, px2, py2):
                dmg = max(1, ex_atk - player.defense // 2)
                player.hp = max(0, player.hp - dmg)
                msgs.append(f"🦇 Another bat swoops for **{dmg}**! ({player.hp}/{player.max_hp} HP)")
                if ex_abilities.get("hit_run") and rng.random() < 0.50:
                    away = _step_toward(ex_x, ex_y,
                                        ARENA_SIZE - 1 - px2, ARENA_SIZE - 1 - py2,
                                        arena["grid"], (px2, py2))
                    extra["x"], extra["y"] = away[0], away[1]
                    ex_x, ex_y = away[0], away[1]
            if player.hp <= 0:
                break

    # ── Poison tick (land combat only) ──
    if not naval and arena["poison_turns"] > 0:
        player.hp = max(0, player.hp - 2)
        arena["poison_turns"] -= 1
        msgs.append(f"🟢 Poison deals **2** damage. ({player.hp}/{player.max_hp} HP)")

    if not msgs:
        msgs.append(f"The {name} circles warily...")

    return " ".join(msgs)


# ── Bat swarm ─────────────────────────────────────────────────────────────────

def maybe_next_bat(arena: dict, player, rng: random.Random) -> bool:
    """If there are more bats in the swarm, reset HP and reposition for the next one.

    Returns True if another bat was spawned (combat continues), False if swarm is done.
    """
    remaining = arena.get("bat_remaining", 1)
    if remaining <= 1:
        return False  # last bat — real victory

    arena["bat_remaining"] = remaining - 1
    bat_hp = ENEMY_STATS["cave_bat"][0]
    player.combat_enemy_hp = bat_hp
    # Reposition the next bat 2-3 tiles from the player
    px, py = player.combat_player_x, player.combat_player_y
    for _ in range(40):
        angle = rng.uniform(0, 2 * math.pi)
        dist = rng.uniform(2.0, 3.5)
        cx = max(1, min(ARENA_SIZE - 2, int(round(px + math.cos(angle) * dist))))
        cy = max(1, min(ARENA_SIZE - 2, int(round(py + math.sin(angle) * dist))))
        if _passable(arena["grid"], cx, cy) and (cx, cy) != (px, py):
            player.combat_enemy_x = cx
            player.combat_enemy_y = cy
            break
    arena["combat_log"].append(
        f"🦇 Another bat swoops in! ({arena['bat_remaining']} remaining)"
    )
    return True


# ── Victory / death ───────────────────────────────────────────────────────────

def apply_victory(player) -> str:
    """Give XP and gold for winning. Returns message."""
    from dwarf_explorer.config import COIN_PURSE_CAPACITY
    _hp, _atk, _defn, xp, gold = ENEMY_STATS[player.combat_enemy_type]
    name = _enemy_name(player.combat_enemy_type)
    cap = COIN_PURSE_CAPACITY.get(player.coin_purse, COIN_PURSE_CAPACITY[None])
    player.gold = min(player.gold + gold, cap)
    player.xp += xp
    return f"🎉 You defeated the **{name}**! +{xp} XP  +{gold}g"


def apply_death_reset(player) -> str:
    """Reset player state after being knocked out. HP restored to full; position set by caller."""
    player.hp = player.max_hp
    player.in_cave = False
    player.cave_id = None
    player.in_village = False
    player.village_id = None
    player.in_house = False
    player.house_id = None
    return "💀 You've been knocked out! You wake up in the nearest village, fully healed."


# ── Renderer ──────────────────────────────────────────────────────────────────

def render_arena(arena: dict, player) -> str:
    """Render the 9×9 combat arena as an emoji grid + status bar."""
    from dwarf_explorer.config import (
        TERRAIN_EMOJI, CAVE_EMOJI, VILLAGE_EMOJI, ENTITY_EMOJI, ARENA_EMOJI,
    )
    ALL_TERRAIN = {**TERRAIN_EMOJI, **CAVE_EMOJI, **VILLAGE_EMOJI}

    is_naval = arena.get("naval", False)
    grid = arena["grid"]
    objects = arena["objects"]
    px, py = player.combat_player_x, player.combat_player_y
    ex, ey = player.combat_enemy_x, player.combat_enemy_y

    # Enemy emoji
    enemy_emoji = ENTITY_EMOJI.get(
        player.combat_enemy_type,
        CAVE_EMOJI.get(player.combat_enemy_type, "👾"),
    )

    rows: list[str] = []

    # Naval: show ship art above the arena
    if is_naval:
        from dwarf_explorer.game.renderer import render_ship_room
        ship_art = render_ship_room(player)
        rows.append(ship_art)
        rows.append("")

    echo_deposits: set[tuple[int, int]] = arena.get("echo_deposits", set())

    # Use ship emoji for player in naval combat
    player_icon = ENTITY_EMOJI.get("player_boat", "⛵") if is_naval else ENTITY_EMOJI["player"]

    # Build extra enemy position lookup (skip dead ones)
    extra_positions = {
        (e["x"], e["y"]) for e in arena.get("extra_enemies", []) if e["hp"] > 0
    }

    for row_y in range(ARENA_SIZE):
        cells: list[str] = []
        for col_x in range(ARENA_SIZE):
            if col_x == px and row_y == py:
                cells.append(player_icon)
            elif col_x == ex and row_y == ey:
                cells.append(enemy_emoji)
            elif (col_x, row_y) in extra_positions:
                cells.append(enemy_emoji)   # same emoji for swarm members
            elif (col_x, row_y) in echo_deposits:
                cells.append("💠")  # chronolite deposit hazard
            elif (col_x, row_y) in objects:
                cells.append(ARENA_EMOJI.get(objects[(col_x, row_y)], "🕸️"))
            else:
                terrain = grid[row_y][col_x]
                cells.append(ALL_TERRAIN.get(terrain, "⬛"))
        rows.append("".join(cells))

    # Status line
    enemy_max_hp = ENEMY_STATS[player.combat_enemy_type][0]
    name = _enemy_name(player.combat_enemy_type)
    if is_naval:
        hp_bar = f"🛳️ {player.ship_hp}/{player.ship_max_hp}"
    else:
        hp_bar = f"❤️ {player.hp}/{player.max_hp}"
    living_extras = [e for e in arena.get("extra_enemies", []) if e["hp"] > 0]
    if living_extras:
        extra_hp_str = "  ".join(f"🦇{e['hp']}/{enemy_max_hp}" for e in living_extras)
        enemy_bar = f"💀 {name} {player.combat_enemy_hp}/{enemy_max_hp}hp  {extra_hp_str}"
    else:
        enemy_bar = f"💀 {name} {player.combat_enemy_hp}/{enemy_max_hp}hp"
    moves_bar = f"⚡ {player.combat_moves_left} move{'s' if player.combat_moves_left != 1 else ''} left"

    rows.append("")
    rows.append(f"{hp_bar}  {enemy_bar}  {moves_bar}")

    if arena.get("player_trapped"):
        rows.append("🕸️ **You are trapped in a cobweb!** Use 🕸️ Free to escape.")
    if not is_naval and arena.get("poison_turns", 0) > 0:
        rows.append(f"🟢 Poisoned ({arena['poison_turns']} turns remaining)")
    if player.combat_enemy_type == "temporal_echo":
        next_spawn = arena.get("echo_deposit_move", 1)
        deposit_active = bool(arena.get("echo_deposits"))
        if deposit_active:
            rows.append(f"💠 Chronolite ring active — next spawn on move **{next_spawn}**")
        else:
            rows.append(f"💠 Ring cleared — deposits will spawn on your move **{next_spawn}**")

    if arena["combat_log"]:
        rows.append("")
        for line in arena["combat_log"][-3:]:
            rows.append(f"> {line}")

    return "\n".join(rows)


# ── Temporal Echo deposit mechanics ───────────────────────────────────────────

def resolve_echo_deposits(arena: dict, player) -> str:
    """Called after each player action when fighting the temporal_echo.

    Spawns a ring of Chronolite deposits around the Echo on the designated
    player move (1 or 3, alternating each echo turn).  Deposits are stored
    in arena["echo_deposits"] and rendered as 💠 tiles in the arena grid.

    If the player is standing on a newly-spawned deposit tile, they take
    instant damage.  Deposits persist until the Echo's next turn clears them.

    Returns a message string (empty string if no spawn this move).
    """
    if player.combat_enemy_type != "temporal_echo":
        return ""

    moves_default = COMBAT_MOVES_DEFAULT + (
        1 if getattr(player, "accessory", None) == "ring_of_time" else 0
    )
    # Which sequential move are we on? (1=first, 2=second, 3=third …)
    moves_taken = moves_default - player.combat_moves_left
    spawn_move = arena.get("echo_deposit_move", 1)

    if moves_taken != spawn_move:
        return ""

    # Spawn ring of deposits at Manhattan distance 2 from the echo
    ex, ey = player.combat_enemy_x, player.combat_enemy_y
    px, py = player.combat_player_x, player.combat_player_y

    deposits: set[tuple[int, int]] = set()
    for ddx in range(-3, 4):
        for ddy in range(-3, 4):
            if abs(ddx) + abs(ddy) == 2:
                nx, ny = ex + ddx, ey + ddy
                if 0 <= nx < ARENA_SIZE and 0 <= ny < ARENA_SIZE:
                    deposits.add((nx, ny))

    # Always include the player's current tile (punishes staying still)
    deposits.add((px, py))

    arena["echo_deposits"] = deposits

    # Flip spawn move for next echo turn (1 → 3 → 1 → …)
    arena["echo_deposit_move"] = 3 if spawn_move == 1 else 1

    move_word = "first" if spawn_move == 1 else "third"

    # Damage if player is on a deposit
    if (px, py) in deposits:
        dmg = 10
        player.hp = max(0, player.hp - dmg)
        return (
            f"💠 Chronolite materialises on you! **{dmg}** damage! "
            f"({player.hp}/{player.max_hp} HP) "
            f"[ring spawned on your {move_word} move]"
        )

    return f"💠 Chronolite ring crystallises around the Echo! [{move_word} move spawn]"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _enemy_name(enemy_type: str) -> str:
    return enemy_type.replace("cave_", "").replace("_", " ").title()
