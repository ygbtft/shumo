from models.q1q2.q2 import SearchConfig
"""Audited P2 contracts: original-index proofs, legal worlds and fair interruption."""
from dataclasses import replace
import math
import time

import numpy as np
import pytest

from models.q1q2 import q2, diagnostics, run
from models.q1q2.feasible import (PhysicsConfig, Feedback, build_source_set,
                                  check_candidate, posterior_contains)
from models.q1q2.geometry import (BearingMeasurement, HalfPlane, NumericPolicy,
                                  RegionKind, intersect_halfplanes)
from models.q1q2.plots import ResultBundle, PlotStyle, render

P = NumericPolicy()


def source(first=None, physics=None):
    return build_source_set(first or BearingMeasurement((0, 0), 0), physics or PhysicsConfig(), P)


def samples(points):
    return q2.SourceSamples(tuple(points), 0, (2, 2))


def test_g1_conflict_indices_reproduce_empty_original_subset():
    hps = [HalfPlane((1, 0), 0), HalfPlane((1, 0), 0),
           HalfPlane((0, 1), 0), HalfPlane((-1, 0), -1)]
    result = intersect_halfplanes(hps, P)
    assert result.conflict_constraints == (0, 3)
    assert intersect_halfplanes([hps[i] for i in result.conflict_constraints], P).kind == RegionKind.EMPTY


def test_f1_same_station_reports_actual_clipped_distance():
    ss = source(physics=PhysicsConfig(arena_center=(1000, 0), arena_radius=1))
    result = check_candidate(ss, (0, 0), True, P)
    assert result.status == result.direction_status == 'IN'
    assert result.distance_to_closure == pytest.approx(999)


def test_q21_boundary_existence_worlds_share_a_legal_radius():
    ss, q = source(), (-1e-10, 0)
    assert check_candidate(ss, q, False, P).status == 'BOUNDARY'
    cloud = samples(((1000., 0.), (1500., 0.)))
    score = q2.score_point(ss, q, cloud, q2.SearchConfig())
    assert score.witness.actual_legal
    for witness in score.top_pairs:
        for world in witness.worlds:
            assert max(world['first_distance_m'], world['second_distance_m']) <= world['rho'] <= ss.physics.rho_hi
    assert score.J_hat == 0  # The 1500 m endpoint cannot receive at this q.
    assert q2._pair_witness(ss, q, (1500, 0), (1500, 0), q2.SearchConfig()) is None
    assert q2._conditional_diagnostics(ss, q, score, cloud, q2.SearchConfig()) == ((), ())
    summary = diagnostics.clearance_summary(ss, q, Feedback('direction', 0), cloud, P)
    assert summary.status == 'RECEPTION_UNRESOLVED'
    assert summary.subsequent_total_seconds is None


@pytest.mark.parametrize('q', [None, (1100., 0.)])
def test_q22_custom_grids_retain_all_earlier_samples(q):
    ss = source(BearingMeasurement((1000, 0), 0))
    grids = ((4, 4), (5, 5), (6, 6))
    clouds = [q2.sample_sources(ss, level, grids, q, inward=1e-7, second_half_width_deg=1.) for level in range(3)]
    assert set(clouds[0].points) <= set(clouds[1].points) <= set(clouds[2].points)


@pytest.mark.parametrize('feedback', [Feedback('near'), Feedback('direction', 1)])
def test_d1_repeated_station_cannot_change_fixed_feedback(feedback):
    summary = diagnostics.clearance_summary(source(), (0, 0), feedback, samples(((1000, 0),)), P)
    assert summary.status == 'INCONSISTENT_FEEDBACK'
    assert summary.subsequent_total_seconds is None
    assert summary.cover_center is None


