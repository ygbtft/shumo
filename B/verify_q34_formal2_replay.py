"""Replay saved official responses against current policies; never create a case."""
import os
for key in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS'):
    os.environ[key] = '1'

import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import sys

import bounded_candidates as candidates
from client import Client

ROOT = Path(__file__).resolve().parent
DEFAULT_AUDIT = ROOT / 'experiments/paper_materials/2026-09-13_formal2_baselines/逐局审计.json'


def replay(problem, trace):
    records = [json.loads(x) for x in trace.read_text(encoding='utf8').splitlines()]
    index, max_delta = 0, 0.
    def transport(path, raw):
        nonlocal index, max_delta
        if index >= len(records):
            raise AssertionError('Current policy sent an extra command')
        expected = records[index]
        request = json.loads(raw)
        assert path == expected['path'], (index, path, expected['path'])
        for key in ('channel', 'arena_id'):
            assert request.get(key) == expected['request'].get(key), (index, key)
        assert ('position' in request) == ('position' in expected['request'])
        if 'position' in request:
            p, q = request['position'], expected['request']['position']
            delta = math.hypot(p['x'] - q['x'], p['y'] - q['y'])
            max_delta = max(max_delta, delta)
            assert delta <= 1e-6, (trace, index, delta)
        index += 1
        return expected['http_status'], copy.deepcopy(expected['response'])
    cli = Client(transport, robot_id='recorded-replay-only')
    policy = candidates.construct(problem, cli)
    policy.run()
    assert index == len(records)
    return dict(problem=problem, commands=index, max_position_delta_m=max_delta,
                cleared=len(policy.cleared), total_virtual_s=cli.virtual_s,
                parameters=candidates.actual_parameters(policy, problem),
                trace=str(trace.relative_to(ROOT)),
                trace_sha256=hashlib.sha256(trace.read_bytes()).hexdigest())


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audit', type=Path, default=DEFAULT_AUDIT)
    parser.add_argument('--output', type=Path, default=ROOT / 'cleanup_formal2/replay.json')
    args = parser.parse_args(argv)
    def deny_network(event, unused):
        if event in ('socket.connect', 'socket.bind', 'socket.getaddrinfo'):
            raise AssertionError('Recorded replay forbids networking: ' + event)
    sys.addaudithook(deny_network)
    audit = json.loads(args.audit.read_text(encoding='utf8'))
    selected = []
    for c in audit['cases']:
        p = c['problem']
        if c['batch'] in ('q3_first', 'q3_repeat', 'q4_repeat') or (
                c['batch'] == 'ablation' and p == 4 and c['setting'] == 'online_nearest__g35'):
            assert {k: c['parameters'][k] for k in candidates.FORMAL_PARAMETERS[p]} == candidates.FORMAL_PARAMETERS[p]
            selected.append(c)
    assert len(selected) == 25
    results = []
    for c in selected:
        result = replay(c['problem'], ROOT / c['trace'])
        assert result['cleared'] == c['cleared']
        assert math.isclose(result['total_virtual_s'], c['virtual_time_us'] / 1e6, abs_tol=1e-6)
        results.append(dict(case_code=c['case_code'], source_mode='practice', **result))
    for c in audit['formal2_provenance']:
        results.append(dict(source_mode='formal', formal_index=2, **replay(c['problem'], ROOT / c['trace'])))
    result = dict(complete=True, recorded_cases=len(results), matched_commands=sum(r['commands'] for r in results),
                  max_position_delta_m=max(r['max_position_delta_m'] for r in results),
                  official_requests_sent=0, new_simulations=0, cases=results)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps({k: v for k, v in result.items() if k != 'cases'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
