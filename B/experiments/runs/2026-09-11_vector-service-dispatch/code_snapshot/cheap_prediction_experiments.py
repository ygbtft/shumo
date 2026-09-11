"""Compare scalar necessary filters with unchanged full-region negative-pair prediction."""
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
from deferred_skip_policy import pair_nonreception_certificate
from cheap_prediction_policy import CheapPredictionWidthPolicy,CheapPredictionFastWidthPolicy,cheap_pair_nonreception_certificate
from geometry import hull, minimum_circle, polygon_area
from layout_alternative_experiments import training_cases
from metaheuristic_experiments import write_json
from peer_benchmark import PeerTransport, Simulator, ErrorField, Limits, Protocol
import batched_history_experiments as builders
import deferred_skip_experiments as original
import coupled_dispatch_experiments as coupled
from mock.scenario_gen import Source
from mock.geometry import covered
import spatial_decision_experiments as engine

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "experiments/runs/2026-09-11_cheap-prediction"
NAMES=tuple(f"predict{size}_{label}" for label in ("width015","arc05_width015","locked_width015") for size in (4,8))
SPECS={4:{name:original.SPECS[4][name].copy() for name in NAMES}}
for name in NAMES:
    spec=SPECS[4][name].copy()
    spec["kind"]="cheap_prediction_fast_width" if spec["kind"]=="deferred_fast_width" else "cheap_prediction_width"
    SPECS[4]["cheap_"+name]=spec
EXPECTED=1116


def paths():
    return builders.paths()


def build(client,spec,problem,all_paths):
    if not spec["kind"].startswith("cheap_prediction_"):
        return builders.build(client,spec,problem,all_paths)
    params=spec.copy()
    kind=params.pop("kind")
    points=all_paths[params.pop("layout")]
    if problem==4:params.setdefault("trial_radius",40.)
    cls={"cheap_prediction_width":CheapPredictionWidthPolicy,"cheap_prediction_fast_width":CheapPredictionFastWidthPolicy}[kind]
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
        derivation="42+25+repeat,0..4; already-used training scenes", untouched_future_seeds=list(range(137,147)),
        stress_derivation="Q3 [42,35,layout_index,count], Q4 [42,20,layout_index,count]; prior training streams",
        specs=SPECS, paths={k:v.tolist() for k,v in all_paths.items()}, expected_executions=EXPECTED,
        negative_prediction_assumptions="Reject only clear violations of a necessary first-vertex segment/distance predicate; every acceptance still uses unchanged full-region certificate",
        scalar_guard_squared_m=1e-5, segment_parameter_guard=1e-4,
        additional_measurement_budget=0, virtual_upper_bound_s=335136, instruction_upper_bound=9766,
        engine_reuse="spatial_decision_experiments.run with explicit OUT/SPECS/build/freeze/all_layouts replacements",
        code_sha256=hashes, python=sys.executable, cpu_threads=1, truth_to_policy=False, official_calls=0,
        peer_commit="c477d3660368f27c7131a0591426b4c4f107ea5d"))
    (OUT / "precheck.md").write_text(f"# 负反馈预测廉价筛选前检查\n\n{result['passed']}项通过：原/新完整区域证书在随机与边界/旋转/平移输入上相同，6种预测策略共558条完整公开反馈和删除统计等价。12方法×93=1116，137—146未生成，正式请求0。\n")


def check():
    if (OUT / "checks.json").exists():raise RuntimeError("Preserving checks")
    rng=np.random.default_rng(42);checks=[]
    def validate(poly,q,a,b,label):
        old=pair_nonreception_certificate(poly,q,a,b)
        new=cheap_pair_nonreception_certificate(poly,q,a,b)
        assert (old is None)==(new is None),label
        if old is not None:
            assert np.array_equal(old[0],new[0]) and np.array_equal(old[1],new[1])
        checks.append(dict(test=label,passed=True,certified=old is not None))
    for i in range(400):
        poly=hull(rng.uniform(-1800,1800,size=(int(rng.integers(3,12)),2)))
        q,a,b=rng.uniform(-3535,3535,size=(3,2))
        validate(poly,q,a,b,f"random_necessary_prefilter_equivalence_{i}")
    for i in range(80):
        angle=rng.uniform(0,2*np.pi);rot=np.array([[np.cos(angle),-np.sin(angle)],[np.sin(angle),np.cos(angle)]])
        shift=rng.uniform(-1000,1000,size=2)
        lower=(800.,500.-1e-4,500.+1e-4,500.+1e-2)[i%4]
        poly=hull([[lower,-10.],[1000.,-10.],[1000.,10.],[lower,10.]])@rot.T+shift
        q,a,b=(np.array(x)@rot.T+shift for x in ([0.,0.],[500.,-100.],[500.,100.]))
        validate(poly,q,a,b,f"boundary_rotated_prefilter_equivalence_{i}")
    all_paths=paths()
    rows=[json.loads(line) for line in (original.OUT / "trials.jsonl").read_text().splitlines()]
    lookup={(r["method"],r["case_id"]):r for r in rows}
    for old in NAMES:
        new="cheap_"+old
        for case_id,category,split,scenario,error in training_cases(4):
            with gzip.open(original.OUT / "traces" / f"q4__{case_id}__{old}.jsonl.gz","rt") as stream:
                trace=[json.loads(line) for line in stream]
            reference=lookup[old,case_id];index=0
            def replay(endpoint,raw):
                nonlocal index
                entry=trace[index]
                assert endpoint==entry["path"] and json.loads(raw)==entry["request"],(old,case_id,index)
                index+=1
                return 200,entry["response"]
            stats=build(Client(replay,robot_id="mock-robot"),SPECS[4][new],4,all_paths).run()
            assert index==len(trace)
            for key in ("certified_scan_skips","predicted_pair_skips","certified_range_scan_skips","deferred_nonstationary_skips","minimum_actual_unknown_per_station"):
                assert stats[key]==reference[key],(old,case_id,key)
            checks.append(dict(test=f"same_feedback_prediction_{old}_{case_id}",passed=True))
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
