"""Paired tests of cooperative information gathering and bounded forward probes."""
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
from policies import Policy
from cooperative_policy import CooperativePolicy
from bracket_policy import BracketPolicy,CooperativeBracketPolicy
from layout_certificates import critical_cover_radius,omni_certificate
from layout_alternative_experiments import training_cases
from ring_coverage import stations,covering_radius
from peer_benchmark import PeerTransport,ErrorConfig,ErrorField,Simulator,Limits,Protocol
from mock.scenario_gen import Source
from mock.geometry import covered
from metaheuristic_experiments import write_json,write_csv,trace_metrics

ROOT=Path(__file__).resolve().parent
OUT=ROOT/"experiments/runs/2026-09-11_spatial-decisions"
SPECS={3:{
    "baseline_peer9":dict(kind="base",layout="ring9"),
    "co_known9":dict(kind="coop",layout="ring9",share_known=True,discover_gain=None,prune=False),
    "co_discover3_9":dict(kind="coop",layout="ring9",share_known=True,discover_gain=.03,prune=False),
    "co_prune3_9":dict(kind="coop",layout="ring9",share_known=True,discover_gain=.03,prune=True),
    "co_prune8_9":dict(kind="coop",layout="ring9",share_known=True,discover_gain=.08,prune=True),
    "co_prune3_tsp9":dict(kind="coop",layout="ring9",share_known=True,discover_gain=.03,prune=True,source_order="two_opt"),
    "co_prune3_uncertainty9":dict(kind="coop",layout="ring9",share_known=True,discover_gain=.03,prune=True,source_order="uncertainty"),
    "co_prune3_7":dict(kind="coop",layout="ring7",share_known=True,discover_gain=.03,prune=True),
    "bracket9":dict(kind="bracket",layout="ring9",dynamic=False,trial_radius=40.),
    "bracket_dynamic9":dict(kind="bracket",layout="ring9",dynamic=True,trial_radius=40.),
    "co_bracket3_9":dict(kind="coop_bracket",layout="ring9",share_known=True,discover_gain=.03,prune=True),
    "co_bracket3_tsp9":dict(kind="coop_bracket",layout="ring9",share_known=True,discover_gain=.03,prune=True,source_order="two_opt"),
},4:{
    "baseline_polar25_conservative":dict(kind="base",layout="polar25",active=False),
    "baseline_polar25_active":dict(kind="base",layout="polar25",active=True),
    "bracket_polar25":dict(kind="bracket",layout="polar25",dynamic=False,trial_radius=40.),
    "bracket_dynamic25":dict(kind="bracket",layout="polar25",dynamic=True,trial_radius=40.),
    "bracket_trial80_25":dict(kind="bracket",layout="polar25",dynamic=True,trial_radius=80.),
    "bracket_polar28":dict(kind="bracket",layout="polar28",dynamic=True,trial_radius=40.),
    "bracket_polar37":dict(kind="bracket",layout="polar37",dynamic=True,trial_radius=40.),
}}


def all_layouts():
    old=json.loads((ROOT/"experiments/runs/2026-09-11_layout-alternatives/certified_layouts.json").read_text())
    return {"ring9":stations(8,1300.),"ring7":stations(6,1140.),
            **{f"polar{n}":np.array(old[f"q4_polar{38 if n==37 else n}"]["route"]) for n in (25,28,37)}}


def build(client,spec,problem,paths):
    params=spec.copy();kind=params.pop("kind");points=paths[params.pop("layout")]
    if kind=="base":return Policy(client,points,mixed=problem==4,active=params.pop("active",True),optimized=True)
    if kind=="bracket":return BracketPolicy(client,points,mixed=problem==4,**params)
    assert problem==3
    cls=CooperativeBracketPolicy if kind=="coop_bracket" else CooperativePolicy
    return cls(client,points,sensing="cov_mean",trial_radius=80.,**params)


