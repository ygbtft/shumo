"""Untouched-seed confirmation of frozen bounded-uncertainty mission policies."""
import argparse
from dataclasses import asdict
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback
import numpy as np
from client import Client
from peer_benchmark import PeerTransport,ErrorConfig,ErrorField,ScenarioConfig,generate,mandatory_conditions,Simulator,Limits,Protocol
from mock.scenario_gen import Scenario,Source
from metaheuristic_experiments import write_json,write_csv,trace_metrics
import replacement_experiments as builders

ROOT=Path(__file__).resolve().parent
OUT=ROOT/"experiments/runs/2026-09-11_icra-confirmation"
SPECS={3:{
    "peer_layout9_proxy":dict(kind="base",layout="ring9"),
    "shared9":dict(kind="coop",layout="ring9",share_known=True,discover_gain=None,prune=False),
    "joint7":dict(kind="task",layout="ring7"),
    "joint9":dict(kind="task",layout="ring9"),
},4:{
    "square45_conservative":dict(kind="base",layout="square45",active=False),
    "polar25_conservative":dict(kind="base",layout="polar25",active=False),
    "bracket25":dict(kind="bracket",layout="polar25",trial_radius=40.),
    "joint25":dict(kind="task",layout="polar25",trial_radius=40.),
    "joint22":dict(kind="task",layout="convex22",trial_radius=40.),
    "replacement22":dict(kind="replace",layout="convex22",trial_radius=40.),
}}


def all_paths():
    result=builders.paths()
    old=json.loads((ROOT/"experiments/runs/2026-09-10_metaheuristics/selected_routes.json").read_text())
    result["square45"]=np.array(old["square700"]["two_opt"]["points"])
    return result


def cases(problem):
    cfg=ScenarioConfig(directional_fraction=.5 if problem==4 else 0.)
    for label,scfg,ecfg in mandatory_conditions(cfg,ErrorConfig()):
        for seed in range(77,87):yield f"{label}__{seed}",label,"ordinary",generate(seed,scfg),ecfg
    index=0
    for li,layout in enumerate(("boundary_outward","boundary_tangent","near_collinear","cluster_far20","range_transition")):
        for count in (10,13,16):
            rng=np.random.default_rng(np.random.SeedSequence([42,113,problem,li,count]))
            channels=list(rng.choice(np.arange(1,20),count-1,replace=False))+[20]
            phase=rng.uniform(0,2*math.pi);angles=np.arange(count)*2*math.pi/count+phase
            if layout.startswith("boundary"):
                points=1800*np.column_stack([np.cos(angles),np.sin(angles)])
            elif layout=="near_collinear":
                angle=.853219;axis=np.array([math.cos(angle),math.sin(angle)]);v=np.array([-axis[1],axis[0]])
                points=np.linspace(-1790,1790,count)[:,None]*axis+rng.uniform(-.001,.001,count)[:,None]*v
            elif layout=="cluster_far20":
                points=rng.normal(0,120,(count,2));points[-1]=1800*np.array([math.cos(phase),math.sin(phase)])
            else:
                radius=np.linspace(850,1500,count)
                points=radius[:,None]*np.column_stack([np.cos(angles),np.sin(angles)])
            sources=[]
            for i,(ch,g) in enumerate(zip(channels,points)):
                direction=None
                if problem==4 and i>0:
                    direction=math.degrees(math.atan2(g[1],g[0]))
                    if layout=="boundary_tangent":direction+=90. if i%2 else -90.
                    elif layout=="range_transition":direction+=89.999 if i%2 else -89.999
                    direction%=360
                radius=1500. if layout=="range_transition" and i%3==0 else 1000.
                sources.append(Source(int(ch),float(g[0]),float(g[1]),radius,direction))
            for sign in ("positive","negative","spatial"):
                seed=42+1100+100*problem+index;index+=1
                scenario=Scenario(seed,tuple(sources),dict(stress_layout=layout,source_rng=[42,113,problem,li,count]))
                yield f"{layout}__n{count}__{sign}",layout,"stress",scenario,ErrorConfig(model="adversarial",adversarial_sign=sign)


