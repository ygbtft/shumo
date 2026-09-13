import math
from dataclasses import replace
import numpy as np
import pytest
from algorithms.q1q2.geometry import NumericPolicy, BearingMeasurement as Obs
from algorithms.q1q2.feasible import PhysicsConfig, build_source_set, Feedback
from algorithms.q1q2.q2 import (SourceSamples, SearchConfig, score_point, sample_sources,
    short_baseline_lower_bound, select_second_point, candidate_bbox, boundary_point)
from algorithms.q1q2.diagnostics import clearance_summary

P = NumericPolicy()


def source():
    return build_source_set(Obs((0.,0.),0.),PhysicsConfig(),P)


def sample(points):
    return SourceSamples(tuple(tuple(p) for p in points),0,(9,25))


def bearing_arc_oracle(points,q,eps):
    near = [p for p in points if math.dist(p,q)<=5]
    direction = [p for p in points if math.dist(p,q)>5]
    def diam(pts):
        return max((math.dist(a,b) for a in pts for b in pts),default=0.)
    best = diam(near)
    angles = [math.degrees(math.atan2(p[1]-q[1],p[0]-q[0])) % 360 for p in direction]
    events = sorted(set((a+sign*eps)%360 for a in angles for sign in (-1,1)))
    candidates = events[:]
    for i,a in enumerate(events):
        b = events[(i+1)%len(events)]+(360 if i==len(events)-1 else 0)
        candidates.append(((a+b)/2)%360)
    for beta in candidates:
        pts = [p for p,a in zip(direction,angles) if abs((a-beta+180)%360-180)<=eps]
        best = max(best,diam(pts))
    return best


@pytest.mark.parametrize('q',[(750,400),(750,-400),(100,0),(999,1)])
def test_pair_score_independent_bearing_event_oracle(q,assert_source_members):
    ss = source()
    pts = [(r*math.cos(math.radians(a)),r*math.sin(math.radians(a)))
           for r in (10,100,500,999,1000,1200,1499) for a in (-.99,0,.99)]
    result = score_point(ss,q,sample(pts),SearchConfig(block_size=4))
    assert result.J_hat == pytest.approx(bearing_arc_oracle(pts,q,1),abs=1e-8)
    assert result.witness.actual_legal
    assert_source_members(ss.first,ss.physics,[result.witness.x,result.witness.y])
    for world in result.witness.worlds:
        p = world['p']
        r1, r2 = math.dist(p,ss.first.position), math.dist(p,q)
        assert world['first_distance_m'] == pytest.approx(r1)
        assert world['second_distance_m'] == pytest.approx(r2)
        assert world['rho'] == pytest.approx(max(ss.physics.rho_lo,r1))
        assert 5 < r1 <= world['rho'] <= 1500
        assert r2 <= world['rho']+1e-9
        if result.witness.branch == 'direction':
            assert r2 > 5
            theta = math.degrees(math.atan2(p[1]-q[1],p[0]-q[0]))
            assert abs(math.remainder(theta-result.witness.common_bearing_deg,360.)) <= 1+1e-10
        else:
            assert r2 <= 5+1e-9


def test_wrap_touch_at_zero_common_reading():
    # First station is different from q, preserving fixed-error semantics.
    ss = build_source_set(Obs((-100.,0.),0.,2.),PhysicsConfig(),P)
    pts = [(100*math.cos(math.radians(a)),100*math.sin(math.radians(a))) for a in (359,1)]
    result = score_point(ss,(0,0),sample(pts),SearchConfig())
    assert result.J_hat == pytest.approx(math.dist(*pts))
    assert abs((result.witness.common_bearing_deg+180)%360-180) < 1e-10


def test_single_direction_sample_has_zero_not_absent_branch():
    score = score_point(source(),(750,400),sample([(1000,0)]),SearchConfig())
    assert score.J_hat == 0 and score.direction_score_m == 0
    assert score.witness is not None
    assert score.near_score_m is None


def test_same_point_preserves_full_source_sample_diameter():
    ss = source()
    pts = [(5.001,0),(500,0),(1500,0)]
    result = score_point(ss,(0,0),sample(pts),SearchConfig())
    assert result.J_hat == pytest.approx(1494.999)
    assert result.witness.common_bearing_deg == ss.first.bearing_deg


def test_near_direction_separation_at_five():
    ss = source()
    points = [(95,0),(100,0),(105,0),(105.00001,0)]
    result = score_point(ss,(100,0),sample(points),SearchConfig())
    assert result.near_score_m == pytest.approx(10)
    assert result.direction_score_m == 0
    assert result.J_hat == pytest.approx(10)


