"""Run the supplied Q1/Q2 tests without editing the pinned reference checkout."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent
OUT = ROOT/"experiments/runs/2026-09-11_q12-peer-benchmark"
WORK = OUT/"upstream_worktree"
AREAS = ("q1_geometry", "q1_circle_cover", "q2_candidate", "q2_worst_diameter")


def env():
    result = os.environ.copy()
    result.update(PYTHONDONTWRITEBYTECODE="1", PYTEST_DISABLE_PLUGIN_AUTOLOAD="1", OPENBLAS_NUM_THREADS="1",
                  OMP_NUM_THREADS="1", MPLCONFIGDIR=str(ROOT/".mplconfig"), XDG_CACHE_HOME=str(ROOT/".cache"), TMPDIR=str(OUT/"tmp"))
    return result


def run():
    marker = OUT/"upstream_started.json"
    with marker.open("x") as stream:
        json.dump(dict(pid=os.getpid(), role="user-requested upstream Q1/Q2 benchmark", official_calls=0), stream)
    jobs = [("unit_tests", ["-m", "pytest", "models/q1q2/tests", "-q", "--import-mode=importlib", "-p", "no:cacheprovider", "--basetemp", str(OUT/"tmp/pytest")])]
    jobs += [(name, ["-m", f"models.q1q2.benchmarks.{name}.run"]) for name in AREAS]
    commands = [dict(label=label, argv=[sys.executable, "-B", *args], cwd=str(WORK)) for label, args in jobs]
    (OUT/"upstream_commands.json").write_text(json.dumps(commands, indent=2))
    before = {str(p.relative_to(WORK)):hashlib.sha256(p.read_bytes()).hexdigest()
              for tree in (WORK/"models/q1q2", WORK/"mock") for p in tree.rglob("*")
              if p.is_file() and (p.suffix == ".py" or p.name == "cases.jsonl")}
    records = []
    for item in commands:
        began = time.perf_counter()
        print("START", item["label"], flush=True)
        with (OUT/"logs"/f"upstream_{item['label']}.txt").open("x") as stream:
            completed = subprocess.run(item["argv"], cwd=WORK, env=env(), stdout=stream, stderr=subprocess.STDOUT)
        record = dict(label=item["label"], exit_code=completed.returncode, wall_s=time.perf_counter()-began)
        records.append(record)
        (OUT/"upstream_progress.json").write_text(json.dumps(records, indent=2))
        print("DONE", json.dumps(record), flush=True)
    unchanged = all(hashlib.sha256((WORK/name).read_bytes()).hexdigest() == digest for name, digest in before.items())
    assert unchanged
    result = dict(jobs=records, source_and_cases_unchanged=unchanged, checked_files=len(before), official_calls=0)
    (OUT/"upstream_completion.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2), flush=True)


def main():
    global OUT
    parser = argparse.ArgumentParser()
    parser.add_argument("--launch", action="store_true")
    parser.add_argument("--attempt", default="initial", choices=("initial", "02"))
    args = parser.parse_args()
    if args.attempt != "initial":
        OUT = OUT/f"attempt-{args.attempt}"
        OUT.mkdir(exist_ok=True)
        (OUT/"tmp").mkdir(exist_ok=True)
        (OUT/"logs").mkdir(exist_ok=True)
    if args.launch:
        if (OUT/"upstream_started.json").exists():
            raise RuntimeError("Preserving upstream benchmark execution")
        with (OUT/"log.txt").open("a") as stream:
            child = subprocess.Popen([sys.executable, "-B", str(Path(__file__).resolve()), "--attempt", args.attempt], cwd=ROOT.parent,
                                     env=env(), stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
        (OUT/"background.pid").write_text(str(child.pid)+"\n")
        print("Background PID", child.pid)
    else:
        run()


if __name__ == "__main__":
    main()
