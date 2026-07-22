"""aip_fleet_sim.world 단위 테스트 — ray casting 수학 검증.

테스트 범주:
  A. _ray_rect_intersect  — slab 교차 계산 핵심 로직
  B. World.raycast        — 멀티 장애물 최근접 hit
  C. World.to_occupancy_grid — 래스터화 정확도
"""
import math

import numpy as np
import pytest

from aip_fleet_sim.world import Rect, World, _ray_rect_intersect

# ── 공통 픽스처 ──────────────────────────────────────────────────────────────

@pytest.fixture
def unit_rect() -> Rect:
    """1×1 사각형 [0,1]×[0,1]."""
    return Rect(0.0, 0.0, 1.0, 1.0)


@pytest.fixture
def simple_world() -> World:
    """10×10m 월드 (origin=-5,-5, res=0.1m).
    장애물: 동벽 [3,4]×[-5,5], 북벽 [-5,5]×[3,4].
    """
    return World(
        size_x=10.0, size_y=10.0,
        origin_x=-5.0, origin_y=-5.0,
        resolution=0.1,
        obstacles=[
            (3.0, -5.0, 4.0,  5.0),   # 동벽
            (-5.0, 3.0, 5.0,  4.0),   # 북벽
        ],
    )


# ═══════════════════════════════════════════════════════════════════════════
# A. _ray_rect_intersect
# ═══════════════════════════════════════════════════════════════════════════

class TestRayRectIntersect:

    def test_direct_hit_east(self, unit_rect):
        """원점 (-1, 0.5)에서 동쪽(+x)으로 쏘면 x=0 에서 hit → t=1.0."""
        t = _ray_rect_intersect(-1.0, 0.5, 1.0, 0.0, unit_rect, 10.0)
        assert t == pytest.approx(1.0, abs=1e-9)

    def test_direct_hit_north(self, unit_rect):
        """원점 (0.5, -2)에서 북쪽(+y)으로 쏘면 y=0 에서 hit → t=2.0."""
        t = _ray_rect_intersect(0.5, -2.0, 0.0, 1.0, unit_rect, 10.0)
        assert t == pytest.approx(2.0, abs=1e-9)

    def test_miss_parallel_edge(self, unit_rect):
        """rect 옆을 y=1.5로 지나가는 동쪽 광선 — miss."""
        t = _ray_rect_intersect(-1.0, 1.5, 1.0, 0.0, unit_rect, 10.0)
        assert math.isinf(t)

    def test_miss_behind(self, unit_rect):
        """rect 왼쪽에서 서쪽(-x)으로 쏘면 rect는 뒤에 있음 — miss."""
        t = _ray_rect_intersect(-1.0, 0.5, -1.0, 0.0, unit_rect, 10.0)
        assert math.isinf(t)

    def test_max_range_clip(self, unit_rect):
        """max_range 0.5: rect가 t=1.0 에 있으면 hit 안 됨."""
        t = _ray_rect_intersect(-1.0, 0.5, 1.0, 0.0, unit_rect, max_t=0.5)
        assert math.isinf(t)

    def test_diagonal_hit(self, unit_rect):
        """45° 대각선으로 [0,1]×[0,1] 모서리 (0,0) 향해 쏘면 hit."""
        # 출발: (-1, -1), 방향: (+1, +1) / sqrt(2)
        dx = 1.0 / math.sqrt(2)
        dy = 1.0 / math.sqrt(2)
        t = _ray_rect_intersect(-1.0, -1.0, dx, dy, unit_rect, 10.0)
        assert math.isfinite(t)
        # 교차점 확인: x = -1 + t*dx == 0 → t = sqrt(2)
        assert t == pytest.approx(math.sqrt(2), abs=1e-6)

    def test_ray_origin_inside_rect(self, unit_rect):
        """원점이 rect 내부에 있으면 t=0 반환."""
        t = _ray_rect_intersect(0.5, 0.5, 1.0, 0.0, unit_rect, 10.0)
        assert t == pytest.approx(0.0, abs=1e-9)

    def test_vertical_ray_parallel_to_x(self, unit_rect):
        """x 방향으로 수직(dx=0)인 광선 — rect x 범위 안에서 y방향 hit."""
        # 출발 (0.5, -1) → +y 방향: rect y_min=0 에서 hit → t=1.0
        t = _ray_rect_intersect(0.5, -1.0, 0.0, 1.0, unit_rect, 10.0)
        assert t == pytest.approx(1.0, abs=1e-9)

    def test_vertical_ray_parallel_miss(self, unit_rect):
        """dx=0, x=1.5 — rect x 범위 밖이므로 miss."""
        t = _ray_rect_intersect(1.5, -1.0, 0.0, 1.0, unit_rect, 10.0)
        assert math.isinf(t)

    def test_grazing_edge_hit(self, unit_rect):
        """rect 모서리 정확히 지나치는 광선 — x_min == origin_x → t=0 처리."""
        # 출발 (0.0, 0.5): rect x_min=0 에 딱 걸림 → t_enter=0
        t = _ray_rect_intersect(0.0, 0.5, 1.0, 0.0, unit_rect, 10.0)
        assert t == pytest.approx(0.0, abs=1e-9)


# ═══════════════════════════════════════════════════════════════════════════
# B. World.raycast
# ═══════════════════════════════════════════════════════════════════════════