def check():
    checks=[];rng=np.random.default_rng(42)
    angles=np.arange(720)*2*math.pi/720
    test_grid=(1800*np.sqrt(np.linspace(0,1,31))[:,None,None]*np.column_stack((np.cos(angles),np.sin(angles)))[None,:,:]).reshape(-1,2)
    point_sets=[np.array([[0.,0.]]),np.array([[-1000.,0.],[1000.,0.]]),np.array([[-1000.,0.],[0.,0.],[1000.,0.]]),stations(8,1300.),stations(6,1140.)]
    point_sets += [rng.normal(0,1400,size=(n,2)) for n in range(3,20)]
    for i,p in enumerate(point_sets):
        exact=critical_cover_radius(p);outer=omni_certificate(p)["radius_upper_m"]
        sampled=float(np.linalg.norm(test_grid[:,None,:]-p[None,:,:],axis=2).min(axis=1).max())
        assert sampled<=exact+1e-5,(i,sampled,exact)
        assert exact<=outer+2e-4,(i,exact,outer)
        checks.append({"test":f"continuous_critical_cover_vs_independent_outer_cells_{i}","passed":True,"critical_m":exact,"outer_m":outer,"sampled_m":sampled})
    assert abs(critical_cover_radius(stations(8,1300.))-covering_radius(8,1300.))<2e-4
    # Test the new implication against both direct halfplane algebra and the
    # unchanged peer visibility implementation, including angular boundaries.
    t=math.tan(math.radians(1.02));instances=0
    for distance in (6.,30.,100.,500.,1000.,1500.):
        for delta_deg in (-1.005,-.5,0.,.5,1.005):
            delta=math.radians(delta_deg);g=distance*np.array([math.cos(delta),math.sin(delta)])
            for ratio in (.01,.25,.5,.9,.999999):
                length=ratio*g[0];probes=[np.array([length,t*length]),np.array([length,-t*length])]
                assert all(np.linalg.norm(q-g)<=distance+1e-7 for q in probes)
                toward_s=math.degrees(math.atan2(-g[1],-g[0]))
                for offset in (-90.,-89.99,-60.,0.,60.,89.99,90.):
                    direction=(toward_s+offset)%360
                    source=Source(1,float(g[0]),float(g[1]),max(1000.,distance),direction)
                    assert covered(source,(0.,0.))
                    assert any(covered(source,tuple(q)) for q in probes),(distance,delta_deg,ratio,offset)
                    instances+=1
    checks.append({"test":"paired_forward_probe_implication_range_and_all_face_boundaries","passed":True,"instances":instances})
    paths=all_layouts()
    tests={3:("co_prune3_9","co_bracket3_9","bracket_dynamic9"),4:("bracket_polar25","bracket_dynamic25","bracket_trial80_25")}
    for problem,methods in tests.items():
        chosen=[item for item in training_cases(problem) if item[2]=="stress" and item[0].endswith(("n16__negative","n10__spatial"))]
        for case_id,category,split,scenario,error in chosen:
            for method in methods:
                sim=Simulator(scenario,ErrorField(scenario.seed,error),Limits(countdown_s=0))
                policy=build(Client(PeerTransport(Protocol(sim)),robot_id="mock-robot"),SPECS[problem][method],problem,paths)
                stats=policy.run()
                assert len(sim.cleared)==len(scenario.sources),(problem,method,case_id)
                assert not stats.get("bracket_cut_inconsistencies",0)
                checks.append({"test":f"full_protocol_all_clear_q{problem}_{method}_{case_id}","passed":True,"total_virtual_s":sim.virtual_time_s,"commands":len(sim.trace),"cuts":stats.get("bracket_pair_cuts",0)})
    write_json(OUT/"checks.json",{"passed":len(checks),"failed":0,"checks":checks,"scored_execution_count":0})
    print("Passed",len(checks),"checks",flush=True)


