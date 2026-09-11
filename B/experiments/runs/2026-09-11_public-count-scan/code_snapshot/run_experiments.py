"""Frozen CPU benchmark; all artifacts stay below B/. No network access."""
import csv
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import sys
import time
import traceback
import numpy as np
import scipy
from client import Client
from coverage import route, route_length, square_stations, triangle_stations
from intelligent import genetic_route
from policies import Policy
from simulator import Source, World, Protocol, serialize_sources

ROOT=Path(__file__).resolve().parent
OUT=ROOT/"experiments/runs/2026-09-10_independent"
SPECS={"random":20,"outward_boundary":6,"minimum_radius":7,"near_collinear":6,
       "worst_plus":3,"worst_minus":3,"worst_alternating":3,"smooth_noise":3,
       "truncated_bearing":3,"unknown_count":7}
STRATEGIES=["square_greedy","square_cropped_2opt","triangle_2opt","triangle_genetic",
            "active_2opt","active_genetic"]


def log(message):
    print(time.strftime("%H:%M:%S"),message,flush=True)


def make_scenarios():
    cases=[]
    index=0
    for mixed in [False,True]:
        for category,count in SPECS.items():
            for j in range(count):
                seq=np.random.SeedSequence([42,1,index])
                rng=np.random.default_rng(seq)
                n=10+j if category=="unknown_count" else int(rng.integers(10,17))
                channels=rng.choice(np.arange(1,21),n,replace=False)
                angles=rng.uniform(0,2*math.pi,n)
                radii=1800*np.sqrt(rng.random(n))
                if category=="outward_boundary":
                    radii[:]=1800
                    angles=(np.arange(n)/n+j/37)*2*math.pi
                points=radii[:,None]*np.column_stack([np.cos(angles),np.sin(angles)])
                if category=="near_collinear":
                    axis=np.array([math.cos(j*.31),math.sin(j*.31)])
                    normal=np.array([-axis[1],axis[0]])
                    points=np.linspace(-1750,1750,n)[:,None]*axis+rng.uniform(-.1,.1,n)[:,None]*normal
                reception=rng.uniform(1000,1500,n)
                if category in ("minimum_radius","outward_boundary","worst_plus","worst_minus","worst_alternating"):
                    reception[:]=1000
                directed=rng.random(n)<.5 if mixed else np.zeros(n,bool)
                facing=rng.uniform(0,2*math.pi,n)
                if category=="outward_boundary" and mixed:
                    directed[:]=True; facing=angles.copy()
                if category=="unknown_count":
                    # Channel 20 is late/remote; the policy is not given n or this construction.
                    channels=np.array(list(range(1,n))+[20])
                    points[-1]=[1800.,0.]
                    reception[-1]=1000.
                    directed[-1]=mixed
                    facing[-1]=0.
                sources=[Source(int(ch),float(pt[0]),float(pt[1]),float(rr),float(fa) if dd else None)
                         for ch,pt,rr,dd,fa in zip(channels,points,reception,directed,facing)]
                mode={"worst_plus":"plus","worst_minus":"minus","worst_alternating":"alternating","smooth_noise":"smooth"}.get(category,"hash")
                noise_seed=int(seq.generate_state(1)[0])
                cases.append({"case_id":f"q{4 if mixed else 3}_{category}_{j:02d}","split_id":1,
                              "case_index":index,"mixed":mixed,"category":category,"noise":mode,
                              "rounding":"truncate" if category=="truncated_bearing" else "nearest",
                              "seed_sequence":[42,1,index],"noise_seed":noise_seed,
                              "sources":serialize_sources(sources)})
                index+=1
    return cases


def prepare_routes():
    packed={}
    metrics=[]
    histories={}
    configs=[("square_greedy",square_stations(650),False),
             ("square_cropped_2opt",square_stations(700,True),True),
             ("q3_triangle_2opt",triangle_stations(1700),True),
             ("q4_triangle_2opt",triangle_stations(990),True)]
    for name,points,opt in configs:
        p=route(points,opt)
        packed[name]=p.tolist()
        metrics.append({"route":name,"stations":len(p),"length_m":route_length(p),"precompute_wall_s":0.})
        if "triangle" in name:
            ga,meta=genetic_route(points)
            gn=name.replace("2opt","genetic")
            packed[gn]=ga.tolist()
            histories[gn]=meta
            metrics.append({"route":gn,"stations":len(ga),"length_m":route_length(ga),"precompute_wall_s":meta["wall_s"]})
            log(f"route {gn}: {len(ga)} stations, {meta['initial_2opt_m']:.1f} -> {meta['best_m']:.1f} m, GA {meta['wall_s']:.2f}s")
    (OUT/"routes.json").write_text(json.dumps(packed,indent=2))
    (OUT/"genetic_history.json").write_text(json.dumps(histories,indent=2))
    write_csv(OUT/"routes.csv",metrics)
    return packed


def write_csv(path,rows):
    if not rows:
        return
    with path.open("w",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)


