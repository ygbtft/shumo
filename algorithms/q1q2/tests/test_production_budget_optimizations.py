"""New analytic results and exact arithmetic / proposal regression contracts."""
import math
import random
from fractions import Fraction as F
from itertools import combinations
import pytest
from algorithms.q1q2 import geometry as g, circle as c, q2
from algorithms.q1q2.feasible import PhysicsConfig, build_source_set


def source():
    return build_source_set(g.BearingMeasurement((0, 0), 0), PhysicsConfig(), g.NumericPolicy())


@pytest.mark.parametrize('budget', [0, 10, 13, 20, 26, 26.15])
def test_tight_budget_extends_legacy(budget):
    ss = source()
    old = q2.short_baseline_lower_bound(ss, 500, 1500, budget)
    new = q2.tight_short_baseline_lower_bound(ss, 500, 1500, budget)
    assert new['lower_bound_m'] == 1000
    if old is not None:
        assert old['lower_bound_m'] == 1000
        assert new['angle_bound_deg'] <= old['angle_bound_deg']
    # Independent extremizer construction and direct angle calculation.
    t = 2000*budget**2/(750000+budget**2)
    z = math.sqrt(max(0, budget**2-t*t))
    expected = math.degrees(math.atan2(-z, 1500-t)-math.atan2(-z, 500-t))
    assert new['angle_bound_deg'] == pytest.approx(expected, abs=2e-14)


def test_budget_limits_and_actual_sources():
    ss = source()
    assert q2.short_baseline_lower_bound(ss, 500, 1500, 10)['lower_bound_m'] == 1000
    assert q2.tight_short_baseline_lower_bound(ss, 500, 1500, 26.151) is None
    assert q2.tight_short_baseline_lower_bound(ss, 500, 1500, 495, 90) is None
    assert q2.tight_short_baseline_lower_bound(ss, 500, 1600, 10) is None
    assert q2.tight_short_baseline_lower_bound(ss, 500, 1500, 0, 0)
    for args in [(0, 1, 0), (1, 1, 0), (1, 2, 1), (1, 2, -1), (1, math.inf, 0)]:
        with pytest.raises(ValueError):
            q2.same_ray_max_angle_deg(*args)


def independent_disk_angle_interval(a, b, budget):
    """100-digit oracle: actual bearings at the extremizer, not G3's formula."""
    from mpmath.ctx_iv import MPIntervalContext
    iv = MPIntervalContext()
    iv.dps = 100
    a, b, r = (iv.mpf(float(v)) for v in (a, b, budget))
    t = (a+b)*r*r/(a*b+r*r)
    z = iv.sqrt(r*r-t*t)
    return iv, (iv.atan2(-z, b-t)-iv.atan2(-z, a-t))*180/iv.pi


CRITICAL_BUDGET = float('26.150756085731231312')


@pytest.mark.parametrize('budget', [
    CRITICAL_BUDGET-1e-10, CRITICAL_BUDGET-1e-12,
    math.nextafter(CRITICAL_BUDGET, -math.inf), CRITICAL_BUDGET,
    math.nextafter(CRITICAL_BUDGET, math.inf),
    CRITICAL_BUDGET+1e-12, CRITICAL_BUDGET+1e-10,
])
def test_audited_budget_threshold_is_conservative(budget):
    iv, actual = independent_disk_angle_interval(500, 1500, budget)
    upper = q2.same_ray_max_angle_deg(500, 1500, budget)
    assert iv.mpf(upper) >= actual.b
    result = q2.tight_short_baseline_lower_bound(source(), 500, 1500, budget)
    if budget >= CRITICAL_BUDGET:
        assert actual.a > 2
        assert result is None
    else:
        assert actual.b < 2
        # A rounded upper bound may conservatively decline a true boundary case.
        if result is not None:
            assert result['angle_bound_deg'] <= 2
            assert result['lower_bound_m'] == 1000
    if budget <= CRITICAL_BUDGET-1e-12:
        assert result is not None


def test_audit_counterexample_and_estimate_are_explicitly_separated():
    assert CRITICAL_BUDGET.hex() == '0x1.a2697f369e37cp+4'
    assert q2.same_ray_max_angle_estimate_deg(500, 1500, CRITICAL_BUDGET) == 2.
    assert q2.same_ray_max_angle_deg(500, 1500, CRITICAL_BUDGET) > 2.
    assert q2.tight_short_baseline_lower_bound(source(), 500, 1500, CRITICAL_BUDGET) is None


@pytest.mark.parametrize('a,b,budget', [
    (52.96035024800184, 52.96493322961901, 52.96035024794888),
    (1., math.nextafter(1., math.inf), math.nextafter(1., 0.)),
    (1e-200, 3e-200, 5e-201), (1e200, 3e200, 5e199),
    (500., 1500., 5e-324), (500., 1500., 10.), (500., 1500., 26.15),
])
def test_outward_angle_covers_near_singular_and_scaled_inputs(a, b, budget):
    iv, actual = independent_disk_angle_interval(a, b, budget)
    assert iv.mpf(q2.same_ray_max_angle_deg(a, b, budget)) >= actual.b