def freeze(paths):
    if (OUT/"run_config.json").exists():raise RuntimeError("Confirmation already frozen; preserving data")
    snapshot=OUT/"code_snapshot";snapshot.mkdir();hashes={}
    for p in ROOT.glob("*.py"):
        raw=p.read_bytes();(snapshot/p.name).write_bytes(raw);hashes[p.name]=hashlib.sha256(raw).hexdigest()
    write_json(OUT/"run_config.json",dict(base_seed=42,confirmation_seeds=list(range(77,87)),
        derivation="42+35+repeat,repeat0..9; not used in prior runs",stress_derivation="SeedSequence([42,113,problem,layout_index,count]), errors42+1100+100*problem+index",
        specs=SPECS,paths={k:v.tolist() for k,v in paths.items()},expected_executions=1950,
        ordinary_cases_per_problem=150,stress_cases_per_problem=45,code_sha256=hashes,
        freeze_before_truth_generation=True,official_calls=0,truth_to_policy=False,cpu_threads=1,python=sys.executable,
        wall_clock_scope="policy.run including client/backend; initialization measured separately; imports, scenario generation, logging excluded",
        peer_commit="c477d3660368f27c7131a0591426b4c4f107ea5d"))
    for name,certificate in builders.CERTIFICATES.items():write_json(OUT/f"certificate_{name}.json",certificate)
    (OUT/"precheck.md").write_text("# 确认前冻结\n\n上轮36完整协议/动态覆盖检查通过，之前59成对几何及共享检查、36联合调度检查通过。此处先写代码快照/参数/证书，再生成77—86和新的压力真值。1950次执行无调参回路。官方请求0。\n")