def test_continuous_line_fixture_has_interior_worst_endpoint():
    # Artificial bounded line F from arena clipping, explicitly separate from the standard ±1° case.
    physics = PhysicsConfig(arena_center=(55.,0.),arena_radius=45.)
    ss = build_source_set(Obs((0,0),0,0),physics,P)
    H,a,b,delta = 20.,10.,100.,math.radians(2)
    inner = max(a,H*(b-H*math.tan(delta))/(H+b*math.tan(delta)))
    expected = b-inner
    pts = [(a,0),(b,0),(inner+1e-9,0)]
    result = score_point(ss,(0,H),sample(pts),SearchConfig())
    assert result.J_hat == pytest.approx(expected,abs=1e-7)
    assert result.J_hat > 15
    endpoints = score_point(ss,(0,H),sample([(a,0),(b,0)]),SearchConfig())
    assert endpoints.J_hat == 0


def test_open_endpoint_supremum_fixture(assert_source_members):
    ss = build_source_set(Obs((0,0),0,0),PhysicsConfig(),P)
    for offset in (.001,.00001):
        pts = [(5+offset,0),(95-offset,0),(95,0),(100,0),(105,0),(105+offset,0),(1500,0)]
        assert_source_members(ss.first,ss.physics,pts)
        result = score_point(ss,(100,0),sample(pts),SearchConfig())
        assert result.direction_score_m == pytest.approx(1395-offset)
        assert result.near_score_m == pytest.approx(10)
        assert result.J_hat < 1395
        assert 1395-result.J_hat <= offset*1.001


def test_nested_sources_and_score_monotonicity(assert_source_members):
    ss = source()
    coarse,medium = sample_sources(ss, 0, SearchConfig().source_grids, inward=1e-7, second_half_width_deg=1.),sample_sources(ss, 1, SearchConfig().source_grids, inward=1e-7, second_half_width_deg=1.)
    assert set(coarse.points) <= set(medium.points)
    fine = sample_sources(ss, 2, SearchConfig().source_grids, inward=1e-7, second_half_width_deg=1.)
    assert set(medium.points) <= set(fine.points)
    for samples in (coarse,medium,fine):
        assert_source_members(ss.first,ss.physics,samples.points)
        assert ss.contains(samples.points).all()
    cfg = SearchConfig()
    q = (750,400)
    assert score_point(ss,q,medium,cfg).J_hat >= score_point(ss,q,coarse,cfg).J_hat
    narrow = score_point(ss,q,coarse,replace(cfg,second_half_width_deg=.5)).J_hat
    assert score_point(ss,q,coarse,cfg).J_hat >= narrow


def test_pair_refinement_never_lowers_legal_score(assert_source_members):
    ss = source()
    samples = sample_sources(ss, 0, SearchConfig().source_grids, inward=1e-7, second_half_width_deg=1.)
    plain = score_point(ss,(750,400),samples,SearchConfig())
    refined = score_point(ss,(750,400),samples,SearchConfig(refine_pairs=True,pair_rounds=2,pair_starts=2))
    assert refined.J_hat >= plain.J_hat
    assert refined.local_improvement_m >= 0
    assert_source_members(ss.first,ss.physics,[p for w in refined.top_pairs for p in (w.x,w.y)])
    for w in refined.top_pairs:
        assert w.distance_m == pytest.approx(math.dist(w.x,w.y))
        for p in (w.x,w.y):
            r = math.dist(p,(750,400))
            if w.branch == 'near':
                assert r <= 5+1e-9
            else:
                theta = math.degrees(math.atan2(p[1]-400,p[0]-750))
                assert r > 5
                assert abs(math.remainder(theta-w.common_bearing_deg,360.)) <= 1+1e-10


def test_short_baseline_analytic_lower_bound():
    ss = source()
    bound = short_baseline_lower_bound(ss,500,1500,10)
    assert bound['lower_bound_m'] == 1000
    assert bound['angle_bound_deg'] == pytest.approx(math.degrees(math.asin(.02)+math.asin(1/150)))
    assert bound['angle_bound_deg'] < 2
    assert short_baseline_lower_bound(ss,500,1500,495) is None
    assert short_baseline_lower_bound(ss,500,1500,100) is None
    for angle in np.linspace(0,2*math.pi,31):
        q = (10*math.cos(angle),10*math.sin(angle))
        a = math.atan2(-q[1],500-q[0])
        b = math.atan2(-q[1],1500-q[0])
        assert abs(a-b) <= math.radians(2)


def test_numerically_close_is_not_same_station():
    ss = source()
    result = score_point(ss,(1e-12,0),sample([(100,0),(1500,0)]),SearchConfig())
    assert result.near_possibility != 'IMPOSSIBLE_BY_FIRST_DIRECTION'


