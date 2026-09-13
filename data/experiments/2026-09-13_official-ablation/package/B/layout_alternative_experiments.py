"""Offline full-policy evaluation of certified alternative Q3/Q4 layouts."""
import argparse
from dataclasses import asdict
import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback
import numpy as np
from client import Client
from policies import Policy
from peer_benchmark import PeerTransport, ErrorConfig, ErrorField, ScenarioConfig, generate, mandatory_conditions, Simulator, Limits, Protocol
from ring_experiments import cases as ring_cases
from metaheuristic_experiments import cases as older_cases, trace_metrics, write_json, write_csv
from ring_coverage import stations

ROOT=Path(__file__).resolve().parent
OUT=ROOT/"experiments/runs/2026-09-11_layout-alternatives"


def layouts():
    candidates=json.loads((OUT/"certified_layouts.json").read_text())
    old=json.loads((ROOT/"experiments/runs/2026-09-10_metaheuristics/selected_routes.json").read_text())
    q3={"baseline_peer9_active":(stations(8,1300.),True)}
    q4={"baseline_triangle31_active":(np.array(old["q4_triangle"]["fireworks"]["points"]),True),
        "baseline_square45_conservative":(np.array(old["square700"]["two_opt"]["points"]),False)}
    for name,item in candidates.items():
        assert item["certificate"]["covered"]
        if name.startswith("q3"):
            q3[name+"_active"]=(np.array(item["route"]),True)
        else:
            # The initial identifier 'polar38' was an arithmetic naming typo;
            # there are 1+6+12+18 = 37 actual points. Preserve frozen input.
            name=name.replace("polar38","polar37")
            for active in (False,True):q4[name+("_active" if active else "_conservative")]=(np.array(item["route"]),active)
    return {3:q3,4:q4}


def training_cases(problem):
    if problem==3:
        for item in ring_cases():
            if item[2]=="stress" or item[3].seed<=71:yield item
    else:
        for label,scfg,ecfg in mandatory_conditions(ScenarioConfig(directional_fraction=.5),ErrorConfig()):
            for seed in range(67,72):yield f"{label}__{seed}",label,"ordinary",generate(seed,scfg),ecfg
        for item in older_cases(True):
            if item[2]=="stress":yield item