def test_d1_empty_F_is_not_a_clearance_plan():
    ss = source(physics=PhysicsConfig(arena_center=(-1000, 0), arena_radius=1))
    assert ss.status != 'OK'
    summary = diagnostics.clearance_summary(ss, (100, 0), Feedback('near'), samples(()), P)
    assert summary.status == 'INCONSISTENT_FEEDBACK'


def test_d1_empty_samples_do_not_disprove_legal_near():
    summary = diagnostics.clearance_summary(source(), (100, 0), Feedback('near'), samples(()), P)
    assert summary.status == 'ON_SITE'
    assert summary.subsequent_total_seconds == 5
    assert summary.r_U == 5


def test_d2_configured_contact_sampling_and_common_witness_retention(monkeypatch):
    cfg = q2.SearchConfig(source_grids=((2, 2),) * 3, second_half_width_deg=2., near_offset_m=1e-4)
    ss = source()
    calls, scored = [], []
    def sample(ss, level, grids, q=None, inward=1e-7, shifted=False, second_half_width_deg=1.):
        calls.append((q, inward, second_half_width_deg))
        return samples(((1000., 0.),))
    def score(ss, q, cloud, config):
        scored.append(set(cloud.points))
        w = q2._pair_witness(ss, q, (1000, 0), (1001, 0), config)
        return q2.Score(1., None, 1., len(cloud.points), None, (w,) if w else ())
    monkeypatch.setattr(q2, 'sample_sources', sample)
    monkeypatch.setattr(q2, 'score_point', score)
    result = diagnostics.compare_heuristics(ss, cfg, (100, 0))
    assert all(offset == cfg.near_offset_m for _, offset, _ in calls)
    assert all(width == 2. for q, _, width in calls if q is not None)
    count = sum(row['score'] is not None for row in result)
    assert all((1001., 0.) in pts for pts in scored[-count:])
    assert all(pts == scored[-1] for pts in scored[-count:])
    diagnostics.reassess_old_point(ss, (100, 0), cfg)
    assert calls[-1] == ((100, 0), cfg.near_offset_m, 2.)


@pytest.mark.parametrize('failure', ['unknown_kind', 'savefig'])
def test_plot1_figures_close_even_when_render_fails(tmp_path, monkeypatch, failure):
    import matplotlib.pyplot as plt
    from matplotlib.figure import Figure
    before = plt.get_fignums()
    kind = 'unknown' if failure == 'unknown_kind' else 'geometry'
    if failure == 'savefig':
        def fail(*args, **kwargs):
            raise ValueError('save failed')
        monkeypatch.setattr(Figure, 'savefig', fail)
    bundle = ResultBundle(figures=({'id': 'failure', 'panels': [{'kind': kind}]},))
    with pytest.raises(ValueError):
        render(bundle, tmp_path, PlotStyle(font_family='DejaVu Sans'))
    assert plt.get_fignums() == before


def test_r1_r2_panels_and_area_curves_use_their_own_feedback_and_widths():
    ss, q = source(BearingMeasurement((0, 0), 0, 2.)), (100, 0)
    cfg = q2.SearchConfig(source_grids=((3, 4),) * 3, pair_rounds=0, second_half_width_deg=2.)
    cloud = q2.sample_sources(ss, 0, cfg.source_grids, q, second_half_width_deg=2., inward=1e-7)
    score = q2.score_point(ss, q, cloud, cfg)
    clear, angular = q2._conditional_diagnostics(ss, q, score, cloud, cfg)
    result = q2.Q2Result(q, check_candidate(ss, q, False, P), score, 100, 20, 5,
                         config=cfg, clearance_diagnostics=clear, angular_comparison=angular)
    figures = run.q2_bundle(ss, result).figures
    panels = [f for f in figures if f['id'].startswith('F7')]
    assert any(c.feedback.kind == 'near' for c in clear)
    for figure, summary in zip(panels, clear):
        for line in figure['panels'][0].get('lines', ()):
            assert posterior_contains(ss, q, summary.feedback, line['values'], P).all()
    f8 = next(f for f in figures if f['id'] == 'F8')
    first_area = f8['panels'][0]['series'][0]['y'][0]
    expected = diagnostics.compare_geometry(ss.actual_point, (ss.first.position, (750, 10)),
                                            diagnostics.DiagnosticConfig(half_widths_deg=(2., 2.)))
    assert first_area == pytest.approx(expected.linear_area_m2)
    assert '(2.0, 2.0)' in f8['caption']


