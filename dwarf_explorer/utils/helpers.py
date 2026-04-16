from dwarf_explorer.config import CHUNK_SIZE, WORLD_SIZE


def world_to_chunk(x: int, y: int) -> tuple[int, int]:
    """Convert world coordinates to chunk coordinates."""
    return x // CHUNK_SIZE, y // CHUNK_SIZE


def world_to_local(x: int, y: int) -> tuple[int, int]:
    """Convert world coordinates to local position within a chunk."""
    return x % CHUNK_SIZE, y % CHUNK_SIZE


def chunk_to_world(chunk_x: int, chunk_y: int) -> tuple[int, int]:
    """Convert chunk coordinates to the world coordinates of the chunk's top-left tile."""
    return chunk_x * CHUNK_SIZE, chunk_y * CHUNK_SIZE


def in_bounds(x: int, y: int) -> bool:
    """Check if world coordinates are within the world."""
    return 0 <= x < WORLD_SIZE and 0 <= y < WORLD_SIZE
