"""Train convex negative-feedback outer regions on existing mission policies."""
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
from negative_hull_policy import NegativeCompletionPolicy, NegativeWidthPolicy, exclude_shadow
from geometry import hull, minimum_circle, polygon_area
from layout_alternative_experiments import training_cases
from metaheuristic_experiments import write_json
from peer_benchmark import PeerTransport, Simulator, ErrorField, Limits, Protocol
import coupled_dispatch_experiments as builders
from mock.scenario_gen import Source
from mock.geometry import covered
import spatial_decision_experiments as engine

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "experiments/runs/2026-09-11_negative-hull"
SPECS = {3: {
    "range_area7": builders.SPECS[3]["range_area7"].copy(),
    "negative_range_area7": dict(builders.SPECS[3]["range_area7"],kind="negative_completion"),
    "range_locked_area7": builders.SPECS[3]["range_locked_area7"].copy(),
    "negative_locked_area7": dict(builders.SPECS[3]["range_locked_area7"],kind="negative_completion"),
}, 4: {
    "range_width015": builders.SPECS[4]["range_width015"].copy(),
    "negative_width015": dict(builders.SPECS[4]["range_width015"],kind="negative_width"),
    "range_arc05_width015": builders.SPECS[4]["range_arc05_width015"].copy(),
    "negative_arc05_width015": dict(builders.SPECS[4]["range_arc05_width015"],kind="negative_width"),
    "range_locked_width015": builders.SPECS[4]["range_locked_width015"].copy(),
    "negative_locked_width015": dict(builders.SPECS[4]["range_locked_width015"],kind="negative_width"),
    "negative_h4_width015": dict(builders.SPECS[4]["range_width015"],kind="negative_width",negative_history=4),
    "negative_h32_width015": dict(builders.SPECS[4]["range_width015"],kind="negative_width",negative_history=32),
}}


def paths():
    return builders.paths()


def build(client, spec, problem, all_paths):
    if not spec["kind"].startswith("negative_"):
        return builders.build(client,spec,problem,all_paths)
    parameters=spec.copy()
    kind=parameters.pop("kind")
    points=all_paths[parameters.pop("layout")]
    if problem==4:
        parameters.setdefault("trial_radius",40.)
    cls=NegativeWidthPolicy if kind=="negative_width" else NegativeCompletionPolicy
    return cls(client,points,mixed=problem==4,**parameters)


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
        specs=SPECS, paths={k:v.tolist() for k,v in all_paths.items()}, expected_executions=1116,
        negative_region_assumptions="Receiving footprint is convex and contains source and successful positions; subtract shadow cones of true negative feedback then retain convex hull; recent history is a conservative subset",
        skip_certificate="known channel only, surveying only; distance(q,MEC.center)>1500+MEC.radius+1e-5; no fabricated protocol replies",
        additional_measurement_budget=0, virtual_upper_bound_s=335136, instruction_upper_bound=9766,
        engine_reuse="spatial_decision_experiments.run with explicit OUT/SPECS/build/freeze/all_layouts replacements",
        code_sha256=hashes, python=sys.executable, cpu_threads=1, truth_to_policy=False, official_calls=0,
        peer_commit="c477d3660368f27c7131a0591426b4c4f107ea5d"))
    (OUT / "precheck.md").write_text(f"# 负反馈训练前检查\n\n{result['passed']}项通过：解析排除锥、独立真实接收夹具和退化几何，186条关闭推断的反馈控制，以及42次完整压力协议。12候选×93=1116，先冻结，不增加RF/打断预算，117—126未生成、正式请求0。\n")


def contains(poly,point,tol=1e-6):
    if len(poly)<3:
        return min(np.linalg.norm(point-q) for q in poly)<tol
    edges=np.roll(poly,-1,axis=0)-poly
    relative=point-poly
    good=np.linalg.norm(edges,axis=1)>1e-10
    return np.min((edges[:,0]*relative[:,1]-edges[:,1]*relative[:,0])[good]/np.linalg.norm(edges[good],axis=1)) >= -tol


