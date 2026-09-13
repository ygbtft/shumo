"""Single authorized formal Q3 execution of the officially practised fused policy."""
import os
for key in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS'):
    os.environ[key] = '1'
import argparse
from datetime import datetime
import json
from pathlib import Path
import re
import time
import traceback

from client import Client, HttpTransport
import bounded_candidates as builders
from official_sensitivity_robot import Journal

ROOT = Path(__file__).resolve().parent
EXPECTED = dict(task_order='nearest', trial_radius=65., max_active=2,
                share_limit=6, localization_weight=.08, remainder_weight=1.5)


def actual_parameters(policy):
    return {key: getattr(policy, 'time_weight' if key == 'localization_weight' else key) for key in EXPECTED}


def construct(client):
    policy = builders.build(client, builders.SPECS[3]['range_area7_nearest65_a2'], 3, builders.load_paths(3))
    assert actual_parameters(policy) == EXPECTED
    return policy


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--robot-id')
    parser.add_argument('--case-code')
    parser.add_argument('--confirm-formal', action='store_true')
    parser.add_argument('--check-config', action='store_true')
    args = parser.parse_args()
    def no_requests(*args, **kwargs):
        raise AssertionError('Configuration check must not send any request')
    policy = construct(Client(no_requests))
    assert not any(name == 'mock' or name.startswith('mock.') for name in __import__('sys').modules)
    if args.check_config:
        assert not args.confirm_formal
        print(json.dumps(dict(parameters=EXPECTED, official_requests=0), ensure_ascii=False))
        return
    if not args.confirm_formal or not args.robot_id or not re.fullmatch(r'\d+', args.robot_id):
        parser.error('Formal execution requires explicit confirmation and the logged-in numeric team ID')
    if not args.case_code or not re.fullmatch(r'[A-Z0-9]{4}(?:-[A-Z0-9]{4}){3}', args.case_code):
        parser.error('The verified current Q3 formal case code is required')
    marker = ROOT.parent / 'FORMAL_CLIENT_STARTED.json'
    with marker.open('x') as stream:
        json.dump(dict(case_code=args.case_code, problem=3, parameters=EXPECTED,
                       at=datetime.now().astimezone().isoformat()), stream)
        stream.flush()
        os.fsync(stream.fileno())
    folder = ROOT / 'robot_runs' / (datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '-bounded-formal')
    folder.mkdir(parents=True, exist_ok=False)
    def write(name, value):
        (folder / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    write('config.json', dict(mode='formal', problem=3, case_code=args.case_code, robot_id=args.robot_id,
        method='range_area7_nearest65_a2', parameters=EXPECTED, mock_executions=0))
    journal = Journal(folder / 'requests.jsonl')
    client = Client(HttpTransport('http://127.0.0.1:2026'), robot_id=args.robot_id, transcript=journal)
    policy = construct(client)
    write('policy.json', dict(class_name=type(policy).__name__, parameters=actual_parameters(policy),
                             stations=policy.stations.tolist()))
    write('endpoint.json', dict(base_url='http://127.0.0.1:2026', owned_mock=False))
    began = time.perf_counter()
    error = ''
    try:
        policy.run()
    except Exception as exc:
        error = repr(exc)
        (folder / 'failure.txt').write_text(traceback.format_exc())
    finally:
        result = dict(status='unexpected-error' if error else 'policy-completed', error=error,
            mode='formal', problem=3, case_code=args.case_code, parameters=actual_parameters(policy),
            cleared=len(policy.cleared), total_virtual_s=client.virtual_s, wall_s=time.perf_counter() - began,
            official_calls=journal.count, mock_executions=0, policy=policy.stats)
        write('summary.json', result)
        print(json.dumps(result, ensure_ascii=False), flush=True)
        print('Local logs:', folder, flush=True)
    if error:
        raise RuntimeError(error)


if __name__ == '__main__':
    main()
