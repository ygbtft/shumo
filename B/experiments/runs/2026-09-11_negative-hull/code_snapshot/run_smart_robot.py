"""Run one new strategy OFFLINE on the peer benchmark; no HTTP/official mode."""
import argparse
from dataclasses import asdict
from datetime import datetime
import gzip
import json
from pathlib import Path
import time
import numpy as np
from client import Client
from policies import Policy
from adaptive_routes import AdaptivePolicy
from route_algorithms import METHODS
from ring_coverage import DESIGNS, stations as ring_stations
from peer_benchmark import PeerTransport, ErrorConfig, ErrorField, ScenarioConfig, generate, Simulator, Limits, Protocol

ROOT=Path(__file__).resolve().parent
RUN=ROOT/"experiments/runs/2026-09-10_metaheuristics"


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--task",choices=("q3_active","q4_active","q4_conservative"),required=True)
    p.add_argument("--method",choices=("auto",)+METHODS+("adaptive_greedy","adaptive_two_opt")+tuple(DESIGNS),default="auto")
    p.add_argument("--seed",type=int,default=42)
    args=p.parse_args()
    method=args.method
    if method=="auto":
        method=json.loads((RUN/"confirmation_selection.json").read_text())["selection"][args.task]["method"]
    mixed=args.task!="q3_active"
    active=args.task!="q4_conservative"
    point_set="square700" if not active else "q4_triangle" if mixed else "q3_triangle"
    routes=json.loads((RUN/"selected_routes.json").read_text())
    if method in DESIGNS:
        if mixed:
            p.error("Ring layouts are certified only for all-omnidirectional q3_active")
        points=ring_stations(*DESIGNS[method])
    else:
        points=np.array(routes[point_set]["two_opt" if method.startswith("adaptive_") else method]["points"])
    scenario=generate(args.seed,ScenarioConfig(directional_fraction=.5 if mixed else 0.))
    error=ErrorConfig()
    sim=Simulator(scenario,ErrorField(args.seed,error),Limits(countdown_s=0))
    cli=Client(PeerTransport(Protocol(sim)),robot_id="mock-robot")
    policy=AdaptivePolicy(cli,points,polish=method=="adaptive_two_opt",mixed=mixed,active=active,optimized=True) if method.startswith("adaptive_") else Policy(cli,points,mixed=mixed,active=active,optimized=True)
    started=time.perf_counter()
    stats=policy.run()
    result={"mode":"offline_peer","task":args.task,"method":method,"seed":args.seed,
            "all_cleared":len(sim.cleared)==len(scenario.sources),"cleared":len(sim.cleared),"sources_scoring_only":len(scenario.sources),
            "total_virtual_s":sim.virtual_time_s,"per_source_s":sim.virtual_time_s/len(sim.cleared) if sim.cleared else None,
            "commands":len(sim.trace),"wall_s":time.perf_counter()-started,"official_requests":0,**stats}
    dest=ROOT/"robot_runs"/(datetime.now().strftime("%Y%m%d-%H%M%S-%f")+"-smart-offline")
    dest.mkdir(parents=True)
    (dest/"summary.json").write_text(json.dumps(result,indent=2))
    (dest/"scoring_only.json").write_text(json.dumps({"scenario":scenario.to_dict(),"error":asdict(error)},indent=2))
    with gzip.open(dest/"trace.jsonl.gz","wt") as stream:
        for entry in sim.trace:
            stream.write(json.dumps(entry)+"\n")
    print(json.dumps(result,ensure_ascii=False,indent=2))
    print(dest)


if __name__=="__main__":main()
