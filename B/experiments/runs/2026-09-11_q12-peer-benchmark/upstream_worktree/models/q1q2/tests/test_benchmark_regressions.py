"""Independent witnesses for production bugs found by the benchmark.

Fixtures live here so tests neither require nor modify benchmark artifacts.
"""
import math
from decimal import Decimal, localcontext

import numpy as np
import pytest

from models.q1q2.geometry import (BearingMeasurement, HalfPlane, NumericPolicy,
                                  RegionKind, intersect_halfplanes, wedge_halfplanes)
from models.q1q2.feasible import PhysicsConfig, build_source_set, check_candidate
from models.q1q2.q2 import SearchConfig, sample_sources, score_point

POLICY = NumericPolicy()


def assert_unbounded_witness(hps):
    result = intersect_halfplanes(hps, POLICY)
    assert result.status == 'OK'
    assert result.kind == RegionKind.UNBOUNDED
    p, v = np.asarray(result.feasible_point), np.asarray(result.recession_direction)
    assert np.linalg.norm(v) == pytest.approx(1.)
    for hp in hps:
        assert np.dot(hp.normal, v) <= 1e-14
        for t in (0., 1., 100000.):
            assert np.dot(hp.normal, p+t*v)-hp.offset <= 1e-8


@pytest.mark.parametrize('position', [(3., -7.), (12345., -6789.), (0., 0.)])
@pytest.mark.parametrize('bearing', [0., 1., 45., 89., 123., 180., 270., 359.])
@pytest.mark.parametrize('width', [0., 1e-10, 1., 45., 89., 90.])
def test_single_wedge_reaches_recession_check(position, bearing, width):
    assert_unbounded_witness(wedge_halfplanes(BearingMeasurement(position, bearing, width)))


@pytest.mark.parametrize('constraints', [
    [], [((1, 0), 2)],
    [((0, 1), 2), ((0, -1), -1)],  # strip
    [((0, 1), 2), ((0, -1), -2)],  # line
    [((0, 1), 2), ((0, -1), -2), ((-1, 0), -3)],  # ray
    [((0, 1), 2), ((0, -1), -1), ((-1, 0), -3)],  # half strip
])
@pytest.mark.parametrize('angle', [0., 37., 123.])
def test_unbounded_families_with_transformed_witnesses(constraints, angle):
    a = math.radians(angle)
    rotation = np.array(((math.cos(a), -math.sin(a)), (math.sin(a), math.cos(a))))
    shift = np.array((3., -7.))
    hps = []
    for n, b in constraints:
        n = rotation @ n
        hps.append(HalfPlane(tuple(n), b+float(n @ shift)))
    assert_unbounded_witness(hps)


def test_feasibility_roundoff_fix_does_not_accept_policy_sized_gap():
    result = intersect_halfplanes([HalfPlane((1, 0), 0.),
                                   HalfPlane((-1, 0), -1e-11)], POLICY)
    assert result.kind != RegionKind.UNBOUNDED
    assert result.status == 'NUMERICAL_UNRESOLVED' or result.kind == RegionKind.EMPTY


@pytest.mark.parametrize('a,b,h,eps,reachable', [
    (10, 100, 20, 1, 15.267857142517855),
    (10, 100, 20, .5, 8.035714285535718),
    (10, 100, 20, 2, 26.517857142267857),
    (20, 80, 40, 1, 6.428571428357145),
    (10, 100, 200, 1, 8.035714285535718),
])
def test_segment_angular_contact_matches_continuous_closed_form(a, b, h, eps, reachable):
    ss = build_source_set(BearingMeasurement((0, 0), 0, 0),
                          PhysicsConfig(arena_center=((a+b)/2, 0), arena_radius=(b-a)/2), POLICY)
    config = SearchConfig(second_half_width_deg=eps)
    # Also exercise scoring a default-angle augmented cloud with custom epsilon.
    samples = sample_sources(ss, 0, (0, h))
    result = score_point(ss, (0, h), samples, config)
    inner = max(a, h*math.tan(math.atan(b/h)-math.radians(2*eps)))
    exact = b-inner
    assert result.J_hat >= reachable
    assert result.J_hat == pytest.approx(exact, abs=1e-7)
    x, y = result.witness.x, result.witness.y
    assert a <= x[0] <= b and a <= y[0] <= b
    assert x[1] == y[1] == 0
    assert abs(math.atan2(x[0], h)-math.atan2(y[0], h)) <= math.radians(2*eps)


