"""Offline sensitivity contract checks, not simulator tests."""
from dataclasses import replace
import math
import pytest
from algorithms.q1q2 import sensitivity as s
from algorithms.q1q2.feasible import PhysicsConfig, build_source_set
from algorithms.q1q2.geometry import BearingMeasurement, NumericPolicy
from algorithms.q1q2.q2 import SearchConfig


def test_shape_control_distinguishes_equal_diameter_clearability():
    control = s.shape_control()
    assert control['triangle']['diameter'] == pytest.approx(36)
    assert control['triangle']['R'] == pytest.approx(36/math.sqrt(3))
    assert control['triangle']['single_clear_possible'] is False
    assert control['segment']['single_clear_possible'] is True


def test_invalid_old_point_is_not_scored(monkeypatch):
    ss = build_source_set(BearingMeasurement((0, 0), 0), PhysicsConfig(), NumericPolicy())
    cfg = SearchConfig(source_grids=((2, 2),)*3)
    def forbidden(*args, **kwargs):
        raise AssertionError('infeasible old point must not be scored')
    monkeypatch.setattr(s, 'score_point', forbidden)
    rows, pool, costs = s.common_evaluation(ss, cfg, [(-2000, 0)])
    assert rows[0]['admissibility']['status'] == 'OUT'
    assert rows[0]['score'] is None
    assert rows[0]['clearance'] is None
    assert costs['score_calls'] == 0


def test_fixed_old_and_new_share_frozen_pool(monkeypatch):
    ss = build_source_set(BearingMeasurement((0, 0), 0), PhysicsConfig(), NumericPolicy())
    cfg = SearchConfig(source_grids=((2, 3),)*3, pair_rounds=0)
    original = s.score_point
    seen = []
    def track(model, q, pool, config):
        seen.append((q, pool.points))
        return original(model, q, pool, config)
    monkeypatch.setattr(s, 'score_point', track)
    rows, pool, costs = s.common_evaluation(ss, cfg, [(100, 100), (200, 100)])
    assert len(rows) == 2
    assert all(r['score'] is not None for r in rows)
    assert seen[-1][1] == seen[-2][1] == pool.points
    assert costs['score_calls'] == 4


def test_information_clipping_retains_unbounded_state():
    ss = build_source_set(BearingMeasurement((0, 0), 0), PhysicsConfig(), NumericPolicy())
    cfg = SearchConfig(source_grids=((2, 3),)*3, pair_rounds=0)
    rows, pool, _ = s.common_evaluation(ss, cfg, [ss.first.position])
    data = s.clipping(ss, rows[0], pool)
    assert data['stages'][0]['kind'].value == 'UNBOUNDED'
    assert data['stages'][1]['d'] is not None
    assert data['q1_object_unchanged']
