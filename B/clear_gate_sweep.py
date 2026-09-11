"""Paired local-mock sweep; truth is used only by the simulator and scorer.

Example: ../mock/.venv/bin/python clear_gate_sweep.py --output experiments/runs/clear-gate-training
Every radius uses identical cases and position-keyed error fields. Radius 0
disables early trials only; the unchanged finite optical fallback can still miss.
"""
import argparse
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import sys
import time

for name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[name] = "1"
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))
import mock
from mock.error_field import ErrorConfig, ErrorField
from mock.scenario_gen import Scenario, ScenarioConfig, generate
from mock.simulator import Simulator, Limits
from mock.protocol import Protocol
sys.path.insert(0, str(ROOT))
import numpy as np
from client import Client
from peer_benchmark import PeerTransport
import cover21_confirmation as builders

METHODS = {3: "range_area7", 4: "range_grid21_29"}
BASELINE = {3: 80., 4: 40.}
RADII = {3: [80., 60., 40., 30., 25., 22., 20., 0.],
         4: [40., 35., 30., 25., 22., 20., 0.]}


def cases(problem, repeats, seed_start):
    errors = [ErrorConfig(), ErrorConfig(model="smooth"),
              *[ErrorConfig(model="adversarial", adversarial_sign=s)
                for s in ("positive", "negative", "spatial")]]
    index = 0
    for repeat in range(repeats):
        for count in range(10, 17):
            for layout in ("uniform", "edge", "clustered"):
                for error in errors:
                    seed = seed_start + index
                    config = ScenarioConfig(count_min=count, count_max=count,
                        position_distribution=layout, directional_fraction=.5 if problem == 4 else 0.,
                        direction_distribution="outward" if repeat % 2 else "uniform",
                        radius_distribution="fixed" if repeat % 2 else "uniform", radius_fixed=1000.)
                    yield dict(case_id=f"q{problem}_{seed}", scenario=generate(seed, config).to_dict(),
                               error=asdict(error), category=f"{layout}/{error.model}/{error.adversarial_sign}")
                    index += 1


def execute(task):
    problem, radius, fixture, spec, paths = task
    scenario = Scenario.from_dict(fixture["scenario"])
    sim = Simulator(scenario, ErrorField(scenario.seed, ErrorConfig(**fixture["error"])), Limits(countdown_s=0))
    parameters = spec.copy() if radius is None else dict(spec, trial_radius=radius)
    policy = builders.build(Client(PeerTransport(Protocol(sim)), robot_id="mock-robot"),
                            parameters, problem, paths)
    if radius is None:
        radius = policy.trial_radius
    assert policy.trial_radius == radius
    if problem == 4:
        assert policy.bracket_trial_radius == radius
    events = []
    original = policy.clear

    def observed_clear(point, channel, certified=False):
        bound = policy.circle(channel)[1] if channel in policy.regions else None
        before = sim.virtual_time_s
        success = original(point, channel, certified)
        events.append(dict(channel=channel, radius=bound, certified=certified,
                           success=success, virtual_delta_s=sim.virtual_time_s-before))
        return success

    policy.clear = observed_clear
    began = time.perf_counter()
    failure = ""
    stats = {}
    try:
        stats = policy.run()
    except Exception as exc:
        failure = repr(exc)
    misses = sum(e["path"] == "/clear" and e["response"].get("clear_result") == "no_target_in_range"
                 for e in sim.trace)
    assert misses == sum(not e["success"] for e in events)
    return dict(problem=problem, radius=radius, case_id=fixture["case_id"], category=fixture["category"],
                split=fixture.get("split", "ordinary"),
                sources=len(scenario.sources), cleared=len(sim.cleared),
                all_cleared=len(sim.cleared) == len(scenario.sources), failure=failure,
                clear_failure_count=misses, total_virtual_s=sim.virtual_time_s,
                wall_s=time.perf_counter()-began, stats=stats, clear_events=events)


