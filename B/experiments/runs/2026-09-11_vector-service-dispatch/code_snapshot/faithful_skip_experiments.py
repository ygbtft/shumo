"""Check unabridged-plan equivalence and train stationary RF deletion."""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import numpy as np

from client import Client
from faithful_skip_policy import FaithfulCompletionPolicy, FaithfulWidthPolicy, FaithfulFastWidthPolicy
from layout_alternative_experiments import training_cases
from metaheuristic_experiments import write_json
from peer_benchmark import PeerTransport, Simulator, ErrorField, Limits, Protocol
import historical_pair_experiments as builders
import coupled_dispatch_experiments as coupled
import fast_dispatch_experiments as fast
import spatial_decision_experiments as engine

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "experiments/runs/2026-09-11_faithful-skips"
Q3 = dict(coupled.SPECS[3]["range_area7"], range_skip=False)
Q4 = dict(coupled.SPECS[4]["range_width015"], range_skip=False)
ARC = dict(fast.SPECS[4]["fast_arc05_width015"], range_skip=False)
LOCK = dict(fast.SPECS[4]["fast_locked_width015"], range_skip=False)
SPECS = {3: {
    "area_return1_7": coupled.SPECS[3]["area_return1_7"].copy(),
    "range_area7": coupled.SPECS[3]["range_area7"].copy(),
    "faithful_area7": dict(Q3, kind="faithful_completion"),
}, 4: {
    "width40_f015_22": coupled.SPECS[4]["width40_f015_22"].copy(),
    "range_width015": coupled.SPECS[4]["range_width015"].copy(),
    "faithful_width015": dict(Q4, kind="faithful_width"),
    "arc05_noskip_width015": ARC,
    "fast_arc05_width015": fast.SPECS[4]["fast_arc05_width015"].copy(),
    "faithful_arc05_width015": dict(ARC, kind="faithful_fast_width"),
    "locked_noskip_width015": LOCK,
    "fast_locked_width015": fast.SPECS[4]["fast_locked_width015"].copy(),
    "faithful_locked_width015": dict(LOCK, kind="faithful_fast_width"),
}}
CONTROLS = ((3, "faithful_area7", "area_return1_7"),
            (4, "faithful_width015", "width40_f015_22"),
            (4, "faithful_arc05_width015", "arc05_width015"),
            (4, "faithful_locked_width015", "locked_width015"))


def paths():
    return builders.paths()


def build(client, spec, problem, all_paths):
    if not spec["kind"].startswith("faithful_"):
        return builders.build(client, spec, problem, all_paths)
    params = spec.copy()
    kind = params.pop("kind")
    points = all_paths[params.pop("layout")]
    if problem == 4:
        params.setdefault("trial_radius", 40.)
    cls = {"faithful_completion": FaithfulCompletionPolicy, "faithful_width": FaithfulWidthPolicy,
           "faithful_fast_width": FaithfulFastWidthPolicy}[kind]
    return cls(client, points, mixed=problem == 4, **params)


def request_identity(entry):
    req = entry["request"]
    return entry["path"], req.get("position"), req.get("channel")


def expanded_plan_replay(trace, spec, problem, all_paths, enabled=True):
    """Only prior public feedback is available; skips consume logical entries.

    Replies retain archived times in this *decision replay*. They are never
    scoring output. Fresh actual protocols separately recompute reduced times.
    """
    index, skips = 0, []

    def replay(endpoint, raw):
        nonlocal index
        req = json.loads(raw)
        entry = trace[index]
        assert (endpoint, req.get("position"), req.get("channel")) == request_identity(entry), index
        if not enabled:
            assert req == entry["request"], index
        index += 1
        return 200, entry["response"]

    client = Client(replay, robot_id="mock-robot")
    policy = build(client, dict(spec, faithful_skip=enabled), problem, all_paths)
    measure = policy.measure

    def watched_measure(p, ch):
        nonlocal index
        before = (client.position, client.channel, client.virtual_s, client.sequence)
        result = measure(p, ch)
        if result == "certified_no_reception":
            entry = trace[index]
            assert entry["path"] == "/measure" and entry["request"]["channel"] == ch
            assert np.array_equal(p, [entry["request"]["position"]["x"], entry["request"]["position"]["y"]])
            assert entry["response"]["measure_result"] == "no_signal"
            assert before == (client.position, client.channel, client.virtual_s, client.sequence)
            assert np.array_equal(p, before[0]) and policy._planned_channel == ch
            assert np.array_equal(policy._attempted[ch][-1], p)
            if hasattr(policy, "_last_negative"):
                assert np.array_equal(policy._last_negative[ch], p)
            skips.append(index)
            index += 1
        return result

    policy.measure = watched_measure
    stats = policy.run()
    assert index == len(trace)
    assert stats["faithful_stationary_skips"] == len(skips)
    return dict(logical_commands=len(trace), actual_commands=client.sequence, skipped=len(skips),
                skipped_indices=skips, stop_reason=stats["stop_reason"])


