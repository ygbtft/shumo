"""Compare equivalent cached route planners including initialization and CPU."""
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
from fast_dispatch_policy import FastCompletionPolicy, FastWidthPolicy, FastNegativeWidthPolicy, fast_arc_route, cached_insert_sources
from coupled_dispatch_policy import arc_route, insert_sources
from geometry import hull, minimum_circle
from layout_alternative_experiments import training_cases
from metaheuristic_experiments import write_json
from peer_benchmark import PeerTransport, Simulator, ErrorField, Limits, Protocol
import negative_hull_experiments as builders
import coupled_dispatch_experiments as coupled
import spatial_decision_experiments as engine

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "experiments/runs/2026-09-11_fast-dispatch"
SPECS={3:{
    "range_locked_area7":coupled.SPECS[3]["range_locked_area7"].copy(),
    "fast_locked_area7":dict(coupled.SPECS[3]["range_locked_area7"],kind="fast_completion"),
},4:{
    "range_arc05_width015":coupled.SPECS[4]["range_arc05_width015"].copy(),
    "fast_arc05_width015":dict(coupled.SPECS[4]["range_arc05_width015"],kind="fast_width"),
    "range_locked_width015":coupled.SPECS[4]["range_locked_width015"].copy(),
    "fast_locked_width015":dict(coupled.SPECS[4]["range_locked_width015"],kind="fast_width"),
    "negative_arc05_width015":builders.SPECS[4]["negative_arc05_width015"].copy(),
    "fast_negative_arc05_width015":dict(builders.SPECS[4]["negative_arc05_width015"],kind="fast_negative_width"),
}}


def paths():
    return builders.paths()


def build(client,spec,problem,all_paths):
    if not spec["kind"].startswith("fast_"):
        return builders.build(client,spec,problem,all_paths)
    params=spec.copy()
    kind=params.pop("kind")
    points=all_paths[params.pop("layout")]
    if problem==4:
        params.setdefault("trial_radius",40.)
    cls={"fast_completion":FastCompletionPolicy,"fast_width":FastWidthPolicy,
         "fast_negative_width":FastNegativeWidthPolicy}[kind]
    return cls(client,points,mixed=problem==4,**params)


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
        specs=SPECS, paths={k:v.tolist() for k,v in all_paths.items()}, expected_executions=744,
        dispatch_assumptions="MEC center is a completion-location proxy; next candidate is an entry proxy; source internal service cost is order-independent in the surrogate, not in physical execution",
        skip_certificate="known channel only, surveying only; distance(q,MEC.center)>1500+MEC.radius+1e-5; no fabricated protocol replies",
        additional_measurement_budget=0, virtual_upper_bound_s=335136, instruction_upper_bound=9766,
        engine_reuse="spatial_decision_experiments.run with explicit OUT/SPECS/build/freeze/all_layouts replacements",
        code_sha256=hashes, python=sys.executable, cpu_threads=1, truth_to_policy=False, official_calls=0,
        peer_commit="c477d3660368f27c7131a0591426b4c4f107ea5d"))
    (OUT / "precheck.md").write_text(f"# 路线加速前检查\n\n{result['passed']}项检查通过：独立随机路径/插入等价，四种策略全部372条原始反馈轨迹严格请求等价。8候选×93=744，仅验证加速和实测CPU，不改决策参数。117—126未生成，正式请求0。\n")


def check():
    if (OUT / "checks.json").exists():
        raise RuntimeError("Preserving passed checks")
    rng=np.random.default_rng(42)
    checks=[]
    for i in range(80):
        n=int(rng.integers(2,31))
        entries,exits,current=rng.uniform(-2500,2500,size=(n,2)),rng.uniform(-2500,2500,size=(n,2)),rng.uniform(-2500,2500,size=2)
        assert np.array_equal(arc_route(entries,exits,current),fast_arc_route(entries,exits,current)),i
        checks.append(dict(test=f"directed_prefix_route_exact_order_{i}",passed=True))
    for i in range(80):
        n,ns=int(rng.integers(1,12)),int(rng.integers(1,8))
        points,current=rng.uniform(-2500,2500,size=(n+ns,2)),rng.uniform(-2500,2500,size=2)
        tasks=[("survey" if j<n else "source",j,q) for j,q in enumerate(points)]
        assert insert_sources(tasks,n,current)==cached_insert_sources(tasks,n,current),i
        checks.append(dict(test=f"cached_scalar_insertion_exact_order_{i}",passed=True))
    all_paths=paths()
    controls=((3,"fast_locked_area7","range_locked_area7","coupled-dispatch"),
              (4,"fast_arc05_width015","range_arc05_width015","coupled-dispatch"),
              (4,"fast_locked_width015","range_locked_width015","coupled-dispatch"),
              (4,"fast_negative_arc05_width015","negative_arc05_width015","negative-hull"))
    for problem,new,old,folder in controls:
        for case_id,category,split,scenario,error in training_cases(problem):
            path=ROOT / "experiments/runs" / f"2026-09-11_{folder}" / "traces" / f"q{problem}__{case_id}__{old}.jsonl.gz"
            with gzip.open(path,"rt") as stream:
                trace=[json.loads(line) for line in stream]
            index=0
            def replay(endpoint,raw):
                nonlocal index
                entry=trace[index]
                assert endpoint==entry["path"] and json.loads(raw)==entry["request"],(new,case_id,index)
                index+=1
                return 200,entry["response"]
            build(Client(replay,robot_id="mock-robot"),SPECS[problem][new],problem,all_paths).run()
            assert index==len(trace)
            checks.append(dict(test=f"same_public_feedback_q{problem}_{new}_{case_id}",passed=True))
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