def test_boundary_enrichment_retains_nested_cloud_and_scores():
    ss = build_source_set(BearingMeasurement((0, 0), 0), PhysicsConfig(), POLICY)
    q = (750., 400.)
    previous, previous_score = set(), 0.
    for level in range(3):
        samples = sample_sources(ss, level, q)
        assert previous.issubset(samples.points)
        score = score_point(ss, q, samples, SearchConfig())
        assert score.J_hat >= previous_score
        assert score.witness.actual_legal
        previous, previous_score = set(samples.points), score.J_hat


@pytest.mark.parametrize('q,width,x,y', [
    ((750, 400), 1., (1366.3097298624427, 23.84902504678052),
     (1499.7715427335875, -26.178609655881644)),
    ((500, 0), 1., (512.2321429235357, 0.), (1499.7715427335875, -26.178609655881644)),
    ((0, 0), 1., (4.999238576766575, -0.08726203394902338),
     (1499.7715427335875, 26.178609655881644)),
    ((500, 2), 1., (512.229713317319, 1.5776688165304342),
     (1499.7715427335875, -26.178609655881644)),
    ((531.6164058668625, -37.33456265993029), .6937341888687443,
     (832.5282567315606, -10.08069957359378), (1499.8900495799196, 18.16147483401648)),
    ((604.0453718438553, 113.91658698480217), .6857184338272723,
     (1152.8638589651239, 13.798184661379164), (1499.8925757159604, -17.951638062917656)),
    ((578.2982087548189, -99.00066818024733), .5130347410040156,
     (1152.9002091714394, -10.323512016657332), (1499.9398678607824, 13.431038633649505)),
    ((230.84488400980555, 160.21338470387042), .724666925448092,
     (1072.7713329197918, 13.568946365579993), (1499.8800260126268, -18.97122993805028)),
    ((430.7447947398914, -15.083389802739655), .9085870744449689,
     (525.5142744940865, -8.334217791691287), (1499.8114007296028, 23.785757051367675)),
])
def test_polar_scores_dominate_independent_reachable_pairs(q, width, x, y, assert_source_members):
    first = BearingMeasurement((0, 0), 0, width)
    physics = PhysicsConfig()
    assert_source_members(first, physics, [x, y])
    angles = [math.atan2(p[1]-q[1], p[0]-q[0]) for p in (x, y)]
    assert abs(math.remainder(angles[1]-angles[0], 2*math.pi)) <= math.radians(2)
    ss = build_source_set(first, physics, POLICY)
    result = score_point(ss, q, sample_sources(ss, 0, q), SearchConfig())
    assert result.J_hat >= math.dist(x, y)
    assert_source_members(first, physics, [result.witness.x, result.witness.y])


@pytest.mark.parametrize('rho', [1000., 1500.])
@pytest.mark.parametrize('q', [(500., 0.), (5., 0.), (10., 0.), (1004.9992246684508, 0.)])
def test_direction_out_returns_actual_near_world(rho, q, assert_source_members):
    ss = build_source_set(BearingMeasurement((0, 0), 0), PhysicsConfig(rho_hi=rho), POLICY)
    result = check_candidate(ss, q, True, POLICY)
    assert result.status == result.direction_status == 'OUT'
    assert result.witness_attained
    assert result.reason == 'near_separating_world'
    assert_source_members(ss.first, ss.physics, [result.extremal_source])
    assert math.dist(q, result.extremal_source) <= 5


@pytest.mark.parametrize('angle', [0., 37., 123., 359.])
@pytest.mark.parametrize('rho', [1000., 1500.])
@pytest.mark.parametrize('q', [(500., 0.), (0., 1000.), (1200., 0.)])
def test_candidate_attainment_distinguishes_closed_edges_and_open_near(angle, rho, q,
                                                                     assert_source_members):
    a = math.radians(angle)
    rotation = np.array(((math.cos(a), -math.sin(a)), (math.sin(a), math.cos(a))))
    shift = np.array((12., -9.))
    station = tuple(shift)
    q = tuple(shift+rotation @ q)
    ss = build_source_set(BearingMeasurement(station, angle),
                          PhysicsConfig(arena_center=station, rho_hi=rho), POLICY)
    for direction in (False, True):
        result = check_candidate(ss, q, direction, POLICY)
        x = result.extremal_source
        assert x is not None
        if result.witness_attained:
            assert_source_members(ss.first, ss.physics, [x])
            with localcontext() as ctx:
                ctx.prec = 70
                d2 = sum((Decimal.from_float(v)-Decimal.from_float(s))**2 for v, s in zip(x, station))
                assert d2 > Decimal(25)
        else:
            assert math.dist(x, station) == pytest.approx(5., abs=1e-10)
        if result.status == 'OUT':
            signal_failure = math.dist(q, x) > max(1000, math.dist(x, station))
            near_failure = direction and result.witness_attained and math.dist(q, x) <= 5+1e-10
            assert signal_failure or near_failure
