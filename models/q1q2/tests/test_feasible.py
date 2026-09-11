import math
import numpy as np
import pytest
from models.q1q2.geometry import BearingMeasurement as Obs, NumericPolicy
from models.q1q2.feasible import (PhysicsConfig, build_source_set, check_candidate,
    posterior_contains, posterior_outer_polygon, Feedback)
from models.q1q2.q2 import sample_sources, SearchConfig, select_second_point

P = NumericPolicy()


def standard(width=1., physics=None):
    return build_source_set(Obs((0.,0.),0.,width),physics or PhysicsConfig(),P)


def four_disk_residual(q,epsilon=1.,a=5.,r0=1000.):
    c,s = math.cos(math.radians(epsilon)),math.sin(math.radians(epsilon))
    return max(math.dist(q,(r*c,sign*r*s))-r0 for r in (a,r0) for sign in (-1,1))


def nearby_sector_witness(first, physics, witness, step_m=1e-5):
    # This test helper is for an unclipped sector, not arbitrary target-circle intersections.
    assert math.dist(first.position, physics.arena_center)+physics.rho_hi <= physics.arena_radius
    r = math.dist(witness, first.position)
    if abs(r-physics.rho_hi) <= 1e-8:
        r = physics.rho_hi-step_m
    elif abs(r-physics.near_radius) <= 1e-8:
        r = physics.near_radius+step_m
    angle = math.degrees(math.atan2(witness[1]-first.position[1], witness[0]-first.position[0]))
    alpha = math.remainder(angle-first.bearing_deg, 360.)
    inset = min(1e-7, first.half_width_deg/2)
    alpha = min(first.half_width_deg-inset, max(-first.half_width_deg+inset, alpha))
    theta = math.radians(first.bearing_deg+alpha)
    return (first.position[0]+r*math.cos(theta), first.position[1]+r*math.sin(theta))


@pytest.mark.parametrize('q',[(0,0),(750,400),(750,-400),(500,0),(-1,0),(1100,0),(500,900),(1500,500)])
def test_four_disks_independent_membership(q):
    result = check_candidate(standard(),q,False,P)
    residual = four_disk_residual(q)
    if q == (0,0):
        assert result.status == 'IN'
    elif residual < -1e-6:
        assert result.status == 'IN'
    elif residual > 1e-6:
        assert result.status == 'OUT'
    else:
        assert result.status == 'BOUNDARY'


def test_four_disks_grid_and_outer_radius_invariance():
    first, second = standard(), standard(physics=PhysicsConfig(rho_hi=1000))
    for x in np.linspace(-50,1100,13):
        for y in np.linspace(-1050,1050,15):
            q = (float(x),float(y))
            expected = four_disk_residual(q)
            for ss in (first,second):
                status = check_candidate(ss,q,False,P).status
                if abs(expected) > 1e-5:
                    assert (status == 'IN') == (expected < 0)


def test_axis_boundary_inside_outside():
    e = math.radians(1)
    limit = min(2000*math.cos(e),5*math.cos(e)+math.sqrt(1000**2-25*math.sin(e)**2))
    ss = standard()
    assert check_candidate(ss,(limit-.001,0),False,P).status == 'IN'
    assert check_candidate(ss,(limit+.001,0),False,P).status == 'OUT'
    assert check_candidate(ss,(limit,0),False,P).status == 'BOUNDARY'


def test_hand_calculation_uses_analytic_not_rounded_486_5():
    e = math.radians(1)
    q = (750,400)
    actual = math.dist(q,(1000*math.cos(e),-1000*math.sin(e)))
    expected = math.sqrt(1722500-2000*(750*math.cos(e)-400*math.sin(e)))
    assert actual == pytest.approx(expected,abs=1e-10)
    assert actual != pytest.approx(486.5,abs=.001)
    result = check_candidate(standard(),q,True,P)
    assert result.status == 'IN' and result.direction_status == 'IN'
    assert result.g_high == pytest.approx(750**2+400**2-2000*(750*math.cos(e)-400*math.sin(e)))
    assert result.distance_to_closure > 386


def test_first_station_is_in_both_sets_despite_closure_distance_five():
    ss = standard()
    for direction in (False,True):
        check = check_candidate(ss,(0,0),direction,P)
        assert check.status == 'IN'
        assert check.direction_status == 'IN'
    assert check_candidate(ss,(100,0),True,P).status == 'OUT'


