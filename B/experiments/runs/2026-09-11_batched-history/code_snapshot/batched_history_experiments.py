"""Compare exact sequential history cuts with guarded batched no-effect screening."""
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
from historical_pair_policy import exclusion_planes,exclude_historical_pair
from batched_history_policy import BatchedHistoricalWidthPolicy,BatchedHistoricalFastWidthPolicy,apply_pair_sequence
from geometry import hull, minimum_circle, polygon_area
from layout_alternative_experiments import training_cases
from metaheuristic_experiments import write_json
from peer_benchmark import PeerTransport, Simulator, ErrorField, Limits, Protocol
import deferred_skip_experiments as builders
import historical_pair_experiments as historical
import coupled_dispatch_experiments as coupled
from mock.scenario_gen import Source
from mock.geometry import covered
import spatial_decision_experiments as engine

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "experiments/runs/2026-09-11_batched-history"
NAMES=("history_first8_width015","history_recent8_width015","history_ends16_width015","history_arc8_width015","history_locked8_width015")
SPECS={4:{name:historical.SPECS[4][name].copy() for name in NAMES}}
for name in NAMES:
    spec=SPECS[4][name].copy()
    spec["kind"]="batched_history_fast_width" if spec["kind"]=="historical_fast_width" else "batched_history_width"
    SPECS[4]["batch_"+name]=spec
EXPECTED=930


def paths():
    return builders.paths()


def build(client,spec,problem,all_paths):
    if not spec["kind"].startswith("batched_history_"):
        return builders.build(client,spec,problem,all_paths)
    params=spec.copy()
    kind=params.pop("kind")
    points=all_paths[params.pop("layout")]
    if problem==4:params.setdefault("trial_radius",40.)
    cls={"batched_history_width":BatchedHistoricalWidthPolicy,"batched_history_fast_width":BatchedHistoricalFastWidthPolicy}[kind]
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
        negative_region_assumptions="Same fixed ordered five-halfplane complements and convex hulls as historical policy; batch only screens definitely idle candidates and recomputes the suffix after each actual cut",
        numerical_guard_m=1e-8,
        additional_measurement_budget=0, virtual_upper_bound_s=335136, instruction_upper_bound=9766,
        engine_reuse="spatial_decision_experiments.run with explicit OUT/SPECS/build/freeze/all_layouts replacements",
        code_sha256=hashes, python=sys.executable, cpu_threads=1, truth_to_policy=False, official_calls=0,
        peer_commit="c477d3660368f27c7131a0591426b4c4f107ea5d"))
    (OUT / "precheck.md").write_text(f"# 批量筛选训练前检查\n\n{result['passed']}项通过：独立原顺序裁剪与批量结果、裁剪后重新激活的反例、465条关闭批量及465条启用批量完整反馈/历史统计等价。10方法×93=930，137—146未生成，正式请求0。\n")


def check():
    if (OUT / "checks.json").exists():raise RuntimeError("Preserving checks")
    rng=np.random.default_rng(42);checks=[]
    def sequential(poly,records):
        cuts=inconsistent=0
        for planes in records:
            candidate=exclude_historical_pair(poly,planes)
            if not len(candidate):inconsistent+=1;continue
            if candidate is not poly:poly=candidate;cuts+=1
        return poly,cuts,inconsistent
    def validate(poly,records,label):
        expected,cuts,bad=sequential(poly,records)
        for enabled in (False,True):
            result,stats=apply_pair_sequence(poly,records,enabled,2)
            assert np.array_equal(expected,result),(label,enabled)
            assert stats["cuts"]==cuts and stats["inconsistent"]==bad
        checks.append(dict(test=label,passed=True,cuts=cuts))
    poly=hull([[-10,-10],[10,-10],[10,10],[-10,10]])
    a=(np.array([[-1.,0],[1,0],[0,1],[0,-1],[1,0]]),np.array([0.,100,100,100,100]))
    b=(np.array([[1.,0],[-1,0],[0,-1],[0,1],[1,0]]),np.array([1.,1,0,100,100]))
    assert exclude_historical_pair(poly,b) is poly
    validate(poly,[a,b],"later_exclusion_activated_by_new_vertices_after_first_cut")
    assert checks[-1]["cuts"]==2
    for i in range(160):
        poly=hull(rng.uniform(-1800.,1800.,size=(int(rng.integers(3,21)),2)))
        records=[exclusion_planes(*rng.uniform(-2500.,2500.,size=(3,2))) for j in range(int(rng.integers(2,60)))]
        if i%7==0:records.insert(0,None)
        validate(poly,records,f"ordered_geometry_sequence_{i}")
    all_paths=paths()
    rows=[json.loads(line) for line in (historical.OUT / "trials.jsonl").read_text().splitlines()]
    lookup={(r["method"],r["case_id"]):r for r in rows}
    for old in NAMES:
        new="batch_"+old
        for case_id,category,split,scenario,error in training_cases(4):
            with gzip.open(historical.OUT / "traces" / f"q4__{case_id}__{old}.jsonl.gz","rt") as stream:
                trace=[json.loads(line) for line in stream]
            reference=lookup[old,case_id]
            for enabled in (False,True):
                index=0
                def replay(endpoint,raw):
                    nonlocal index
                    entry=trace[index]
                    assert endpoint==entry["path"] and json.loads(raw)==entry["request"],(old,case_id,index,enabled)
                    index+=1
                    return 200,entry["response"]
                stats=build(Client(replay,robot_id="mock-robot"),dict(SPECS[4][new],history_batch=enabled),4,all_paths).run()
                assert index==len(trace)
                for key in ("historical_pair_cuts","historical_pair_updates","historical_pair_checks","historical_inconsistent_cuts","historical_cache_evictions"):
                    assert stats[key]==reference[key],(old,case_id,key,enabled)
                checks.append(dict(test=f"exact_public_history_batch{enabled}_{old}_{case_id}",passed=True,
                                   exact_clip_calls=stats["historical_exact_clip_calls"],screens=stats["historical_batch_screens"]))
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