class TestWorldRaycast:

    def test_east_wall_direct(self, simple_world):
        """원점 (0,0)에서 동쪽 → 동벽 x=3.0 에서 hit → 거리=3.0."""
        d = simple_world.raycast(0.0, 0.0, 0.0, max_range=10.0)
        assert d == pytest.approx(3.0, abs=1e-6)

    def test_north_wall_direct(self, simple_world):
        """원점 (0,0)에서 북쪽(π/2) → 북벽 y=3.0 에서 hit → 거리=3.0."""
        d = simple_world.raycast(0.0, 0.0, math.pi / 2, max_range=10.0)
        assert d == pytest.approx(3.0, abs=1e-6)

    def test_miss_returns_max_range(self, simple_world):
        """서쪽(-x) 방향에 장애물 없음 → max_range 반환."""
        d = simple_world.raycast(0.0, 0.0, math.pi, max_range=5.0)
        assert d == pytest.approx(5.0, abs=1e-6)

    def test_closer_obstacle_wins(self):
        """두 장애물이 같은 방향에 있을 때 가까운 것이 반환됨."""
        w = World(10.0, 10.0, 0.0, 0.0, 0.1, [
            (2.0, 4.5, 3.0, 5.5),   # 가까운 장애물 (x=2)
            (5.0, 4.5, 6.0, 5.5),   # 먼 장애물 (x=5)
        ])
        d = w.raycast(0.0, 5.0, 0.0, max_range=10.0)
        assert d == pytest.approx(2.0, abs=1e-6)

    def test_max_range_clamps(self, simple_world):
        """max_range=1.0 — 동벽(거리 3.0)에 도달 전에 클램프."""
        d = simple_world.raycast(0.0, 0.0, 0.0, max_range=1.0)
        assert d == pytest.approx(1.0, abs=1e-6)

    def test_diagonal_45deg(self):
        """45° 방향 ray: (0,0) → 정사각 장애물 (2,2,4,4) 모서리 hit."""
        w = World(10.0, 10.0, 0.0, 0.0, 0.1, [(2.0, 2.0, 4.0, 4.0)])
        d = w.raycast(0.0, 0.0, math.pi / 4, max_range=10.0)
        # 45° 방향 단위벡터 (1/√2, 1/√2), rect x_min=2 에서 t=2√2
        assert d == pytest.approx(2.0 * math.sqrt(2), abs=1e-5)

    def test_backward_ray_miss(self, simple_world):
        """원점 (0,0)에서 남쪽(-y)으로 — 장애물 없음 → max_range."""
        d = simple_world.raycast(0.0, 0.0, -math.pi / 2, max_range=4.0)
        assert d == pytest.approx(4.0, abs=1e-6)

    def test_origin_on_obstacle_boundary(self):
        """광선 원점이 장애물 서쪽 면 위에서 서쪽으로 쏠 때.
        raycast 내부에서 t=0.0은 '0 < t' 조건에 걸리지 않아 등록되지 않음.
        → 해당 방향에 다른 장애물이 없으면 max_range 반환 (의도된 설계).
        """
        w = World(10.0, 10.0, 0.0, 0.0, 0.1, [(1.0, 0.0, 3.0, 2.0)])
        d = w.raycast(1.0, 1.0, math.pi, max_range=5.0)   # rect 서쪽 면에서 서쪽으로
        assert d == pytest.approx(5.0, abs=1e-6)   # 장애물 반대 방향 → max_range

    def test_no_obstacles(self):
        """장애물 없음 → max_range 그대로 반환."""
        w = World(10.0, 10.0, 0.0, 0.0, 0.1, [])
        d = w.raycast(5.0, 5.0, 0.0, max_range=7.5)
        assert d == pytest.approx(7.5, abs=1e-6)


# ═══════════════════════════════════════════════════════════════════════════
# C. World.to_occupancy_grid
# ═══════════════════════════════════════════════════════════════════════════

class TestOccupancyGrid:

    def test_shape(self, simple_world):
        """그리드 크기 = (size_y/res, size_x/res)."""
        g = simple_world.to_occupancy_grid()
        assert g.shape == (100, 100)    # 10/0.1 × 10/0.1

    def test_dtype(self, simple_world):
        """dtype은 int8."""
        g = simple_world.to_occupancy_grid()
        assert g.dtype == np.int8

    def test_free_cells(self, simple_world):
        """장애물 없는 중심 셀은 0(free)."""
        g = simple_world.to_occupancy_grid()
        # 월드 (0,0) → 그리드 인덱스 (50, 50) (origin=-5)
        assert g[50, 50] == 0

    def test_obstacle_cells_occupied(self, simple_world):
        """동벽 [3,4]×[-5,5] 내부 셀은 100(occupied)."""
        g = simple_world.to_occupancy_grid()
        # 동벽 중심 (3.5, 0.0) → col = int((3.5-(-5))/0.1) = 85, row = 50
        assert g[50, 85] == 100

    def test_no_obstacles_all_free(self):
        """장애물 없는 월드는 전부 0."""
        w = World(5.0, 5.0, 0.0, 0.0, 0.5, [])
        g = w.to_occupancy_grid()
        assert np.all(g == 0)

    def test_full_obstacle_fill(self):
        """장애물이 전체 월드를 채우면 전부 100."""
        w = World(4.0, 4.0, 0.0, 0.0, 1.0, [(0.0, 0.0, 4.0, 4.0)])
        g = w.to_occupancy_grid()
        assert np.all(g == 100)

    def test_obstacle_boundary_precision(self):
        """장애물 경계 셀 정확도: x=[1,2]×y=[1,2] 장애물의 첫 셀 확인."""
        # origin=(0,0), res=1.0 → 셀 (1,1) 이 occupied 여야 함
        w = World(5.0, 5.0, 0.0, 0.0, 1.0, [(1.0, 1.0, 2.0, 2.0)])
        g = w.to_occupancy_grid()
        assert g[1, 1] == 100   # row=j, col=i
        assert g[0, 0] == 0     # 원점 셀은 free
        assert g[2, 2] == 0     # 장애물 밖
