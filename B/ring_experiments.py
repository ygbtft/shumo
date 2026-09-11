"""Paired offline Q3 layout comparison; same frozen feedback-only active policy."""
import argparse
from dataclasses import asdict
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import subprocess
import sys
import time
import traceback
import numpy as np
from ring_coverage import DESIGNS, stations, metadata
from coverage import route_length
from policies import Policy
from client import Client
from peer_benchmark import PeerTransport, ErrorConfig, ErrorField, ScenarioConfig, generate, mandatory_conditions, Simulator, Limits, Protocol
from mock.scenario_gen import Scenario, Source
from metaheuristic_experiments import trace_metrics, write_json, write_csv

ROOT=Path(__file__).resolve().parent
OUT=ROOT/"experiments/runs/2026-09-11_peer-paper-review"


def cases():
    for label,scfg,ecfg in mandatory_conditions(ScenarioConfig(directional_fraction=0.),ErrorConfig()):
        for seed in range(67,77):
            yield f"{label}__{seed}", label, "ordinary", generate(seed,scfg), ecfg
    index=0
    for li,layout in enumerate(("boundary_min", "near_collinear_min", "unknown_count_late")):
        for count in (10,16):
            rng=np.random.default_rng(np.random.SeedSequence([42,35,li,count]))
            channels=list(rng.choice(np.arange(1,20),count-1,replace=False))+[20]
            angles=(np.arange(count)/count+.041)*2*math.pi
            if layout=="boundary_min":
                points=1800*np.column_stack((np.cos(angles),np.sin(angles)))
            elif layout=="near_collinear_min":
                axis=np.array([math.cos(.317),math.sin(.317)])
                normal=np.array([-axis[1],axis[0]])
                points=np.linspace(-1750,1750,count)[:,None]*axis+rng.uniform(-.05,.05,count)[:,None]*normal
            else:
                points=rng.normal(0,170,size=(count,2))
                points[-1]=1800*np.array([math.cos(.041),math.sin(.041)])
            sources=tuple(Source(int(ch),float(p[0]),float(p[1]),1000.,None) for ch,p in zip(channels,points))
            for sign in ("positive","negative","spatial"):
                seed=42+200+index
                scenario=Scenario(seed,sources,{"stress_layout":layout,"source_rng":[42,35,li,count]})
                yield f"{layout}__n{count}__{sign}",layout,"stress",scenario,ErrorConfig(model="adversarial",adversarial_sign=sign)
                index+=1


def freeze():
    if (OUT/"ring_run_config.json").exists():
        raise RuntimeError("Existing run preserved; choose a fresh --output")
    baseline=json.loads((ROOT/"experiments/runs/2026-09-10_metaheuristics/selected_routes.json").read_text())
    paths={"old_triangle19":np.array(baseline["q3_triangle"]["two_opt"]["points"])}
    paths.update({name:stations(n,a) for name,(n,a) in DESIGNS.items()})
    snapshot=OUT/"ring_code_snapshot";snapshot.mkdir()
    hashes={}
    for name in ("ring_coverage.py","ring_experiments.py","policies.py","geometry.py","intelligent.py","client.py","coverage.py","peer_benchmark.py","metaheuristic_experiments.py","adaptive_routes.py","route_algorithms.py"):
        raw=(ROOT/name).read_bytes();(snapshot/name).write_bytes(raw);hashes[name]=hashlib.sha256(raw).hexdigest()
    cfg={"base_seed":42,"random_seeds":list(range(67,77)),"derivation":"42 + 25 + repeat, repeat=0..9; all new relative to earlier scored runs",
         "stress_rng":"SeedSequence([42,35,layout_index,count]); error seed=42+200+case_index",
         "matrix":"(3 locations x 5 errors x 10 seeds + 3 stress layouts x 2 counts x 3 errors) x 5 methods = 840",
         "selection":"Four fixed geometrically certified layouts, parameters frozen before online evaluation; same angular start 0, counterclockwise open ring traversal",
         "baseline":"Previously frozen q3_triangle/two_opt, not reoptimized",
         "peer_paper_reproduced":"Only center+8 ring station layout; all five share our unchanged active localization/clearing/stopping policy. NOT full peer policy replication.",
         "policy_parameters":{"mixed":False,"active":True,"optimized":True,"max_active":3,"time_weight":.08},
         "metadata":metadata(),"paths":{k:v.tolist() for k,v in paths.items()},
         "path_lengths_m":{k:route_length(v) for k,v in paths.items()},
         "peer_commit":"c477d3660368f27c7131a0591426b4c4f107ea5d",
         "python":sys.executable,"platform":platform.platform(),"code_sha256":hashes,
         "official_requests":0,"hidden_state_to_policy":False,"count_to_policy":False,"cpu_threads":1}
    write_json(OUT/"ring_run_config.json",cfg)
    print("Frozen layouts",json.dumps(cfg["path_lengths_m"]),flush=True)
    return paths


