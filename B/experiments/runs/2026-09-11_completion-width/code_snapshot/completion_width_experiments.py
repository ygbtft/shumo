"""Q3 completion-travel/area-prior ablation and Q4 bounded-width training."""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import numpy as np

from bounded_width_policy import BoundedWidthPacketPolicy
from client import Client
from completion_sensing_policy import CompletionClearancePolicy, area_quadrature
from geometry import hull
from layout_alternative_experiments import training_cases
from metaheuristic_experiments import write_json
from peer_benchmark import PeerTransport, Simulator, ErrorField, Limits, Protocol
import wide_probe_experiments as builders
import spatial_decision_experiments as engine

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "experiments/runs/2026-09-11_completion-width"
SPECS = {3: {
    "clearance7": dict(kind="clearance", layout="ring7"),
    "return1_7": dict(kind="completion", layout="ring7", remainder_weight=1.),
    "return2_7": dict(kind="completion", layout="ring7", remainder_weight=2.),
    "area7": dict(kind="completion", layout="ring7", area_prior=True),
    "area_return1_7": dict(kind="completion", layout="ring7", area_prior=True, remainder_weight=1.),
    "expanded7": dict(kind="completion", layout="ring7", expanded=True),
    "expanded_return1_7": dict(kind="completion", layout="ring7", expanded=True, remainder_weight=1.),
    "expanded_area7": dict(kind="completion", layout="ring7", expanded=True, area_prior=True),
    "expanded_area_return1_7": dict(kind="completion", layout="ring7", expanded=True, area_prior=True, remainder_weight=1.),
}, 4: {
    "packet_wide5_22": dict(kind="wide_packet", layout="convex22", fraction=.25, share_cooldown=150., probe_angle=5.),
    "width20_22": dict(kind="bounded_width", layout="convex22", fraction=.25, share_cooldown=150., transverse_m=20.),
    "width40_22": dict(kind="bounded_width", layout="convex22", fraction=.25, share_cooldown=150., transverse_m=40.),
    "width60_22": dict(kind="bounded_width", layout="convex22", fraction=.25, share_cooldown=150., transverse_m=60.),
    "width100_22": dict(kind="bounded_width", layout="convex22", fraction=.25, share_cooldown=150., transverse_m=100.),
    "width40_f015_22": dict(kind="bounded_width", layout="convex22", fraction=.15, share_cooldown=150., transverse_m=40.),
    "width_uncertainty100_22": dict(kind="bounded_width", layout="convex22", fraction=.25, share_cooldown=150., transverse_m=100., width_rule="uncertainty"),
    "width40_pause4_22": dict(kind="bounded_width", layout="convex22", fraction=.25, share_cooldown=150., transverse_m=40., pause_limit=4),
}}


def paths():
    return builders.paths()


def build(client, spec, problem, all_paths):
    if spec["kind"] not in ("completion", "bounded_width"):
        return builders.build(client, spec, problem, all_paths)
    params = spec.copy()
    kind = params.pop("kind")
    points = all_paths[params.pop("layout")]
    if problem == 4:
        params.setdefault("trial_radius", 40.)
    cls = CompletionClearancePolicy if kind == "completion" else BoundedWidthPacketPolicy
    return cls(client, points, mixed=problem == 4, **params)


def freeze(all_paths):
    if (OUT / "run_config.json").exists():
        raise RuntimeError("Preserving training")
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
        derivation="42+25+repeat,0..4; already-used training", untouched_future_seeds=list(range(107, 117)),
        stress_derivation="Q3 [42,35,layout_index,count], Q4 [42,20,layout_index,count]; errors42+200/indexQ3,42+100/indexQ4",
        specs=SPECS, paths={k: v.tolist() for k, v in all_paths.items()}, expected_executions=1581,
        q3_prior="Optional positive triangle quadrature: exact area moments, approximate nonlinear posterior surrogate; only candidate ranking",
        q3_completion_proxy="Extra q-to-MEC-center distance in ranking, not an actual source coordinate or guaranteed remaining travel",
        q3_new_candidate_rectangle=[-150.,1652.,-277.,277.], q4_width_cap_deg=30.,
        virtual_upper_bound_s=335136, instruction_upper_bound=9766,
        engine_reuse="spatial_decision_experiments.run with explicit OUT/SPECS/build/freeze/all_layouts replacements",
        code_sha256=hashes, python=sys.executable, cpu_threads=1, truth_to_policy=False, official_calls=0,
        peer_commit="c477d3660368f27c7131a0591426b4c4f107ea5d"))
    (OUT / "precheck.md").write_text(f"# 完工成本/宽度策略前检查\n\n{checked['passed']}项通过：面积矩的解析及边细分不变性、退化点/线、93条Q3零改动控制重放和完整压力协议。Q3扩展候选限制在原1900m内部转移矩形内；Q4变量半角始终1.02—30度。17候选×93=1581，107—116未生成，正式请求0。\n")


