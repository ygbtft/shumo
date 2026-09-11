"""Static-review B1–B5 regression paths; scripted search isolates result assembly."""
from dataclasses import replace
import json
import math
import pytest
from models.q1q2 import q2, run
from models.q1q2.adapters import ErrorMode, read_measurements
from models.q1q2.diagnostics import clearance_summary, posterior_area, reassess_old_point
from models.q1q2.feasible import PhysicsConfig, Feedback, build_source_set, check_candidate
from models.q1q2.geometry import BearingMeasurement, NumericPolicy

POLICY = NumericPolicy()


def source(position=(0.,0.), angle=0., physics=None):
    return build_source_set(BearingMeasurement(position,angle),physics or PhysicsConfig(),POLICY)


def test_b1_on_site_circle_contains_outer_vertices_and_independent_source():
    ss = source(physics=PhysicsConfig(arena_center=(1000.,0.),arena_radius=1.))
    q, actual = (1000.,12.), (1000.,0.)
    summary = clearance_summary(ss,q,Feedback('direction',270),q2.SourceSamples((actual,),0,(9,25)),POLICY)
    assert summary.status == 'ON_SITE'
    assert summary.outer_vertices
    assert summary.cover_center != q
    # Raw geometry establishes this posterior point independently of the production predicate.
    assert math.dist(actual,ss.first.position) == 1000
    assert math.dist(actual,ss.physics.arena_center) <= 1
    assert math.degrees(math.atan2(actual[1]-q[1],actual[0]-q[0])) % 360 == 270
    for p in (*summary.outer_vertices, actual):
        assert math.dist(summary.cover_center,p) <= summary.r_U
    assert summary.subsequent_movement_seconds == 0


def test_b2_empty_source_bundle_and_cli_export(tmp_path):
    path = tmp_path/'input.json'
    path.write_text(json.dumps({'measurements':[{'position':[4000,0],'bearing_deg':180,'half_width_deg':1}]}))
    ss = source((4000.,0.),180.)
    result = q2.select_second_point(ss,q2.SearchConfig())
    bundle = run.q2_bundle(ss,result)
    assert bundle.figures == ()
    assert bundle.metadata['result_status'] == 'INCONSISTENT_FIRST_OBSERVATION'
    output = tmp_path/'export'
    run.main(['q2',str(path),'--output',str(output),'--frontier','--sensitivity'])
    saved = json.loads((output/'results.json').read_text())
    assert saved['q2']['status'] == 'INCONSISTENT_FIRST_OBSERVATION'
    assert saved['q2']['q_best'] is None
    assert (output/'bundle.json').exists() and (output/'manifest.json').exists()
    assert not list(output.glob('*.png')) and not list(output.glob('*.pdf'))


@pytest.mark.parametrize('old_q',[(100.,20.),(200.,20.)])
def test_b3_frontier_refreshes_same_or_changed_station_and_retains_witnesses(monkeypatch,old_q):
    ss = source()
    cfg = q2.SearchConfig(pair_rounds=0,source_grids=((3,3),(3,3),(3,3)))
    stations = ((100.,20.),(200.,20.))
    endpoints = ((1200.,0.),(1300.,0.))
    witness = q2.PairWitness(*endpoints,'direction',123.,100.,{},False,True,())
    old_score = q2.Score(100.,None,100.,2,witness,(witness,))
    checks = {q:check_candidate(ss,q,False,POLICY) for q in stations}
    alternatives = tuple(q2.CandidateResult(q,checks[q],old_score,math.dist(q,ss.first.position)) for q in stations)
    old = q2.Q2Result(old_q,checks[old_q],old_score,math.dist(old_q,ss.first.position),1.,5.,alternatives,
                       sensitivity_range_m=(10.,10.),source_change_m=0.,station_change_m=7.,tolerance_change_m=0.,
                       stability='STABLE_UNDER_REFINEMENT',tie_threshold_m=.3,
                       improvement_status='NUMERICAL_IMPROVEMENT',clearance_diagnostics=('stale',),
                       angular_comparison=({'stale':True},),config=cfg)
    monkeypatch.setattr(q2,'_search',lambda *args,**kwargs:old)
    base = q2.SourceSamples(((1000.,0.),(1100.,0.)),2,(3,3))
    monkeypatch.setattr(q2,'_sample_sources',lambda *args,**kwargs:base)
    actual_score = q2.score_point
    scored_samples = []
    def checked_score(ss,q,samples,config,deadline=None):
        scored_samples.append(samples.points)
        assert set(endpoints) <= set(samples.points)
        return actual_score(ss,q,samples,config)
    monkeypatch.setattr(q2,'score_point',checked_score)
    results = q2.movement_frontier(ss,(250.,300.),cfg)
    for result in results:
        assert result.q_best == stations[0]
        assert result.score.J_hat == pytest.approx(300.)
        assert result.score.witness.common_bearing_deg != 123.
        assert result.clearance_diagnostics
        feedback = result.clearance_diagnostics[0].feedback
        assert feedback.kind == result.score.witness.branch
        assert feedback.bearing_deg == result.score.witness.common_bearing_deg
        assert result.angular_comparison[0]['feedback'] == feedback
        assert result.sensitivity_range_m is None
        assert result.source_change_m is result.station_change_m is result.tolerance_change_m is None
        assert result.stability == 'NEEDS_REFINEMENT' and result.improvement_status is None
        assert result.tie_threshold_m == .3
        assert result.config.movement_budget_m in (250.,300.)
        assert {r.score.sample_count for r in result.alternatives} == {result.score.sample_count}
        assert all(r.sensitivity_range_m is None for r in result.alternatives)
        assert result.numerical_assessment['not_evaluated']
        retained = result.refinement_history[-1]['retained_witness_points']
        assert result.score.witness.x in retained and result.score.witness.y in retained
    assert len(set(scored_samples)) == 1