@pytest.mark.parametrize('s,angle,expected', [((1800,0),180,'OK'),((2200,0),180,'OK'),
                                           ((4000,0),180,'INCONSISTENT_FIRST_OBSERVATION'),
                                           ((1805,0),0,'INCONSISTENT_FIRST_OBSERVATION')])
def test_target_boundary_and_outside_first(s,angle,expected,assert_source_members):
    ss = build_source_set(Obs(s,angle),PhysicsConfig(),P)
    assert ss.status == expected
    if expected == 'OK':
        assert check_candidate(ss,s,True,P).status == 'IN'
        samples = sample_sources(ss, 0, SearchConfig().source_grids, inward=1e-7, second_half_width_deg=1.)
        assert len(samples.points) > 0
        assert_source_members(ss.first,ss.physics,samples.points)


def test_f_only_at_excluded_five_is_empty():
    # Arena disk tangent to the first station's 5m circle from the inside of the hole.
    physics = PhysicsConfig(arena_radius=1.,arena_center=(4.,0.))
    ss = build_source_set(Obs((0,0),0),physics,P)
    assert ss.status == 'INCONSISTENT_FIRST_OBSERVATION'


def test_legal_single_radial_tangent_not_discarded_by_zero_area(assert_source_members):
    physics = PhysicsConfig(arena_radius=100.,arena_center=(110.,100.),rho_lo=1000,rho_hi=1500)
    ss = build_source_set(Obs((0,0),0,0),physics,P)
    assert ss.status == 'OK'
    assert ss.actual_point == pytest.approx((110,0))
    assert_source_members(ss.first,ss.physics,[(110,0)])
    assert ss.contains([(110,0)])[0]


def test_far_source_radius_coupling_not_fixed_1000_disks():
    ss = standard()
    assert check_candidate(ss,(0,0),False,P).status == 'IN'
    assert math.dist((0,0),(1500,0)) > 1000
    # A nearby distinct point is also legal despite being >1000m from the far source.
    assert check_candidate(ss,(100,0),False,P).status == 'IN'
    assert math.dist((100,0),(1500,0)) > 1000


@pytest.mark.parametrize('q',[(-100,500),(1200,0)])
def test_candidate_convexity_and_separating_actual_world(q,assert_source_members):
    ss = standard()
    a,b = np.array((750,400)),np.array((750,-400))
    for t in np.linspace(0,1,9):
        assert check_candidate(ss,tuple((1-t)*a+t*b),False,P).status == 'IN'
    c = check_candidate(ss,q,False,P)
    assert c.status == 'OUT'
    if c.witness_attained:
        witness = c.extremal_source
    else:
        witness = nearby_sector_witness(ss.first,ss.physics,c.extremal_source)
        assert math.dist(witness,c.extremal_source) < 2e-5
    assert_source_members(ss.first,ss.physics,[witness])
    r = math.dist(witness,ss.first.position)
    assert ss.physics.near_radius < r <= ss.physics.rho_hi
    rho = max(ss.physics.rho_lo,r)
    assert r <= rho <= ss.physics.rho_hi
    assert math.dist(q,witness) > rho+1e-9
    assert ss.contains([witness])[0]  # Secondary reference, not the membership oracle.


@pytest.mark.parametrize('rho',[1000.,1250.,1500.])
def test_known_radius_rebuilds_source_and_candidate(rho):
    ss = standard(physics=PhysicsConfig(rho_lo=rho,rho_hi=rho))
    assert ss.radial_interval(0).high == rho
    assert ss.physics.rho_lo == rho
    assert check_candidate(ss,(0,0),False,P).status == 'IN'


def test_transformed_physics():
    angle = math.radians(37)
    rotation = np.array(((math.cos(angle),-math.sin(angle)),(math.sin(angle),math.cos(angle))))
    shift = np.array((1200,-600))
    scale = 2.
    physics = PhysicsConfig(rho_lo=2000,rho_hi=3000,near_radius=10,clearance_radius=40,
                            arena_radius=3600,arena_center=tuple(shift))
    ss = build_source_set(Obs(tuple(shift),37),physics,P)
    for q in ((750,400),(1100,0),(500,0)):
        transformed = tuple(shift+scale*(rotation @ q))
        expected = 'IN' if four_disk_residual(q) < 0 else 'OUT'
        assert check_candidate(ss,transformed,False,P).status == expected
        assert check_candidate(standard(),q,False,P).status == expected


