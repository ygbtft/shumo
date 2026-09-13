"""Verify equivalent vector routing and measure its actual CPU tradeoff."""
import json
from pathlib import Path
import numpy as np
from client import Client
from metaheuristic_experiments import write_json
from mission_final_checks import load_trace
from service_aware_policy import service_route
from vector_service_policy import vector_service_route, VectorServiceWidthPolicy, VectorServiceCompletionPolicy
import service_aware_experiments as scalar
import scan_experiment_support as support

ROOT = Path(__file__).resolve().parent
OUT = ROOT/"experiments/runs/2026-09-11_vector-service-dispatch"
FAMILIES = [(3, "service_locked1_area7"), (4, "service_free2_grid21_29"),
            (4, "service_locked0_grid21_29"), (4, "service_free1_convex22"), (4, "service_locked1_convex22")]
SPECS = {3:{}, 4:{}}
for problem, name in FAMILIES:
    old = scalar.SPECS[problem][name]
    SPECS[problem][name] = old.copy()
    SPECS[problem]["vector_"+name] = dict(old, kind="vector_"+old["kind"])
EXPECTED = sum(map(len, SPECS.values()))*93
assert EXPECTED == 930
paths = scalar.paths


def build(client, spec, problem, all_paths):
    if not spec["kind"].startswith("vector_service_"):
        return scalar.build(client, spec, problem, all_paths)
    params = spec.copy()
    kind, stations = params.pop("kind"), all_paths[params.pop("layout")]
    if problem == 4:
        params.setdefault("trial_radius", 40.)
    cls = VectorServiceWidthPolicy if kind == "vector_service_width" else VectorServiceCompletionPolicy
    return cls(client, stations, mixed=problem == 4, **params)


def check():
    if (OUT/"checks.json").exists():
        raise RuntimeError("Preserving completed checks")
    rng = np.random.default_rng(42)
    checks = []
    for trial in range(120):
        n = int(rng.integers(1, 39))
        entry, exit_, origin = rng.normal(size=(n, 2))*1000, rng.normal(size=(n, 2))*1000, rng.normal(size=2)*1000
        if trial % 6 == 0:
            exit_ = entry.copy()
        if trial % 10 == 0:
            entry[:min(n, 3)] = 0.
            exit_[:min(n, 3)] = 0.
        penalty = rng.integers(0, 100, size=(n, n)).astype(float)
        np.fill_diagonal(penalty, 0.)
        if trial % 5 == 0:
            penalty[:] = 0.
        stations = int(rng.integers(0, n+1))
        for mode in ("free", "locked"):
            for polish in (True, False):
                a = service_route(entry, exit_, origin, penalty, stations, mode, polish)
                b = vector_service_route(entry, exit_, origin, penalty, stations, mode, polish)
                assert np.array_equal(a, b), (trial, mode, polish, a, b)
        checks.append(dict(test=f"same_route_with_ties_zero_cost_and_arbitrary_directed_costs_{trial}", passed=True, nodes=n))
    all_paths = paths()
    rows = [json.loads(line) for line in (scalar.OUT/"trials.jsonl").read_text().splitlines()]
    for problem, name in FAMILIES:
        for row in rows:
            if (row["problem"], row["method"]) != (problem, name):
                continue
            trace = load_trace(scalar.OUT/"traces"/f"q{problem}__{row['case_id']}__{name}.jsonl.gz")
            index = 0
            def replay(endpoint, raw):
                nonlocal index
                expected = trace[index]
                assert endpoint == expected["path"] and json.loads(raw) == expected["request"], (problem, name, row["case_id"], index)
                index += 1
                return 200, expected["response"]
            stats = build(Client(replay, robot_id="mock-robot"), SPECS[problem]["vector_"+name], problem, all_paths).run()
            assert index == len(trace)
            assert all(key in row and value == row[key] for key, value in stats.items())
            checks.append(dict(test=f"full_public_feedback_and_all_statistics_q{problem}_{name}_{row['case_id']}", passed=True))
        print("Equivalent", problem, name, flush=True)
    assert len(checks) == 585
    write_json(OUT/"checks.json", dict(passed=len(checks), failed=0, checks=checks, scored_executions=0, official_calls=0))
    print("Passed", len(checks), flush=True)


def freeze(all_paths):
    support.freeze(OUT, SPECS, all_paths,
        "按原标量顺序接受第一个改进，再重算后续反转候选；5组实际反馈/全部统计等价，比较CPU而不虚构虚拟收益。",
        dict(untouched_future_seeds=list(range(157, 167)), expected_executions=EXPECTED,
             same_decision_pairs_before_training=465, route_equivalence_tests=120,
             scalar_training_out=str(scalar.OUT.relative_to(ROOT))))
    p = OUT/"precheck.md"
    p.write_text(p.read_text().replace("未来147—156", "未来157—166"))


if __name__ == "__main__":
    support.main(OUT, SPECS, build, paths, check, freeze, __file__)
