"""Verify the collector-only repair using already-seen complete feedback traces."""
import gzip
import json
import time
from client import Client
from task_confirmation_v2 import ROOT, OUT, SPECS, all_paths, build


def main():
    paths = all_paths()
    checks = []
    for problem, method in ((3, "packet_center7"), (4, "packet_action4_22")):
        path = ROOT / "experiments/runs/2026-09-11_interleaved-tasks/traces" / f"q{problem}__uniform__iid__67__{method}.jsonl.gz"
        with gzip.open(path, "rt") as stream:
            trace = [json.loads(line) for line in stream]
        index = 0
        def replay(endpoint, raw):
            nonlocal index
            entry = trace[index]
            assert endpoint == entry["path"] and json.loads(raw) == entry["request"]
            index += 1
            return 200, entry["response"]
        began = time.perf_counter()
        policy = build(Client(replay, robot_id="mock-robot"), SPECS[problem][method], problem, paths)
        initialization = time.perf_counter() - began
        stats = policy.run()
        row = dict(initialization_s=initialization, **stats)
        assert index == len(trace) and row["initialization_s"] >= 0.
        checks.append(dict(test=f"collector_key_and_exact_seen_feedback_q{problem}_{method}", passed=True, commands=index))
    result = dict(passed=2, failed=0, checks=checks, scored_executions=0, official_calls=0)
    (OUT / "collector_checks.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