def test_budget_empty_premises():
    ss = standard()
    for b in (0,1,100):
        assert math.dist(ss.first.position,ss.first.position) <= b
        assert check_candidate(ss,ss.first.position,True,P).status == 'IN'
    with pytest.raises(ValueError):
        SearchConfig(movement_budget_m=-1)
    result = select_second_point(ss,SearchConfig(movement_budget_m=0))
    assert result.status == 'NO_DISTINCT_CANDIDATE'
    outside = build_source_set(Obs((2200,0),180),PhysicsConfig(),P)
    result = select_second_point(outside,SearchConfig(movement_budget_m=10,restrict_action_to_arena=True))
    assert result.status == 'EMPTY_ADMISSIBLE_SET'
    assert 'ADDED_ARENA' in result.stop_reason


def test_outer_polygon_tangents_contain_independent_actual_points():
    ss = standard()
    q = (750,400)
    beta = math.degrees(math.atan2(-400,250)) % 360
    feedback = Feedback('direction',beta,1)
    outer = posterior_outer_polygon(ss,q,feedback)
    assert outer.vertices
    # Raw polar/angle oracle; no posterior_contains in construction of expected members.
    points = []
    for r in np.linspace(5.01,1500,301):
        for a in np.linspace(-1,1,15):
            p = (r*math.cos(math.radians(a)),r*math.sin(math.radians(a)))
            angle = math.degrees(math.atan2(p[1]-q[1],p[0]-q[0]))
            if math.dist(p,q)>5 and abs((angle-beta+180)%360-180)<=1:
                points.append(p)
    assert points
    vertices = np.array(outer.vertices)
    for p in points:
        for i,v in enumerate(vertices):
            edge = vertices[(i+1)%len(vertices)]-v
            offset = np.array(p)-v
            assert edge[0]*offset[1]-edge[1]*offset[0] >= -1e-5


def test_near_and_same_station_feedback_semantics():
    ss = standard()
    points = [(100,0),(105,0),(105.001,0),(5,0)]
    mask = posterior_contains(ss,(100,0),Feedback('near'),points,P)
    assert mask.tolist() == [True,True,False,False]
    assert not posterior_contains(ss,(0,0),Feedback('direction',.1),[(100,0)],P)[0]
    with pytest.raises(ValueError,match='GUARANTEE_MISMATCH'):
        Feedback('no_signal')


@pytest.mark.parametrize('radius',[5.,1500.])
@pytest.mark.parametrize('alpha',[-1.,1.])
def test_limit_witness_moves_into_correct_radial_and_angular_sides(radius,alpha,assert_source_members):
    first = Obs((12.,-9.),359.)
    physics = PhysicsConfig(arena_center=first.position)
    noisy_radius = math.nextafter(radius,math.inf)
    theta = math.radians(first.bearing_deg+alpha)
    endpoint = (first.position[0]+noisy_radius*math.cos(theta),
                first.position[1]+noisy_radius*math.sin(theta))
    witness = nearby_sector_witness(first,physics,endpoint)
    r = math.dist(witness,first.position)
    assert r == pytest.approx(radius+(1e-5 if radius == 5 else -1e-5),abs=1e-10)
    assert 5 < r < 1500
    assert math.dist(endpoint,witness) < 2e-5
    assert_source_members(first,physics,[witness])


@pytest.mark.parametrize('p',[(5.,0.),(1500.00001,0.),(100.,2.),(math.nan,0.)])
def test_independent_source_oracle_rejects_invalid_points(p,assert_source_members):
    with pytest.raises(AssertionError):
        assert_source_members(Obs((0,0),0),PhysicsConfig(),[p])


def test_independent_source_oracle_checks_arena_and_closed_endpoints(assert_source_members):
    first = Obs((0,0),0)
    assert_source_members(first,PhysicsConfig(),[(1500.,0.),(5.00001,0.)])
    physics = PhysicsConfig(arena_center=(100,0),arena_radius=10)
    with pytest.raises(AssertionError):
        assert_source_members(first,physics,[(500.,0.)])
