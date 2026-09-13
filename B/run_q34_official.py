"""Run the formal-test-2 Q3/Q4 policies in an already opened official session."""
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

import bounded_candidates as policies
from client import Client, HttpTransport

ROOT = Path(__file__).resolve().parent


class Journal:
    def __init__(self, path):
        self.path, self.count = path, 0
        self.enter_ms = self.exit_ms = None

    def append(self, row):
        with self.path.open('a', encoding='utf8') as stream:
            stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + '\n')
        self.count += 1
        response = row.get('response', {})
        if response.get('accepted') and row['path'] in ('/enter', '/exit'):
            setattr(self, 'enter_ms' if row['path'] == '/enter' else 'exit_ms', response['real_timestamp_ms'])

    @property
    def runtime_s(self):
        if self.enter_ms is None or self.exit_ms is None:
            return None
        return (self.exit_ms - self.enter_ms) / 1000


def main(argv=None, *, fixed_problem=None, formal_only=False):
    parser = argparse.ArgumentParser(description=__doc__)
    if fixed_problem is None:
        parser.add_argument('--problem', type=int, choices=(3, 4), required=True)
    parser.add_argument('--mode', choices=('practice', 'formal'), default='formal' if formal_only else None)
    parser.add_argument('--check-config', action='store_true')
    parser.add_argument('--robot-id')
    parser.add_argument('--case-code')
    parser.add_argument('--confirm-practice', action='store_true')
    parser.add_argument('--confirm-formal', action='store_true')
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'robot_runs')
    args = parser.parse_args(argv)
    problem = fixed_problem if fixed_problem is not None else args.problem
    if args.check_config:
        if args.confirm_formal or args.confirm_practice:
            parser.error('--check-config cannot be combined with execution confirmation')
        def no_io(*unused):
            raise AssertionError('Configuration inspection must not issue requests')
        policy = policies.construct(problem, Client(no_io))
        print(json.dumps(dict(problem=problem, formal_version=2, method=policies.METHODS[problem],
                              parameters=policies.actual_parameters(policy, problem), official_requests=0), ensure_ascii=False))
        return
    if args.mode is None or (formal_only and args.mode != 'formal'):
        parser.error('Specify the already opened official session mode')
    if not args.robot_id or not re.fullmatch(r'\d+', args.robot_id):
        parser.error('A numeric team ID is required; no request sent')
    if not args.case_code or not re.fullmatch(r'[A-Z0-9]{4}(?:-[A-Z0-9]{4}){3}', args.case_code):
        parser.error('The currently opened official case code is required; no request sent')
    if args.confirm_practice != (args.mode == 'practice') or args.confirm_formal != (args.mode == 'formal'):
        parser.error('Exactly one confirmation matching the session mode is required; no request sent')
    args.output_dir.mkdir(parents=True, exist_ok=True)
    # Retrying a process must not issue a second /enter on a potentially used case.
    marker = args.output_dir / f'ATTEMPT-q{problem}-{args.mode}-{args.case_code}.json'
    with marker.open('x', encoding='utf8') as stream:
        json.dump(dict(problem=problem, mode=args.mode, case_code=args.case_code), stream)
    folder = args.output_dir / (datetime.now().strftime('%Y%m%d-%H%M%S-%f') + f'-q{problem}-{args.mode}')
    folder.mkdir(exist_ok=False)
    def write(name, value):
        (folder / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf8')
    base_url = 'http://127.0.0.1:2026'
    write('config.json', dict(problem=problem, mode=args.mode, formal_version=2, case_code=args.case_code,
                             robot_id=args.robot_id, method=policies.METHODS[problem],
                             parameters=policies.FORMAL_PARAMETERS[problem], mock_executions=0))
    journal = Journal(folder / 'requests.jsonl')
    client = Client(HttpTransport(base_url), robot_id=args.robot_id, transcript=journal)
    policy = policies.construct(problem, client)
    write('policy.json', dict(class_name=type(policy).__name__, parameters=policies.actual_parameters(policy, problem),
                             stations=policy.stations.tolist()))
    write('endpoint.json', dict(base_url=base_url, owned_mock=False))
    began, error = time.perf_counter(), ''
    try:
        policy.run()
    except Exception as exc:
        error = repr(exc)
        (folder / 'failure.txt').write_text(traceback.format_exc(), encoding='utf8')
    finally:
        result = dict(status='unexpected-error' if error else 'policy-completed', error=error,
                      problem=problem, mode=args.mode, formal_version=2, case_code=args.case_code,
                      parameters=policies.actual_parameters(policy, problem), cleared=len(policy.cleared),
                      total_virtual_s=client.virtual_s,
                      average_localization_clear_s=client.virtual_s / len(policy.cleared) if policy.cleared else None,
                      program_runtime_s=journal.runtime_s, client_policy_wall_s=time.perf_counter() - began,
                      official_calls=journal.count, mock_executions=0, policy=policy.stats)
        write('summary.json', result)
        print(json.dumps(result, ensure_ascii=False), flush=True)
        print('Local logs:', folder, flush=True)
    if error:
        raise RuntimeError(error)


if __name__ == '__main__':
    main()
