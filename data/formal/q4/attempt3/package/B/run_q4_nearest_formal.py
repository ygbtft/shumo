"""Single authorized formal Q4 execution of the officially practised nearest policy."""
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
import official_sensitivity_config as tested
from official_sensitivity_robot import Journal

ROOT = Path(__file__).resolve().parent
EXPECTED = dict(trial_radius=35., share_limit=6, share_cooldown=150.,
                transverse_m=40., fraction=.15, steps=10, pause_limit=16, dispatch='nearest')


def actual_parameters(policy):
    return tested.actual_parameters(policy,4)


def construct(client):
    policy = tested.construct(4,client,{})
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
        parser.error('The verified current Q4 formal case code is required')
    marker = ROOT.parent / 'FORMAL_CLIENT_STARTED.json'
    with marker.open('x') as stream:
        json.dump(dict(case_code=args.case_code, problem=4, parameters=EXPECTED,
                       at=datetime.now().astimezone().isoformat()), stream)
        stream.flush()
        os.fsync(stream.fileno())
    folder = ROOT / 'robot_runs' / (datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '-bounded-formal')
    folder.mkdir(parents=True, exist_ok=False)
    def write(name, value):
        (folder / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    write('config.json', dict(mode='formal', problem=4, case_code=args.case_code, robot_id=args.robot_id,
        method='range_grid21_29_nearest35', parameters=EXPECTED, mock_executions=0))
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
            mode='formal', problem=4, case_code=args.case_code, parameters=actual_parameters(policy),
            cleared=len(policy.cleared), total_virtual_s=client.virtual_s, wall_s=time.perf_counter() - began,
            official_calls=journal.count, mock_executions=0, policy=policy.stats)
        write('summary.json', result)
        print(json.dumps(result, ensure_ascii=False), flush=True)
        print('Local logs:', folder, flush=True)
    if error:
        raise RuntimeError(error)


if __name__ == '__main__':
    main()
