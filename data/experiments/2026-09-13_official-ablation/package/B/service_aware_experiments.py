"""Train bounded service-aware routing on reused scenes, without new holdout."""
import gzip
import json
import math
from pathlib import Path
from types import SimpleNamespace
import numpy as np
from client import Client
from metaheuristic_experiments import write_json
from layout_alternative_experiments import training_cases
from peer_benchmark import PeerTransport, Simulator, ErrorField, Limits, Protocol
from fast_dispatch_policy import FastWidthPolicy, FastCompletionPolicy, fast_arc_route
from service_aware_policy import (ServiceAwareWidthPolicy, ServiceAwareCompletionPolicy,
    service_route, route_objective, reversal_prefix, reversal_delta, directed_insertion,
    ServiceAwareMixin)
import cover21_confirmation as previous
import cover21_experiments as layouts
import scan_experiment_support as support

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "experiments/runs/2026-09-11_service-aware-dispatch"


def candidate(problem, layout, weight=1., mode="free", order=0.):
    base = previous.SPECS[3]["range_area7"] if problem == 3 else previous.SPECS[4]["range_grid21_29"]
    return dict(base, kind="service_completion" if problem == 3 else "service_width",
                layout=layout, dispatch_model="arc", entry_blend=.5,
                scan_cost_weight=weight, service_mode=mode, scan_order_cost_s=order)


SPECS = {3: {
    "range_area7": previous.SPECS[3]["range_area7"].copy(),
    "service_free0_area7": candidate(3, "ring7", weight=0.),
    "service_free1_area7": candidate(3, "ring7"),
    "service_locked1_area7": candidate(3, "ring7", mode="locked"),
}, 4: {
    "range_grid21_29": previous.SPECS[4]["range_grid21_29"].copy(),
    "range_convex22": previous.SPECS[4]["range_convex22"].copy(),
    "count_locked_grid21_29": previous.SPECS[4]["count_locked_grid21_29"].copy(),
    "service_free0_grid21_29": candidate(4, "grid21_29", weight=0.),
    "service_free1_grid21_29": candidate(4, "grid21_29"),
    "service_free2_grid21_29": candidate(4, "grid21_29", weight=2.),
    "service_locked0_grid21_29": candidate(4, "grid21_29", weight=0., mode="locked"),
    "service_locked1_grid21_29": candidate(4, "grid21_29", mode="locked"),
    "service_soft20_grid21_29": candidate(4, "grid21_29", order=20.),
    "service_free1_convex22": candidate(4, "convex22"),
    "service_locked1_convex22": candidate(4, "convex22", mode="locked"),
}}
EXPECTED = sum(map(len, SPECS.values()))*93
assert EXPECTED == 1395
paths = layouts.paths


def build(client, spec, problem, all_paths):
    if not spec["kind"].startswith("service_"):
        return previous.build(client, spec, problem, all_paths)
    params = spec.copy()
    kind, stations = params.pop("kind"), all_paths[params.pop("layout")]
    if problem == 4:
        params.setdefault("trial_radius", 40.)
    cls = ServiceAwareWidthPolicy if kind == "service_width" else ServiceAwareCompletionPolicy
    return cls(client, stations, mixed=problem == 4, **params)


def independent_cost(route, entries, exits, current, precedence):
    if not len(route):
        return 0.
    result = math.dist(current, entries[route[0]])
    result += sum(math.dist(exits[a], entries[b]) for a, b in zip(route[:-1], route[1:]))
    result += sum(float(precedence[a, b]) for i, a in enumerate(route) for b in route[i+1:])
    return result


