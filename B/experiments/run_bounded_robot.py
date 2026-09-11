"""Historical experiment CLI; the delivery entry is ../run_bounded_robot.py."""
import time
PROGRAM_STARTED = time.perf_counter()
import argparse
from dataclasses import asdict
from datetime import datetime
import gzip
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from client import Client
from peer_benchmark import PeerTransport,ErrorConfig,ErrorField,ScenarioConfig,generate,Simulator,Limits,Protocol
from metaheuristic_experiments import trace_metrics
from icra_confirmation import SPECS,all_paths
from replacement_experiments import build

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--problem",type=int,choices=(3,4),required=True)
    parser.add_argument("--method",required=True)
    parser.add_argument("--seed",type=int,default=42)
    parser.add_argument("--series",choices=("icra","mission","task","wide","coupled","history","deferred","cover21"),default="icra")
    parser.add_argument("--mode", choices=("mock-http", "offline", "practice"), default="mock-http")
    parser.add_argument("--base-url", help="Practice HTTP endpoint only; mock-http always owns its random loopback port")
    parser.add_argument("--robot-id")
    parser.add_argument("--confirm-practice", action="store_true", help="User has manually logged in and opened a PRACTICE session")
    args=parser.parse_args()
    if args.mode == "practice" and (not args.confirm_practice or not args.robot_id):
        parser.error("Practice needs --confirm-practice and --robot-id after manual login. No request sent.")
    if args.mode != "practice" and (args.base_url or args.robot_id or args.confirm_practice):
        parser.error("--base-url, --robot-id and --confirm-practice are practice-only. No request sent.")
    selected_specs,load_paths,factory=SPECS,all_paths,build
    if args.series=="mission":
        from mission_confirmation import SPECS as mission_specs,all_paths as mission_paths
        from clearance_experiments import build as mission_build
        selected_specs,load_paths,factory=mission_specs,mission_paths,mission_build
    elif args.series=="task":
        from task_confirmation_v2 import SPECS as task_specs,all_paths as task_paths,build as task_build
        selected_specs,load_paths,factory=task_specs,task_paths,task_build
    elif args.series=="wide":
        from wide_confirmation import SPECS as wide_specs,all_paths as wide_paths,build as wide_build
        selected_specs,load_paths,factory=wide_specs,wide_paths,wide_build
    elif args.series=="coupled":
        from coupled_confirmation import SPECS as coupled_specs,all_paths as coupled_paths,build as coupled_build
        selected_specs,load_paths,factory=coupled_specs,coupled_paths,coupled_build
    elif args.series=="history":
        from history_confirmation import SPECS as history_specs,all_paths as history_paths,build as history_build
        selected_specs,load_paths,factory=history_specs,history_paths,history_build
    elif args.series=="deferred":
        from deferred_confirmation import SPECS as deferred_specs,all_paths as deferred_paths,build as deferred_build
        selected_specs,load_paths,factory=deferred_specs,deferred_paths,deferred_build
    elif args.series=="cover21":
        from cover21_confirmation import SPECS as cover21_specs,all_paths as cover21_paths,build as cover21_build
        selected_specs,load_paths,factory=cover21_specs,cover21_paths,cover21_build
    if args.method not in selected_specs[args.problem]:parser.error("Methods: "+", ".join(selected_specs[args.problem]))
    paths=load_paths()
    if args.mode != "offline":
        from bounded_http import run_http
        run_http(args, factory, selected_specs[args.problem][args.method], paths, PROGRAM_STARTED)
        return
    scenario=generate(args.seed,ScenarioConfig(directional_fraction=.5 if args.problem==4 else 0.));error=ErrorConfig()
    sim=Simulator(scenario,ErrorField(args.seed,error),Limits(countdown_s=0))
    initialized=time.perf_counter();policy=factory(Client(PeerTransport(Protocol(sim)),robot_id="mock-robot"),selected_specs[args.problem][args.method],args.problem,paths)
    initialization=time.perf_counter()-initialized;began=time.perf_counter();cpu=time.process_time();stats=policy.run()
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
        for entry in sim.trace:stream.write(json.dumps(entry)+"\n")
    print(json.dumps(result,ensure_ascii=False,indent=2));print(dest)


if __name__=="__main__":main()
