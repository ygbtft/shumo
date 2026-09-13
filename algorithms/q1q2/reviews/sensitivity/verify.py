"""Run only the four authorized local mathematical benchmarks; archive reports."""
import json
from pathlib import Path
import subprocess
import sys
import time

root = Path(__file__).resolve().parents[4]
here = Path(__file__).resolve().parent
areas = [('q1_geometry', 285), ('q1_circle_cover', 330), ('q2_candidate', 531), ('q2_worst_diameter', 48)]
results = []
for area, expected in areas:
    report = root/'algorithms/q1q2/benchmarks'/area/'report.json'
    previous = report.read_bytes() if report.exists() else None
    started = time.monotonic()
    try:
        command = [sys.executable, '-m', 'algorithms.q1q2.benchmarks.'+area+'.run']
        with (here/(area+'.log')).open('w') as log:
            proc = subprocess.run(command, cwd=root, stdout=log, stderr=subprocess.STDOUT)
        content = report.read_bytes()
        (here/(area+'_report.json')).write_bytes(content)
        data = json.loads(content)
        row = dict(area=area, expected=expected, n_cases=data['n_cases'], n_pass=data['n_pass'],
                   n_fail=data['n_fail'], returncode=proc.returncode,
                   elapsed_seconds=time.monotonic()-started, command=command)
        results.append(row)
        print(row, flush=True)
    finally:
        if previous is not None:
            report.write_bytes(previous)
        elif report.exists():
            report.unlink()
(here/'verification.json').write_text(json.dumps(results, indent=2)+'\n')
assert all(r['returncode'] == 0 and r['n_cases'] == r['n_pass'] == r['expected'] and r['n_fail'] == 0 for r in results)
