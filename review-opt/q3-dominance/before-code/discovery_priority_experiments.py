"""Ablate finite-prior discovery rewards without weakening coverage guarantees."""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from client import Client
from discovery_priority_policy import (DiscoveryClearancePolicy, DiscoveryProbePolicy,
                                        DiscoveryPacketClearancePolicy, DiscoveryPacketProbePolicy)
from layout_alternative_experiments import training_cases
from metaheuristic_experiments import write_json
from peer_benchmark import PeerTransport, Simulator, ErrorField, Limits, Protocol
import interleaved_experiments as builders
import spatial_decision_experiments as engine

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "experiments/runs/2026-09-11_discovery-priority"
# Removed clear-reward variants are archived in the original run snapshot;
# see ../code-review/fix-discovery-clear-weight.md for the historical mapping.
SPECS = {3: {
    "packet_center7": dict(kind="packet_clearance", layout="ring7"),
    "discover300_7": dict(kind="discovery_clearance", layout="ring7", discovery_weight=300.),
    "discover900_7": dict(kind="discovery_clearance", layout="ring7", discovery_weight=900.),
    "discover1800_7": dict(kind="discovery_clearance", layout="ring7", discovery_weight=1800.),
    "packet_discover300_7": dict(kind="discovery_packet_clearance", layout="ring7", discovery_weight=300.),
    "packet_discover900_7": dict(kind="discovery_packet_clearance", layout="ring7", discovery_weight=900.),
}, 4: {
    "packet_action4_22": dict(kind="packet_probe", layout="convex22", fraction=.25, share_cooldown=150., prediction="action", pause_limit=4),
    "discover300_22": dict(kind="discovery_probe", layout="convex22", fraction=.25, share_cooldown=150., discovery_weight=300.),
    "discover900_22": dict(kind="discovery_probe", layout="convex22", fraction=.25, share_cooldown=150., discovery_weight=900.),
    "discover1800_22": dict(kind="discovery_probe", layout="convex22", fraction=.25, share_cooldown=150., discovery_weight=1800.),
    "packet_discover300_22": dict(kind="discovery_packet_probe", layout="convex22", fraction=.25, share_cooldown=150., discovery_weight=300., prediction="action", pause_limit=4),
    "packet_discover900_22": dict(kind="discovery_packet_probe", layout="convex22", fraction=.25, share_cooldown=150., discovery_weight=900., prediction="action", pause_limit=4),
    "packet_discover1800_22": dict(kind="discovery_packet_probe", layout="convex22", fraction=.25, share_cooldown=150., discovery_weight=1800., prediction="action", pause_limit=4),
}}


def paths():
    return builders.paths()


def build(client, spec, problem, all_paths):
    began = time.perf_counter()
    if not spec["kind"].startswith("discovery"):
        policy = builders.build(client, spec, problem, all_paths)
    else:
        params = spec.copy()
        kind = params.pop("kind")
        points = all_paths[params.pop("layout")]
        if problem == 4:
            params.setdefault("trial_radius", 40.)
        cls = {"discovery_clearance": DiscoveryClearancePolicy, "discovery_probe": DiscoveryProbePolicy,
               "discovery_packet_clearance": DiscoveryPacketClearancePolicy,
               "discovery_packet_probe": DiscoveryPacketProbePolicy}[kind]
        policy = cls(client, points, mixed=problem == 4, **params)
    policy.stats["initialization_s"] = time.perf_counter() - began
    return policy


