"""Checks that matter for routing: coverage permutation, costs, velocity, reproducibility."""
from itertools import permutations
import json
from pathlib import Path
import numpy as np
from coverage import square_stations, triangle_stations, route_length
from route_algorithms import Problem, Budget, METHODS, STOCHASTIC, optimize, two_opt, swap_difference, order_crossover

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "experiments/runs/2026-09-10_metaheuristics"


def main():
    rng = np.random.default_rng(42)
    checks = []
    # Independent brute force for small arbitrary sets; objective and bound sanity.
    for trial in range(6):
        points = np.vstack((np.zeros(2), rng.uniform(-10, 10, size=(6, 2))))
        p = Problem(points)
        optimum = min(route_length(points[[0]+list(t)]) for t in permutations(range(1, 7)))
        assert p.lower_bound <= optimum+1e-7
        for method in METHODS:
            route, meta = optimize(points, method, seed=42, budget=3000)
            assert meta["best_m"] >= optimum-1e-7
            assert sorted(map(tuple, route)) == sorted(map(tuple, points))
            if method in STOCHASTIC:
                assert meta["comparisons"] <= meta["comparison_budget"]
        checks.append(f"brute_force_permutation_objective_{trial}")
    for trial in range(50):
        p = Problem(np.vstack((np.zeros(2), rng.normal(size=(9, 2)))))
        a, b = [np.r_[0, rng.permutation(np.arange(1, p.n))] for _ in range(2)]
        q = a.copy()
        for i, j in swap_difference(q, b):
            q[i], q[j] = q[j], q[i]
        assert np.array_equal(q, b)
        p.validate(order_crossover(a, b, rng))
        polished = two_opt(p, a, Budget(10000), sweeps=30)
        assert route_length(p.points[polished]) <= route_length(p.points[a])+1e-7
        checks.append(f"swap_velocity_crossover_two_opt_{trial}")
    for method in STOCHASTIC:
        p = np.vstack((np.zeros(2), rng.normal(size=(10, 2))))
        a, ma = optimize(p, method, seed=42, budget=3500)
        b, mb = optimize(p, method, seed=42, budget=3500)
        assert np.array_equal(a, b) and ma["history"] == mb["history"]
        checks.append(f"reproducibility_{method}")
    for points in (square_stations(), square_stations(700, True), triangle_stations(1700)):
        _, meta = optimize(points, "two_opt")
        assert meta["certified_optimal"]
        checks.append(meta["bound_kind"])
    OUT.mkdir(parents=True, exist_ok=True)
    result = {"base_seed": 42, "checks": checks, "passed": len(checks), "failed": 0}
    (OUT/"checks.json").write_text(json.dumps(result, indent=2))
    print(json.dumps({"passed": len(checks), "failed": 0}))


if __name__ == "__main__":
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",help="Fresh check directory under B/ for reproducing the main matrix")
    args=parser.parse_args()
    if args.output:
        OUT=Path(args.output).resolve()
        if not OUT.is_relative_to(ROOT):parser.error("Output must stay below B/")
    main()