def summarize(rows, out):
    result = []
    rng = np.random.default_rng(20260911)
    for problem in (3, 4):
        base = {r["case_id"]: r for r in rows if r["problem"] == problem and r["radius"] == BASELINE[problem]}
        for radius in sorted({r["radius"] for r in rows if r["problem"] == problem}, reverse=True):
            group = [r for r in rows if r["problem"] == problem and r["radius"] == radius]
            sources = np.array([r["sources"] for r in group])
            delta = np.array([r["total_virtual_s"]-base[r["case_id"]]["total_virtual_s"] for r in group])
            # Paired case bootstrap, keeping source weighting inside each resample.
            ids = rng.integers(len(group), size=(4000, len(group)))
            ci = np.quantile(delta[ids].sum(axis=1)/sources[ids].sum(axis=1), [.025, .975])
            trials = sum(r["stats"].get("early_optical_trials", 0)+r["stats"].get("bracket_optical_trials", 0) for r in group)
            success = sum(r["stats"].get("early_optical_success", 0)+r["stats"].get("bracket_optical_success", 0) for r in group)
            result.append(dict(problem=problem, radius=radius, runs=len(group), sources=int(sources.sum()),
                all_cleared=sum(r["all_cleared"] and not r["failure"] for r in group),
                clear_failure_count=sum(r["clear_failure_count"] for r in group),
                pooled_per_source_s=sum(r["total_virtual_s"] for r in group)/int(sources.sum()),
                delta_per_source_s=float(delta.sum()/sources.sum()), delta_95ci_s=ci.tolist(),
                early_trials=trials, early_failures=trials-success,
                certified_failures=sum(e["certified"] and not e["success"] for r in group for e in r["clear_events"]),
                slower_cases=int((delta > 1e-6).sum()), worst_case_delta_s=float(delta.max())))
    (out/"summary.json").write_text(json.dumps(result, indent=2)+"\n")
    lines = ["|问题|门限 m|局数/全清|失手|秒/源（源加权）|相对基线秒/源|配对95%区间|提前试探/失手|",
             "|---|---:|---:|---:|---:|---:|---|---:|"]
    for r in result:
        lines.append(f"|Q{r['problem']}|{r['radius']:g}|{r['runs']}/{r['all_cleared']}|{r['clear_failure_count']}|"
                     f"{r['pooled_per_source_s']:.4f}|{r['delta_per_source_s']:+.4f}|{r['delta_95ci_s']}|{r['early_trials']}/{r['early_failures']}|")
    (out/"summary.md").write_text("\n".join(lines)+"\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=2, help="105 unique seeds per repeat and problem")
    parser.add_argument("--seed-start", type=int, default=202609110)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--radii", type=float, nargs="+", help="Common radii; original baseline always included")
    parser.add_argument("--q3-radii", type=float, nargs="+")
    parser.add_argument("--q4-radii", type=float, nargs="+")
    parser.add_argument("--stress", action="store_true", help="Also run existing 45 boundary/collinearity stress cases per problem")
    args = parser.parse_args()
    supplied = (args.radii or []) + (args.q3_radii or []) + (args.q4_radii or [])
    if args.repeats < 1 or any(not 0 <= r <= 80 for r in supplied):
        parser.error("Positive repeats and radii in [0,80] required")
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    if (out/"config.json").exists():
        raise RuntimeError("Choose a fresh output directory; preserving scored results")
    paths = builders.all_paths()
    specs = {p: builders.SPECS[p][METHODS[p]].copy() for p in METHODS}
    radii = {p: sorted(set([BASELINE[p]]+(getattr(args, f"q{p}_radii") or args.radii or RADII[p])), reverse=True) for p in METHODS}
    fixtures = {p: list(cases(p, args.repeats, args.seed_start)) for p in METHODS}
    if args.stress:
        for p in METHODS:
            for cid, category, split, scenario, error in builders.cases(p):
                if split == "stress":
                    fixtures[p].append(dict(case_id=f"q{p}_{cid}", category=category, split="stress",
                                            scenario=scenario.to_dict(), error=asdict(error)))
    snapshot = out/"code_snapshot"
    snapshot.mkdir()
    hashes = {}
    for path in ROOT.glob("*.py"):
        data = path.read_bytes()
        (snapshot/path.name).write_bytes(data)
        hashes[path.name] = hashlib.sha256(data).hexdigest()
    config = dict(python=sys.executable, mock_path=mock.__file__, seeds_start=args.seed_start,
                  repeats=args.repeats, radii=radii, specs=specs, code_sha256=hashes,
                  paths={k: v.tolist() for k, v in paths.items()}, official_calls=0,
                  metric="sum(total_virtual_s)/sum(actual_sources); all failures retained",
                  mock_sha256={p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in Path(mock.__file__).parent.glob("*.py")})
    (out/"config.json").write_text(json.dumps(config, indent=2)+"\n")
    (out/"fixtures.json").write_text(json.dumps(fixtures)+"\n")
    tasks = [(p, r, f, specs[p], paths) for p in METHODS for f in fixtures[p] for r in radii[p]]
    rows = []
    began = time.perf_counter()
    with (out/"trials.jsonl").open("x") as stream, ProcessPoolExecutor(max_workers=args.workers) as pool:
        for row in pool.map(execute, tasks, chunksize=1):
            rows.append(row)
            stream.write(json.dumps(row)+"\n")
            stream.flush()
            if len(rows) % 50 == 0:
                print(f"{len(rows)}/{len(tasks)} runs, {time.perf_counter()-began:.1f}s", flush=True)
    summarize(rows, out)
    if args.stress:
        for split in ("ordinary", "stress"):
            target = out/split
            target.mkdir()
            summarize([r for r in rows if r["split"] == split], target)
    failed = [r for r in rows if r["failure"] or not r["all_cleared"]]
    (out/"completion.json").write_text(json.dumps(dict(runs=len(rows), failed=len(failed), wall_s=time.perf_counter()-began), indent=2)+"\n")
    print((out/"summary.md").read_text(), flush=True)
    if failed:
        raise RuntimeError(f"{len(failed)} incomplete/error runs; retained in denominator and artifacts")


if __name__ == "__main__":
    main()