def evaluate(paths):
    (OUT/"ring_traces").mkdir();(OUT/"ring_scenarios_scoring_only").mkdir()
    rows=[];started=time.perf_counter()
    with (OUT/"ring_trials.jsonl").open("x") as stream:
        for ci,(case_id,category,split,scenario,ecfg) in enumerate(cases()):
            write_json(OUT/"ring_scenarios_scoring_only"/f"{case_id}.json",{"scenario":scenario.to_dict(),"error":asdict(ecfg)})
            for method,points in paths.items():
                sim=Simulator(scenario,ErrorField(scenario.seed,ecfg),Limits(countdown_s=0))
                cli=Client(PeerTransport(Protocol(sim)),robot_id="mock-robot")
                policy=Policy(cli,points,mixed=False,active=True,optimized=True)
                began=time.perf_counter();cpu=time.process_time();failure="";extra={}
                try:
                    extra=policy.run()
                except Exception as exc:
                    failure=repr(exc)
                    (OUT/"ring_traces"/f"{case_id}__{method}.error.txt").write_text(traceback.format_exc())
                row={"case_id":case_id,"method":method,"category":category,"split":split,"seed":scenario.seed,
                     "sources":len(scenario.sources),"cleared":len(sim.cleared),"all_cleared":len(sim.cleared)==len(scenario.sources),
                     "total_virtual_s":sim.virtual_time_s,"per_source_s":sim.virtual_time_s/len(sim.cleared) if sim.cleared else None,
                     "commands":len(sim.trace),"wall_s":time.perf_counter()-began,"cpu_s":time.process_time()-cpu,
                     "failure":failure,"missed_channels":sorted(set(sim.sources)-sim.cleared),**trace_metrics(sim.trace),**extra}
                rows.append(row);stream.write(json.dumps(row,allow_nan=False)+"\n");stream.flush()
                with gzip.open(OUT/"ring_traces"/f"{case_id}__{method}.jsonl.gz","wt") as f:
                    for entry in sim.trace:
                        f.write(json.dumps(entry,separators=(",",":"))+"\n")
                if failure or not row["all_cleared"]:
                    print("FAIL",case_id,method,failure,row["missed_channels"],flush=True)
            if (ci+1)%5==0 or split=="stress":
                print(f"{ci+1}/168 cases, {len(rows)} executions, {time.perf_counter()-started:.1f}s",flush=True)
    write_csv(OUT/"ring_trials.csv",rows)
    write_json(OUT/"ring_completion.json",{"executions":len(rows),"all_cleared":sum(r["all_cleared"] for r in rows),
               "errors":sum(bool(r["failure"]) for r in rows),"wall_s":time.perf_counter()-started})
    print("Completed",len(rows),"executions",flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--launch",action="store_true");parser.add_argument("--output")
    args=parser.parse_args()
    global OUT
    if args.output:
        OUT=Path(args.output).resolve()
        if not OUT.is_relative_to(ROOT):parser.error("B/ writes only")
    OUT.mkdir(parents=True,exist_ok=True)
    if args.launch:
        if (OUT/"ring_run_config.json").exists():raise RuntimeError("Existing run preserved")
        env=os.environ.copy();env.update(PYTHONDONTWRITEBYTECODE="1",OPENBLAS_NUM_THREADS="1",OMP_NUM_THREADS="1",MPLCONFIGDIR=str(ROOT/".mplconfig"),XDG_CACHE_HOME=str(ROOT/".cache"))
        with (OUT/"log.txt").open("a") as log:
            p=subprocess.Popen([sys.executable,"-B",str(Path(__file__).resolve()),"--output",str(OUT)],cwd=ROOT.parent,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        (OUT/"background.pid").write_text(str(p.pid)+"\n");print("Background PID",p.pid)
    else:
        evaluate(freeze())


if __name__=="__main__":main()