def summarize(rows):
    summary=[];regressions=[]
    for problem,methods in SPECS.items():
        baseline=next(iter(methods))
        for split in ("ordinary","stress"):
            baseline_rows={r["case_id"]:r for r in rows if r["problem"]==problem and r["method"]==baseline and r["split"]==split}
            for method in methods:
                group=[r for r in rows if r["problem"]==problem and r["method"]==method and r["split"]==split]
                times=np.array([r["total_virtual_s"] for r in group]);delta=np.array([r["total_virtual_s"]-baseline_rows[r["case_id"]]["total_virtual_s"] for r in group])
                summary.append(dict(problem=problem,split=split,method=method,runs=len(group),all_cleared=sum(r["all_cleared"] for r in group),
                    mean_total_s=times.mean(),mean_per_source_s=np.mean([r["per_source_s"] for r in group]),pooled_per_source_s=times.sum()/sum(r["cleared"] for r in group),
                    p95_total_s=np.quantile(times,.95),max_total_s=times.max(),mean_commands=np.mean([r["commands"] for r in group]),
                    mean_wall_s=np.mean([r["wall_s"] for r in group]),max_wall_s=max(r["wall_s"] for r in group),
                    mean_init_s=np.mean([r["initialization_s"] for r in group]),mean_cpu_s=np.mean([r["cpu_s"] for r in group]),
                    faster_cases=int((delta<-1e-6).sum()),slower_cases=int((delta>1e-6).sum()),worst_regression_s=delta.max()))
                regressions.extend(dict(problem=problem,split=split,method=method,case_id=r["case_id"],delta_s=float(d)) for r,d in zip(group,delta) if d>1e-6)
    write_csv(OUT/"summary.csv",summary);write_json(OUT/"regressions.json",sorted(regressions,key=lambda r:r["delta_s"],reverse=True))
    write_json(OUT/"failures.json",[r for r in rows if not r["all_cleared"] or r["failure"]])
    lines=["# 冻结后确认：未用于调参的场景","","普通150、压力45场景/问题，seed42派生77—86及新压力流。基线分别为Q3论文布局代理、Q4旧方格保守；不是官方成绩。", "", "|问题|场景|策略|全清|平均每源秒|源数加权每源秒|平均总秒|P95/最大总秒|平均指令|平均/最大策略墙钟秒|平均初始化秒|更快/更慢局数|", "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for s in summary:lines.append(f"|Q{s['problem']}|{s['split']}|{s['method']}|{s['all_cleared']}/{s['runs']}|{s['mean_per_source_s']:.2f}|{s['pooled_per_source_s']:.2f}|{s['mean_total_s']:.2f}|{s['p95_total_s']:.2f}/{s['max_total_s']:.2f}|{s['mean_commands']:.2f}|{s['mean_wall_s']:.4f}/{s['max_wall_s']:.4f}|{s['mean_init_s']:.4f}|{s['faster_cases']}/{s['slower_cases']}|")
    (OUT/"summary.md").write_text("\n".join(lines)+"\n")


def run():
    paths=all_paths();freeze(paths);began=time.perf_counter();rows=[]
    (OUT/"traces").mkdir();(OUT/"scenarios_scoring_only").mkdir()
    with (OUT/"trials.jsonl").open("x") as stream:
        for problem,methods in SPECS.items():
            for ci,(case_id,category,split,scenario,error) in enumerate(cases(problem)):
                case=f"q{problem}__{case_id}";write_json(OUT/"scenarios_scoring_only"/f"{case}.json",dict(scenario=scenario.to_dict(),error=asdict(error)))
                for method,spec in methods.items():
                    sim=Simulator(scenario,ErrorField(scenario.seed,error),Limits(countdown_s=0))
                    init=time.perf_counter();policy=builders.build(Client(PeerTransport(Protocol(sim)),robot_id="mock-robot"),spec,problem,paths);initialization=time.perf_counter()-init
                    start=time.perf_counter();cpu=time.process_time();failure="";stats={}
                    try:stats=policy.run()
                    except Exception as exc:
                        failure=repr(exc);(OUT/"traces"/f"{case}__{method}.error.txt").write_text(traceback.format_exc())
                    row=dict(problem=problem,method=method,case_id=case_id,category=category,split=split,seed=scenario.seed,
                        sources=len(scenario.sources),cleared=len(sim.cleared),all_cleared=len(sim.cleared)==len(scenario.sources),
                        total_virtual_s=sim.virtual_time_s,per_source_s=sim.virtual_time_s/len(sim.cleared) if sim.cleared else None,
                        commands=len(sim.trace),wall_s=time.perf_counter()-start,cpu_s=time.process_time()-cpu,initialization_s=initialization,
                        failure=failure,missed_channels=sorted(set(sim.sources)-sim.cleared),**trace_metrics(sim.trace),**stats)
                    rows.append(row);stream.write(json.dumps(row,allow_nan=False)+"\n");stream.flush()
                    with gzip.open(OUT/"traces"/f"{case}__{method}.jsonl.gz","wt") as f:
                        for entry in sim.trace:f.write(json.dumps(entry,separators=(",",":"))+"\n")
                    if failure or not row["all_cleared"]:print("FAIL",problem,method,case_id,failure,row["missed_channels"],flush=True)
                if (ci+1)%10==0 or split=="stress":print(f"Q{problem} {ci+1}/195, {len(rows)} executions, {time.perf_counter()-began:.1f}s",flush=True)
    write_csv(OUT/"trials.csv",rows);summarize(rows)
    write_json(OUT/"completion.json",dict(executions=len(rows),all_cleared=sum(r["all_cleared"] for r in rows),errors=sum(bool(r["failure"]) for r in rows),wall_s=time.perf_counter()-began))
    print("Completed",len(rows),"executions",flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--launch",action="store_true");args=p.parse_args()
    OUT.mkdir(parents=True,exist_ok=True)
    if args.launch:
        if (OUT/"run_config.json").exists():raise RuntimeError("Preserving confirmation")
        env=os.environ.copy();env.update(PYTHONDONTWRITEBYTECODE="1",OPENBLAS_NUM_THREADS="1",OMP_NUM_THREADS="1",MPLCONFIGDIR=str(ROOT/".mplconfig"),XDG_CACHE_HOME=str(ROOT/".cache"))
        with (OUT/"log.txt").open("a") as f:
            proc=subprocess.Popen([sys.executable,"-B",str(Path(__file__).resolve())],cwd=ROOT.parent,env=env,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
        (OUT/"background.pid").write_text(str(proc.pid)+"\n");print("Background PID",proc.pid)
    else:run()


if __name__=="__main__":main()
