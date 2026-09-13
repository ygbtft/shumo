"""Train packet-wise task replanning on explicitly reused seed-42 scenes."""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

from client import Client
from interleaved_policy import InterleavedClearancePolicy, InterleavedProbePolicy
from layout_alternative_experiments import training_cases
from metaheuristic_experiments import write_json
from peer_benchmark import PeerTransport, Simulator, ErrorField, Limits, Protocol
import clearance_experiments as builders
import spatial_decision_experiments as engine

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "experiments/runs/2026-09-11_interleaved-tasks"
SPECS = {3: {
    "clearance7": dict(kind="clearance", layout="ring7"),
    "packet_center7": dict(kind="packet_clearance", layout="ring7"),
    "packet_action7": dict(kind="packet_clearance", layout="ring7", prediction="action"),
    "packet_nearest7": dict(kind="packet_clearance", layout="ring7", prediction="action", dispatch="nearest"),
    "packet_center9": dict(kind="packet_clearance", layout="ring9"),
}, 4: {
    "quarter22": dict(kind="probe", layout="convex22", fraction=.25, share_cooldown=150.),
    "packet_center22": dict(kind="packet_probe", layout="convex22", fraction=.25, share_cooldown=150.),
    "packet_action22": dict(kind="packet_probe", layout="convex22", fraction=.25, share_cooldown=150., prediction="action"),
    "packet_action4_22": dict(kind="packet_probe", layout="convex22", fraction=.25, share_cooldown=150., prediction="action", pause_limit=4),
    "packet_action24_22": dict(kind="packet_probe", layout="convex22", fraction=.25, share_cooldown=150., prediction="action", pause_limit=24),
    "packet_nearest22": dict(kind="packet_probe", layout="convex22", fraction=.25, share_cooldown=150., prediction="action", dispatch="nearest"),
    "packet_half22": dict(kind="packet_probe", layout="convex22", fraction=.5, share_cooldown=150., prediction="action"),
    "packet_action25": dict(kind="packet_probe", layout="polar25", fraction=.25, share_cooldown=150., prediction="action"),
}}


def paths():
    return builders.paths()


def build(client, spec, problem, all_paths):
    if not spec["kind"].startswith("packet"):
        return builders.build(client, spec, problem, all_paths)
    params = spec.copy()
    kind = params.pop("kind")
    points = all_paths[params.pop("layout")]
    if problem == 4:
        params.setdefault("trial_radius", 40.)
    cls = InterleavedClearancePolicy if kind == "packet_clearance" else InterleavedProbePolicy
    return cls(client, points, mixed=problem == 4, **params)


def freeze(all_paths):
    if (OUT / "run_config.json").exists():
        raise RuntimeError("Preserving completed training")
    checked = json.loads((OUT / "checks.json").read_text())
    assert checked["failed"] == 0
    snapshot = OUT / "code_snapshot"
    snapshot.mkdir()
    hashes = {}
    for path in ROOT.glob("*.py"):
        raw = path.read_bytes()
        (snapshot / path.name).write_bytes(raw)
        hashes[path.name] = hashlib.sha256(raw).hexdigest()
    write_json(OUT / "run_config.json", dict(base_seed=42, training_seeds=list(range(67, 72)),
        derivation="42+25+repeat, 0..4; already-used training scenes",
        stress_derivation="Q3 SeedSequence([42,35,layout_index,count]); Q4 [42,20,layout_index,count]; errors42+200+index/Q3,42+100+index/Q4",
        untouched_future_seeds=list(range(97, 107)), specs=SPECS,
        paths={name: p.tolist() for name, p in all_paths.items()}, expected_executions=1209,
        lifetime_probe_rounds_q4=10, lifetime_primary_rf_q3=3, max_interruptions=24,
        virtual_upper_bound_s=264096 + 24 * 2080, instruction_upper_bound=9766,
        engine_reuse="spatial_decision_experiments.run with explicit OUT/SPECS/build/freeze/all_layouts replacements",
        policy_reads_truth=False, official_calls=0, cpu_threads=1, python=sys.executable,
        peer_commit="c477d3660368f27c7131a0591426b4c4f107ea5d", code_sha256=hashes))
    (OUT / "precheck.md").write_text(f"# 运行前检查\n\n{checked['passed']}项检查通过，含零打断预算与旧训练反馈逐请求等价重放、完整协议压力检查和跨任务累计预算。13候选×93=1209，先冻结后运行；97—106未生成。本轮不宣称新确认，正式请求0。\n")