@pytest.mark.parametrize('width', [0., math.nextafter(1., 0.), 1.,
                                   math.nextafter(1., math.inf), 45., 90.])
def test_conservative_angle_test_at_adjacent_thresholds(width):
    iv, actual = independent_disk_angle_interval(500, 1500, CRITICAL_BUDGET)
    result = q2.tight_short_baseline_lower_bound(source(), 500, 1500, CRITICAL_BUDGET, width)
    if result is not None:
        assert actual.b <= 2*iv.mpf(width)
    if actual.a > 2*iv.mpf(width):
        assert result is None


@pytest.mark.parametrize('sign', [-1, 1])
def test_noncollinear_pair_bound(sign):
    ss = source()
    x = (500., 0.)
    y = (1499*math.cos(math.radians(.2)), sign*1499*math.sin(math.radians(.2)))
    bound = q2.source_pair_budget_lower_bound(ss, x, y, 10)
    assert bound['lower_bound_m'] == math.dist(x, y)
    assert bound['initial_angle_deg'] == pytest.approx(.2)
    for k in range(360):
        a = k*math.pi/180
        q = (10*math.cos(a), 10*math.sin(a))
        actual = abs(math.degrees(math.atan2(x[1]-q[1], x[0]-q[0])-math.atan2(y[1]-q[1], y[0]-q[0])))
        assert actual <= bound['angle_bound_deg']
    assert q2.source_pair_budget_lower_bound(ss, x, y, 495, 90) is None
    assert q2.source_pair_budget_lower_bound(ss, x, (0., 500.), 10) is None
    assert q2.source_pair_budget_lower_bound(ss, x, y, 10, 0) is None


@pytest.mark.parametrize('seed', range(100))
def test_integer_intersections_equal_independent_rational_enumeration(seed):
    r = random.Random(2026091400+seed)
    rows = [tuple(F(r.randint(-100, 100), r.randint(1, 100)) for _ in range(3)) for _ in range(r.randint(2, 14))]
    expected = set()
    for a, b in combinations(rows, 2):
        d = a[0]*b[1]-a[1]*b[0]
        if d:
            p = ((a[2]*b[1]-a[1]*b[2])/d, (a[0]*b[2]-a[2]*b[0])/d)
            if all(x*p[0]+y*p[1] <= z for x, y, z in rows):
                expected.add(p)
    assert g._exact_vertices(rows) == expected


@pytest.mark.parametrize('points', [[], [(0., 0.)], [(0., 0.), (1., 0.), (1., 1.), (0., 1.)], [(F(1, 3), 0), (F(2, 7), F(4, 5))], [(5e-324, 0), (0., 0.)], [(-1e308, 0), (1e308, 0)]])
def test_distance_exact_extremes_and_ties(points):
    v = [tuple(map(F, p)) for p in points]
    expected, pair = F(-1), (0, 0)
    for i in range(len(v)):
        for j in range(i, len(v)):
            d = sum((x-y)**2 for x, y in zip(v[i], v[j]))
            if d > expected:
                expected, pair = d, (i, j)
    assert g._farthest_pair(points) == (expected, pair)


def test_wrong_mec_proposal_cannot_escape_certificate(monkeypatch):
    points = [(0., 0.), (4., 0.), (1., 3.)]
    expected = c.minimum_circle(points, 0)
    monkeypatch.setattr(c, '_proposal_circle', lambda _: c.CircleResult((0., 0.), 1e100))
    result = c.minimum_circle(points, 0)
    assert (result.center, result.radius, result.status) == (expected.center, expected.radius, expected.status)
    assert result.method == 'welzl_exact_fallback'


def test_proposal_obtuse_and_unreliable():
    points = [(0., 0.), (2., 0.), (.5, .1)]
    proposal = c._proposal_circle(points)
    assert all(math.dist(proposal.center, p) == pytest.approx(proposal.radius) for p in points)
    assert proposal.radius > 1
    with pytest.raises(c.ForcedSupportError):
        c._proposal_circle([(0., 0.), (1., 0.), (2., 0.)])


def test_legal_cache_exact_keys_none_and_call_scope(monkeypatch):
    from types import SimpleNamespace
    # Repeated rejected coordinates must cache None; adjacent floats stay distinct.
    class Piece:
        kind = 'segment'
        def at(self, t):
            return (1. if t < .75 else math.nextafter(1., math.inf), 0.)
    piece = Piece()
    calls = []
    def witness(ss, x):
        calls.append(tuple(x))
        return x, True
    monkeypatch.setattr(q2, '_boundary_witness', witness)
    import numpy as np
    ss = SimpleNamespace(first=SimpleNamespace(position=(0., 0.)), boundaries=(piece,),
                         contains=lambda _: np.array([False]))
    for station, width, inward in [((2., 0.), 1., 1e-7), ((3., 0.), 1., 1e-7),
                                    ((2., 0.), 2., 1e-7), ((2., 0.), 1., 1e-6)]:
        before = len(calls)
        assert q2._direction_boundary_samples(ss, station, 5, width, inward) == ()
        assert len(calls)-before == 2
    assert len(set(calls)) == 2
