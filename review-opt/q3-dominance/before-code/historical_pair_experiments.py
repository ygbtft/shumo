"""Train bounded historical-pair inference with independent geometry checks."""
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
from historical_pair_policy import HistoricalCompletionPolicy,HistoricalWidthPolicy,HistoricalFastWidthPolicy,exclusion_planes,exclude_historical_pair
from geometry import hull, minimum_circle, polygon_area
from layout_alternative_experiments import training_cases
from metaheuristic_experiments import write_json
from peer_benchmark import PeerTransport, Simulator, ErrorField, Limits, Protocol
import fast_dispatch_experiments as builders
import coupled_dispatch_experiments as coupled
from mock.scenario_gen import Source
from mock.geometry import covered
import spatial_decision_experiments as engine

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "experiments/runs/2026-09-11_historical-negatives"
Q3=coupled.SPECS[3]["range_area7"]
Q4=coupled.SPECS[4]["range_width015"]
SPECS={3:{
    "range_area7":Q3.copy(),
    "history_first8_area7":dict(Q3,kind="historical_completion",anchor_mode="first"),
    "history_ends8_area7":dict(Q3,kind="historical_completion"),
    "history_ends16_area7":dict(Q3,kind="historical_completion",negative_history=16),
},4:{
    "range_width015":Q4.copy(),
    "history_recent8_width015":dict(Q4,kind="historical_width",anchor_mode="recent"),
    "history_first8_width015":dict(Q4,kind="historical_width",anchor_mode="first"),
    "history_ends4_width015":dict(Q4,kind="historical_width",negative_history=4),
    "history_ends8_width015":dict(Q4,kind="historical_width"),
    "history_ends16_width015":dict(Q4,kind="historical_width",negative_history=16),
    "fast_arc05_width015":builders.SPECS[4]["fast_arc05_width015"].copy(),
    "history_arc8_width015":dict(builders.SPECS[4]["fast_arc05_width015"],kind="historical_fast_width"),
    "fast_locked_width015":builders.SPECS[4]["fast_locked_width015"].copy(),
    "history_locked8_width015":dict(builders.SPECS[4]["fast_locked_width015"],kind="historical_fast_width"),
}}


def paths():
    return builders.paths()


def build(client,spec,problem,all_paths):
    if not spec["kind"].startswith("historical_"):
        return builders.build(client,spec,problem,all_paths)
    params=spec.copy()
    kind=params.pop("kind")
    points=all_paths[params.pop("layout")]
    if problem==4:params.setdefault("trial_radius",40.)
    cls={"historical_completion":HistoricalCompletionPolicy,"historical_width":HistoricalWidthPolicy,
         "historical_fast_width":HistoricalFastWidthPolicy}[kind]
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
        derivation="42+25+repeat,0..4; already-used training scenes", untouched_future_seeds=list(range(127,137)),
        stress_derivation="Q3 [42,35,layout_index,count], Q4 [42,20,layout_index,count]; prior training streams",
        specs=SPECS, paths={k:v.tolist() for k,v in all_paths.items()}, expected_executions=1302,
        negative_region_assumptions="Two actual negatives no farther than a successful anchor and segment intersection form a five-halfplane exclusion; history and anchors are fixed bounded subsets",
        skip_certificate="known channel only, surveying only; distance(q,MEC.center)>1500+MEC.radius+1e-5; no fabricated protocol replies",
        additional_measurement_budget=0, virtual_upper_bound_s=335136, instruction_upper_bound=9766,
        engine_reuse="spatial_decision_experiments.run with explicit OUT/SPECS/build/freeze/all_layouts replacements",
        code_sha256=hashes, python=sys.executable, cpu_threads=1, truth_to_policy=False, official_calls=0,
        peer_commit="c477d3660368f27c7131a0591426b4c4f107ea5d"))
    (OUT / "precheck.md").write_text(f"# 历史负反馈训练前检查\n\n{result['passed']}项通过：独立线段/距离判定、窄对截断、45度合法反例、合法半圆/圆盘源保留、退化几何、279条禁用功能的完整反馈等价以及60次压力协议。14候选×93=1302。127—136未生成；只缩小外包区域，不新增RF预算，正式请求0。\n")


def contains(poly,point):
    edges=np.roll(poly,-1,axis=0)-poly
    good=np.linalg.norm(edges,axis=1)>1e-9
    if not good.any():return np.linalg.norm(poly[0]-point)<1e-6
    values=edges[:,0]*(point-poly)[:,1]-edges[:,1]*(point-poly)[:,0]
    return np.min(values[good]/np.linalg.norm(edges[good],axis=1))>=-1e-6


