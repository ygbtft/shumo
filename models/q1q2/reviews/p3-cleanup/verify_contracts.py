"""Targeted integration checks for the P3 call/serialization/accounting contracts."""
from dataclasses import asdict, replace
from importlib.metadata import version
import json
from unittest.mock import patch
from models.q1q2 import q1, q2
from models.q1q2.geometry import BearingMeasurement, NumericPolicy
from models.q1q2.feasible import PhysicsConfig, build_source_set
from models.q1q2.diagnostics import equilateral_case
from models.q1q2.optional.certified import certify
from models.q1q2.run import jsonable, q1_bundle

policy = NumericPolicy()
with patch.object(q1, 'minimum_circle', wraps=q1.minimum_circle) as mec:
    result = q1.solve(equilateral_case()['measurements'], policy)
    assert mec.call_count == 1
    q1.solve([], policy)
    assert mec.call_count == 1
assert json.loads(json.dumps(jsonable(result)))['minimum_circle']['radius'] == result.minimum_circle.radius
assert all('panels' in f for f in q1_bundle({'case': result}).figures)
ss = build_source_set(BearingMeasurement((0., 0.), 0.), PhysicsConfig(), policy)
config = q2.SearchConfig(source_grids=((2, 2),)*3, movement_budget_m=0., time_budget_s=10.)
with patch.object(q2, 'score_point', wraps=q2.score_point) as scored:
    zero = q2.select_second_point(ss, config)
    assert zero.evaluations == scored.call_count == 1
with patch.object(q2, 'select_second_point', return_value=zero):
    with patch.object(q2, 'score_point', wraps=q2.score_point) as scored:
        rows = q2.movement_frontier(ss, (0., 1.), config)
        assert rows[0].frontier_shared_evaluations == scored.call_count == 1
        assert rows[1].frontier_shared_evaluations == 0
        assert rows[1].frontier_shared_elapsed_seconds == 0
        assert all(r.evaluations == zero.evaluations and r.elapsed_seconds == zero.elapsed_seconds for r in rows)
certificate = certify(ss, (0., 0.), max_nodes=0, time_limit_s=0.)
encoded = json.loads(json.dumps(asdict(certificate)))
assert encoded['backend'] == 'mpmath.iv' and certificate.lower_m <= certificate.upper_m
print(json.dumps({'status': 'PASS', 'q1_mec_calls': 1, 'zero_budget_score_calls': 1,
                  'frontier_shared_score_calls_once': 1, 'serialization': 'PASS',
                  'certificate': encoded, 'dependencies': {n: version(n) for n in
                    ('numpy', 'matplotlib', 'pytest', 'mpmath')}}, ensure_ascii=False, indent=2))
