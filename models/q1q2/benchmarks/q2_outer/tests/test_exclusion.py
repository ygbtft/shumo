"""Proof integrity, strict boundaries and honest budget exits."""
import copy
from fractions import Fraction as F
import json
from pathlib import Path

import pytest
pytest.importorskip('mpmath')
pytest.importorskip('numpy')
from models.q1q2.optional.outer_exclusion import (
    Evidence, Proposals, ROOT, bisect, certify_outer, pair_proves, quadratic_min)
from models.q1q2.benchmarks.q2_outer.check_exclusion import coverage, minimum, verify

ARTIFACT = Path(__file__).resolve().parents[1]/'exclusion/certificate.json'


@pytest.fixture(scope='module')
def artifact():
    return json.loads(ARTIFACT.read_text())


def test_saved_full_certificate(artifact):
    result = verify(artifact)
    assert result['valid'] and result['complete']
    assert F(result['gap']) <= F('0.01')
    assert result['display_gap'] == '0.010001'


@pytest.mark.parametrize('coeff,box,answer', [
    ((2, -4, 8, 7), (-5, 5, -5, 5), -3),
    ((1, -10, 10, 0), (0, 1, 0, 1), -9),
    ((F(1, 3), F(-2, 7), F(4, 9), F(1, 11)), (0, 0, 0, 0), F(1, 11)),
])
def test_minimum_independent_formula(coeff, box, answer):
    assert quadratic_min(coeff, box) == answer
    k, bx, by, c = map(F, coeff)
    assert minimum(k, (bx, by), c, tuple(map(F, box))) == answer


def test_longest_side_closed_partition():
    a, b = bisect(ROOT)
    assert a[1] == b[0] == F(1005, 2)
    assert coverage([a, b])['area_exact'] == '1005000'
    c, d = bisect(a)
    assert c[3] == d[2] == 500
    coverage([c, d, b])


@pytest.mark.parametrize('boxes', [
    [(0, 500, 0, 1000), (501, 1005, 0, 1000)],
    [(0, 501, 0, 1000), (500, 1005, 0, 1000)],
    [(0, 1005, 0, 500), (0, 1005, 0, 500)],  # same area, overlap and gap
    [(0, 1005, 0, 999)], [],
])
def test_coverage_rejects_gaps_and_overlaps(boxes):
    with pytest.raises(ValueError):
        coverage([tuple(map(F, b)) for b in boxes])


def test_near_equality_is_not_direction():
    k = Evidence().k
    assert not pair_proves((5, 0), (10, 0), (0, 0, 0, 0), 4, k)
    assert pair_proves((F(5001, 1000), 0), (10, 0), (0, 0, 0, 0), 4, k)


def test_disk_center_infeasible_does_not_exclude_box():
    evidence = Evidence()
    # Center is far outside C_sig but the box includes the origin.
    assert evidence.outside(tuple(map(F, (0, 2000, 0, 2000)))) is None
    assert evidence.outside(tuple(map(F, (2000, 2001, 2000, 2001)))) is not None


@pytest.mark.parametrize('p', [(5., 0.), (1500.001, 0.), (100., 100.), (-20., 0.)])
def test_actual_source_rejection(p):
    assert not Evidence().legal(p)


@pytest.mark.parametrize('mutation', ['missing', 'duplicate', 'source', 'disk', 'lower', 'k', 'root', 'upper', 'status'])
def test_tamper_rejected(artifact, mutation):
    data = copy.deepcopy(artifact)
    if mutation == 'missing':
        data['leaves'].pop()
    elif mutation == 'duplicate':
        data['leaves'].append(data['leaves'][0])
    elif mutation == 'source':
        next(v for v in data['leaves'] if v['kind'] == 'pair')['x'] = [5., 0.]
    elif mutation == 'disk':
        leaf = next(v for v in data['leaves'] if v['kind'] == 'pair')
        leaf.update(kind='disk', disk=0, box=['0', '1005', '0', '1000'])
    elif mutation == 'lower':
        data['lower'] = data['upper']
    elif mutation == 'k':
        data['k'] = '1'
    elif mutation == 'root':
        data['root'][1] = '1000'
    elif mutation == 'upper':
        data['upper'] = '1'
    else:
        data['converged'] = False
    with pytest.raises(ValueError):
        verify(data)


@pytest.mark.parametrize('options,reason', [
    ({'max_nodes': 0}, 'node_budget'),
    ({'time_limit_s': 0}, 'time_budget'),
    ({'max_nodes': 9}, 'node_budget'),
])
def test_budget_retains_complete_domain(options, reason):
    data = certify_outer(**options)
    assert not data['converged'] and data['pending'] > 0
    assert data['stop_reason'] == reason and F(data['lower']) == 0
    result = verify(data)
    assert result['valid'] and not result['complete']
    assert F(result['gap']) > F(data['tau'])


def test_bad_dynamic_proposal_never_prunes(monkeypatch):
    monkeypatch.setattr(Proposals, 'dynamic', lambda *a: [((0., 0.), (1500., 0.))])
    monkeypatch.setattr(Proposals, 'static', lambda *a: [])
    data = certify_outer(max_nodes=7)
    assert not data['converged']
    assert all(v['kind'] != 'pair' for v in data['leaves'])
    verify(data)


def test_fixed_budget_not_mislabelled():
    data = certify_outer(max_nodes=0, fixed_max_nodes=0)
    assert not data['fixed_certificate']['converged']
    assert not data['converged']
    verify(data)


@pytest.mark.parametrize('options', [
    {'tau': 0}, {'tau': -1}, {'max_nodes': -1}, {'max_nodes': 1.5},
    {'dps': 20}, {'time_limit_s': float('nan')}, {'q': (2000, 2000)},
])
def test_invalid_options(options):
    with pytest.raises(ValueError):
        certify_outer(**options)