def check():
    if (OUT/"checks.json").exists():
        raise RuntimeError("Preserving completed checks")
    checks = []
    rng = np.random.default_rng(42)
    for trial in range(40):
        n = int(rng.integers(1, 14))
        entry, exit_, origin = rng.normal(size=(n, 2))*1000, rng.normal(size=(n, 2))*1000, rng.normal(size=2)*1000
        penalty = rng.integers(0, 100, size=(n, n)).astype(float)
        np.fill_diagonal(penalty, 0.)
        costs, start = np.linalg.norm(exit_[:, None]-entry[None, :], axis=2), np.linalg.norm(entry-origin, axis=1)
        route = rng.permutation(n)
        assert abs(route_objective(route, costs, start, penalty)-independent_cost(route, entry, exit_, origin, penalty)) < 1e-7
        prefix = reversal_prefix(route, costs, penalty)
        for i in range(n-1):
            for j in range(i+1, n):
                r = route.copy(); r[i:j+1] = r[i:j+1][::-1]
                delta = independent_cost(r, entry, exit_, origin, penalty)-independent_cost(route, entry, exit_, origin, penalty)
                assert abs(delta-reversal_delta(route, i, j, costs, start, prefix)) < 1e-7
        station_count = int(rng.integers(0, n+1))
        for mode in ("free", "locked"):
            initial = service_route(entry, exit_, origin, penalty, station_count, mode, False)
            final = service_route(entry, exit_, origin, penalty, station_count, mode, True)
            assert sorted(final) == list(range(n))
            assert independent_cost(final, entry, exit_, origin, penalty) <= independent_cost(initial, entry, exit_, origin, penalty)+1e-7
            if mode == "locked":
                assert [int(x) for x in final if x < station_count] == list(range(station_count))
        assert np.array_equal(service_route(entry, exit_, origin, np.zeros((n, n)), station_count), fast_arc_route(entry, exit_, origin))
        checks.append(dict(test=f"independent_objective_every_reversal_polish_and_zero_weight_{trial}", passed=True, nodes=n))
    for trial in range(40):
        n = int(rng.integers(1, 12))
        entries, exits, origin = rng.normal(size=(n+1, 2))*1000, rng.normal(size=(n+1, 2))*1000, rng.normal(size=2)*1000
        penalty = rng.integers(0, 100, size=(n+1, n+1)).astype(float)
        costs, start = np.linalg.norm(exits[:, None]-entries[None, :], axis=2), np.linalg.norm(entries-origin, axis=1)
        result = directed_insertion(costs, start, penalty, n)
        options = [list(range(i))+[n]+list(range(i, n)) for i in range(n+1)]
        assert abs(independent_cost(result, entries, exits, origin, penalty)-min(independent_cost(r, entries, exits, origin, penalty) for r in options)) < 1e-7
        checks.append(dict(test=f"exhaustive_single_source_insertion_{trial}", passed=True))
    # The established scan already omits a source with a certified <=20 m
    # region. Explicitly reject a duplicate reward for clearing that source.
    stations = [np.array([0., 0.]), np.array([1700., 0.])]
    tasks = [("survey", i, p) for i, p in enumerate(stations)] + [("source", 1, np.zeros(2)), ("source", 2, np.zeros(2))]
    fake = SimpleNamespace(scan_cost_weight=1., scan_order_cost_s=0., stats={"modeled_known_scan_pairs":0},
                           circle=lambda ch: (np.zeros(2), 19. if ch == 1 else 50.))
    penalty = ServiceAwareMixin.precedence_costs(fake, tasks, 2)
    assert np.all(penalty[:, 2] == 0) and penalty[0, 3] == 25. and penalty[1, 3] == 0.
    checks.append(dict(test="no_reward_for_already_precise_or_certified_out_of_range_scan", passed=True))
    all_paths = paths()
    controls = []
    for problem in (3, 4):
        name = "service_free0_area7" if problem == 3 else "service_free0_grid21_29"
        scenarios = [case for case in training_cases(problem) if case[2] == "stress" or case[0] == "uniform__iid__67"]
        for case_id, _, _, scenario, error in scenarios:
            spec = SPECS[problem][name]
            params = {k:v for k,v in spec.items() if k not in ("kind", "layout", "scan_cost_weight", "scan_order_cost_s", "service_mode")}
            if problem == 4:
                params.setdefault("trial_radius", 40.)
            sim = Simulator(scenario, ErrorField(scenario.seed, error), Limits(countdown_s=0))
            cls = FastWidthPolicy if problem == 4 else FastCompletionPolicy
            cls(Client(PeerTransport(Protocol(sim)), robot_id="mock-robot"), all_paths[spec["layout"]], mixed=problem == 4, **params).run()
            index = 0
            def replay(endpoint, raw):
                nonlocal index
                expected = sim.trace[index]
                assert endpoint == expected["path"] and json.loads(raw) == expected["request"], (name, case_id, index)
                index += 1
                return 200, expected["response"]
            build(Client(replay, robot_id="mock-robot"), spec, problem, all_paths).run()
            assert index == len(sim.trace)
            controls.append(dict(problem=problem, case_id=case_id, commands=index))
            checks.append(dict(test=f"zero_weight_old_fast_arc_public_replay_q{problem}_{case_id}", passed=True))
    write_json(OUT/"zero_weight_controls.json", controls)
    trace_dir = OUT/"precheck_protocol_traces"
    trace_dir.mkdir(exist_ok=True)
    for problem, methods in SPECS.items():
        for case_id, _, split, scenario, error in training_cases(problem):
            if split != "stress":
                continue
            for name, spec in methods.items():
                sim = Simulator(scenario, ErrorField(scenario.seed, error), Limits(countdown_s=0))
                stats = build(Client(PeerTransport(Protocol(sim)), robot_id="mock-robot"), spec, problem, all_paths).run()
                assert len(sim.cleared) == len(scenario.sources)
                assert not stats["inconsistent_updates"] and not stats.get("bracket_cut_inconsistencies", 0)
                assert sim.virtual_time_s < 335136 and len(sim.trace) <= 9766
                if problem == 4:
                    assert stats["source_interruptions"] <= spec.get("pause_limit", 16)
                    assert stats["maximum_source_rounds"] <= 10 and stats["maximum_source_primary_rf"] <= 20
                with gzip.open(trace_dir/f"q{problem}__{case_id}__{name}.jsonl.gz", "wt") as stream:
                    for e in sim.trace:
                        stream.write(json.dumps(e, separators=(",", ":"))+"\n")
                checks.append(dict(test=f"full_protocol_q{problem}_{name}_{case_id}", passed=True,
                                   total_virtual_s=sim.virtual_time_s, commands=len(sim.trace), stop_reason=stats["stop_reason"]))
        print("Protocol prechecks completed Q", problem, flush=True)
    write_json(OUT/"checks.json", dict(passed=len(checks), failed=0, checks=checks, scored_executions=0, official_calls=0))
    print("Passed", len(checks), flush=True)


def freeze(all_paths):
    support.freeze(OUT, SPECS, all_paths,
        "扫描当前未能排除的已知源需5秒RF，计入有向任务次序代价；只作为冻结区域的排名代理，不预知真实源/未来反馈。",
        dict(untouched_future_seeds=list(range(157, 167)),
             expected_executions=EXPECTED, ranking_only=True,
             surrogate_limitations="MEC center/entry and region are frozen for ranking; actual packet may not finish source, other scans may shrink region; RF switch costs are not included in surrogate; no pointwise cost guarantee",
             invariants="same certified stations, bounded source actions and lifetime pause budget, full optical fallback and public stop conditions"))
    p = OUT/"precheck.md"
    p.write_text(p.read_text().replace("未来147—156", "未来157—166"))


if __name__ == "__main__":
    support.main(OUT, SPECS, build, paths, check, freeze, __file__)
