from __future__ import annotations

import asyncio
import math
import random
from dataclasses import dataclass, field

from dwarf_explorer.config import WORLD_SIZE
from dwarf_explorer.world.noise import fbm
from dwarf_explorer.world.terrain import get_biome

_WATER_BIOMES = {"deep_water", "shallow_water"}


@dataclass
class StreamSegment:
    """One segment of the river tree."""
    start: tuple[float, float]
    end: tuple[float, float]
    path: list[tuple[int, int]]
    order: int = 1
    angle: float = 0.0
    children: list[StreamSegment] = field(default_factory=list)


def _is_water(x: int, y: int, seed: int) -> bool:
    return get_biome(x, y, seed) in _WATER_BIOMES


def _place_lake(lake_tiles: set, cx: int, cy: int, radius: int) -> None:
    r2 = radius * radius
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            if dx * dx + dy * dy <= r2:
                tx, ty = cx + dx, cy + dy
                if 0 <= tx < WORLD_SIZE and 0 <= ty < WORLD_SIZE:
                    lake_tiles.add((tx, ty))


def _local_flow_direction(path: list[tuple[int, int]], idx: int) -> float:
    """Compute local flow angle from neighboring path tiles."""
    i0 = max(0, idx - 2)
    i1 = min(len(path) - 1, idx + 2)
    if i0 == i1:
        return 0.0
    dx = path[i1][0] - path[i0][0]
    dy = path[i1][1] - path[i0][1]
    return math.atan2(dy, dx)


def _generate_main_trunk(rng: random.Random, seed: int) -> StreamSegment:
    """Generate the main river trunk flowing W->E across the map."""
    start_y = rng.randint(40, WORLD_SIZE - 40)
    path: list[tuple[int, int]] = []

    fy = float(start_y)
    momentum = 0.0

    for x in range(WORLD_SIZE):
        cy = max(8, min(WORLD_SIZE - 8, int(round(fy))))
        if not path or (x, cy) != path[-1]:
            path.append((x, cy))

        noise_val = fbm(x * 0.015, fy * 0.015, seed, octaves=2)
        momentum = momentum * 0.80 + (noise_val - 0.5) * 0.8
        momentum = max(-1.5, min(1.5, momentum))
        fy += momentum
        fy = max(8.0, min(WORLD_SIZE - 8.0, fy))

    end = path[-1] if path else (WORLD_SIZE - 1, start_y)
    return StreamSegment(
        start=(0, start_y),
        end=end,
        path=path,
        angle=0.0,
    )


def _walk_upstream(
    start_x: float, start_y: float,
    angle: float,
    length: int,
    rng: random.Random,
    seed: int,
    noise_idx: int,
    occupied: set[tuple[int, int]],
    meander_amp: float = 2.0,
) -> list[tuple[int, int]]:
    """Walk upstream from a junction point in the given angle direction."""
    path: list[tuple[int, int]] = []
    x, y = start_x, start_y
    dx = math.cos(angle)
    dy = math.sin(angle)
    perp_dx = -dy
    perp_dy = dx

    momentum = 0.0

    for step in range(length * 2):
        ix = max(0, min(WORLD_SIZE - 1, int(round(x))))
        iy = max(0, min(WORLD_SIZE - 1, int(round(y))))

        if not (0 <= ix < WORLD_SIZE and 0 <= iy < WORLD_SIZE):
            break
        if len(path) >= length:
            break

        if not path or (ix, iy) != path[-1]:
            if len(path) > 8 and (ix, iy) in occupied:
                break
            path.append((ix, iy))

        noise_val = fbm(step * 0.07, noise_idx * 17.3 + 3.1, seed ^ 0xBEEF, octaves=2)
        momentum = momentum * 0.6 + (noise_val - 0.5) * meander_amp
        momentum = max(-3.0, min(3.0, momentum))

        x += dx + perp_dx * momentum * 0.3
        y += dy + perp_dy * momentum * 0.3
        x = max(1.0, min(WORLD_SIZE - 2.0, x))
        y = max(1.0, min(WORLD_SIZE - 2.0, y))

    return path


def _compute_tributary_angle(parent_angle: float, side: int, rng: random.Random) -> float:
    """Compute upstream walking angle for a tributary.

    side: +1 = clockwise, -1 = counterclockwise from parent direction.
    Offset is 60-100 degrees, producing natural acute junction angles.
    """
    offset = rng.uniform(math.radians(60), math.radians(100))
    return parent_angle + side * offset


