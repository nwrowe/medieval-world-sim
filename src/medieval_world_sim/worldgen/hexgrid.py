"""Odd-row offset pointy-top hex-grid topology and cartographic coordinates.

Game coordinates remain stable integer (x, y) tile IDs. All six neighbors,
river links and road paths use this topology; drawing does not invent edges.
"""
from __future__ import annotations

from math import cos, pi, sin, sqrt

SQRT3 = sqrt(3.0)


def edge_neighbor(x: int, y: int, edge: int) -> tuple[int, int]:
    """Neighbor across polygon edge 0..5, starting with NE then clockwise."""
    if y & 1:
        offsets = ((1, -1), (1, 0), (1, 1), (0, 1), (-1, 0), (0, -1))
    else:
        offsets = ((0, -1), (1, 0), (0, 1), (-1, 1), (-1, 0), (-1, -1))
    dx, dy = offsets[edge]
    return x + dx, y + dy


def neighbors(x: int, y: int, width: int, height: int):
    """Yield exactly the in-bounds edge-sharing tiles (six in the interior)."""
    for edge in range(6):
        nx, ny = edge_neighbor(x, y, edge)
        if 0 <= nx < width and 0 <= ny < height:
            yield nx, ny


def hex_distance(a: tuple[int, int], b: tuple[int, int]) -> int:
    """Minimal number of six-way steps between odd-row offset coordinates."""
    ax, ay = a
    bx, by = b
    aq, bq = ax - (ay - (ay & 1)) // 2, bx - (by - (by & 1)) // 2
    return (abs(aq - bq) + abs(ay - by) + abs((aq + ay) - (bq + by))) // 2


def center(x: int, y: int, radius: float) -> tuple[float, float]:
    """Pixel center for pointy-top regular hexagons of circumradius radius."""
    return (SQRT3 * radius * (x + (y & 1) * 0.5 + 0.5),
            radius * (1.0 + y * 1.5))


def vertices(x: int, y: int, radius: float) -> tuple[tuple[float, float], ...]:
    cx, cy = center(x, y, radius)
    return tuple((cx + radius * cos(-pi / 2 + i * pi / 3),
                  cy + radius * sin(-pi / 2 + i * pi / 3)) for i in range(6))


def map_size(width: int, height: int, radius: float) -> tuple[int, int]:
    from math import ceil
    return (ceil(SQRT3 * radius * (width + 0.5)),
            ceil(radius * (1.5 * (height - 1) + 2)))
