"""Bounded, optional Q2 interval-oracle checks on the pinned peer code."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent
RUN = ROOT / "experiments/runs/2026-09-11_q12-peer-benchmark"
WORK = RUN / "upstream_worktree"
OUT = RUN / "certification"
CASES = ["segment_10_100_20_1", "segment_10_100_20_0.5", "tangent_segment_2",
         "polar_same_station_closed_0", "segment_special_18", "polar_0", "polar_1", "polar_6"]


def main():
    OUT.mkdir(exist_ok=True)
    (OUT / "tmp").mkdir(exist_ok=True)
    env = os.environ.copy()
    env.update(PYTHONDONTWRITEBYTECODE="1", PYTEST_DISABLE_PLUGIN_AUTOLOAD="1",
               OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1", TMPDIR=str(OUT / "tmp"),
               MPLCONFIGDIR=str(ROOT / ".mplconfig"), XDG_CACHE_HOME=str(ROOT / ".cache"))
    if "--launch" in sys.argv:
        if (OUT / "background.pid").exists():
            raise RuntimeError("Preserving the original optional run")
        with (OUT / "log.txt").open("x") as log:
            child = subprocess.Popen([sys.executable, "-B", str(Path(__file__).resolve())],
                                     cwd=ROOT.parent, env=env, stdout=log, stderr=subprocess.STDOUT,
                                     start_new_session=True)
        (OUT / "background.pid").write_text(str(child.pid) + "\n")
        print("Background PID", child.pid)
        return
    jobs = [dict(label="optional_unit_tests", timeout_s=180,
                 argv=[sys.executable, "-B", "-m", "pytest",
                       "models/q1q2/benchmarks/q2_worst_diameter/tests/test_certified.py",
                       "-q", "--import-mode=importlib", "-p", "no:cacheprovider",
                       "--basetemp", str(OUT / "tmp/pytest")]),
            dict(label="selected_fixed_q_certification", timeout_s=240,
                 argv=[sys.executable, "-B", "-m", "models.q1q2.benchmarks.q2_worst_diameter.run",
                       "--certify", "--certify-tol", ".1", "--certify-seconds", "10",
                       "--certify-nodes", "20000", "--report", str(OUT / "report.json"),
                       *[x for case_id in CASES for x in ("--case", case_id)]])]
    (OUT / "commands.json").write_text(json.dumps(dict(cwd=str(WORK), jobs=jobs), indent=2))
    (OUT / "config.json").write_text(json.dumps(dict(cases=CASES, base_seed=42, regenerated_cases=False,
        selection="Analytic segments, tangency, near branch, fixed-site feedback, ordinary sector and both nesting failures",
        certified_tolerance_m=.1, time_limit_s_per_selected_case=10, max_nodes=20000,
        official_calls=0, scored_mission_executions=0), indent=2))
    before = {str(p.relative_to(WORK)):hashlib.sha256(p.read_bytes()).hexdigest()
              for tree in (WORK / "models/q1q2", WORK / "mock") for p in tree.rglob("*")
              if p.is_file() and (p.suffix == ".py" or p.name == "cases.jsonl")}
    records = []
    for job in jobs:
        began = time.perf_counter()
        print("START", job["label"], flush=True)
        with (OUT / (job["label"] + ".txt")).open("x") as log:
            try:
                result = subprocess.run(job["argv"], cwd=WORK, env=env, stdout=log,
                                        stderr=subprocess.STDOUT, timeout=job["timeout_s"])
                code, timed_out = result.returncode, False
            except subprocess.TimeoutExpired:
                code, timed_out = None, True
        records.append(dict(label=job["label"], exit_code=code, timed_out=timed_out,
                            wall_s=time.perf_counter()-began))
        (OUT / "progress.json").write_text(json.dumps(records, indent=2))
        print("DONE", records[-1], flush=True)
    unchanged = all(hashlib.sha256((WORK / p).read_bytes()).hexdigest() == digest for p,digest in before.items())
    assert unchanged
    (OUT / "completion.json").write_text(json.dumps(dict(jobs=records,
        source_and_cases_unchanged=True, checked_files=len(before), official_calls=0,
        scored_mission_executions=0), indent=2))


if __name__ == "__main__":
    main()