def test_outer_bbox_has_physical_disk_justification_and_boundary_rays():
    ss = source()
    cfg = SearchConfig()
    box = candidate_bbox(ss,cfg)
    p = ss.actual_point
    radius = max(1000,math.dist(p,ss.first.position))
    assert box == pytest.approx((p[0]-radius,p[0]+radius,p[1]-radius,p[1]+radius))
    upper,lower = boundary_point(ss,math.pi/4,cfg),boundary_point(ss,-math.pi/4,cfg)
    assert upper[0] == pytest.approx(lower[0],abs=1e-5)
    assert upper[1] == pytest.approx(-lower[1],abs=1e-5)


def test_time_budget_outputs_unassessed_spread_as_null():
    result = select_second_point(source(),SearchConfig(time_budget_s=0))
    assert result.stop_reason == 'TIME_BUDGET'
    assert result.sensitivity_range_m is None
    assert result.completed_stages == ()
    assert result.status == 'NUMERICAL_UNRESOLVED'


@pytest.mark.parametrize('width',[0,45,90,-1])
def test_unsupported_q2_angle(width):
    with pytest.raises(ValueError):
        SearchConfig(second_half_width_deg=width)


def test_near_clearance_is_analytic_even_without_sample_cover():
    summary = clearance_summary(source(),(100,0),Feedback('near'),sample([]),P)
    assert summary.status == 'ON_SITE'
    assert summary.evidence == 'near_analytic'
    assert summary.R_hat is None
    assert summary.r_U == 5
    assert summary.subsequent_total_seconds == 5


def test_small_sample_circle_is_not_clearance_guarantee():
    ss = source()
    summary = clearance_summary(ss,(0,0),Feedback('direction',0),sample([(1000,0)]),P)
    assert summary.R_hat == 0
    assert summary.status == 'NOT_YET_GUARANTEED'
    assert summary.reason == 'insufficient_evidence'


def test_impossible_common_pair_clearance_witness():
    ss = source()
    summary = clearance_summary(ss,(100,0),Feedback('direction',0),sample([(200,0),(1000,0)]),P)
    assert summary.status == 'NOT_YET_GUARANTEED'
    assert summary.evidence == 'impossible_pair'
    assert math.dist(*summary.impossibility_witness) > 40


def test_move_to_conservative_cover_center():
    physics = PhysicsConfig(arena_center=(1000,0),arena_radius=10)
    ss = build_source_set(Obs((0,0),0),physics,P)
    q = (750,400)
    beta = math.degrees(math.atan2(-400,250))%360
    summary = clearance_summary(ss,q,Feedback('direction',beta),sample([(1000,0)]),P)
    assert summary.status == 'MOVE_TO_COVER_CENTER'
    assert summary.r_U < 20
    assert summary.subsequent_total_seconds == pytest.approx(math.dist(q,summary.cover_center)/5+5)
    assert summary.must_move_proven


def test_direction_can_clear_on_site():
    physics = PhysicsConfig(arena_center=(1000,0),arena_radius=1)
    ss = build_source_set(Obs((0,0),0),physics,P)
    q = (1000,12)
    summary = clearance_summary(ss,q,Feedback('direction',270),sample([(1000,0)]),P)
    assert summary.status == 'ON_SITE'
    assert summary.H_U < 20


def test_same_feedback_triangle_impossibility():
    ss = build_source_set(Obs((-1100,0),.9),PhysicsConfig(),P)
    points = [(0,0),(36,0),(18,18*math.sqrt(3))]
    summary = clearance_summary(ss,(-1000,0),Feedback('direction',.9),sample(points),P)
    assert summary.status == 'NOT_YET_GUARANTEED'
    assert summary.evidence == 'impossible_triple'
    assert summary.R_hat == pytest.approx(12*math.sqrt(3))


def test_small_search_records_full_grid_and_shared_final_precision():
    physics = PhysicsConfig(arena_center=(55,0),arena_radius=45)
    ss = build_source_set(Obs((0,0),0,0),physics,P)
    cfg = SearchConfig(station_steps_m=(500.,250.),source_grids=((3,5),(5,9),(9,17)),
                       starts=2,pair_starts=2,pair_rounds=1,station_initial_step_m=50,
                       station_min_step_m=25,boundary_step_deg=90,time_budget_s=60)
    result = select_second_point(ss,cfg)
    assert result.status == 'NUMERICAL_CANDIDATE'
    assert result.q_best != ss.first.position
    assert result.candidate_check.status in ('IN','BOUNDARY')
    grids = [r for r in result.refinement_history if r['stage']=='grid']
    assert len(grids) == 2 and all(r['complete'] and r['scanned']==r['planned'] for r in grids)
    assert len({r.score.sample_count for r in result.alternatives}) == 1
    assert result.sensitivity_range_m is not None
    assert result.objective == 'physical_posterior_worst_diameter'
