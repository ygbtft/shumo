import math
from itertools import combinations
import numpy as np
import pytest
from models.q1q2.geometry import NumericPolicy, Region, RegionKind, convex_hull, diameter
from models.q1q2.circle import (minimum_circle, forced_circle, ordinary_three_point_circle,
    ForcedSupportError, diameter_circle_cover, clearance_diameter_regime)
from models.q1q2.diagnostics import equilateral_case, worst_radius_scale
from models.q1q2.q1 import solve

P = NumericPolicy()


def oracle_circle(points):
    points = np.asarray(points)
    candidates = [(p,0.) for p in points]
    for a,b in combinations(points,2):
        candidates.append(((a+b)/2,math.dist(a,b)/2))
    for a,b,c in combinations(points,3):
        matrix = np.array([b-a,c-a])*2
        if abs(np.linalg.det(matrix)) > 1e-12:
            center = a+np.linalg.solve(matrix,[np.dot(b-a,b-a),np.dot(c-a,c-a)])
            candidates.append((center,math.dist(center,a)))
    valid = [(c,r) for c,r in candidates if all(math.dist(c,p) <= r+1e-8 for p in points)]
    return min(valid,key=lambda pair:pair[1])


@pytest.mark.parametrize('seed',range(10))
def test_welzl_against_independent_enumeration(seed):
    points = np.random.default_rng(seed).normal(size=(9,2))*100
    expected_center, expected_radius = oracle_circle(points)
    actual = minimum_circle(points,P,seed)
    assert actual.status == 'OK'
    assert actual.radius == pytest.approx(expected_radius,rel=1e-8)
    assert math.dist(actual.center,expected_center) < 1e-6
    assert len(actual.support_vertex_indices) <= 3


@pytest.mark.parametrize('points', [((0,0),(1,0),(2,0)),((0,0),(2,0),(1,.1)),
                                     ((0,0),(2,0),(0,2)),((0,0),(0,0),(0,0)),
                                     ((0,0),(1,1e-11),(2,0))])
def test_ordinary_degenerate_triples(points):
    c = ordinary_three_point_circle(points,P)
    assert c.radius == pytest.approx(oracle_circle(points)[1])
    assert all(math.dist(c.center,p) <= c.radius+1e-8 for p in points)


def test_forced_obtuse_triple_is_circumcircle():
    points = ((0,0),(2,0),(1,.1))
    forced = forced_circle(points,P)
    ordinary = ordinary_three_point_circle(points,P)
    assert forced.radius > ordinary.radius
    assert all(math.dist(forced.center,p) == pytest.approx(forced.radius) for p in points)
    assert ordinary.radius == pytest.approx(1.)


def test_collinear_forced_support_reports_invariant_exception():
    with pytest.raises(ForcedSupportError,match='FORCED_SUPPORT'):
        forced_circle(((0,0),(1,0),(2,0)),P)
    assert minimum_circle(((0,0),(1,0),(2,0)),P,0).radius == pytest.approx(1.)


@pytest.mark.parametrize('side',[20.,36.])
def test_real_wedge_triangle_thales_and_tight_ratios(side):
    case = equilateral_case(side)
    result = solve(case['measurements'],P)
    assert len(result.region.vertices) == 3
    assert result.diameter.length == pytest.approx(side,rel=1e-8)
    assert result.minimum_circle.radius == pytest.approx(side/math.sqrt(3),rel=1e-8)
    cover = result.coverage
    assert cover.status == 'NO'
    assert cover.kappa == pytest.approx(2/math.sqrt(3))
    assert cover.eta == pytest.approx(math.sqrt(3))
    assert cover.thales_max == pytest.approx(side**2/2)
    assert cover.eta == pytest.approx(math.sqrt(1+4*cover.thales_max/result.diameter.squared))
    assert math.dist(cover.counterexample_vertex,cover.forced_center) > side/2
    for obs in case['measurements']:
        d = math.dist(obs.position,case['synthetic_truth'])
        assert 5 < d <= 1500


def test_square_diameter_centers_coincide():
    vertices = ((0.,0.),(2.,0.),(2.,2.),(0.,2.))
    region = Region(RegionKind.POLYGON,vertices)
    d = diameter(region,P)
    cover = diameter_circle_cover(region,d,P)
    assert cover.status == 'YES'
    assert cover.forced_center == (1.,1.)
    assert cover.kappa == pytest.approx(1.)
    for i,j in ((0,2),(1,3)):
        assert tuple((np.array(vertices[i])+vertices[j])/2) == cover.forced_center


def test_point_ratios_not_applicable():
    region = Region(RegionKind.POINT,((3.,4.),))
    cover = diameter_circle_cover(region,diameter(region,P),P)
    assert cover.status == 'YES'
    assert cover.kappa is None and cover.eta is None


@pytest.mark.parametrize('d,expected',[(0,'EXISTS_COVER_CENTER'),(20*math.sqrt(3),'EXISTS_COVER_CENTER'),
                                      (36,'SHAPE_DEPENDENT'),(40,'SHAPE_DEPENDENT'),(40.001,'IMPOSSIBLE')])
def test_clearance_three_diameter_regimes(d,expected):
    assert clearance_diameter_regime(d) == expected


def test_e20_shape_counterexample_and_support_lipschitz():
    triangle = ((0.,0.),(36.,0.),(18.,18*math.sqrt(3)))
    triangle_circle = minimum_circle(triangle,P,0)
    segment_circle = minimum_circle(((0.,0.),(36.,0.)),P,0)
    assert triangle_circle.radius > 20 and segment_circle.radius <= 20
    # Symmetry forces the triangle minimax center; the segment midpoint lies in both 20m disks.
    assert triangle_circle.radius == pytest.approx(12*math.sqrt(3))
    assert all(math.dist(segment_circle.center,p) <= 20 for p in ((0,0),(36,0)))
    perturbed = [(x+.01,y-.02) for x,y in triangle]
    assert abs(minimum_circle(perturbed,P,0).radius-triangle_circle.radius) <= math.hypot(.01,.02)
    assert worst_radius_scale(36) == pytest.approx((18,12*math.sqrt(3)))