def candidate(value=100.,audit=None):
    score = q2.Score(value,None,value,3,None)
    return q2.CandidateResult((10.,10.),check_candidate(source(),(10.,10.),False,POLICY),score,math.sqrt(200),
                              source_values_m=(10.,10.,10.),sensitivity_range_m=(10.,value),
                              source_change_m=0.,tolerance_change_m=0.,audit_values_m=audit or {})


def test_b4_large_shift_without_rank_flip_is_not_stable():
    audit = {'source':(10.,10.,10.),'tolerance':(10.,10.),'shifted':(10.,100.),
             'local_refinement':(10.,10.),'common_final':(100.,100.)}
    result = q2.refinement_assessment(candidate(audit=audit),({'rank_flip':False},))
    assert result['completed_change_m'] == 90
    assert result['not_evaluated'] == ()
    assert result['status'] == 'NEEDS_REFINEMENT'


@pytest.mark.parametrize('stage',['shifted','local_refinement','common_final'])
def test_b4_missing_audit_cannot_be_stable(stage):
    audit = {k:(10.,10.) for k in ('source','tolerance','shifted','local_refinement','common_final')}
    del audit[stage]
    result = q2.refinement_assessment(candidate(10.,audit))
    assert stage in result['not_evaluated']
    assert result['status'] == 'NEEDS_REFINEMENT'


def test_b4_completed_small_changes_can_be_stable():
    audit = {k:(10.,10.) for k in ('source','tolerance','shifted','local_refinement','common_final')}
    assert q2.refinement_assessment(candidate(10.,audit))['status'] == 'STABLE_UNDER_REFINEMENT'


def test_b4_station_change_includes_local_winner_and_missing_stage():
    first = candidate(100.)
    local = replace(first,q=(20.,20.),score=replace(first.score,J_hat=40.))
    change, audit = q2.station_refinement_change((first,local),(first.q,first.q,local.q))
    assert change == 60. and audit['values_m'] == (100.,100.,40.)
    assert q2.station_refinement_change((first,local),(first.q,first.q))[0] is None


def test_b5_old_point_signal_in_but_added_action_out(monkeypatch):
    ss = source((2200.,0.),180.)
    q = (2190.,0.)
    assert math.dist(q,(0,0)) > 1800
    assert check_candidate(ss,q,False,POLICY).status == 'IN'
    def forbidden_score(*args,**kwargs):
        pytest.fail('excluded old point must not be scored')
    monkeypatch.setattr(q2,'score_point',forbidden_score)
    for cfg,reason in ((q2.SearchConfig(restrict_action_to_arena=True),'outside_added_arena_action_domain'),
                       (q2.SearchConfig(movement_budget_m=5),'outside_movement_budget')):
        result = reassess_old_point(ss,q,cfg)
        assert result['signal_check'].status == 'IN'
        assert result['status'] == 'OUT' and not result['action_admissible']
        assert reason in result['reasons'] and result['score'] is None


