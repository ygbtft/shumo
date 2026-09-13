from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


import math
import pytest


@pytest.fixture
def assert_source_members():
    def check(first, physics, points):
        # Closed boundaries tolerate float64 roundoff; the excluded near disk stays strict.
        length_tol, angle_tol_deg = 1e-9, 1e-10
        for p in points:
            assert len(p) == 2 and all(math.isfinite(v) for v in p)
            r = math.dist(p, first.position)
            assert r > physics.near_radius, ('excluded near disk', p, r)
            assert r <= physics.rho_hi+length_tol, ('receiving radius', p, r)
            assert math.dist(p, physics.arena_center) <= physics.arena_radius+length_tol, ('arena', p)
            theta = math.degrees(math.atan2(p[1]-first.position[1], p[0]-first.position[0]))
            delta = math.remainder(theta-first.bearing_deg, 360.)
            assert abs(delta) <= first.half_width_deg+angle_tol_deg, ('bearing', p, delta)
    return check
