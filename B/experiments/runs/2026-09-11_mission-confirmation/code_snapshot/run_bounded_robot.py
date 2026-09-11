"""Run a frozen bounded-uncertainty strategy on the local peer protocol only."""
import argparse
from dataclasses import asdict
from datetime import datetime
import gzip
import json
from pathlib import Path
import time
from client import Client
from peer_benchmark import PeerTransport,ErrorConfig,ErrorField,ScenarioConfig,generate,Simulator,Limits,Protocol
from metaheuristic_experiments import trace_metrics
from icra_confirmation import SPECS,all_paths
from replacement_experiments import build

ROOT=Path(__file__).resolve().parent


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--problem",type=int,choices=(3,4),required=True)
    parser.add_argument("--method",required=True)
    parser.add_argument("--seed",type=int,default=42)
    args=parser.parse_args()
    if args.method not in SPECS[args.problem]:parser.error("Methods: "+", ".join(SPECS[args.problem]))
    paths=all_paths();scenario=generate(args.seed,ScenarioConfig(directional_fraction=.5 if args.problem==4 else 0.));error=ErrorConfig()
    sim=Simulator(scenario,ErrorField(args.seed,error),Limits(countdown_s=0))
    initialized=time.perf_counter();policy=build(Client(PeerTransport(Protocol(sim)),robot_id="mock-robot"),SPECS[args.problem][args.method],args.problem,paths)
    initialization=time.perf_counter()-initialized;began=time.perf_counter();cpu=time.process_time();stats=policy.run()
    result=dict(mode="offline_peer_only",problem=args.problem,method=args.method,seed=args.seed,
        all_cleared=len(sim.cleared)==len(scenario.sources),cleared=len(sim.cleared),source_count_scoring_only=len(scenario.sources),
        total_virtual_s=sim.virtual_time_s,per_source_s=sim.virtual_time_s/len(sim.cleared) if sim.cleared else None,
        commands=len(sim.trace),wall_s=time.perf_counter()-began,cpu_s=time.process_time()-cpu,initialization_s=initialization,
        official_calls=0,**trace_metrics(sim.trace),**stats)
    dest=ROOT/"robot_runs"/(datetime.now().strftime("%Y%m%d-%H%M%S-%f")+"-bounded-offline")
    dest.mkdir(parents=True)
    (dest/"summary.json").write_text(json.dumps(result,indent=2))
    (dest/"scoring_only.json").write_text(json.dumps(dict(scenario=scenario.to_dict(),error=asdict(error)),indent=2))
    with gzip.open(dest/"trace.jsonl.gz","wt") as stream:
        for entry in sim.trace:stream.write(json.dumps(entry)+"\n")
    print(json.dumps(result,ensure_ascii=False,indent=2));print(dest)


if __name__=="__main__":main()