@pytest.mark.parametrize('field',['tie_floor_m','tie_multiplier'])
@pytest.mark.parametrize('value',[math.nan,math.inf,-math.inf,-1.])
def test_tie_parameters_reject_nonfinite_and_negative(field,value):
    with pytest.raises(ValueError,match='tie'):
        q2.SearchConfig(**{field:value})


@pytest.mark.parametrize('steps',[(),(math.nan,),(math.inf,),(-math.inf,),(0.,),(-1.,)])
def test_area_steps_validate_before_geometry(steps):
    with pytest.raises(ValueError,match='spacings'):
        posterior_area(None,None,None,steps)


@pytest.mark.parametrize('value',[math.nan,math.inf,-math.inf])
def test_station_step_rejects_nonfinite(value):
    with pytest.raises(ValueError):
        q2.SearchConfig(station_steps_m=(50.,value))


def read_row(tmp_path,**fields):
    row = {'position':[0.,0.],'bearing_deg':0.}
    row.update(fields)
    path = tmp_path/'input.json'
    path.write_text(json.dumps([row]))
    return read_measurements(path)[0]


def test_manual_nearest_mode_derives_correct_width_and_assumption(tmp_path):
    mode = ErrorMode.NEAREST_ROUNDING_OUTER_1_005_DEG
    obs = read_row(tmp_path,error_mode=mode.value)
    assert obs.half_width_deg == 1.005
    assert obs.rounding_mode == mode.value
    assert obs.rounding_assumption_source == mode.assumption_source


@pytest.mark.parametrize('fields',[
    {'error_mode':'TYPO'}, {'error_mode':'OFFICIAL_UNKNOWN'},
    {'error_mode':'THEORETICAL_1_DEG','half_width_deg':1.005},
    {'error_mode':'NEAREST_ROUNDING_OUTER_1_005_DEG','half_width_deg':1.},
    {'error_mode':'THEORETICAL_1_DEG','rounding_mode':'NEAREST_ROUNDING_OUTER_1_005_DEG'},
    {'error_mode':'NEAREST_ROUNDING_OUTER_1_005_DEG','rounding_assumption_source':'official guaranteed'},
    {'rounding_mode':'THEORETICAL_1_DEG'},
])
def test_manual_mode_conflicts_rejected(tmp_path,fields):
    with pytest.raises(ValueError):
        read_row(tmp_path,**fields)


def test_manual_custom_width_has_no_named_model_claim(tmp_path):
    obs = read_row(tmp_path,half_width_deg=7.)
    assert obs.half_width_deg == 7. and obs.error_mode is None


def test_b4_search_assembly_observes_shifted_gain_without_rank_change(monkeypatch):
    ss = source()
    cfg = q2.SearchConfig(station_steps_m=(10.,5.),source_grids=((3,3),(3,3),(3,3)),
                          starts=1,pair_rounds=0,boundary_step_deg=180,
                          station_initial_step_m=2.,station_min_step_m=2.,time_budget_s=20)
    monkeypatch.setattr(q2,'candidate_bbox',lambda *args:(10.,20.,10.,20.))
    def samples(ss,level,grids,q=None,inward=1e-7,shifted=False,second_half_width_deg=1.,deadline=None):
        points = ((1000.,0.),(1100.,0.))+(((1200.,0.),) if shifted else ())
        return q2.SourceSamples(points,level,grids[level],shifted=shifted)
    monkeypatch.setattr(q2,'_sample_sources',samples)
    def score(ss,q,samples,config,deadline=None):
        value = 100. if (1200.,0.) in samples.points else 10.
        return q2.Score(value,None,value,len(samples.points),None,local_improvement_m=0.)
    monkeypatch.setattr(q2,'score_point',score)
    monkeypatch.setattr(q2,'_conditional_diagnostics',lambda *args,**kwargs:((),()))
    result = q2.select_second_point(ss,cfg)
    assert result.stop_reason == 'COMPLETED'
    assert result.score.J_hat == 100.
    assert result.source_change_m == result.tolerance_change_m == 0.
    assert result.sensitivity_range_m == (10.,100.)
    assert result.stability == 'NEEDS_REFINEMENT'
    assert not result.numerical_assessment['rank_flip']
    assert result.numerical_assessment['not_evaluated'] == ()
    assert result.numerical_assessment['station_comparison']['not_evaluated_stage_indices'] == ()
