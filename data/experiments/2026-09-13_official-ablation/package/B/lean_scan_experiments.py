"""Same feedback and actual paired timing for lazy scan computations."""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

from client import Client
from lean_scan_policy import LeanCompletionPolicy,LeanWidthPolicy,LeanFastWidthPolicy
from layout_alternative_experiments import training_cases
from metaheuristic_experiments import write_json
from peer_benchmark import PeerTransport,Simulator,ErrorField,Limits,Protocol
import cheap_prediction_experiments as cheap
import deferred_skip_experiments as deferred
import spatial_decision_experiments as engine

ROOT=Path(__file__).resolve().parent
OUT=ROOT/"experiments/runs/2026-09-11_lean-scan"
FAMILIES=((3,"deferred_area7",deferred.OUT),(4,"deferred_width015",deferred.OUT),
          (4,"cheap_predict4_width015",cheap.OUT),(4,"cheap_predict8_width015",cheap.OUT),
          (4,"cheap_predict8_arc05_width015",cheap.OUT),(4,"cheap_predict8_locked_width015",cheap.OUT))
SPECS={3:{},4:{}}
for problem,name,folder in FAMILIES:
    old=(deferred if folder==deferred.OUT else cheap).SPECS[problem][name].copy()
    SPECS[problem][name]=old
    kind="lean_completion" if problem==3 else "lean_fast_width" if "fast_width" in old["kind"] else "lean_width"
    SPECS[problem]["lean_"+name]=dict(old,kind=kind,cheap_prediction=old["kind"].startswith("cheap_prediction_"))
EXPECTED=1116


def paths():return cheap.paths()


def build(client,spec,problem,all_paths):
    if not spec["kind"].startswith("lean_"):return cheap.build(client,spec,problem,all_paths)
    params=spec.copy();kind=params.pop("kind");stations=all_paths[params.pop("layout")]
    if problem==4:params.setdefault("trial_radius",40.)
    cls={"lean_completion":LeanCompletionPolicy,"lean_width":LeanWidthPolicy,"lean_fast_width":LeanFastWidthPolicy}[kind]
    return cls(client,stations,mixed=problem==4,**params)


def check():
    if (OUT/"checks.json").exists():raise RuntimeError("Preserving checks")
    checks=[];all_paths=paths()
    for problem,name,folder in FAMILIES:
        lookup={r["case_id"]:r for r in map(json.loads,(folder/"trials.jsonl").read_text().splitlines()) if r["method"]==name}
        for case_id,category,split,scenario,error in training_cases(problem):
            with gzip.open(folder/"traces"/f"q{problem}__{case_id}__{name}.jsonl.gz","rt") as stream:
                trace=[json.loads(line) for line in stream]
            def replay_one(trace,spec):
                index=0
                def transport(endpoint,raw):
                    nonlocal index
                    entry=trace[index]
                    assert endpoint==entry["path"] and json.loads(raw)==entry["request"],(name,case_id,index)
                    index+=1;return 200,entry["response"]
                stats=build(Client(transport,robot_id="mock-robot"),spec,problem,all_paths).run()
                assert index==len(trace)
                return stats
            stats=replay_one(trace,SPECS[problem]["lean_"+name])
            reference=lookup[case_id]
            for key,value in stats.items():assert key in reference and value==reference[key],(name,case_id,key,value,reference.get(key))
            checks.append(dict(test=f"full_feedback_and_all_original_statistics_q{problem}_{name}_{case_id}",passed=True))
            if case_id in ("uniform__iid__67","boundary_outward__n10__negative","near_collinear__n16__positive","cluster_far20__n13__spatial"):
                for flag in (dict(faithful_skip=False),dict(defer_scan=False)):
                    sim=Simulator(scenario,ErrorField(scenario.seed,error),Limits(countdown_s=0))
                    control=build(Client(PeerTransport(Protocol(sim)),robot_id="mock-robot"),dict(SPECS[problem][name],**flag),problem,all_paths).run()
                    tested=replay_one(sim.trace,dict(SPECS[problem]["lean_"+name],**flag))
                    assert tested==control and len(sim.cleared)==len(scenario.sources)
                    checks.append(dict(test=f"disabled_control_{name}_{case_id}_{next(iter(flag))}",passed=True))
    write_json(OUT/"checks.json",dict(passed=len(checks),failed=0,checks=checks,scored_executions=0,official_calls=0))
    print("Passed",len(checks),flush=True)


def freeze(all_paths):
    if (OUT/"run_config.json").exists():raise RuntimeError("Preserving run")
    tests=json.loads((OUT/"checks.json").read_text());assert tests["failed"]==0
    snapshot=OUT/"code_snapshot";snapshot.mkdir();hashes={}
    for p in ROOT.glob("*.py"):
        raw=p.read_bytes();(snapshot/p.name).write_bytes(raw);hashes[p.name]=hashlib.sha256(raw).hexdigest()
    write_json(OUT/"run_config.json",dict(base_seed=42,training_seeds=list(range(67,72)),
        derivation="42+25+repeat; reused 75 ordinary and 18 stress scenes per problem",untouched_future_seeds=list(range(147,157)),
        specs=SPECS,paths={k:v.tolist() for k,v in all_paths.items()},expected_executions=EXPECTED,
        change="Lazy position comparison/conversion with unchanged ordered full-region certificate; all prior statistics preserved",
        virtual_upper_bound_s=335136,instruction_upper_bound=9766,code_sha256=hashes,python=sys.executable,cpu_threads=1,
        truth_to_policy=False,official_calls=0,peer_commit="c477d3660368f27c7131a0591426b4c4f107ea5d"))
    (OUT/"precheck.md").write_text(f"# 延迟求值训练前检查\n\n{tests['passed']}项反馈/全部原统计等价与关闭功能控制通过。6对方法×93=1116计分，仅比较相同决策CPU；未来147—156未生成，正式请求0。\n")


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--check",action="store_true");parser.add_argument("--launch",action="store_true")
    args=parser.parse_args();engine.OUT,engine.SPECS,engine.build,engine.freeze,engine.all_layouts=OUT,SPECS,build,freeze,paths
    if args.check:check()
    elif args.launch:
        if (OUT/"run_config.json").exists():raise RuntimeError("Preserving scored run")
        env=os.environ.copy();env.update(PYTHONDONTWRITEBYTECODE="1",OPENBLAS_NUM_THREADS="1",OMP_NUM_THREADS="1",
                                         MPLCONFIGDIR=str(ROOT/".mplconfig"),XDG_CACHE_HOME=str(ROOT/".cache"))
        with (OUT/"log.txt").open("a") as stream:
            p=subprocess.Popen([sys.executable,"-B",str(Path(__file__).resolve())],cwd=ROOT.parent,env=env,
                               stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
        (OUT/"background.pid").write_text(str(p.pid)+"\n");print("Background PID",p.pid)
    else:engine.run()


if __name__=="__main__":main()
