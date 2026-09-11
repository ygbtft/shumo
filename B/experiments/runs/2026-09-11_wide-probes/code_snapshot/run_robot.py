"""Offline demo by default; practice HTTP only with explicit local session declaration."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import sys
import numpy as np
from client import Client,HttpTransport
from policies import Policy

ROOT=Path(__file__).resolve().parent


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode",choices=["offline","practice"],default="offline")
    parser.add_argument("--problem",type=int,choices=[3,4],default=4)
    parser.add_argument("--strategy",choices=["square_greedy","square_cropped_2opt","triangle_2opt","triangle_genetic","active_2opt","active_genetic"],default="square_cropped_2opt")
    parser.add_argument("--seed",type=int,default=42)
    parser.add_argument("--base-url",default="http://127.0.0.1:2026")
    parser.add_argument("--robot-id")
    parser.add_argument("--confirm-practice",action="store_true",help="Human declaration that an official PRACTICE session is ready; cannot query mode over the API")
    args=parser.parse_args()
    packed=ROOT/"routes.json"
    if not packed.exists():
        packed=ROOT/"experiments/runs/2026-09-10_independent/routes.json"
    paths=json.loads(packed.read_text())
    name=args.strategy if args.strategy.startswith("square") else f"q{args.problem}_triangle_{'genetic' if 'genetic' in args.strategy else '2opt'}"
    if args.mode=="practice" and (not args.confirm_practice or not args.robot_id):
        parser.error("Practice needs --confirm-practice and --robot-id after the user manually opens a PRACTICE session. No request sent.")
    folder=ROOT/"robot_runs"/(datetime.now().strftime("%Y%m%d-%H%M%S-%f")+"-"+args.mode)
    folder.mkdir(parents=True)
    (folder/"config.json").write_text(json.dumps(vars(args),ensure_ascii=False,indent=2))
    world=None
    if args.mode=="offline":
        from simulator import World,Source,Protocol
        rng=np.random.default_rng(args.seed)
        sources=[]
        n=int(rng.integers(10,17))
        for ch in rng.choice(np.arange(1,21),n,replace=False):
            r=1800*np.sqrt(rng.random()); a=rng.uniform(0,2*np.pi)
            sources.append(Source(int(ch),float(r*np.cos(a)),float(r*np.sin(a)),float(rng.uniform(1000,1500)),
                                  float(rng.uniform(0,2*np.pi)) if args.problem==4 and rng.random()<.5 else None))
        world=World(sources,args.seed)
        transport=Protocol(world).dispatch
        identity="offline-robot"
    else:
        transport=HttpTransport(args.base_url)
        identity=args.robot_id
    # Flush every complete response; official simulator's own encrypted logs are separate.
    class Journal:
        def append(self,row):
            with (folder/"requests.jsonl").open("a",encoding="utf-8") as f:
                f.write(json.dumps(row,ensure_ascii=False,separators=(",",":"))+"\n")
    cli=Client(transport,robot_id=identity,transcript=Journal())
    policy=Policy(cli,np.asarray(paths[name]),mixed=args.problem==4,active=args.strategy.startswith("active"),optimized=args.strategy!="square_greedy")
    try:
        stats=policy.run()
        summary={"mode":args.mode,"virtual_s":cli.virtual_s,"policy":stats,"source_truth":world.score() if world else None}
        (folder/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2))
        print(json.dumps(summary,ensure_ascii=False,indent=2))
    except Exception as exc:
        (folder/"failure.txt").write_text(repr(exc))
        raise
    finally:
        print(f"Local logs: {folder}")


if __name__=="__main__":
    main()