def freeze(paths):
    if (OUT/"run_config.json").exists():raise RuntimeError("Existing run preserved")
    checked=json.loads((OUT/"checks.json").read_text());assert checked["failed"]==0
    (OUT/"code_snapshot").mkdir();hashes={}
    names=("spatial_decision_experiments.py","cooperative_policy.py","bracket_policy.py","joint_policy.py","layout_certificates.py","layout_alternative_experiments.py","ring_coverage.py","geometry.py","policies.py","client.py","intelligent.py","adaptive_routes.py","coverage.py","ring_experiments.py","peer_benchmark.py","metaheuristic_experiments.py","route_algorithms.py")
    for name in names:
        raw=(ROOT/name).read_bytes();(OUT/"code_snapshot"/name).write_bytes(raw);hashes[name]=hashlib.sha256(raw).hexdigest()
    write_json(OUT/"run_config.json",{"base_seed":42,"training_seeds":list(range(67,72)),"derivation":"42+25+repeat,0..4; already-used training scenes; holdout77..86 untouched",
        "stress_derivation":"Q3 SeedSequence([42,35,layout_index,count]); Q4 [42,20,layout_index,count]; errors42+200+index/Q3,42+100+index/Q4",
        "specs":SPECS,"paths":{name:p.tolist() for name,p in paths.items()},"expected_executions":sum(len(v) for v in SPECS.values())*93,
        "bracket_steps":10,"probe_half_angle_deg":1.02,"geometry_error_halfwidth_deg":1.01,
        "selection":"full clearance first; separate mean/p95/max total, per-source, commands and real time; retain all failure and regression cases",
        "peer_commit":"c477d3660368f27c7131a0591426b4c4f107ea5d","official_calls":0,"truth_to_policy":False,"python":sys.executable,"code_sha256":hashes})
    (OUT/"precheck.md").write_text(f"# 运行前检查\n\n{checked['passed']}项检查通过：连续覆盖临界点算法与独立外包Voronoi核对，1050个成对前向探测的半径/方向边界组合通过未改动后端，完整协议压力案例全清。\n\n19候选、每候选93训练场景，共1767次；配置先冻结，后台单线程CPU，seed42派生。正式请求0。所有源真值仅用于后端/评分，动态覆盖只读取已执行的公共坐标。\n")


