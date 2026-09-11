"""Train public-state service arcs, fixed scan order and certified RF skips."""
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
from coupled_dispatch_policy import CoupledCompletionPolicy, CoupledWidePolicy, CoupledWidthPolicy, arc_route, insert_sources
from geometry import hull, minimum_circle
from layout_alternative_experiments import training_cases
from metaheuristic_experiments import write_json
from peer_benchmark import PeerTransport, Simulator, ErrorField, Limits, Protocol
import completion_width_experiments as builders
import spatial_decision_experiments as engine

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "experiments/runs/2026-09-11_coupled-dispatch"
Q3 = dict(layout="ring7", area_prior=True, remainder_weight=1.)
WIDTH = dict(layout="convex22", fraction=.15, share_cooldown=150., transverse_m=40.)
WIDE = dict(layout="convex22", fraction=.25, share_cooldown=150., probe_angle=5.)
SPECS = {3: {
    "area_return1_7": dict(kind="completion", **Q3),
    # Small time/risk tradeoff validated in CLEAR_GATE_TRADEOFF.md; explicit
    # overrides (including the original 80 m baseline) remain available.
    "range_area7": dict(kind="coupled_completion", dispatch_model="base", range_skip=True, trial_radius=50., **Q3),
    "locked_area7": dict(kind="coupled_completion", dispatch_model="locked", **Q3),
    "range_locked_area7": dict(kind="coupled_completion", dispatch_model="locked", range_skip=True, **Q3),
}, 4: {
    "width40_f015_22": dict(kind="bounded_width", **WIDTH),
    "range_width015": dict(kind="coupled_width", dispatch_model="base", range_skip=True, **WIDTH),
    "arc025_width015": dict(kind="coupled_width", entry_blend=.25, **WIDTH),
    "arc05_width015": dict(kind="coupled_width", entry_blend=.5, **WIDTH),
    "arc1_width015": dict(kind="coupled_width", entry_blend=1., **WIDTH),
    "arc1_nearest_width015": dict(kind="coupled_width", entry_blend=1., arc_polish=False, **WIDTH),
    "locked_width015": dict(kind="coupled_width", dispatch_model="locked", **WIDTH),
    "locked0_width015": dict(kind="coupled_width", dispatch_model="locked", pause_limit=0, **WIDTH),
    "arc05_pause4_width015": dict(kind="coupled_width", entry_blend=.5, pause_limit=4, **WIDTH),
    "range_arc05_width015": dict(kind="coupled_width", entry_blend=.5, range_skip=True, **WIDTH),
    "range_locked_width015": dict(kind="coupled_width", dispatch_model="locked", range_skip=True, **WIDTH),
    "packet_wide5_22": dict(kind="wide_packet", **WIDE),
    "arc05_wide5": dict(kind="coupled_wide", entry_blend=.5, **WIDE),
    "locked_wide5": dict(kind="coupled_wide", dispatch_model="locked", **WIDE),
}}


def paths():
    return builders.paths()


def build(client, spec, problem, all_paths):
    if not spec["kind"].startswith("coupled_"):
        return builders.build(client, spec, problem, all_paths)
    parameters = spec.copy()
    kind = parameters.pop("kind")
    points = all_paths[parameters.pop("layout")]
    if problem == 4:
        parameters.setdefault("trial_radius", 40.)
    cls = {"coupled_width": CoupledWidthPolicy, "coupled_wide": CoupledWidePolicy,
           "coupled_completion": CoupledCompletionPolicy}[kind]
    return cls(client, points, mixed=problem == 4, **parameters)


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
    write_json(OUT / "run_config.json", dict(base_seed=42, training_seeds=list(range(67,72)),
        derivation="42+25+repeat,0..4; already-used training scenes", untouched_future_seeds=list(range(117,127)),
        stress_derivation="Q3 [42,35,layout_index,count], Q4 [42,20,layout_index,count]; prior training streams",
        specs=SPECS, paths={k:v.tolist() for k,v in all_paths.items()}, expected_executions=1674,
        dispatch_assumptions="MEC center is a completion-location proxy; next candidate is an entry proxy; source internal service cost is order-independent in the surrogate, not in physical execution",
        skip_certificate="known channel only, surveying only; distance(q,MEC.center)>1500+MEC.radius+1e-5; no fabricated protocol replies",
        additional_measurement_budget=0, virtual_upper_bound_s=335136, instruction_upper_bound=9766,
        engine_reuse="spatial_decision_experiments.run with explicit OUT/SPECS/build/freeze/all_layouts replacements",
        code_sha256=hashes, python=sys.executable, cpu_threads=1, truth_to_policy=False, official_calls=0,
        peer_commit="c477d3660368f27c7131a0591426b4c4f107ea5d"))
    (OUT / "precheck.md").write_text(f"# 训练前检查\n\n{result['passed']}项检查通过，含有向路线实际成本、保序插入、MEC距离推断、279条零改动反馈控制及压力协议。18候选×93=1674。只调整排序和推断跳过，不增加测向/打断预算；117—126未生成，正式请求0。\n")


def path_cost(route, entries, exits, current):
    if not len(route):
        return 0.
    return float(np.linalg.norm(entries[route[0]]-current) + sum(np.linalg.norm(exits[a]-entries[b]) for a,b in zip(route[:-1],route[1:])))