def _populate_tributaries(
    segment: StreamSegment,
    depth: int,
    max_depth: int,
    rng: random.Random,
    seed: int,
    occupied: set[tuple[int, int]],
) -> None:
    """Recursively spawn tributaries along a stream segment."""
    if depth >= max_depth or len(segment.path) < 10:
        return

    if depth == 0:
        num_tribs = rng.randint(5, 8)
        min_spacing = 20
    elif depth == 1:
        num_tribs = rng.randint(2, 4)
        min_spacing = 12
    else:
        num_tribs = rng.randint(1, 2)
        min_spacing = 8

    if num_tribs == 0:
        return

    # Avoid first/last ~15% of the path
    margin = max(1, len(segment.path) // 7)
    start_idx = margin
    end_idx = len(segment.path) - margin
    available = end_idx - start_idx
    if available < min_spacing:
        return

    # Evenly spaced junctions with jitter
    spacing = available / (num_tribs + 1)
    junction_indices: list[int] = []
    for i in range(num_tribs):
        ideal = start_idx + int(spacing * (i + 1))
        jitter = rng.randint(-int(spacing * 0.3), int(spacing * 0.3))
        idx = max(start_idx, min(end_idx - 1, ideal + jitter))
        if junction_indices and abs(idx - junction_indices[-1]) < min_spacing:
            continue
        junction_indices.append(idx)

    side = rng.choice([-1, 1])

    for t_idx, j_idx in enumerate(junction_indices):
        jx, jy = segment.path[j_idx]
        parent_local_angle = _local_flow_direction(segment.path, j_idx)
        trib_angle = _compute_tributary_angle(parent_local_angle, side, rng)
        side *= -1

        if depth == 0:
            trib_length = rng.randint(40, 80)
        elif depth == 1:
            trib_length = rng.randint(20, 45)
        else:
            trib_length = rng.randint(12, 30)

        trib_path = _walk_upstream(
            float(jx), float(jy),
            trib_angle, trib_length,
            rng, seed,
            noise_idx=depth * 100 + t_idx,
            occupied=occupied,
            meander_amp=1.5 + depth * 0.5,
        )

        if len(trib_path) < 5:
            continue

        child = StreamSegment(
            start=(jx, jy),
            end=trib_path[-1] if trib_path else (jx, jy),
            path=trib_path,
            angle=trib_angle,
        )
        segment.children.append(child)

        for px, py in trib_path:
            occupied.add((px, py))

        _populate_tributaries(child, depth + 1, max_depth, rng, seed, occupied)


def _compute_strahler_order(segment: StreamSegment) -> int:
    """Compute Strahler stream order bottom-up."""
    if not segment.children:
        segment.order = 1
        return 1

    child_orders = [_compute_strahler_order(c) for c in segment.children]
    max_order = max(child_orders)
    count_max = child_orders.count(max_order)

    segment.order = max_order + 1 if count_max >= 2 else max_order
    return segment.order


def _widen_perpendicular(
    px: int, py: int,
    flow_angle: float,
    half_width: int,
    river_tiles: set[tuple[int, int]],
    seed: int,
) -> None:
    """Add tiles perpendicular to flow direction at (px, py)."""
    perp_dx = -math.sin(flow_angle)
    perp_dy = math.cos(flow_angle)

    for w in range(-half_width, half_width + 1):
        nx = int(round(px + perp_dx * w))
        ny = int(round(py + perp_dy * w))
        if 0 <= nx < WORLD_SIZE and 0 <= ny < WORLD_SIZE:
            if not _is_water(nx, ny, seed):
                river_tiles.add((nx, ny))


def _render_stream_tree(
    segment: StreamSegment,
    river_tiles: set[tuple[int, int]],
    seed: int,
) -> None:
    """Recursively render all stream segments with width based on order."""
    order = segment.order

    for i, (px, py) in enumerate(segment.path):
        flow_angle = _local_flow_direction(segment.path, i)

        if order >= 4:
            hw = 2 if (i % 15 < 5) else 1
            _widen_perpendicular(px, py, flow_angle, hw, river_tiles, seed)
        elif order == 3:
            _widen_perpendicular(px, py, flow_angle, 1, river_tiles, seed)
        elif order == 2:
            _widen_perpendicular(px, py, flow_angle, 1, river_tiles, seed)
        else:
            if not _is_water(px, py, seed):
                river_tiles.add((px, py))

    for child in segment.children:
        _render_stream_tree(child, river_tiles, seed)


def _collect_segments(segment: StreamSegment, result: list[StreamSegment]) -> None:
    result.append(segment)
    for child in segment.children:
        _collect_segments(child, result)


def _place_bridge_at(
    path: list[tuple[int, int]],
    idx: int,
    river_tiles: set[tuple[int, int]],
    bridge_tiles: set[tuple[int, int]],
) -> None:
    """Place a bridge crossing at a specific path index."""
    if idx < 0 or idx >= len(path):
        return

    px, py = path[idx]
    flow_angle = _local_flow_direction(path, idx)
    perp_dx = -math.sin(flow_angle)
    perp_dy = math.cos(flow_angle)

    # Replace river tiles across the full width with bridge tiles
    for w in range(-4, 5):
        nx = int(round(px + perp_dx * w))
        ny = int(round(py + perp_dy * w))
        if (nx, ny) in river_tiles:
            bridge_tiles.add((nx, ny))
            river_tiles.discard((nx, ny))

    # Approach tiles on each side of the bridge
    for sign in [-1, 1]:
        for dist in range(1, 6):
            ax = int(round(px + perp_dx * sign * dist))
            ay = int(round(py + perp_dy * sign * dist))
            if 0 <= ax < WORLD_SIZE and 0 <= ay < WORLD_SIZE:
                if (ax, ay) not in river_tiles and (ax, ay) not in bridge_tiles:
                    bridge_tiles.add((ax, ay))
                    break


def _place_bridges(
    root: StreamSegment,
    river_tiles: set[tuple[int, int]],
    bridge_tiles: set[tuple[int, int]],
    rng: random.Random,
) -> None:
    """Place bridges along the stream tree."""
    all_segments: list[StreamSegment] = []
    _collect_segments(root, all_segments)

    for seg in all_segments:
        if seg.order >= 3:
            interval = rng.randint(30, 45)
            idx = interval
            while idx < len(seg.path) - 5:
                _place_bridge_at(seg.path, idx, river_tiles, bridge_tiles)
                idx += rng.randint(30, 45)
        elif seg.order == 2 and len(seg.path) >= 10:
            mid = len(seg.path) // 2
            _place_bridge_at(seg.path, mid, river_tiles, bridge_tiles)


def _place_source_lakes(
    segment: StreamSegment,
    lake_tiles: set[tuple[int, int]],
    rng: random.Random,
) -> None:
    """Place source lakes at headwater endpoints recursively."""
    if not segment.children:
        if segment.path:
            ex, ey = segment.path[-1]
            at_edge = ex <= 5 or ex >= WORLD_SIZE - 5 or ey <= 5 or ey >= WORLD_SIZE - 5
            if not at_edge and rng.random() < 0.6:
                _place_lake(lake_tiles, ex, ey, rng.randint(2, 4))
    else:
        for child in segment.children:
            _place_source_lakes(child, lake_tiles, rng)


def _generate_rivers_sync(
    seed: int,
) -> tuple[list[tuple[int, int]], list[tuple[int, int]], list[tuple[int, int]]]:
    """Generate a Mississippi-style recursive drainage network."""
    rng = random.Random(seed ^ 0xDEAD_BEEF)

    river_tiles: set[tuple[int, int]] = set()
    bridge_tiles: set[tuple[int, int]] = set()
    lake_tiles: set[tuple[int, int]] = set()

    # 1. Main trunk W->E
    root = _generate_main_trunk(rng, seed)
    occupied: set[tuple[int, int]] = set(root.path)

    # 2. Recursive tributaries (max depth 3)
    _populate_tributaries(root, 0, 3, rng, seed, occupied)

    # 3. Strahler order
    _compute_strahler_order(root)

    # 4. Render tiles with widths
    _render_stream_tree(root, river_tiles, seed)

    # 5. Bridges
    _place_bridges(root, river_tiles, bridge_tiles, rng)

    # 6. Source lakes at headwaters
    _place_source_lakes(root, lake_tiles, rng)

    # Clean up overlaps
    lake_tiles -= river_tiles
    lake_tiles -= bridge_tiles

    return list(river_tiles), list(bridge_tiles), list(lake_tiles)


async def generate_rivers(seed: int, db) -> None:
    """Generate rivers, bridges, and lakes; store in tile_overrides."""
    river_tiles, bridge_tiles, lake_tiles = await asyncio.to_thread(
        _generate_rivers_sync, seed
    )

    if river_tiles:
        await db.executemany(
            "INSERT OR IGNORE INTO tile_overrides (world_x, world_y, tile_type) VALUES (?, ?, 'river')",
            [(x, y) for x, y in river_tiles],
        )
    if bridge_tiles:
        await db.executemany(
            "INSERT OR IGNORE INTO tile_overrides (world_x, world_y, tile_type) VALUES (?, ?, 'bridge')",
            [(x, y) for x, y in bridge_tiles],
        )
    if lake_tiles:
        await db.executemany(
            "INSERT OR IGNORE INTO tile_overrides (world_x, world_y, tile_type) VALUES (?, ?, 'shallow_water')",
            [(x, y) for x, y in lake_tiles],
        )