def check():
    if (OUT / "checks.json").exists():
        raise RuntimeError("Preserving prior checks")
    all_paths = paths()
    checks = []
    old = ROOT / "experiments/runs/2026-09-11_clearance-neighborhood"
    for problem, old_name, spec in (
        (3, "clearance7", {**SPECS[3]["packet_center7"], "pause_limit": 0}),
        (4, "quarter_cd22", {**SPECS[4]["packet_center22"], "pause_limit": 0}),
    ):
        for case_id, category, split, scenario, error in training_cases(problem):
            with gzip.open(old / "traces" / f"q{problem}__{case_id}__{old_name}.jsonl.gz", "rt") as stream:
                trace = [json.loads(line) for line in stream]
            index = 0
            def replay(endpoint, raw):
                nonlocal index
                entry = trace[index]
                assert endpoint == entry["path"] and json.loads(raw) == entry["request"], (problem, case_id, index)
                index += 1
                return 200, entry["response"]
            policy = build(Client(replay, robot_id="mock-robot"), spec, problem, all_paths)
            stats = policy.run()
            assert index == len(trace) and stats["source_interruptions"] == 0
            checks.append(dict(test=f"zero_interruptions_exact_feedback_q{problem}_{case_id}", passed=True, commands=index))
    for problem, methods in SPECS.items():
        selected = [c for c in training_cases(problem) if c[2] == "stress" and c[0].endswith(("n16__negative", "n10__spatial"))]
        for method, spec in methods.items():
            if not spec["kind"].startswith("packet"):
                continue
            for case_id, category, split, scenario, error in selected:
                sim = Simulator(scenario, ErrorField(scenario.seed, error), Limits(countdown_s=0))
                policy = build(Client(PeerTransport(Protocol(sim)), robot_id="mock-robot"), spec, problem, all_paths)
                stats = policy.run()
                assert len(sim.cleared) == len(scenario.sources), (method, case_id)
                assert not stats["inconsistent_updates"] and not stats["bracket_cut_inconsistencies"]
                assert stats["source_interruptions"] <= spec.get("pause_limit", 16)
                assert stats["maximum_source_primary_rf"] <= (20 if problem == 4 else 3)
                checks.append(dict(test=f"complete_protocol_lifetime_budget_q{problem}_{method}_{case_id}", passed=True,
                                   interruptions=stats["source_interruptions"], max_source_rf=stats["maximum_source_primary_rf"],
                                   total_s=sim.virtual_time_s))
    write_json(OUT / "checks.json", dict(passed=len(checks), failed=0, checks=checks, scored_execution_count=0))
    print("Passed", len(checks), "checks", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--launch", action="store_true")
    args = parser.parse_args()
    engine.OUT, engine.SPECS, engine.build = OUT, SPECS, build
    engine.freeze, engine.all_layouts = freeze, paths
    if args.check:
        check()
    elif args.launch:
        if (OUT / "run_config.json").exists():
            raise RuntimeError("Preserving old results")
        env = os.environ.copy()
        env.update(PYTHONDONTWRITEBYTECODE="1", OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1",
                   MPLCONFIGDIR=str(ROOT / ".mplconfig"), XDG_CACHE_HOME=str(ROOT / ".cache"))
        with (OUT / "log.txt").open("a") as stream:
            process = subprocess.Popen([sys.executable, "-B", str(Path(__file__).resolve())], cwd=ROOT.parent,
                                       env=env, stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
        (OUT / "background.pid").write_text(str(process.pid) + "\n")
        print("Background PID", process.pid)
    else:
        engine.run()


if __name__ == "__main__":
    main()