def run():
    selected=layouts();config_path=OUT/"evaluation_config.json"
    if config_path.exists():raise RuntimeError("Existing evaluation preserved")
    (OUT/"evaluation_code_snapshot").mkdir();hashes={}
    for name in ("layout_alternative_experiments.py","layout_certificates.py","policies.py","geometry.py","intelligent.py","client.py","coverage.py","peer_benchmark.py","ring_experiments.py","metaheuristic_experiments.py","route_algorithms.py","adaptive_routes.py"):
        raw=(ROOT/name).read_bytes();(OUT/"evaluation_code_snapshot"/name).write_bytes(raw);hashes[name]=hashlib.sha256(raw).hexdigest()
    write_json(config_path,{"base_seed":42,"training_seeds":list(range(67,72)),"derivation":"42+25+repeat,0..4; exploratory use, not post-selection holdout",
        "q3_stress_rng":"SeedSequence([42,35,layout_index,count]); shared with ring/joint studies",
        "q4_stress_rng":"SeedSequence([42,20,layout_index,count]); shared with older mixed stress study",
        "specs":{str(task):{name:{"points":p.tolist(),"active":active} for name,(p,active) in methods.items()} for task,methods in selected.items()},
        "expected_executions":sum(len(v) for v in selected.values())*93,"source_counts_to_policy":False,"official_calls":0,
        "peer_commit":"c477d3660368f27c7131a0591426b4c4f107ea5d","code_sha256":hashes,"python":sys.executable,
        "label_correction":"Frozen layout id q4_polar38 has 37 points, relabeled q4_polar37 during evaluation; coordinates unchanged."})
    (OUT/"traces").mkdir();(OUT/"scenarios_scoring_only").mkdir();began=time.perf_counter();rows=[]
    with (OUT/"trials.jsonl").open("x") as stream:
        for problem,methods in selected.items():
            for ci,(case_id,category,split,scenario,error) in enumerate(training_cases(problem)):
                case=f"q{problem}__{case_id}"
                write_json(OUT/"scenarios_scoring_only"/f"{case}.json",{"scenario":scenario.to_dict(),"error":asdict(error)})
                for method,(points,active) in methods.items():
                    sim=Simulator(scenario,ErrorField(scenario.seed,error),Limits(countdown_s=0))
                    policy=Policy(Client(PeerTransport(Protocol(sim)),robot_id="mock-robot"),points,mixed=problem==4,active=active,optimized=True)
                    start=time.perf_counter();cpu=time.process_time();stats={};failure=""
                    try:stats=policy.run()
                    except Exception as exc:
                        failure=repr(exc);(OUT/"traces"/f"{case}__{method}.error.txt").write_text(traceback.format_exc())
                    row={"problem":problem,"case_id":case_id,"category":category,"split":split,"seed":scenario.seed,"method":method,
                         "sources":len(scenario.sources),"cleared":len(sim.cleared),"all_cleared":len(sim.cleared)==len(scenario.sources),
                         "total_virtual_s":sim.virtual_time_s,"per_source_s":sim.virtual_time_s/len(sim.cleared) if sim.cleared else None,
                         "commands":len(sim.trace),"wall_s":time.perf_counter()-start,"cpu_s":time.process_time()-cpu,"failure":failure,
                         "missed_channels":sorted(set(sim.sources)-sim.cleared),**trace_metrics(sim.trace),**stats}
                    rows.append(row);stream.write(json.dumps(row,allow_nan=False)+"\n");stream.flush()
                    with gzip.open(OUT/"traces"/f"{case}__{method}.jsonl.gz","wt") as f:
                        for entry in sim.trace:f.write(json.dumps(entry,separators=(",",":"))+"\n")
                    if failure or not row["all_cleared"]:print("FAIL",problem,method,case_id,failure,row["missed_channels"],flush=True)
                if (ci+1)%5==0 or split=="stress":print(f"Q{problem} {ci+1}/93, {len(rows)} executions, {time.perf_counter()-began:.1f}s",flush=True)
    write_csv(OUT/"trials.csv",rows)
    write_json(OUT/"completion.json",{"executions":len(rows),"all_cleared":sum(r["all_cleared"] for r in rows),"errors":sum(bool(r["failure"]) for r in rows),"wall_s":time.perf_counter()-began})
    summary=[]
    for problem,methods in selected.items():
        for split in ("ordinary","stress"):
            for method in methods:
                group=[r for r in rows if r["problem"]==problem and r["method"]==method and r["split"]==split]
                total=np.array([r["total_virtual_s"] for r in group])
                summary.append({"problem":problem,"split":split,"method":method,"runs":len(group),"all_cleared":sum(r["all_cleared"] for r in group),
                    "mean_total_s":total.mean(),"mean_per_source_s":np.mean([r["per_source_s"] or 0 for r in group]),"max_total_s":total.max(),"p95_total_s":np.quantile(total,.95),
                    "mean_commands":np.mean([r["commands"] for r in group]),"mean_wall_s":np.mean([r["wall_s"] for r in group]),"max_wall_s":max(r["wall_s"] for r in group)})
    write_csv(OUT/"summary.csv",summary);write_json(OUT/"failures.json",[r for r in rows if not r["all_cleared"] or r["failure"]])
    lines=["# 非单环布局全流程训练比较","","Q3/Q4分别评价，训练场景不作为未查看确认集。", "", "|问题|场景|布局/策略|全清|平均每源秒|平均总秒|最慢总秒|平均指令|平均/最大墙钟秒|", "|---|---|---|---:|---:|---:|---:|---:|---:|"]
    for s in summary:lines.append(f"|Q{s['problem']}|{s['split']}|{s['method']}|{s['all_cleared']}/{s['runs']}|{s['mean_per_source_s']:.2f}|{s['mean_total_s']:.2f}|{s['max_total_s']:.2f}|{s['mean_commands']:.2f}|{s['mean_wall_s']:.3f}/{s['max_wall_s']:.3f}|")
    (OUT/"summary.md").write_text("\n".join(lines)+"\n")
    print("Completed",len(rows),"executions",flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--launch",action="store_true");args=parser.parse_args()
    if args.launch:
        if (OUT/"evaluation_config.json").exists():raise RuntimeError("Existing evaluation preserved")
        env=os.environ.copy();env.update(PYTHONDONTWRITEBYTECODE="1",OPENBLAS_NUM_THREADS="1",OMP_NUM_THREADS="1",MPLCONFIGDIR=str(ROOT/".mplconfig"),XDG_CACHE_HOME=str(ROOT/".cache"))
        with (OUT/"log.txt").open("a") as f:
            p=subprocess.Popen([sys.executable,"-B",str(Path(__file__).resolve())],cwd=ROOT.parent,env=env,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
        (OUT/"background.pid").write_text(str(p.pid)+"\n");print("Background PID",p.pid)
    else:run()


if __name__=="__main__":main()