def freeze(all_paths):
    if (OUT / "run_config.json").exists():
        raise RuntimeError("Preserving prior results")
    checked = json.loads((OUT / "checks.json").read_text())
    assert checked["failed"] == 0
    snapshot = OUT / "code_snapshot"
    snapshot.mkdir()
    hashes = {}
    for path in ROOT.glob("*.py"):
        raw = path.read_bytes()
        (snapshot / path.name).write_bytes(raw)
        hashes[path.name] = hashlib.sha256(raw).hexdigest()
    candidate_count = sum(len(methods) for methods in SPECS.values())
    write_json(OUT / "run_config.json", dict(base_seed=42, training_seeds=list(range(67, 72)),
        derivation="42+25+repeat,0..4; already-used training scenes", untouched_future_seeds=list(range(97, 107)),
        stress_derivation="Q3 SeedSequence([42,35,layout_index,count]); Q4 [42,20,layout_index,count]; errors42+200+index/Q3,42+100+index/Q4",
        specs=SPECS, paths={k: v.tolist() for k, v in all_paths.items()}, expected_executions=candidate_count * 93,
        prior="seed42,384 uniform-disc positions +128 boundary positions, radius1000; Q4 12 faces including outward per position; ranking only",
        ranking="Promote each of first four 2-opt tasks; open path metres/5 minus weighted new visible prior fraction; zero discovery weight retains the base route",
        coverage_or_stop_depends_on_samples=False, initialization_measured_separately=True,
        virtual_upper_bound_s=314016, instruction_upper_bound=9766, code_sha256=hashes,
        engine_reuse="spatial_decision_experiments.run with explicit OUT/SPECS/build/freeze/all_layouts replacements",
        truth_to_policy=False, official_calls=0, cpu_threads=1, python=sys.executable,
        peer_commit="c477d3660368f27c7131a0591426b4c4f107ea5d"))
    (OUT / "precheck.md").write_text(f"# 运行前检查\n\n{checked['passed']}项检查通过，含零权重公开反馈等价、完整压力任务全清和打断/每源预算检查。有限位置/朝向先验仅用于排序，实际unknown覆盖扫描保留。{candidate_count}候选×93={candidate_count * 93}次训练，97—106未生成，正式请求0。\n")


def check():
    if (OUT / "checks.json").exists():
        raise RuntimeError("Preserving checks")
    all_paths = paths()
    checks = []
    old = ROOT / "experiments/runs/2026-09-11_interleaved-tasks"
    for problem, method, spec in (
        (3, "packet_center7", dict(kind="discovery_packet_clearance", layout="ring7", discovery_weight=0.)),
        (4, "packet_action4_22", {**SPECS[4]["packet_discover300_22"], "discovery_weight": 0.}),
    ):
        for case_id, category, split, scenario, error in training_cases(problem):
            with gzip.open(old / "traces" / f"q{problem}__{case_id}__{method}.jsonl.gz", "rt") as stream:
                trace = [json.loads(line) for line in stream]
            index = 0
            def replay(endpoint, raw):
                nonlocal index
                entry = trace[index]
                assert endpoint == entry["path"] and json.loads(raw) == entry["request"], (problem, case_id, index)
                index += 1
                return 200, entry["response"]
            policy = build(Client(replay, robot_id="mock-robot"), spec, problem, all_paths)
            policy.run()
            assert index == len(trace)
            checks.append(dict(test=f"zero_priority_exact_feedback_q{problem}_{case_id}", passed=True))
    for problem, methods in SPECS.items():
        selected = [c for c in training_cases(problem) if c[2] == "stress" and c[0].endswith(("n16__negative", "n10__spatial"))]
        for name, spec in methods.items():
            if not spec["kind"].startswith("discovery"):
                continue
            for case_id, category, split, scenario, error in selected:
                sim = Simulator(scenario, ErrorField(scenario.seed, error), Limits(countdown_s=0))
                policy = build(Client(PeerTransport(Protocol(sim)), robot_id="mock-robot"), spec, problem, all_paths)
                stats = policy.run()
                assert len(sim.cleared) == len(scenario.sources) and not stats["inconsistent_updates"]
                assert not stats.get("bracket_cut_inconsistencies", 0)
                assert stats.get("source_interruptions", 0) <= spec.get("pause_limit", 16)
                checks.append(dict(test=f"complete_protocol_q{problem}_{name}_{case_id}", passed=True,
                                   overrides=stats["discovery_priority_overrides"], total_s=sim.virtual_time_s))
    write_json(OUT / "checks.json", dict(passed=len(checks), failed=0, checks=checks, scored_execution_count=0))
    print("Passed", len(checks), "checks", flush=True)


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
            raise RuntimeError("Preserving prior results")
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
