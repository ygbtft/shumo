"""Train wider paired bearings after algebra, boundaries and controls pass."""
import argparse
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import numpy as np

from client import Client
from layout_alternative_experiments import training_cases
from metaheuristic_experiments import write_json
from peer_benchmark import PeerTransport, Simulator, ErrorField, Limits, Protocol
from mock.scenario_gen import Source
from mock.geometry import covered
from wide_probe_policy import WideProbePolicy, WidePacketPolicy
import interleaved_experiments as builders
import spatial_decision_experiments as engine

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "experiments/runs/2026-09-11_wide-probes"
SPECS = {4: {
    "quarter22": dict(kind="probe", layout="convex22", fraction=.25, share_cooldown=150.),
    "packet_center22": dict(kind="packet_probe", layout="convex22", fraction=.25, share_cooldown=150.),
}}
for angle in (3, 5, 10, 15, 20, 30):
    for kind, prefix in (("wide", "wide"), ("wide_packet", "packet_wide")):
        SPECS[4][f"{prefix}{angle}_22"] = dict(kind=kind, layout="convex22", fraction=.25, share_cooldown=150., probe_angle=float(angle))
SPECS[4].update({
    "packet_decay20_22": dict(kind="wide_packet", layout="convex22", fraction=.25, share_cooldown=150., probe_angle=20., angle_mode="decay"),
    "packet_first30_22": dict(kind="wide_packet", layout="convex22", fraction=.25, share_cooldown=150., probe_angle=30., angle_mode="first"),
    "packet_f015_15_22": dict(kind="wide_packet", layout="convex22", fraction=.15, share_cooldown=150., probe_angle=15.),
    "wide_f05_10_22": dict(kind="wide", layout="convex22", fraction=.5, share_cooldown=150., probe_angle=10.),
})


def paths():
    return builders.paths()


def build(client, spec, problem, all_paths):
    if not spec["kind"].startswith("wide"):
        return builders.build(client, spec, problem, all_paths)
    assert problem == 4
    params = spec.copy()
    kind = params.pop("kind")
    points = all_paths[params.pop("layout")]
    params.setdefault("trial_radius", 40.)
    cls = WideProbePolicy if kind == "wide" else WidePacketPolicy
    return cls(client, points, mixed=True, **params)


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
    write_json(OUT / "run_config.json", dict(base_seed=42, training_seeds=list(range(67, 72)),
        derivation="42+25+repeat,0..4; already-used training scenes", untouched_future_seeds=list(range(107, 117)),
        stress_derivation="Q4 SeedSequence([42,20,layout_index,count]); errors42+100+index",
        specs=SPECS, paths={k: v.tolist() for k, v in all_paths.items()}, expected_executions=1674,
        probe_angle_range_deg=[1.02, 30.], readout_outer_halfwidth_deg=1.01,
        max_primary_rf_per_source=20, max_interruptions=24, virtual_upper_bound_s=335136, instruction_upper_bound=9766,
        algebra="t<=k and k*k+2*k*t<=1, t=tan(1.02deg); two negatives imply projected x<=l",
        engine_reuse="spatial_decision_experiments.run with explicit OUT/SPECS/build/freeze/all_layouts replacements",
        code_sha256=hashes, python=sys.executable, cpu_threads=1, truth_to_policy=False, official_calls=0,
        peer_commit="c477d3660368f27c7131a0591426b4c4f107ea5d"))
    (OUT / "precheck.md").write_text(f"# 宽探测前检查\n\n{checked['passed']}项通过：独立距离/半平面代数、原后端方向边界、45度失败反例、335136s预算计算、186条1.02度控制重放及完整协议压力检查。18候选×93=1674；107—116未生成。先冻结、CPU单线程，正式请求0。\n")


