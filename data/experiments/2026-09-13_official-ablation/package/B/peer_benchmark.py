"""Frozen policies on the supplied independent benchmark. In-process only."""
from dataclasses import asdict
import csv
import gzip
import json
import math
from pathlib import Path
import sys
import time
import traceback
import numpy as np

ROOT=Path(__file__).resolve().parent
PEER=ROOT/"reference/shumo-b"
OUT=ROOT/"experiments/runs/2026-09-10_peer-benchmark"
sys.path.insert(0,str(PEER))
from mock.error_field import ErrorConfig,ErrorField
from mock.evaluator import mandatory_conditions
from mock.scenario_gen import ScenarioConfig,generate
from mock.simulator import Simulator,Limits
from mock.protocol import Protocol
from mock.backends.inproc import InProcMock
from mock.strategy import Baseline
from mock.client_or_inproc import run_strategy
from client import Client
from policies import Policy


class PeerTransport:
    def __init__(self,protocol):
        self.__protocol=protocol
    def __call__(self,path,raw):
        reply=self.__protocol.handle("POST",path,raw,{"Content-Type":"application/json"})
        return reply.status,reply.body


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    if (OUT/"trials.jsonl").exists():
        raise RuntimeError("Preserving existing peer results; choose a new output directory")
    (OUT/"traces").mkdir(exist_ok=True)
    (OUT/"scenarios_scoring_only").mkdir(exist_ok=True)
    paths=json.loads((ROOT/"experiments/runs/2026-09-10_independent/routes.json").read_text())
    strategies=["peer_baseline","square_greedy","square_cropped_2opt","active_2opt"]
    config={"base_seed":42,"seeds":list(range(42,52)),"derivation":"seed = 42 + trial, 0 <= trial < 10; paired across errors and policies",
            "peer_commit":"c477d3660368f27c7131a0591426b4c4f107ea5d","strategies":strategies,
            "matrix":"2 problems x 3 positions x 5 error fields x 10 seeds x 4 policies = 1200 executions",
            "policy_changed_since_main":False,"protocol":"unmodified peer Protocol.handle","official_connections":0,
            "count_to_policy":False,"truth_to_policy":False,"active_max_measurements":3,"active_time_weight":.08}
    (OUT/"run_config.json").write_text(json.dumps(config,indent=2))
    began=time.perf_counter(); rows=[]; combo=0
    with (OUT/"trials.jsonl").open("a") as stream:
        for mixed in [False,True]:
            cfg=ScenarioConfig(directional_fraction=.5 if mixed else 0.)
            for label,scfg,ecfg in mandatory_conditions(cfg,ErrorConfig()):
                for seed in range(42,52):
                    scenario=generate(seed,scfg)
                    case_id=f"q{4 if mixed else 3}_{label}_{seed}"
                    (OUT/"scenarios_scoring_only"/f"{case_id}.json").write_text(json.dumps({"scenario":scenario.to_dict(),"error":asdict(ecfg)},indent=2))
                    for strategy in strategies:
                        sim=Simulator(scenario,ErrorField(seed,ecfg),Limits(countdown_s=0))
                        protocol=Protocol(sim)
                        start=time.perf_counter(); cpu=time.process_time(); failure=""; extra={}
                        try:
                            if strategy=="peer_baseline":
                                result=run_strategy(InProcMock(protocol),Baseline(seed=42))
                                failure=result.error or ("" if result.stop_reason=="user_exit" else result.stop_reason)
                                extra["stop_reason"]=result.stop_reason
                            else:
                                path=strategy if strategy.startswith("square") else f"q{4 if mixed else 3}_triangle_2opt"
                                cli=Client(PeerTransport(protocol),robot_id="mock-robot")
                                extra=Policy(cli,np.array(paths[path]),mixed=mixed,active=strategy=="active_2opt",
                                             optimized=strategy!="square_greedy").run()
                        except Exception as exc:
                            failure=repr(exc)
                            (OUT/"traces"/f"{case_id}__{strategy}.error.txt").write_text(traceback.format_exc())
                        wall=time.perf_counter()-start; cpu=time.process_time()-cpu
                        position=(0.,0.); channel=1; move=0.; measures=0; clear_calls=0; switches=0
                        for entry in sim.trace:
                            if entry["path"] not in ("/measure","/clear"):
                                continue
                            request=entry["request"]
                            q=(request["position"]["x"],request["position"]["y"])
                            move+=math.dist(position,q); position=q
                            if entry["path"]=="/measure":
                                measures+=1; switches+=int(request["channel"]!=channel); channel=request["channel"]
                            else:
                                clear_calls+=1
                        row={"case_id":case_id,"category":label,"mixed":mixed,"strategy":strategy,"seed":seed,
                             "sources":len(scenario.sources),"cleared":len(sim.cleared),
                             "all_cleared":len(sim.cleared)==len(scenario.sources),
                             "clear_fraction":len(sim.cleared)/len(scenario.sources),
                             "total_virtual_s":sim.virtual_time_s,"per_source_s":sim.virtual_time_s/len(sim.cleared) if sim.cleared else None,
                             "commands":len(sim.trace),"measurements":measures,"clear_calls":clear_calls,"switches":switches,
                             "move_m":move,"wall_s":wall,"cpu_s":cpu,"failure":failure,
                             "missed_channels":sorted(set(sim.sources)-sim.cleared),**extra}
                        rows.append(row); stream.write(json.dumps(row)+"\n"); stream.flush()
                        with gzip.open(OUT/"traces"/f"{case_id}__{strategy}.jsonl.gz","wt") as f:
                            for entry in sim.trace:
                                f.write(json.dumps(entry,separators=(",",":"))+"\n")
                    combo+=1
                print(f"{time.strftime('%H:%M:%S')} q{4 if mixed else 3} {label}: {len(rows)} executions, wall {time.perf_counter()-began:.1f}s",flush=True)
    fields=sorted(set().union(*(row.keys() for row in rows)))
    with (OUT/"trials.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(rows)
    result={"combinations":combo,"executions":len(rows),"wall_s":time.perf_counter()-began,
            "all_cleared":sum(r["all_cleared"] for r in rows),"errors":sum(bool(r["failure"]) for r in rows)}
    (OUT/"completion.json").write_text(json.dumps(result,indent=2))
    print(json.dumps(result),flush=True)


if __name__=="__main__":
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",help="A fresh run directory below B/")
    args=parser.parse_args()
    if args.output:
        selected=Path(args.output).resolve()
        if not selected.is_relative_to(ROOT):
            parser.error("Output must stay below B/")
        OUT=selected
    main()