def main():
    start=time.perf_counter()
    OUT.mkdir(parents=True,exist_ok=True)
    if (OUT/"trials.jsonl").exists():
        raise RuntimeError("Existing main run preserved; choose a new run directory before rerunning")
    for name in ["traces","code_snapshot"]:
        (OUT/name).mkdir(exist_ok=True)
    checks=json.loads((OUT/"checks.json").read_text())
    assert all(c["passed"] for c in checks["checks"])
    code_hashes={}
    for path in sorted(ROOT.glob("*.py")):
        raw=path.read_bytes()
        (OUT/"code_snapshot"/path.name).write_bytes(raw)
        code_hashes[path.name]=hashlib.sha256(raw).hexdigest()
    source_hashes=json.loads((ROOT/"inputs_readonly_extract/input_sha256.json").read_text())
    legacy=ROOT.parent/"project/topic_probes/b_probe.py"
    source_hashes[str(legacy.relative_to(ROOT.parent))]=hashlib.sha256(legacy.read_bytes()).hexdigest()
    config={"seed":42,"seed_derivation":"SeedSequence([42, 1, case_index]); state[0] is fixed spatial noise seed",
            "split_id":1,"specs":SPECS,"strategies":STRATEGIES,"active_max_measurements":3,
            "active_time_weight":.08,"bearing_bound_deg":1.01,"optical_grid_step_m":28.,
            "q3_triangle_side_m":1700.,"q4_triangle_side_m":990.,
            "genetic":{"seed":42,"population":96,"generations":180,"elite":8,"mutation_probability":.35},
            "python_executable":sys.executable,"python":sys.version,"numpy":np.__version__,"scipy":scipy.__version__,
            "platform":platform.platform(),"cpu":platform.machine(),"pid":os.getpid(),
            "input_sha256":source_hashes,"code_sha256":code_hashes,
            "official_requests":0,"truth_access":"Only generator/World/scorer; policy receives Client and public Q3/Q4 flag"}
    (OUT/"run_config.json").write_text(json.dumps(config,ensure_ascii=False,indent=2))
    scenarios=make_scenarios()
    (OUT/"scenarios_scoring_only.json").write_text(json.dumps(scenarios,indent=2))
    paths=prepare_routes()
    rows=[]
    jsonl=(OUT/"trials.jsonl").open("a")
    log(f"Frozen benchmark: {len(scenarios)} cases x {len(STRATEGIES)} strategies")
    for index,case in enumerate(scenarios):
        for strategy in STRATEGIES:
            if strategy.startswith("square"):
                name=strategy
            else:
                name=f"q{4 if case['mixed'] else 3}_triangle_{'genetic' if 'genetic' in strategy else '2opt'}"
            points=np.array(paths[name])
            world=World([Source(**s) for s in case["sources"]],case["noise_seed"],case["noise"],case["rounding"])
            transcript=[]
            cli=Client(Protocol(world).dispatch,transcript=transcript)
            policy=Policy(cli,points,mixed=case["mixed"],active=strategy.startswith("active"),optimized=strategy!="square_greedy")
            began=time.perf_counter(); cpu=time.process_time()
            failure=""
            try:
                extra=policy.run()
            except Exception as exc:
                failure=repr(exc)
                extra=policy.stats.copy()
                (OUT/"traces"/f"{case['case_id']}__{strategy}.error.txt").write_text(traceback.format_exc())
            wall=time.perf_counter()-began; cpu=time.process_time()-cpu
            row={"case_id":case["case_id"],"category":case["category"],"mixed":case["mixed"],"strategy":strategy,
                 "noise":case["noise"],"rounding":case["rounding"],**world.score(),
                 "wall_s":wall,"cpu_s":cpu,"failure":failure,**extra}
            rows.append(row)
            jsonl.write(json.dumps(row)+"\n"); jsonl.flush()
            with gzip.open(OUT/"traces"/f"{case['case_id']}__{strategy}.jsonl.gz","wt") as f:
                for entry in transcript:
                    f.write(json.dumps(entry,separators=(",",":"))+"\n")
            if failure or not row["all_cleared"]:
                log(f"FAIL {case['case_id']} {strategy}: {failure or row['missed_channels']}")
        if (index+1)%5==0 or index+1==len(scenarios):
            log(f"Completed {index+1}/{len(scenarios)} cases; {len(rows)} executions; wall {time.perf_counter()-start:.1f}s")
    jsonl.close()
    fields=sorted(set().union(*(set(row) for row in rows)))
    with (OUT/"trials.csv").open("w",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=fields); writer.writeheader(); writer.writerows(rows)
    completion={"executions":len(rows),"cases":len(scenarios),"wall_s":time.perf_counter()-start,
                "all_cleared_runs":sum(row["all_cleared"] for row in rows),"exceptions":sum(bool(row["failure"]) for row in rows)}
    (OUT/"completion.json").write_text(json.dumps(completion,indent=2))
    log(json.dumps(completion))


if __name__=="__main__":
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",help="A fresh run directory under B/; preserves existing results")
    args=parser.parse_args()
    if args.output:
        previous_checks=OUT/"checks.json"
        selected=Path(args.output).resolve()
        if not selected.is_relative_to(ROOT):
            parser.error("Output must stay below B/")
        selected.mkdir(parents=True,exist_ok=True)
        if not (selected/"checks.json").exists():
            (selected/"checks.json").write_bytes(previous_checks.read_bytes())
        OUT=selected
    main()