def check():
    if (OUT / "checks.json").exists():
        raise RuntimeError("Preserving passed checks")
    checks, details = [], []
    rng = np.random.default_rng(42)
    for i in range(80):
        channels = rng.integers(1, 21, size=200)
        kept = channels[rng.uniform(size=200) > .4]
        before = int(np.count_nonzero(np.diff(np.r_[1, channels])))
        after = int(np.count_nonzero(np.diff(np.r_[1, kept])))
        assert after <= before
        checks.append(dict(test=f"switch_metric_subsequence_{i}", passed=True))
    all_paths = paths()
    for problem, new, old in CONTROLS:
        for case_id, category, split, scenario, error in training_cases(problem):
            path = ROOT / "experiments/runs/2026-09-11_coupled-dispatch/traces" / f"q{problem}__{case_id}__{old}.jsonl.gz"
            with gzip.open(path, "rt") as stream:
                trace = [json.loads(line) for line in stream]
            for enabled in (False, True):
                result = expanded_plan_replay(trace, SPECS[problem][new], problem, all_paths, enabled)
                checks.append(dict(test=f"{'expanded' if enabled else 'disabled'}_plan_q{problem}_{new}_{case_id}", passed=True,
                                   skipped=result["skipped"]))
                if enabled:
                    details.append(dict(problem=problem, strategy=new, case=case_id, **result))
    for problem, new, old in CONTROLS:
        selected = [c for c in training_cases(problem) if c[2] == "stress" and c[0].endswith(("n16__negative", "n10__spatial"))]
        for case_id, category, split, scenario, error in selected:
            runs = []
            for enabled in (False, True):
                sim = Simulator(scenario, ErrorField(scenario.seed, error), Limits(countdown_s=0))
                trace = []
                client = Client(PeerTransport(Protocol(sim)), robot_id="mock-robot", transcript=trace)
                stats = build(client, dict(SPECS[problem][new], faithful_skip=enabled), problem, all_paths).run()
                assert len(sim.cleared) == len(scenario.sources)
                assert not stats["inconsistent_updates"] and not stats.get("bracket_cut_inconsistencies", 0)
                runs.append((sim.virtual_time_s, trace, stats))
            baseline, candidate = runs
            k = candidate[2]["faithful_stationary_skips"]
            assert candidate[0] <= baseline[0] - 5*k + 1e-5
            assert len(candidate[1]) == len(baseline[1]) - k
            detail = expanded_plan_replay(baseline[1], SPECS[problem][new], problem, all_paths)
            reduced = [e for i, e in enumerate(baseline[1]) if i not in set(detail["skipped_indices"])]
            assert [request_identity(e) for e in reduced] == [request_identity(e) for e in candidate[1]]
            checks.append(dict(test=f"actual_protocol_subsequence_and_cost_q{problem}_{new}_{case_id}", passed=True,
                               skipped=k, saved_s=baseline[0]-candidate[0]))
    write_json(OUT / "expanded_plan_checks.json", details)
    write_json(OUT / "checks.json", dict(passed=len(checks), failed=0, checks=checks,
                                        scored_execution_count=0, official_calls=0))
    print("Passed", len(checks), "checks; expanded-plan skips", sum(r["skipped"] for r in details), flush=True)


def freeze(all_paths):
    if (OUT / "run_config.json").exists():
        raise RuntimeError("Preserving training archive")
    result = json.loads((OUT / "checks.json").read_text())
    assert result["failed"] == 0
    snapshot = OUT / "code_snapshot"
    snapshot.mkdir()
    hashes = {}
    for path in ROOT.glob("*.py"):
        raw = path.read_bytes()
        (snapshot / path.name).write_bytes(raw)
        hashes[path.name] = hashlib.sha256(raw).hexdigest()
    write_json(OUT / "run_config.json", dict(base_seed=42, training_seeds=list(range(67, 72)),
        derivation="42+25+repeat,0..4; already-used training scenes", untouched_future_seeds=list(range(127,137)),
        stress_derivation="Q3 [42,35,layout_index,count], Q4 [42,20,layout_index,count]; prior training streams",
        specs=SPECS, paths={k:v.tolist() for k,v in all_paths.items()}, expected_executions=1116,
        skip_certificate="Certified known-source range, surveying, exactly same physical position; logical channel/attempt history retained",
        dominance_scope="Versus respective no-skip deterministic plans, virtual time and commands; no CPU dominance claim",
        additional_measurement_budget=0, virtual_upper_bound_s=335136, instruction_upper_bound=9766,
        engine_reuse="spatial_decision_experiments.run with explicit OUT/SPECS/build/freeze/all_layouts replacements",
        code_sha256=hashes, python=sys.executable, cpu_threads=1, truth_to_policy=False, official_calls=0,
        peer_commit="c477d3660368f27c7131a0591426b4c4f107ea5d"))
    (OUT / "precheck.md").write_text(f"# 保序静止RF删除训练前检查\n\n{result['passed']}项通过：80条独立频道子序列成本，372次关闭功能严格重放，372次只读反馈展开计划，24组双实际协议子序列及减费核验。12策略×93=1116，127—136留待冻结，正式请求0。\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--launch", action="store_true")
    args = parser.parse_args()
    engine.OUT, engine.SPECS, engine.build, engine.freeze, engine.all_layouts = OUT, SPECS, build, freeze, paths
    if args.check:
        check()
    elif args.launch:
        if (OUT / "run_config.json").exists():
            raise RuntimeError("Preserving scored run")
        env = os.environ.copy()
        env.update(PYTHONDONTWRITEBYTECODE="1", OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1",
                   MPLCONFIGDIR=str(ROOT / ".mplconfig"), XDG_CACHE_HOME=str(ROOT / ".cache"))
        with (OUT / "log.txt").open("a") as stream:
            process = subprocess.Popen([sys.executable, "-B", str(Path(__file__).resolve())], cwd=ROOT.parent,
                                       env=env, stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
        (OUT / "background.pid").write_text(str(process.pid)+"\n")
        print("Background PID", process.pid)
    else:
        engine.run()


if __name__ == "__main__":
    main()