def test_r3_complexity_table_describes_executed_algorithms():
    table = run.q1_bundle({}).tables['T3']
    text = str(table)
    assert 'deque' not in text and 'degenerate enumeration' not in text
    assert 'exact_enumeration' in text and 'O(M^3)' in text
    assert 'all vertex pairs' in text and 'O(V^2)' in text
    assert 'circle enumeration fallback' in text and 'O(V^4)' in text
    assert 'bit-length' in text


@pytest.mark.parametrize('budget', [.001, .01])
def test_q24_small_budget_interrupts_initial_boundary_work(budget):
    cfg = q2.SearchConfig(source_grids=((2, 2),) * 3, time_budget_s=budget)
    start = time.monotonic()
    result = q2.select_second_point(source(), cfg)
    elapsed = time.monotonic() - start
    assert result.stop_reason == 'TIME_BUDGET'
    assert elapsed < .1 + budget  # Soft budget allows one atomic operation and scheduler delay.
    assert len({r.score.sample_count for r in result.alternatives}) <= 1


@pytest.mark.parametrize('operation', ['sources', 'contacts', 'score'])
def test_q24_deadline_interrupts_inside_work(monkeypatch, operation):
    ss = source()
    ticks = iter([0., 0., 2.])
    monkeypatch.setattr(q2.time, 'monotonic', lambda: next(ticks, 2.))
    with pytest.raises(q2._BudgetExpired):
        if operation == 'sources':
            q2.sample_sources(ss, 2, ((4, 4),) * 3, deadline=1., inward=1e-7, second_half_width_deg=1.)
        elif operation == 'contacts':
            q2._direction_boundary_samples(ss, (100, 0), 4, 1., 1e-7, deadline=1.)
        else:
            q2.score_point(ss, (100, 0), samples(((1000, 0), (1100, 0), (1200, 0))),
                           q2.SearchConfig(block_size=1), deadline=1.)


def test_q24_frontier_does_not_publish_partial_common_round(monkeypatch):
    ss = source()
    cfg = q2.SearchConfig(source_grids=((2, 2),) * 3, time_budget_s=1)
    cloud = samples(((1000, 0), (1100, 0)))
    candidates = tuple(q2.CandidateResult(q, check_candidate(ss, q, False, P),
                        q2.score_point(ss, q, cloud, cfg), math.dist(q, (0, 0)))
                       for q in ((100., 0.), (200., 0.)))
    old = q2.Q2Result(candidates[0].q, candidates[0].check, candidates[0].score, 100, 20, 5,
                      alternatives=candidates, config=cfg)
    monkeypatch.setattr(q2, 'select_second_point', lambda *args: old)
    monkeypatch.setattr(q2, 'sample_sources', lambda *args, **kwargs: cloud)
    calls = []
    def score(*args, deadline=None):
        assert deadline is not None
        calls.append(args[1])
        if len(calls) == 4:  # first pass complete, second pass interrupted
            raise q2._BudgetExpired
        return replace(old.score, J_hat=999.)
    monkeypatch.setattr(q2, 'score_point', score)
    results = q2.movement_frontier(ss, (250., 300.), cfg)
    assert len(calls) == 4
    for result in results:
        assert result.score is old.score
        assert result.alternatives == old.alternatives
        assert result.stop_reason == 'FRONTIER_COMMON_TIME_BUDGET'
        assert result.numerical_assessment['frontier_common_comparison'] == 'NOT_COMPLETED'
