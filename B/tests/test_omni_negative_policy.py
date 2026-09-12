"""Distance-dominance safety, including boundary and degenerate retained sets."""
from unittest.mock import Mock

import numpy as np
import pytest

import bounded_candidates as bc
from geometry import hull
from omni_negative_policy import dominance_clip, OmniNegativeCompletionPolicy
from policies import Policy
from client import Rejected


def contains(poly, g, tol=1e-8):
    p = hull(poly)
    assert len(p)
    if len(p) == 1:
        return np.linalg.norm(g-p[0]) <= tol
    if len(p) == 2:
        d = p[1]-p[0]
        t = np.clip((g-p[0])@d/(d@d), 0, 1)
        return np.linalg.norm(g-p[0]-t*d) <= tol
    edges = np.roll(p, -1, axis=0)-p
    rel = g-p
    return np.all((edges[:, 0]*rel[:, 1]-edges[:, 1]*rel[:, 0]) >= -tol*np.linalg.norm(edges, axis=1))


@pytest.mark.parametrize('g', [np.array([570., 0.]), np.array([570.+1e-9, 0.]), np.array([1100., 0.])])
@pytest.mark.parametrize('kind', ['polygon', 'segment', 'point'])
def test_boundary_and_degeneracies_keep_truth(g, kind):
    poly = {'polygon': np.array([[-400., -20.], [1200., -20.], [1200., 20.], [-400., 20.]]),
            'segment': np.array([[-400., 0.], [1200., 0.]]), 'point': g[None, :]}[kind]
    result = dominance_clip(poly, [0., 0.], [1140., 0.])
    assert contains(result, g)
    assert result[:, 0].min() >= 570.-1e-7


@pytest.mark.parametrize('delta', [0., 1e-12, 1e-8, 1e-6])
def test_coincident_and_near_coincident_keep_equidistant_truth(delta):
    g = np.array([1e6+delta/2, 100.])
    assert contains(dominance_clip(g[None, :], [1e6+delta, 0.], [1e6, 0.]), g)


def test_random_legal_worlds_keep_truth_after_every_constraint():
    rng = np.random.default_rng(72634)
    for _ in range(200):
        g = rng.uniform(-1800, 1800, 2)
        rho = rng.uniform(1000, 1500)
        poly = g+np.array([[-2000., -2000.], [2000., -2000.], [2000., 2000.], [-2000., 2000.]])
        for _ in range(5):
            angles = rng.uniform(0, 2*np.pi, 2)
            a = g+rng.uniform(1, rho)*np.array([np.cos(angles[0]), np.sin(angles[0])])
            q = g+(rho+rng.uniform(1e-6, 1000))*np.array([np.cos(angles[1]), np.sin(angles[1])])
            poly = dominance_clip(poly, q, a)
            assert contains(poly, g)


def policy():
    return bc.build(Mock(), bc.SPECS[3]['range_area7'], 3, bc.load_paths(3))


def feedback(p, point, result, accepted=True):
    p.record_feedback(point, 1, dict(accepted=accepted, measure_result=result))


@pytest.mark.parametrize('negative_first', [True, False])
def test_history_orders_dedup_multiple_anchors_and_cache(negative_first):
    p = policy()
    if negative_first:
        feedback(p, [0., 0.], 'no_signal')
        assert not p.regions
    p.regions[1] = np.array([[-400., -20.], [1200., -20.], [1200., 20.], [-400., 20.]])
    p.circle(1)
    feedback(p, [1140., 0.], 'direction')
    if not negative_first:
        feedback(p, [0., 0.], 'no_signal')
    assert 1 not in p._circles
    assert contains(p.regions[1], np.array([1100., 0.]))
    assert p.regions[1][:, 0].min() >= 570.-1e-7
    count = p.stats['omni_negative_cuts']
    feedback(p, [0., 0.], 'no_signal')
    feedback(p, [1140., 0.], 'direction')
    assert p.stats['omni_negative_cuts'] == count
    feedback(p, [1150., 10.], 'direction')
    assert contains(p.regions[1], np.array([1100., 0.]))
    assert len(p._success_anchors[1]) == 2


@pytest.mark.parametrize('result,accepted', [('no_signal', False), ('certified_no_reception', True)])
def test_inferences_and_rejections_are_not_real_negatives(result, accepted):
    p = policy()
    feedback(p, [0., 0.], result, accepted)
    assert not p._real_negatives.get(1)


def test_transport_failure_never_reaches_history():
    p = policy()
    p.client.measure.side_effect = Rejected('rejected')
    with pytest.raises(Rejected):
        p.measure([0., 0.], 1)
    assert not p._real_negatives


def test_empty_intersection_retains_old_region_and_cache():
    p = policy()
    p.regions[1] = np.array([[0., 0.]])
    old = p.regions[1]
    cached = p.circle(1)
    feedback(p, [0., 0.], 'no_signal')
    feedback(p, [1140., 0.], 'direction')
    assert p.regions[1] is old
    assert p.circle(1) is cached
    assert p.stats['omni_negative_inconsistencies'] == 1


def test_q4_and_historical_policy_do_not_enable_dominance():
    p = bc.build(Mock(), bc.SPECS[4]['range_grid21_29'], 4, bc.load_paths(4))
    assert type(p).record_feedback is Policy.record_feedback
    assert not hasattr(p, '_real_negatives')
    with pytest.raises(ValueError):
        OmniNegativeCompletionPolicy(Mock(), [[0., 0.]], mixed=True)


def test_real_update_hook_precedes_sharing():
    p = policy()
    p.share_at = Mock(side_effect=lambda *args: assert_cut())
    def assert_cut():
        assert p.regions[1][:, 0].min() >= 570.-1e-7
        assert 1 not in p._circles
    p._surveying = True
    p.client.measure.return_value = dict(accepted=True, measure_result='no_signal')
    p.measure([0., 0.], 1)
    p._surveying = False
    p.client.measure.return_value = dict(accepted=True, measure_result='direction', svd_deg=180.)
    p.measure([1140., 0.], 1)
    p.share_at.assert_called_once()
