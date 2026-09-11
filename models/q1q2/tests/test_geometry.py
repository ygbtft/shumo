import math
from itertools import combinations
import numpy as np
import pytest
from models.q1q2.geometry import (BearingMeasurement as Obs, NumericPolicy, HalfPlane as HP,
    Region, RegionKind as Kind, wedge_halfplanes, intersect_halfplanes, convex_hull,
    diameter, polygon_area, bearing, angle_delta)
from models.q1q2.q1 import solve

P = NumericPolicy()


def raw_member(obs, p, tolerance=1e-7):
    dx, dy = p[0]-obs.position[0], p[1]-obs.position[1]
    if math.hypot(dx, dy) <= tolerance:
        return True
    degrees = math.degrees(math.atan2(dy, dx))
    delta = (degrees-obs.bearing_deg+180) % 360-180
    return abs(delta) <= obs.half_width_deg+tolerance


def brute_diameter(points):
    return max((math.dist(a, b) for a in points for b in points), default=0.)


@pytest.mark.parametrize('target,expected', [((1,0),0),((0,1),90),((-1,0),180),((0,-1),270)])
def test_compass(target, expected):
    assert bearing((0,0), target) == expected


def test_wrap():
    assert angle_delta(359.99, .01) == pytest.approx(-.02)
    obs = Obs((13, -9), 359.9, 1.)
    for angle in (358.9, 359.9, .9):
        p = np.array(obs.position)+100*np.array((math.cos(math.radians(angle)), math.sin(math.radians(angle))))
        assert raw_member(obs, p)
        assert all(np.dot(h.normal, p) <= h.offset+1e-9 for h in wedge_halfplanes(obs))


@pytest.mark.parametrize('half', [-1, 90.01, float('nan'), float('inf')])
def test_bad_width(half):
    with pytest.raises(ValueError):
        Obs((0,0), 0, half)


@pytest.mark.parametrize('position,angle', [((float('nan'),0),0),((0,0),float('inf'))])
def test_nonfinite(position, angle):
    with pytest.raises(ValueError):
        Obs(position, angle)


def test_zero_width_is_forward_ray():
    hps = wedge_halfplanes(Obs((0,0), 0, 0))
    assert all(np.dot(h.normal, (1,0)) <= h.offset for h in hps)
    assert not all(np.dot(h.normal, (-1,0)) <= h.offset for h in hps)
    assert intersect_halfplanes(hps, P).kind == Kind.UNBOUNDED


def test_ninety_width_half_plane():
    result = intersect_halfplanes(wedge_halfplanes(Obs((0,0), 0, 90)), P)
    assert result.kind == Kind.UNBOUNDED
    assert len(wedge_halfplanes(Obs((0,0), 0, 90))) == 1


@pytest.mark.parametrize('hps,kind,feasible', [
    ([], Kind.UNBOUNDED, (0,0)),
    ([HP((1,0),1)], Kind.UNBOUNDED, (0,0)),
    ([HP((1,0),1),HP((-1,0),1)], Kind.UNBOUNDED, (0,0)),
    ([HP((1,0),0),HP((-1,0),0)], Kind.UNBOUNDED, (0,0)),
    ([HP((1,0),0),HP((-1,0),-1)], Kind.EMPTY, None),
    ([HP((1,0),0),HP((-1,0),0),HP((0,1),0),HP((0,-1),0)], Kind.POINT, (0,0)),
    ([HP((1,0),10),HP((-1,0),0),HP((0,1),0),HP((0,-1),0)], Kind.SEGMENT, (3,0)),
    ([HP((1,0),10),HP((-1,0),0),HP((0,1),1),HP((0,-1),0)], Kind.POLYGON, (3,.5)),
    ([HP((1,0),1),HP((-1,0),0),HP((0,1),1e-7),HP((0,-1),0)], Kind.POLYGON, (.5,5e-8)),
])
def test_halfplane_classification(hps, kind, feasible):
    region = intersect_halfplanes(hps, P)
    assert region.kind == kind
    if feasible is not None:
        assert all(np.dot(h.normal, feasible) <= h.offset+1e-12 for h in hps)
    if kind == Kind.UNBOUNDED:
        v = np.array(region.recession_direction)
        assert np.linalg.norm(v) > .9
        for t in (0., 1., 1e7):
            p = np.array(region.feasible_point)+t*v
            assert all(np.dot(h.normal, p)-h.offset <= 1e-7 for h in hps)
    if kind == Kind.EMPTY:
        assert diameter(region).length is None