def check():
    if (OUT / "checks.json").exists():raise RuntimeError("Preserving checks")
    rng=np.random.default_rng(42);checks=[]
    s=np.zeros(2);t=np.tan(np.radians(1.02));e=np.tan(np.radians(1.01))
    a,b=np.array([500.,-500*t]),np.array([500.,500*t])
    poly=hull([[0.,0.],[1500.,1500*e],[1500.,-1500*e]])
    result=exclude_historical_pair(poly,exclusion_planes(s,a,b))
    assert result[:,0].max()<500.01 and contains(result,np.array([400.,0.]))
    source=Source(1,400.,0.,1000.,180.)
    assert covered(source,tuple(s)) and not covered(source,tuple(a)) and not covered(source,tuple(b))
    checks.append(dict(test="narrow_pair_recovers_safe_forward_cut",passed=True))
    fixture=json.loads((ROOT / "experiments/runs/2026-09-11_wide-probes/geometry_details.json").read_text())["counterexample"]
    g=np.array(fixture["true_source"]);a,b=map(np.array,fixture["probes"])
    result=exclude_historical_pair(poly,exclusion_planes(s,a,b))
    assert contains(result,g)
    assert not np.all(exclusion_planes(s,a,b)[0]@g<=exclusion_planes(s,a,b)[1])
    checks.append(dict(test="wide45_false_pair_does_not_discard_legal_source",passed=True))
    independent_points=0
    for i in range(120):
        s,a,b=rng.uniform(-1800,1800,size=(3,2))
        planes=exclusion_planes(s,a,b)
        if planes is not None:
            normals,bounds=planes
            for g in rng.uniform(-1800,1800,size=(40,2)):
                values=normals@g-bounds
                if np.min(np.abs(values))<1e-5:continue
                matrix=np.column_stack((g-s,-(b-a)))
                if abs(np.linalg.det(matrix))<1e-8:continue
                u,v=np.linalg.solve(matrix,a-s)
                expected=0<=u<=1 and 0<=v<=1 and max(np.linalg.norm(a-g),np.linalg.norm(b-g))<=np.linalg.norm(s-g)
                assert bool(np.all(values<=0))==bool(expected),(i,g)
                independent_points+=1
        checks.append(dict(test=f"five_planes_vs_independent_segment_and_distances_{i}",passed=True))
    for i in range(200):
        angle=rng.uniform(0,2*np.pi)
        g=1700*np.sqrt(rng.uniform())*np.array([np.cos(angle),np.sin(angle)])
        radius=1000. if i%2 else 1500.
        yaw=None if i%3==0 else float(rng.uniform(0,360))
        source=Source(1,float(g[0]),float(g[1]),radius,yaw)
        def point():
            angle=rng.uniform(0,2*np.pi)
            return g+rng.uniform(10.,radius*1.8)*np.array([np.cos(angle),np.sin(angle)])
        s=point()
        while not covered(source,tuple(s)):s=point()
        negatives=[]
        while len(negatives)<2:
            q=point()
            if not covered(source,tuple(q)):negatives.append(q)
        poly=hull(np.vstack((g,g+rng.normal(size=(20,2))*rng.uniform(20.,1800.))))
        result=exclude_historical_pair(poly,exclusion_planes(s,*negatives))
        assert len(result) and contains(result,g),i
        checks.append(dict(test=f"legal_footprint_true_source_retained_{i}",passed=True))
    for i,(s,a,b) in enumerate((([0,0],[1,0],[2,0]),([0,0],[-1,0],[1,0]),([0,0],[0,0],[1,2]),([2,3],[3,4],[3,4]))):
        assert exclusion_planes(np.array(s),np.array(a),np.array(b)) is None
        checks.append(dict(test=f"degenerate_history_is_noop_{i}",passed=True))
    all_paths=paths()
    controls=((3,"range_area7","historical_completion","coupled-dispatch",Q3),
              (4,"range_width015","historical_width","coupled-dispatch",Q4),
              (4,"fast_arc05_width015","historical_fast_width","fast-dispatch",SPECS[4]["fast_arc05_width015"]))
    for problem,name,kind,folder,base in controls:
        spec=dict(base,kind=kind,history_enabled=False)
        for case_id,category,split,scenario,error in training_cases(problem):
            path=ROOT / "experiments/runs" / f"2026-09-11_{folder}" / "traces" / f"q{problem}__{case_id}__{name}.jsonl.gz"
            with gzip.open(path,"rt") as stream:trace=[json.loads(line) for line in stream]
            index=0
            def replay(endpoint,raw):
                nonlocal index
                entry=trace[index]
                assert endpoint==entry["path"] and json.loads(raw)==entry["request"],(name,case_id,index)
                index+=1
                return 200,entry["response"]
            build(Client(replay,robot_id="mock-robot"),spec,problem,all_paths).run()
            assert index==len(trace)
            checks.append(dict(test=f"history_disabled_exact_feedback_q{problem}_{name}_{case_id}",passed=True))
    for problem,methods in SPECS.items():
        selected=[c for c in training_cases(problem) if c[2]=="stress" and c[0].endswith(("n16__negative","n10__spatial"))]
        for name,spec in methods.items():
            if not spec["kind"].startswith("historical_"):continue
            for case_id,category,split,scenario,error in selected:
                sim=Simulator(scenario,ErrorField(scenario.seed,error),Limits(countdown_s=0))
                stats=build(Client(PeerTransport(Protocol(sim)),robot_id="mock-robot"),spec,problem,all_paths).run()
                assert len(sim.cleared)==len(scenario.sources),(problem,name,case_id)
                assert not stats["historical_inconsistent_cuts"] and not stats["inconsistent_updates"] and not stats.get("bracket_cut_inconsistencies",0)
                checks.append(dict(test=f"full_protocol_q{problem}_{name}_{case_id}",passed=True,
                                   historical_cuts=stats["historical_pair_cuts"],virtual_s=sim.virtual_time_s))
    write_json(OUT / "checks.json",dict(passed=len(checks),failed=0,checks=checks,independent_point_checks=independent_points,
                                      scored_execution_count=0,official_calls=0))
    print("Passed",len(checks),"checks",independent_points,"independent point predicates",flush=True)


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
