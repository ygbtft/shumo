"""Frozen strategies: owned mock HTTP by default; explicit opt-in for official sessions."""
import time
PROGRAM_STARTED = time.perf_counter()
import argparse
from dataclasses import asdict
from datetime import datetime
import gzip
import json
import math
from pathlib import Path
from client import Client
from bounded_candidates import SPECS, load_paths, build

ROOT=Path(__file__).resolve().parent


def trace_metrics(trace):
    # Preserve the offline experiment's accounting order without importing its
    # runner: distance in metres, every measure/clear, and actual channel changes.
    position, channel = (0.,0.), 1
    move, measures, clears, switches = 0., 0, 0, 0
    for entry in trace:
        if entry["path"] not in ("/measure", "/clear"):
            continue
        request = entry["request"]
        q = (request["position"]["x"], request["position"]["y"])
        move += math.dist(position, q)
        position = q
        if entry["path"] == "/measure":
            measures += 1
            switches += int(request["channel"] != channel)
            channel = request["channel"]
        else:
            clears += 1
    return dict(move_m=move, measurements=measures, clear_calls=clears, switches=switches)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--problem",type=int,choices=(3,4),required=True)
    parser.add_argument("--method",required=True)
    parser.add_argument("--seed",type=int,default=42)
    parser.add_argument("--series",choices=("cover21",),default="cover21")
    parser.add_argument("--mode", choices=("mock-http", "offline", "practice", "formal"), default="mock-http")
    parser.add_argument("--base-url", help="Official HTTP endpoint only; mock-http always owns its random loopback port")
    parser.add_argument("--robot-id")
    parser.add_argument("--confirm-practice", action="store_true", help="User has manually logged in and opened a PRACTICE session")
    parser.add_argument("--confirm-formal", action="store_true", help="User authorized this FORMAL run and the matching session is open")
    args=parser.parse_args()
    if args.mode == "practice" and (not args.confirm_practice or not args.robot_id):
        parser.error("Practice needs --confirm-practice and --robot-id after manual login. No request sent.")
    if args.mode == "formal" and (not args.confirm_formal or not args.robot_id):
        parser.error("Formal needs --confirm-formal and --robot-id. No request sent.")
    if (args.confirm_practice and args.mode != "practice") or (args.confirm_formal and args.mode != "formal"):
        parser.error("Confirmation must match the session mode. No request sent.")
    if args.mode not in ("practice", "formal") and (args.base_url or args.robot_id):
        parser.error("--base-url and --robot-id are official-session-only. No request sent.")
    if args.method not in SPECS[args.problem]:
        parser.error("Methods: " + ", ".join(SPECS[args.problem]))
    spec = SPECS[args.problem][args.method]
    paths = load_paths(args.problem)
    if args.mode != "offline":
        from bounded_http import run_http
        run_http(args, build, spec, paths, PROGRAM_STARTED)
        return
    # Offline deliberately retains the peer backend. Equal seeds across the
    # two modes do not mean equal source fixtures or equal virtual-time scores.
    from peer_benchmark import PeerTransport,ErrorConfig,ErrorField,ScenarioConfig,generate,Simulator,Limits,Protocol
    scenario=generate(args.seed,ScenarioConfig(directional_fraction=.5 if args.problem==4 else 0.))
    error=ErrorConfig()
    sim=Simulator(scenario,ErrorField(args.seed,error),Limits(countdown_s=0))
    initialized=time.perf_counter()
    policy=build(Client(PeerTransport(Protocol(sim)),robot_id="mock-robot"),spec,args.problem,paths)
    # wall_s/cpu_s cover policy.run only, excluding imports, paths and initialization.
    initialization=time.perf_counter()-initialized
    began=time.perf_counter()
    cpu=time.process_time()
    stats=policy.run()
    result=dict(mode="offline_peer_only",series=args.series,problem=args.problem,method=args.method,seed=args.seed,
        all_cleared=len(sim.cleared)==len(scenario.sources),cleared=len(sim.cleared),source_count_scoring_only=len(scenario.sources),
        total_virtual_s=sim.virtual_time_s,per_source_s=sim.virtual_time_s/len(sim.cleared) if sim.cleared else None,
        commands=len(sim.trace),wall_s=time.perf_counter()-began,cpu_s=time.process_time()-cpu,initialization_s=initialization,
        official_calls=0,**trace_metrics(sim.trace),**stats)
    dest=ROOT/"robot_runs"/(datetime.now().strftime("%Y%m%d-%H%M%S-%f")+"-bounded-offline")
    dest.mkdir(parents=True)
    (dest/"summary.json").write_text(json.dumps(result,indent=2))
    (dest/"scoring_only.json").write_text(json.dumps(dict(scenario=scenario.to_dict(),error=asdict(error)),indent=2))
    with gzip.open(dest/"trace.jsonl.gz","wt") as stream:
        for entry in sim.trace:
            stream.write(json.dumps(entry)+"\n")
    print(json.dumps(result,ensure_ascii=False,indent=2))
    print(dest)


if __name__=="__main__":
    main()