@pytest.mark.parametrize('obs,kind,expected', [
    ([Obs((-1,0),0,0), Obs((0,-1),90,0)], Kind.POINT,0),
    ([Obs((0,0),0,0), Obs((10,0),180,0)], Kind.SEGMENT,10),
    ([Obs((0,0),180), Obs((10,0),0)], Kind.EMPTY,None),
    ([Obs((0,0),0)]*7, Kind.UNBOUNDED,math.inf),
])
def test_observation_classifications(obs, kind, expected):
    r = solve(obs, P)
    assert r.region.kind == kind
    if expected is None:
        assert r.diameter.length is None
        assert r.coverage.status == 'NOT_APPLICABLE'
    else:
        assert r.diameter.length == pytest.approx(expected)
    for v in r.region.vertices:
        assert all(raw_member(m, v) for m in obs)


@pytest.mark.parametrize('a,eps', [(500,1),(1,10),(1000,30)])
def test_orthogonal_closed_form_ccw(a, eps):
    t = math.tan(math.radians(eps))
    v1 = (a*t/(1-t),)*2
    v3 = (-a*t/(1+t),)*2
    v2 = (a*t*(1-t)/(1+t*t), -a*t*(1+t)/(1+t*t))
    v4 = v2[::-1]
    vertices = convex_hull((v1,v2,v3,v4), P)
    signed = sum(vertices[i][0]*vertices[(i+1)%4][1]-vertices[i][1]*vertices[(i+1)%4][0] for i in range(4))
    assert signed > 0
    result = solve([Obs((-a,0),0,eps), Obs((0,-a),90,eps)], P)
    expected = 2*math.sqrt(2)*a*t/(1-t*t)
    assert result.diameter.length == pytest.approx(expected, rel=1e-9)
    assert result.area_m2 == pytest.approx(4*a*a*t*t/(1-t**4), rel=1e-9)
    assert diameter(Region(Kind.POLYGON, vertices)).length == pytest.approx(expected)
    assert result.minimum_circle.radius == pytest.approx(expected/2)
    assert all(min(math.dist(v,w) for w in vertices) < 1e-7 for v in result.region.vertices)


@pytest.mark.parametrize('seed', range(6))
def test_calipers_independent_all_pairs(seed):
    points = np.random.default_rng(seed).normal(size=(30,2))
    hull = convex_hull(points, P)
    result = diameter(Region(Kind.POLYGON, hull))
    assert result.length == pytest.approx(brute_diameter(points))


def test_square_parallel_ties_and_collinear_interior():
    hull = convex_hull([(0,0),(1,0),(2,0),(2,2),(0,2),(0,0)], P)
    assert len(hull) == 4
    d = diameter(Region(Kind.POLYGON,hull))
    assert d.length == pytest.approx(math.sqrt(8))
    assert d.indices == (0,2)


@pytest.mark.parametrize('scale,shift', [(1., (0., 0.)),
                                       (1e-6, (0., 0.)),
                                       (1e6, (2e6, -2e6))])
def test_hull_merges_near_duplicates_and_collinear_vertices(scale, shift):
    from fractions import Fraction
    from models.q1q2.circle import minimum_circle, diameter_circle_cover
    corners = [(-1., -1.), (1., -1.), (1., 1.), (-1., 1.)]
    # Noisy edge midpoint and corner, plus a duplicate closing vertex.
    noise = P.length(2*scale)/8/scale
    raw = corners + [(0., -1.-noise), (1.+noise, 1.),
                     (-1.-noise, -1.), corners[0]]
    raw = [tuple(np.asarray(shift)+scale*np.asarray(p)) for p in raw]
    hull = convex_hull(raw, P)
    assert len(hull) == 4
    assert hull[0] == min(hull)
    assert len(set(hull)) == len(hull)
    for order in (raw[::-1], raw[2:]+raw[:2]):
        assert convex_hull(order, P) == hull
    exact = [tuple(map(Fraction.from_float, p)) for p in hull]
    for i in range(4):
        a, b, c = exact[i], exact[(i+1) % 4], exact[(i+2) % 4]
        assert (b[0]-a[0])*(c[1]-b[1])-(b[1]-a[1])*(c[0]-b[0]) > 0
    region = Region(Kind.POLYGON, hull)
    d = diameter(region)
    tolerance = P.length(3*scale)
    assert abs(d.length-brute_diameter(raw)) <= tolerance
    assert abs(minimum_circle(hull, 0).radius-math.sqrt(2)*scale) <= tolerance
    assert diameter_circle_cover(region, d, P, minimum_circle(region.vertices, seed=0)).status != 'NO'


