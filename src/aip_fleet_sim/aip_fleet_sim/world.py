"""Shared world model: axis-aligned rectangular obstacles with ray casting."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Tuple

import numpy as np


@dataclass
class Rect:
    x_min: float
    y_min: float
    x_max: float
    y_max: float


class World:
    def __init__(
        self,
        size_x: float,
        size_y: float,
        origin_x: float,
        origin_y: float,
        resolution: float,
        obstacles: List[Tuple[float, float, float, float]],
    ) -> None:
        self.size_x = size_x
        self.size_y = size_y
        self.origin_x = origin_x
        self.origin_y = origin_y
        self.resolution = resolution
        self.obstacles: List[Rect] = [Rect(*o) for o in obstacles]

    # ------------------------------------------------------------------
    # Occupancy grid rendering (for /map)
    # ------------------------------------------------------------------
    def to_occupancy_grid(self) -> np.ndarray:
        """Return an int8 numpy array in ROS occupancy-grid layout (row-major,
        origin at lower-left). 0 = free, 100 = occupied."""
        w = int(round(self.size_x / self.resolution))
        h = int(round(self.size_y / self.resolution))
        grid = np.zeros((h, w), dtype=np.int8)
        for r in self.obstacles:
            i0 = max(0, int((r.x_min - self.origin_x) / self.resolution))
            i1 = min(w, int(math.ceil((r.x_max - self.origin_x) / self.resolution)))
            j0 = max(0, int((r.y_min - self.origin_y) / self.resolution))
            j1 = min(h, int(math.ceil((r.y_max - self.origin_y) / self.resolution)))
            grid[j0:j1, i0:i1] = 100
        return grid

    # ------------------------------------------------------------------
    # Ray casting (for fake LiDAR)
    # ------------------------------------------------------------------
    def raycast(self, x: float, y: float, theta: float, max_range: float) -> float:
        """Return the closest hit distance along heading theta from (x, y),
        clamped to max_range. Uses slab method on every rectangle."""
        best = max_range
        dx = math.cos(theta)
        dy = math.sin(theta)
        for r in self.obstacles:
            t = _ray_rect_intersect(x, y, dx, dy, r, max_range)
            if 0.0 < t < best:
                best = t
        return best


def _ray_rect_intersect(
    ox: float, oy: float, dx: float, dy: float, rect: Rect, max_t: float
) -> float:
    """Return the smallest positive t where (ox+t*dx, oy+t*dy) enters rect,
    or +inf if the ray misses. Slab method."""
    eps = 1e-9
    if abs(dx) < eps:
        if ox < rect.x_min or ox > rect.x_max:
            return math.inf
        tx_min = -math.inf
        tx_max = math.inf
    else:
        t1 = (rect.x_min - ox) / dx
        t2 = (rect.x_max - ox) / dx
        tx_min = min(t1, t2)
        tx_max = max(t1, t2)

    if abs(dy) < eps:
        if oy < rect.y_min or oy > rect.y_max:
            return math.inf
        ty_min = -math.inf
        ty_max = math.inf
    else:
        t1 = (rect.y_min - oy) / dy
        t2 = (rect.y_max - oy) / dy
        ty_min = min(t1, t2)
        ty_max = max(t1, t2)

    t_enter = max(tx_min, ty_min)
    t_exit = min(tx_max, ty_max)

    if t_exit < 0 or t_enter > t_exit or t_enter > max_t:
        return math.inf
    # We treat the ray as hitting when it enters the rect, even if origin is inside.
    return max(t_enter, 0.0)
