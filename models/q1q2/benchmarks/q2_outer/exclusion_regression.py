"""Run existing offline suites unchanged, redirecting reports to a new directory.

The benchmark worker redirects ONLY report.json writes; cases/truth and all
comparisons are untouched. Existing reports and paper-full.md are never written.
Mock HTTP workers use the owned ephemeral loopback server, never practice mode.
"""
import argparse
import hashlib
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[4]
SUITES = ('q1_geometry', 'q1_circle_cover', 'q2_candidate', 'q2_worst_diameter')


def benchmark_worker(name, destination):
    module = importlib.import_module('models.q1q2.benchmarks.'+name+'.run')
    original = Path.write_text
    def write(path, text, *args, **kwargs):
        if path.name == 'report.json':
            return original(destination/(name+'.json'), text, *args, **kwargs)
        raise RuntimeError('unexpected benchmark write: '+str(path))
    sys.argv = [name]
    with patch.object(Path, 'write_text', write):
        result = (module.run if name == 'q2_candidate' else module.main)()
    if name == 'q2_candidate' and result['n_fail']:
        raise SystemExit(1)


def hashes():
    paths = [p for folder in ('models/q1q2', 'B') for p in (REPO/folder).glob('*.py')]
    paths += list((REPO/'models/q1q2/optional').glob('*.py'))
    paths += list((REPO/'B/tests').glob('*.py'))
    return {str(p.relative_to(REPO)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--worker', choices=SUITES)
    a = p.parse_args(); out = a.output.resolve(); out.mkdir(parents=True, exist_ok=True)
    if a.worker:
        benchmark_worker(a.worker, out)
        return
    env = dict(os.environ, OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1',
               VECLIB_MAXIMUM_THREADS='1')
    rows = []; before = hashes()
    commands = [(s, [sys.executable, '-m', __spec__.name, '--worker', s, '--output', str(out)], REPO)
                for s in SUITES]
    commands += [('q12-tests', [sys.executable, '-m', 'pytest', '-q', 'models/q1q2/tests'], REPO),
                 ('q34-tests', [sys.executable, '-m', 'pytest', '-q', 'tests'], REPO/'B'),
                 ('outer-tests', [sys.executable, '-m', 'pytest', '-q', 'models/q1q2/benchmarks/q2_outer/tests'], REPO)]
    for problem, method in ((3, 'range_area7'), (4, 'range_grid21_29')):
        commands.append((f'q{problem}-mock-http', [sys.executable, '-B', 'run_bounded_robot.py',
                         '--series', 'cover21', '--problem', str(problem), '--method', method,
                         '--seed', '42', '--mode', 'mock-http'], REPO/'B'))
    for name, command, cwd in commands:
        with (out/(name+'.log')).open('w') as log:
            run = subprocess.run(command, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT)
        row = dict(name=name, command=command, cwd=str(cwd), exit_code=run.returncode)
        if name in SUITES:
            report = json.loads((out/(name+'.json')).read_text())
            row['counts'] = {k: report[k] for k in ('n_cases', 'n_pass', 'n_fail') if k in report}
        if name.endswith('mock-http') and run.returncode == 0:
            last = (out/(name+'.log')).read_text().strip().splitlines()[-1]
            folder = Path(last.removeprefix('Local logs: '))
            report = json.loads((folder/'summary.json').read_text())
            row['summary_path'] = str(folder/'summary.json')
            row['all_cleared'] = report['all_cleared']
            (out/(name+'.json')).write_text(json.dumps(report, indent=2)+'\n')
            if not report['all_cleared']:
                row['exit_code'] = 1
        rows.append(row)
        print(name, row['exit_code'], flush=True)
    after = hashes()
    result = dict(runs=rows, before_sha256=before, after_sha256=after,
                  changed_during_run=[k for k in before if before[k] != after.get(k)],
                  passed=all(r['exit_code'] == 0 for r in rows))
    (out/'summary.json').write_text(json.dumps(result, indent=2)+'\n')
    raise SystemExit(0 if result['passed'] else 1)


if __name__ == '__main__':
    main()
