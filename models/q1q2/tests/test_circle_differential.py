"""All 515 minimized OURS_WRONG/BOTH_WRONG circle cases from the peer audit.

Truth is recomputed independently on the same binary64 inputs. No peer solver
or mutable audit output is needed to run these tests.
"""
import json
import math
from pathlib import Path

import pytest

from models.q1q2.benchmarks.q1_circle_cover.generate import oracle, exact_mec, root
from models.q1q2.circle import (minimum_circle, enumerate_circle, forced_circle,
                              diameter_circle_cover, clearance_diameter_regime)
from models.q1q2.geometry import NumericPolicy, DiameterResult, Region, RegionKind

P = NumericPolicy()
CASES = json.loads((Path(__file__).parent/'fixtures/q1_circle_differential.json').read_text())
CASES += json.loads((Path(__file__).parent/'fixtures/q1_circle_cover_sign.json').read_text())


def assert_circle(result, points, gt):
    assert result.status in ('OK', 'NUMERICAL_UNRESOLVED')
    if result.status != 'OK':
        return
    # The unchanged differential audit's strict tolerance, without a metre floor.
    tol = 1e-9*gt['diameter']+32*max(math.ulp(x) for v in points for x in v)
    assert abs(result.radius-gt['radius']) <= tol
    assert math.dist(result.center, gt['center']) <= tol
    assert all(math.dist(result.center, v) <= result.radius+tol for v in points)
    support, _ = exact_mec([points[i] for i in result.support_vertex_indices])
    assert abs(root(support[1])-gt['radius']) <= tol


@pytest.mark.parametrize('case', CASES, ids=lambda c:c['case_id'])
def test_all_minimized_circle_failures(case):
    points = case['points']
    gt = oracle(points)
    for result in (minimum_circle(points, P, case['seed']), enumerate_circle(points, P)):
        assert_circle(result, points, gt)
        # These small unshifted counterexamples are resolvable; blanket abstention
        # is not an acceptable replacement for fixing their numerical predicates.
        if max(abs(x) for p in points for x in p) <= 1e-3:
            assert result.status == 'OK'
    i, j = gt['pair']
    d = DiameterResult(gt['diameter'], gt['diameter_squared'],
                       (tuple(points[i]), tuple(points[j])), (i,j))
    cover = diameter_circle_cover(Region(RegionKind.POLYGON, tuple(map(tuple, points))), d, P)
    assert cover.status in gt['allowed_cover_status']
    for field in ('kappa','eta'):
        value = getattr(cover, field)
        if value is not None:
            assert abs(value-gt[field]) <= 2e-8


@pytest.mark.parametrize('scale', [1e-150, 1e-12, 5e-10, 1e-7, 1., 1e150])
def test_resolvable_segment_and_equilateral_at_all_scales(scale):
    segment = ((0.,0.), (scale,0.))
    triangle = (*segment, (scale/2, scale*math.sqrt(3)/2))
    for points, radius in ((segment,scale/2), (triangle,scale/math.sqrt(3))):
        for result in (minimum_circle(points,P,7), enumerate_circle(points,P), forced_circle(points,P)):
            assert result.status == 'OK'
            assert result.radius == pytest.approx(radius,rel=2e-14,abs=0)


def test_unrepresentable_midpoint_abstains_without_inflating_radius():
    a = 1e9
    points = ((a,a), (math.nextafter(a,math.inf),a))
    for result in (minimum_circle(points,P,0), enumerate_circle(points,P), forced_circle(points,P)):
        assert result.status == 'NUMERICAL_UNRESOLVED'
        assert result.radius == (points[1][0]-a)/2


def test_near_collinear_forced_circle_uses_exact_fallback():
    points = ((0.,0.), (1.,1e-30), (2.,0.))
    c = forced_circle(points,P)
    assert c.status == 'OK'
    assert c.radius == pytest.approx(5e29)
    assert minimum_circle(points,P,0).radius == 1.


@pytest.mark.parametrize('radius', [math.nan, math.inf, -math.inf])
def test_clearance_rejects_nonfinite_radius(radius):
    with pytest.raises(ValueError):
        clearance_diameter_regime(1., radius)


def test_subnormal_radius_cannot_be_reported_as_zero_ok():
    points = ((0.,0.), (math.ulp(0.),0.))
    for result in (minimum_circle(points,P,0), enumerate_circle(points,P)):
        assert result.status == 'NUMERICAL_UNRESOLVED'


def test_cover_squared_scale_overflow_is_honest_unresolved():
    points = ((0.,0.), (1e200,0.), (5e199,8e199))
    d = DiameterResult(1e200, math.inf, points[:2], (0,1))
    cover = diameter_circle_cover(Region(RegionKind.POLYGON,points),d,P)
    assert cover.status == 'UNRESOLVED'
    assert minimum_circle(points,P,0).status == 'OK'