def geometry_checks():
    t = math.tan(math.radians(1.02))
    count = 0
    for beta in (1.02, 3., 5., 10., 15., 20., 30.):
        k = math.tan(math.radians(beta))
        assert k >= t and k*k + 2*k*t < 1.
        cases = [(distance, error) for distance in (6., 30., 100., 500., 999.999999, 1499.999999)
                 for error in (-1.0049, -1., 0., 1., 1.0049)] + [(1000., 0.), (1500., 0.)]
        for distance, error in cases:
            delta = math.radians(error)
            g = distance * np.array([math.cos(delta), math.sin(delta)])
            radius = 1000. if distance <= 1000. else 1500.
            toward_s = math.degrees(math.atan2(-g[1], -g[0]))
            for ratio in (.001, .25, .5, .9, .999999):
                length = ratio * g[0]
                qs = [np.array([length, k*length]), np.array([length, -k*length])]
                ds = float(np.linalg.norm(g))
                assert all(np.linalg.norm(q - g) <= ds + 1e-8 for q in qs)
                for offset in (-90., -89.999, -30., 0., 30., 89.999, 90.):
                    direction = (toward_s + offset) % 360.
                    n = np.array([math.cos(math.radians(direction)), math.sin(math.radians(direction))])
                    assert float(n @ (-g)) >= -1e-8
                    assert max(float(n @ (q - g)) for q in qs) >= -1e-8
                    source = Source(1, float(g[0]), float(g[1]), radius, direction)
                    assert covered(source, (0., 0.))
                    assert any(covered(source, tuple(q)) for q in qs), (beta, distance, error, ratio, offset)
                    count += 1
    # Legal physical example beyond the safe probe-angle condition: the upper
    # candidate is inside range but outside the beam, the lower is too far.
    g = 999.999999 * np.array([math.cos(math.radians(1.)), math.sin(math.radians(1.))])
    length = .9999 * g[0]
    qs = [np.array([length, length]), np.array([length, -length])]
    source = Source(1, float(g[0]), float(g[1]), 1000., 270.)
    assert covered(source, (0., 0.)) and g[0] > length
    assert not any(covered(source, tuple(q)) for q in qs)
    counter = dict(probe_angle_deg=45., true_source=g.tolist(), anchor=[0., 0.], received_deg=0.,
                   legal_first_error_deg=-1., radius=1000., direction_deg=270., length=length,
                   probes=[q.tolist() for q in qs], distances=[float(np.linalg.norm(q-g)) for q in qs])
    a, k = 1502., math.tan(math.radians(30.))
    max_distance = max(a*math.sqrt(1+k*k), a*math.sqrt(1+t*t), a*(k+t))
    mec = math.sqrt(1503.**2 + 54.**2) / 2
    assert max_distance < 1735. and mec < 752.
    bound = 264096 + 16*900/5 + 24*2*7100/5
    assert bound == 335136 and bound < 360000
    details = dict(instances=count, counterexample=counter, source_distance_upper_m=max_distance,
                   first_wedge_mec_upper_m=mec, paired_safe_angle_limit_deg=math.degrees(math.atan(math.sqrt(1+t*t)-t)),
                   wide_virtual_upper_bound_s=bound, instruction_upper_bound=9766)
    write_json(OUT / "geometry_details.json", details)
    return [dict(test="wide_pair_distance_and_closed_halfplane_against_unchanged_backend", passed=True, instances=count),
            dict(test="unsafe_45_degree_counterexample_retained", passed=True),
            dict(test="new_action_domain_and_finite_time_bounds", passed=True, virtual_s=bound)]


def check():
    if (OUT / "checks.json").exists():
        raise RuntimeError("Preserving checks")
    checks = geometry_checks()
    all_paths = paths()
    old = ROOT / "experiments/runs/2026-09-11_interleaved-tasks"
    for method, kind in (("quarter22", "wide"), ("packet_center22", "wide_packet")):
        spec = dict(kind=kind, layout="convex22", fraction=.25, share_cooldown=150., probe_angle=1.02)
        for case_id, category, split, scenario, error in training_cases(4):
            with gzip.open(old / "traces" / f"q4__{case_id}__{method}.jsonl.gz", "rt") as stream:
                trace = [json.loads(line) for line in stream]
            index = 0
            def replay(endpoint, raw):
                nonlocal index
                entry = trace[index]
                assert endpoint == entry["path"] and json.loads(raw) == entry["request"], (method, case_id, index)
                index += 1
                return 200, entry["response"]
            policy = build(Client(replay, robot_id="mock-robot"), spec, 4, all_paths)
            policy.run()
            assert index == len(trace)
            checks.append(dict(test=f"narrow_angle_exact_feedback_{method}_{case_id}", passed=True, commands=index))
    selected = [c for c in training_cases(4) if c[2] == "stress" and c[0].endswith(("n16__negative", "n10__spatial"))]
    for name, spec in SPECS[4].items():
        if not spec["kind"].startswith("wide"):
            continue
        for case_id, category, split, scenario, error in selected:
            sim = Simulator(scenario, ErrorField(scenario.seed, error), Limits(countdown_s=0))
            policy = build(Client(PeerTransport(Protocol(sim)), robot_id="mock-robot"), spec, 4, all_paths)
            stats = policy.run()
            assert len(sim.cleared) == len(scenario.sources), (name, case_id)
            assert not stats["inconsistent_updates"] and not stats["bracket_cut_inconsistencies"]
            assert stats.get("maximum_source_primary_rf", 0) <= 20
            checks.append(dict(test=f"complete_protocol_{name}_{case_id}", passed=True, total_s=sim.virtual_time_s,
                               measurements=stats["active_measurements"], negatives=stats["active_no_signal"]))
    write_json(OUT / "checks.json", dict(passed=len(checks), failed=0, checks=checks, scored_execution_count=0, official_calls=0))
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
        (OUT / "background.pid").write_text(str(process.pid)+"\n")
        print("Background PID", process.pid)
    else:
        engine.run()


if __name__ == "__main__":
    main()