def check():
    if (OUT / "checks.json").exists():
        raise RuntimeError("Preserving passed checks")
    rng = np.random.default_rng(42)
    checks = []
    for i in range(80):
        n = int(rng.integers(2,16))
        entries, exits, current = rng.normal(size=(n,2))*1000, rng.normal(size=(n,2))*1000, rng.normal(size=2)*1000
        a, b = arc_route(entries,exits,current,False), arc_route(entries,exits,current,True)
        assert sorted(b) == list(range(n)) and path_cost(b,entries,exits,current) <= path_cost(a,entries,exits,current)+1e-7
        checks.append(dict(test=f"directed_route_actual_cost_nonincrease_{i}",passed=True))
    for i in range(80):
        n = int(rng.integers(1,10))
        source_count = 1 if i < 40 else int(rng.integers(2,8))
        points, current = rng.normal(size=(n+source_count,2))*1000, rng.normal(size=2)*1000
        tasks = [("survey" if j<n else "source",j,p) for j,p in enumerate(points)]
        route = insert_sources(tasks,n,current)
        assert sorted(route) == list(range(len(tasks))) and [j for j in route if j<n] == list(range(n))
        if source_count == 1:
            options = [list(range(j))+[n]+list(range(j,n)) for j in range(n+1)]
            assert abs(path_cost(route,points,points,current)-min(path_cost(r,points,points,current) for r in options)) < 1e-7
        checks.append(dict(test=f"scan_order_and_exhaustive_single_insertion_{i}",passed=True))
    for i in range(80):
        poly = hull(rng.normal(size=(16,2))*rng.uniform(1.,700.))
        center,radius = minimum_circle(poly)
        theta = rng.uniform(0,2*np.pi)
        q = center+(1500+radius+rng.uniform(.01,100.))*np.array([np.cos(theta),np.sin(theta)])
        # Independent lower bound applies to every convex combination, not
        # just these vertices; generated barycentric points check numerics.
        weights = rng.dirichlet(np.ones(len(poly)),size=80)
        assert np.min(np.linalg.norm(weights@poly-q,axis=1)) > 1500
        assert np.linalg.norm(q-center)-radius > 1500+1e-5
        checks.append(dict(test=f"known_region_range_certificate_{i}",passed=True))
    all_paths = paths()
    old = ROOT / "experiments/runs/2026-09-11_completion-width"
    controls = ((3,"area_return1_7",dict(kind="coupled_completion",dispatch_model="base",**Q3)),
                (4,"packet_wide5_22",dict(kind="coupled_wide",dispatch_model="base",**WIDE)),
                (4,"width40_f015_22",dict(kind="coupled_width",entry_blend=0.,**WIDTH)))
    for problem,name,spec in controls:
        for case_id,category,split,scenario,error in training_cases(problem):
            with gzip.open(old / "traces" / f"q{problem}__{case_id}__{name}.jsonl.gz","rt") as stream:
                trace=[json.loads(line) for line in stream]
            index=0
            def replay(endpoint,raw):
                nonlocal index
                entry=trace[index]
                assert endpoint==entry["path"] and json.loads(raw)==entry["request"],(name,case_id,index)
                index+=1
                return 200,entry["response"]
            build(Client(replay,robot_id="mock-robot"),spec,problem,all_paths).run()
            assert index==len(trace)
            checks.append(dict(test=f"zero_dispatch_change_feedback_q{problem}_{name}_{case_id}",passed=True))
    for problem,methods in SPECS.items():
        selected=[c for c in training_cases(problem) if c[2]=="stress" and c[0].endswith(("n16__negative","n10__spatial"))]
        for name,spec in methods.items():
            if not spec["kind"].startswith("coupled_"):
                continue
            for case_id,category,split,scenario,error in selected:
                sim=Simulator(scenario,ErrorField(scenario.seed,error),Limits(countdown_s=0))
                policy=build(Client(PeerTransport(Protocol(sim)),robot_id="mock-robot"),spec,problem,all_paths)
                stats=policy.run()
                assert len(sim.cleared)==len(scenario.sources),(problem,name,case_id)
                assert not stats["inconsistent_updates"] and not stats.get("bracket_cut_inconsistencies",0)
                if problem==3:
                    assert stats["active_no_signal"]==0
                checks.append(dict(test=f"full_protocol_q{problem}_{name}_{case_id}",passed=True,total_s=sim.virtual_time_s,
                                   certified_skips=stats["certified_range_scan_skips"]))
    write_json(OUT / "checks.json",dict(passed=len(checks),failed=0,checks=checks,scored_execution_count=0,official_calls=0))
    print("Passed",len(checks),"checks",flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check",action="store_true")
    parser.add_argument("--launch",action="store_true")
    args=parser.parse_args()
    engine.OUT,engine.SPECS,engine.build,engine.freeze,engine.all_layouts=OUT,SPECS,build,freeze,paths
    if args.check:
        check()
    elif args.launch:
        if (OUT / "run_config.json").exists():
            raise RuntimeError("Preserving scored run")
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


if __name__=="__main__":
    main()