def moments(poly):
    points, weights = area_quadrature(np.asarray(poly, dtype=float))
    center = np.sum(points*weights[:, None], axis=0)
    cov = ((points-center)*weights[:, None]).T @ (points-center)
    assert (weights >= 0.).all() and abs(weights.sum()-1.) < 1e-12
    return center, cov


def check():
    if (OUT / "checks.json").exists():
        raise RuntimeError("Preserving checks")
    checks = []
    fixtures = (
        ([[-3.,-2.],[3.,-2.],[3.,2.],[-3.,2.]], [0.,0.], [[3.,0.],[0.,4/3]]),
        ([[0.,0.],[6.,0.],[0.,6.]], [2.,2.], [[2.,-1.],[-1.,2.]]),
        ([[-3.,0.],[3.,0.]], [0.,0.], [[3.,0.],[0.,0.]]),
        ([[2.,3.],[2.,3.]], [2.,3.], [[0.,0.],[0.,0.]]),
    )
    for i, (poly, mean, covariance) in enumerate(fixtures):
        m, c = moments(poly)
        assert np.allclose(m, mean, atol=1e-10) and np.allclose(c, covariance, atol=1e-10)
        checks.append(dict(test=f"analytic_uniform_area_or_degenerate_moments_{i}", passed=True))
    rng = np.random.default_rng(42)
    for i in range(80):
        p = hull(rng.normal(size=(12,2))*rng.uniform(1.,100.) + rng.uniform(-1800.,1800.,2))
        midpoints = (p+np.roll(p,-1,axis=0))/2
        refined = np.stack((p,midpoints),axis=1).reshape(-1,2)
        m,c = moments(p)
        mr,cr = moments(refined)
        assert np.allclose(m,mr,atol=1e-8) and np.allclose(c,cr,atol=1e-7)
        checks.append(dict(test=f"prior_moment_boundary_subdivision_invariance_{i}", passed=True))
    all_paths = paths()
    old = ROOT / "experiments/runs/2026-09-11_clearance-neighborhood"
    control = dict(kind="completion", layout="ring7")
    for case_id, category, split, scenario, error in training_cases(3):
        with gzip.open(old / "traces" / f"q3__{case_id}__clearance7.jsonl.gz", "rt") as stream:
            trace = [json.loads(line) for line in stream]
        index = 0
        def replay(endpoint, raw):
            nonlocal index
            entry = trace[index]
            assert endpoint == entry["path"] and json.loads(raw) == entry["request"], (case_id,index)
            index += 1
            return 200, entry["response"]
        build(Client(replay,robot_id="mock-robot"),control,3,all_paths).run()
        assert index == len(trace)
        checks.append(dict(test=f"completion_zero_changes_exact_feedback_{case_id}", passed=True))
    for problem, methods in SPECS.items():
        selected = [c for c in training_cases(problem) if c[2] == "stress" and c[0].endswith(("n16__negative","n10__spatial"))]
        for name,spec in methods.items():
            if spec["kind"] not in ("completion","bounded_width"):
                continue
            for case_id, category, split, scenario, error in selected:
                sim = Simulator(scenario,ErrorField(scenario.seed,error),Limits(countdown_s=0))
                policy = build(Client(PeerTransport(Protocol(sim)),robot_id="mock-robot"),spec,problem,all_paths)
                stats = policy.run()
                assert len(sim.cleared) == len(scenario.sources), (problem,name,case_id)
                assert not stats["inconsistent_updates"] and not stats.get("bracket_cut_inconsistencies",0)
                if problem == 3:
                    assert stats["active_no_signal"] == 0
                checks.append(dict(test=f"complete_protocol_q{problem}_{name}_{case_id}", passed=True,
                                   total_s=sim.virtual_time_s, active_rf=stats["active_measurements"]))
    write_json(OUT / "checks.json",dict(passed=len(checks),failed=0,checks=checks,scored_execution_count=0,official_calls=0))
    print("Passed",len(checks),"checks",flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check",action="store_true")
    parser.add_argument("--launch",action="store_true")
    args = parser.parse_args()
    engine.OUT,engine.SPECS,engine.build,engine.freeze,engine.all_layouts = OUT,SPECS,build,freeze,paths
    if args.check:
        check()
    elif args.launch:
        if (OUT / "run_config.json").exists():
            raise RuntimeError("Preserving training")
        env=os.environ.copy()
        env.update(PYTHONDONTWRITEBYTECODE="1",OPENBLAS_NUM_THREADS="1",OMP_NUM_THREADS="1",
                   MPLCONFIGDIR=str(ROOT / ".mplconfig"),XDG_CACHE_HOME=str(ROOT / ".cache"))
        with (OUT / "log.txt").open("a") as stream:
            process=subprocess.Popen([sys.executable,"-B",str(Path(__file__).resolve())],cwd=ROOT.parent,
                                     env=env,stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
        (OUT / "background.pid").write_text(str(process.pid)+"\n")
        print("Background PID",process.pid)
    else:
        engine.run()


if __name__ == "__main__":
    main()