@pytest.mark.parametrize('width', [1e-7, 1e-12, 1e-15])
def test_normalization_preserves_genuine_thin_polygon(width):
    corners = [(0., 0.), (1., 0.), (1., width), (0., width)]
    assert convex_hull(corners, P) == tuple(corners)
    region = intersect_halfplanes([HP((1, 0), 1), HP((-1, 0), 0),
                                   HP((0, 1), width), HP((0, -1), 0)], P)
    assert region.kind == Kind.POLYGON
    assert len(region.vertices) == 4


def test_square_wedges_four_normalized_vertices():
    # Same observations as the independent benchmark's square_wedges case.
    observations = [Obs((-1, -1), 45, 45), Obs((1, 1), 225, 45)]
    result = solve(observations, P)
    assert result.region.kind == Kind.POLYGON
    assert len(result.region.vertices) == 4
    assert result.region.vertices[0] == min(result.region.vertices)
    assert result.diameter.length == pytest.approx(2*math.sqrt(2), abs=P.length(3))
    assert result.minimum_circle.radius == pytest.approx(math.sqrt(2), abs=P.length(3))
    assert result.coverage.status == 'YES'


@pytest.mark.parametrize('policy', [NumericPolicy(length_abs=1e-8, relative=0),
                                   NumericPolicy(length_abs=0, relative=1e-8)])
def test_normalization_obeys_absolute_and_relative_policy(policy):
    points = [(0., 0.), (1., -1e-9), (2., 0.), (2., 2.), (0., 2.)]
    assert len(convex_hull(points, NumericPolicy(length_abs=0, relative=0))) == 5
    assert len(convex_hull(points, policy)) == 4


def test_deque_against_independent_line_systems():
    normals = np.array([(math.cos(a),math.sin(a)) for a in np.linspace(0,2*math.pi,9,endpoint=False)])
    offsets = np.array([1,1.1,.9,1.2,1.,.95,1.05,1.2,.9])
    hps = [HP(tuple(n),b) for n,b in zip(normals,offsets)]
    expected = []
    for i,j in combinations(range(len(hps)),2):
        matrix = normals[[i,j]]
        if abs(np.linalg.det(matrix)) < 1e-12:
            continue
        p = np.linalg.solve(matrix, offsets[[i,j]])
        if np.all(normals @ p <= offsets+1e-10):
            expected.append(p)
    result = intersect_halfplanes(hps,P)
    assert result.kind == Kind.POLYGON
    assert len(result.vertices) == len(expected)
    assert all(min(math.dist(v,p) for p in expected) < 1e-8 for v in result.vertices)


def test_tighter_duplicate_and_order_invariance():
    hps = [HP((1,0),2),HP((1,0),1),HP((-1,0),0),HP((0,1),1),HP((0,-1),0)]
    r1 = intersect_halfplanes(hps,P)
    r2 = intersect_halfplanes(list(reversed(hps)),P)
    assert diameter(r1).length == pytest.approx(math.sqrt(2))
    assert set(r1.vertices) == set(r2.vertices)


@pytest.mark.parametrize('scale,offset,rotation', [(1,(1999000,1999000),0),(.001,(0,0),37),(1000,(100,20),123)])
def test_similarity(scale,offset,rotation):
    from models.q1q2.diagnostics import equilateral_case
    obs = equilateral_case()['measurements']
    a = math.radians(rotation)
    matrix = np.array(((math.cos(a),-math.sin(a)),(math.sin(a),math.cos(a))))
    transformed = [Obs(tuple(np.array(offset)+scale*(matrix @ m.position)), m.bearing_deg+rotation,1) for m in obs]
    result = solve(transformed,P)
    assert result.region.kind == Kind.POLYGON
    assert result.diameter.length == pytest.approx(20*scale,rel=1e-6)
    assert result.minimum_circle.radius == pytest.approx(20*scale/math.sqrt(3),rel=1e-6)
    assert result.coverage.status == 'NO'


def test_metadata_and_same_point_diagnostic():
    with pytest.raises(ValueError):
        solve([Obs((0,0),0,channel=1),Obs((1,0),0,channel=2)],P)
    result = solve([Obs((0,0),0),Obs((0,0),.5)],P)
    assert 'SAME_POSITION_DIFFERENT_BEARING' in result.diagnostics