def check():
    if (OUT / "checks.json").exists():
        raise RuntimeError("Preserving passed checks")
    rng=np.random.default_rng(42)
    checks=[]
    poly=np.array([[80.,-10.],[200.,-10.],[200.,10.],[80.,10.]])
    a,b,q=np.array([0.,-20.]),np.array([0.,20.]),np.array([110.,0.])
    restricted=exclude_shadow(poly,q,a,b)
    assert 164.99 < restricted[:,0].max() < 165.01 and polygon_area(restricted)<polygon_area(poly)
    kept=0
    for x in np.linspace(80.,200.,41):
        for y in np.linspace(-10.,10.,31):
            g=np.array([x,y])
            weights=np.linalg.solve(np.vstack((np.column_stack((g,a,b)),np.ones(3))),np.r_[q,1.])
            if np.min(weights)<-1e-8:
                assert contains(restricted,g)
                kept+=1
    checks.append(dict(test="analytic_shadow_and_barycentric_complement_containment",passed=True,sampled_feasible=kept))
    for i in range(300):
        angle=rng.uniform(0,2*np.pi)
        g=1700*np.sqrt(rng.uniform())*np.array([np.cos(angle),np.sin(angle)])
        radius=1000. if i%2 else 1500.
        direction=None if i%3==0 else float(rng.uniform(0,360))
        source=Source(1,float(g[0]),float(g[1]),radius,direction)
        successes=[]
        while len(successes)<2:
            candidate=g+rng.uniform(5.,radius*.999999)*np.array([np.cos(t:=rng.uniform(0,2*np.pi)),np.sin(t)])
            if covered(source,tuple(candidate)):
                successes.append(candidate)
        while True:
            q=g+rng.uniform(1.,radius*1.6)*np.array([np.cos(t:=rng.uniform(0,2*np.pi)),np.sin(t)])
            if not covered(source,tuple(q)):
                break
        poly=hull(np.vstack((g,g+rng.normal(size=(20,2))*rng.uniform(20.,1800.))))
        result=exclude_shadow(poly,q,*successes)
        assert len(result) and contains(result,g),(i,g,successes,q)
        checks.append(dict(test=f"convex_receiving_footprint_true_source_retained_{i}",passed=True))
    for i,(a,b,q) in enumerate((([0.,0.],[1.,0.],[2.,0.]),([0.,0.],[1.,0.],[.5,0.]),
                               ([0.,0.],[1.,1.],[0.,0.]),([0.,0.],[0.,0.],[2.,3.]))):
        poly=np.array([[-5.,-5.],[5.,-5.],[5.,5.],[-5.,5.]])
        assert exclude_shadow(poly,np.array(q),np.array(a),np.array(b)) is poly
        checks.append(dict(test=f"degenerate_shadow_is_conservative_noop_{i}",passed=True))
    all_paths=paths()
    old=ROOT / "experiments/runs/2026-09-11_coupled-dispatch"
    for problem,name in ((3,"range_area7"),(4,"range_width015")):
        spec=dict(SPECS[problem][name],kind="negative_completion" if problem==3 else "negative_width",negative_hull=False)
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
            checks.append(dict(test=f"disabled_negative_inference_feedback_q{problem}_{case_id}",passed=True))
    for problem,methods in SPECS.items():
        selected=[c for c in training_cases(problem) if c[2]=="stress" and c[0].endswith(("n16__negative","n10__spatial"))]
        for name,spec in methods.items():
            if not spec["kind"].startswith("negative_"):
                continue
            for case_id,category,split,scenario,error in selected:
                sim=Simulator(scenario,ErrorField(scenario.seed,error),Limits(countdown_s=0))
                policy=build(Client(PeerTransport(Protocol(sim)),robot_id="mock-robot"),spec,problem,all_paths)
                stats=policy.run()
                assert len(sim.cleared)==len(scenario.sources),(problem,name,case_id)
                assert not stats["negative_hull_inconsistent_cuts"] and not stats["inconsistent_updates"] and not stats.get("bracket_cut_inconsistencies",0)
                checks.append(dict(test=f"full_protocol_q{problem}_{name}_{case_id}",passed=True,
                                   total_s=sim.virtual_time_s,shadow_cuts=stats["negative_shadow_cuts"]))
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