def run():
    paths=all_layouts();freeze(paths);rows=[];began=time.perf_counter()
    (OUT/"traces").mkdir();(OUT/"scenarios_scoring_only").mkdir()
    with (OUT/"trials.jsonl").open("x") as stream:
        for problem,methods in SPECS.items():
            for ci,(case_id,category,split,scenario,error) in enumerate(training_cases(problem)):
                case=f"q{problem}__{case_id}";write_json(OUT/"scenarios_scoring_only"/f"{case}.json",{"scenario":scenario.to_dict(),"error":asdict(error)})
                for method,spec in methods.items():
                    sim=Simulator(scenario,ErrorField(scenario.seed,error),Limits(countdown_s=0))
                    policy=build(Client(PeerTransport(Protocol(sim)),robot_id="mock-robot"),spec,problem,paths)
                    start=time.perf_counter();cpu=time.process_time();failure="";stats={}
                    try:stats=policy.run()
                    except Exception as exc:
                        failure=repr(exc);(OUT/"traces"/f"{case}__{method}.error.txt").write_text(traceback.format_exc())
                    row={"problem":problem,"method":method,"case_id":case_id,"category":category,"split":split,"seed":scenario.seed,
                        "sources":len(scenario.sources),"cleared":len(sim.cleared),"all_cleared":len(sim.cleared)==len(scenario.sources),
                        "total_virtual_s":sim.virtual_time_s,"per_source_s":sim.virtual_time_s/len(sim.cleared) if sim.cleared else None,
                        "commands":len(sim.trace),"wall_s":time.perf_counter()-start,"cpu_s":time.process_time()-cpu,"failure":failure,"missed_channels":sorted(set(sim.sources)-sim.cleared),
                        **trace_metrics(sim.trace),**stats}
                    rows.append(row);stream.write(json.dumps(row,allow_nan=False)+"\n");stream.flush()
                    with gzip.open(OUT/"traces"/f"{case}__{method}.jsonl.gz","wt") as f:
                        for entry in sim.trace:f.write(json.dumps(entry,separators=(",",":"))+"\n")
                    if failure or not row["all_cleared"]:print("FAIL",problem,method,case_id,failure,row["missed_channels"],flush=True)
                if (ci+1)%5==0 or split=="stress":print(f"Q{problem} {ci+1}/93, {len(rows)} executions, {time.perf_counter()-began:.1f}s",flush=True)
    write_csv(OUT/"trials.csv",rows)
    write_json(OUT/"completion.json",{"executions":len(rows),"all_cleared":sum(r["all_cleared"] for r in rows),"errors":sum(bool(r["failure"]) for r in rows),"wall_s":time.perf_counter()-began})
    summary=[];regressions=[]
    for problem,methods in SPECS.items():
        baseline_name=next(iter(methods))
        for split in ("ordinary","stress"):
            baseline={r["case_id"]:r for r in rows if r["problem"]==problem and r["method"]==baseline_name and r["split"]==split}
            for method in methods:
                group=[r for r in rows if r["problem"]==problem and r["method"]==method and r["split"]==split];times=np.array([r["total_virtual_s"] for r in group])
                summary.append({"problem":problem,"split":split,"method":method,"runs":len(group),"all_cleared":sum(r["all_cleared"] for r in group),"errors":sum(bool(r["failure"]) for r in group),
                    "mean_total_s":times.mean(),"mean_per_source_s":np.mean([r["per_source_s"] or 0 for r in group]),"p95_total_s":np.quantile(times,.95),"max_total_s":times.max(),
                    "mean_commands":np.mean([r["commands"] for r in group]),"mean_wall_s":np.mean([r["wall_s"] for r in group]),"max_wall_s":max(r["wall_s"] for r in group),
                    "mean_pair_cuts":np.mean([r.get("bracket_pair_cuts",0) for r in group]),"mean_optical_fallbacks":np.mean([r.get("optical_fallback_calls",0) for r in group]),
                    "slower_cases":sum(r["total_virtual_s"]>baseline[r["case_id"]]["total_virtual_s"]+1e-6 for r in group)})
                for r in group:
                    if r["total_virtual_s"]>baseline[r["case_id"]]["total_virtual_s"]+1e-6:regressions.append({"problem":problem,"method":method,"case_id":r["case_id"],"split":split,"delta_s":r["total_virtual_s"]-baseline[r["case_id"]]["total_virtual_s"]})
    write_csv(OUT/"summary.csv",summary);write_json(OUT/"regressions.json",sorted(regressions,key=lambda r:r["delta_s"],reverse=True));write_json(OUT/"failures.json",[r for r in rows if r["failure"] or not r["all_cleared"]])
    lines=["# 共享测向与成对前向探测：训练比较","","新候选使用已看过训练场景，不能代替冻结后的确认。", "", "|问题|场景|策略|全清|平均每源秒|平均总秒|最慢总秒|平均指令|平均/最大墙钟秒|成对无信号约束/局|光学兜底/局|", "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for s in summary:lines.append(f"|Q{s['problem']}|{s['split']}|{s['method']}|{s['all_cleared']}/{s['runs']}|{s['mean_per_source_s']:.2f}|{s['mean_total_s']:.2f}|{s['max_total_s']:.2f}|{s['mean_commands']:.2f}|{s['mean_wall_s']:.4f}/{s['max_wall_s']:.4f}|{s['mean_pair_cuts']:.2f}|{s['mean_optical_fallbacks']:.2f}|")
    (OUT/"summary.md").write_text("\n".join(lines)+"\n")
    print("Completed",len(rows),"executions",flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--check",action="store_true");p.add_argument("--launch",action="store_true");args=p.parse_args()
    OUT.mkdir(parents=True,exist_ok=True)
    if args.check:check();return
    if args.launch:
        if (OUT/"run_config.json").exists():raise RuntimeError("Existing run preserved")
        env=os.environ.copy();env.update(PYTHONDONTWRITEBYTECODE="1",OPENBLAS_NUM_THREADS="1",OMP_NUM_THREADS="1",MPLCONFIGDIR=str(ROOT/".mplconfig"),XDG_CACHE_HOME=str(ROOT/".cache"))
        with (OUT/"log.txt").open("a") as f:proc=subprocess.Popen([sys.executable,"-B",str(Path(__file__).resolve())],cwd=ROOT.parent,env=env,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
        (OUT/"background.pid").write_text(str(proc.pid)+"\n");print("Background PID",proc.pid)
    else:run()


if __name__=="__main__":main()
