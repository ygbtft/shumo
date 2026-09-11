"""Frozen joint-policy ablations, paired offline training and honest tail metrics."""
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
from adaptive_routes import AdaptivePolicy
from joint_policy import JointPolicy, choose_covariance
from intelligent import guaranteed_omni
from geometry import update_region
from ring_coverage import stations
from ring_experiments import cases
from peer_benchmark import PeerTransport, ErrorConfig, ErrorField, ScenarioConfig, generate, Simulator, Limits, Protocol
from metaheuristic_experiments import trace_metrics, write_json, write_csv

ROOT=Path(__file__).resolve().parent
OUT=ROOT/"experiments/runs/2026-09-11_joint-search"
SPECS={
    "baseline_peer9":dict(kind="base",ring=(8,1300.)),
    "baseline_ring7":dict(kind="base",ring=(6,1140.)),
    "dynamic_greedy9":dict(kind="adaptive",ring=(8,1300.),polish=False),
    "dynamic_two_opt9":dict(kind="adaptive",ring=(8,1300.),polish=True),
    "deferred9":dict(kind="joint",ring=(8,1300.),mode="deferred"),
    "opportunistic200_9":dict(kind="joint",ring=(8,1300.),mode="opportunistic",detour_limit=200.),
    "opportunistic600_9":dict(kind="joint",ring=(8,1300.),mode="opportunistic",detour_limit=600.),
    "trial80_9":dict(kind="joint",ring=(8,1300.),trial_radius=80.),
    "cov_mean9":dict(kind="joint",ring=(8,1300.),sensing="cov_mean"),
    "cov_trial80_9":dict(kind="joint",ring=(8,1300.),sensing="cov_mean",trial_radius=80.),
    "cov_robust80_9":dict(kind="joint",ring=(8,1300.),sensing="cov_robust",trial_radius=80.),
    "cov_dynamic80_9":dict(kind="joint",ring=(8,1300.),sensing="cov_mean",trial_radius=80.,order="two_opt"),
    "cov_opportunistic80_9":dict(kind="joint",ring=(8,1300.),mode="opportunistic",sensing="cov_mean",trial_radius=80.,detour_limit=200.),
    "cov_deferred80_9":dict(kind="joint",ring=(8,1300.),mode="deferred",sensing="cov_mean",trial_radius=80.),
    "cov_trial80_7":dict(kind="joint",ring=(6,1140.),sensing="cov_mean",trial_radius=80.),
    "cov_robust80_7":dict(kind="joint",ring=(6,1140.),sensing="cov_robust",trial_radius=80.),
}


def build(client,spec):
    params=spec.copy();kind=params.pop("kind");points=stations(*params.pop("ring"))
    if kind=="base":return Policy(client,points,mixed=False,active=True,optimized=True)
    if kind=="adaptive":return AdaptivePolicy(client,points,mixed=False,active=True,optimized=True,**params)
    return JointPolicy(client,points,**params)


def training_cases():
    for item in cases():
        if item[2]=="stress" or item[3].seed<=71:yield item


def check():
    checks=[]
    # Identity ablation replays the original complete action stream, feedback
    # only: schedule refactor preserves behavior when every option is disabled.
    path=ROOT/"experiments/runs/2026-09-11_peer-paper-review/ring_traces/uniform__iid__67__peer_ring9_r1300.jsonl.gz"
    with gzip.open(path,"rt") as f:trace=[json.loads(line) for line in f]
    index=0
    def replay(endpoint,raw):
        nonlocal index
        e=trace[index];assert endpoint==e["path"] and json.loads(raw)==e["request"],index
        index+=1;return 200,e["response"]
    JointPolicy(Client(replay,robot_id="mock-robot"),stations(8,1300.),skip_precise=False).run()
    assert index==len(trace);checks.append({"test":"identity_refactor_exact_feedback_replay","passed":True,"commands":index})
    rng=np.random.default_rng(42)
    for angle in (0.,30.,90.,359.99):
        p=np.array([0.,0.]);poly=update_region(None,p,angle)
        for robust in (False,True):
            q=choose_covariance(poly,[(p,angle)],p,robust)
            assert guaranteed_omni(q,poly,p)
            checks.append({"test":f"fast_sensing_universal_omni_certificate_{angle}_{robust}","passed":True})
    selected=[item for item in training_cases() if item[0] in ("boundary_min__n16__negative","unknown_count_late__n10__spatial")]
    for method in ("deferred9","opportunistic200_9","trial80_9","cov_robust80_9","cov_dynamic80_9","cov_opportunistic80_9"):
        for case_id,category,split,scenario,error in selected:
            sim=Simulator(scenario,ErrorField(scenario.seed,error),Limits(countdown_s=0))
            stats=build(Client(PeerTransport(Protocol(sim)),robot_id="mock-robot"),SPECS[method]).run()
            assert len(sim.cleared)==len(scenario.sources)
            assert stats["stop_reason"] in ("public_upper_bound_16","full_coverage_and_all_discovered_cleared")
            checks.append({"test":f"feedback_contract_all_clear_stop_{method}_{case_id}","passed":True,"commands":len(sim.trace)})
    write_json(OUT/"checks.json",{"passed":len(checks),"failed":0,"checks":checks,"scored_execution_count":0})
    print("Passed",len(checks),"checks")


def freeze():
    if (OUT/"run_config.json").exists():raise RuntimeError("Existing run preserved")
    checked=json.loads((OUT/"checks.json").read_text());assert checked["failed"]==0
    (OUT/"code_snapshot").mkdir();hashes={}
    for name in ("joint_policy.py","joint_experiments.py","ring_coverage.py","policies.py","geometry.py","client.py","intelligent.py","adaptive_routes.py","coverage.py","peer_benchmark.py","ring_experiments.py","metaheuristic_experiments.py","route_algorithms.py"):
        raw=(ROOT/name).read_bytes();(OUT/"code_snapshot"/name).write_bytes(raw);hashes[name]=hashlib.sha256(raw).hexdigest()
    write_json(OUT/"run_config.json",{"base_seed":42,"training_seeds":list(range(67,72)),"derivation":"42+25+repeat, repeat=0..4; reused exploratory scenes, not held-out",
               "stress_rng":"SeedSequence([42,35,layout_index,count]); error seed 42+200+case_index; already seen in layout review",
               "specs":SPECS,"executions_expected":93*len(SPECS),"peer_commit":"c477d3660368f27c7131a0591426b4c4f107ea5d",
               "selection_rule":"require all-clear; inspect separate ordinary/stress mean total/per-source, p95/max total, commands and CPU/wall; retain tradeoffs, do not substitute weighted average",
               "holdout_plan":"Freeze selected candidates then evaluate new generator seeds77..86 and fresh adversarial layouts; do not evaluate them during tuning",
               "paper_original_code_available":False,"baseline_scope":"Peer paper center/ring layout + our robust active policy, stronger reproducible proxy, not exact paper implementation",
               "covariance_assumption":"vertex covariance + linearized independent angular variance, used only to rank next points; exact containing set and certificates remain in control",
               "code_sha256":hashes,"official_calls":0,"hidden_state_to_policy":False,"python":sys.executable,"cpu_threads":1})
    (OUT/"precheck.md").write_text(f"# 运行前检查\n\n{checked['passed']}项检查通过，包括旧反馈轨迹逐条重放、快速选点保收证书、未知数量/边界/端点误差的清除与结束。\n\n16候选事先冻结，93个配对训练场景；seed42派生；单线程CPU；命令已保存，长任务后台执行。全部进程内调用同学Protocol.handle，正式请求0。复用训练场景明示，确认集尚未查看。\n")


def evaluate():
    freeze();rows=[];began=time.perf_counter()
    (OUT/"traces").mkdir();(OUT/"scenarios_scoring_only").mkdir()
    with (OUT/"trials.jsonl").open("x") as stream:
        for ci,(case_id,category,split,scenario,error) in enumerate(training_cases()):
            write_json(OUT/"scenarios_scoring_only"/f"{case_id}.json",{"scenario":scenario.to_dict(),"error":asdict(error)})
            for method,spec in SPECS.items():
                sim=Simulator(scenario,ErrorField(scenario.seed,error),Limits(countdown_s=0))
                policy=build(Client(PeerTransport(Protocol(sim)),robot_id="mock-robot"),spec)
                start=time.perf_counter();cpu=time.process_time();failure="";stats={}
                try:stats=policy.run()
                except Exception as exc:
                    failure=repr(exc);(OUT/"traces"/f"{case_id}__{method}.error.txt").write_text(traceback.format_exc())
                row={"case_id":case_id,"category":category,"split":split,"seed":scenario.seed,"method":method,
                     "sources":len(scenario.sources),"cleared":len(sim.cleared),"all_cleared":len(sim.cleared)==len(scenario.sources),
                     "total_virtual_s":sim.virtual_time_s,"per_source_s":sim.virtual_time_s/len(sim.cleared) if sim.cleared else None,
                     "commands":len(sim.trace),"wall_s":time.perf_counter()-start,"cpu_s":time.process_time()-cpu,
                     "failure":failure,"missed_channels":sorted(set(sim.sources)-sim.cleared),**trace_metrics(sim.trace),**stats}
                rows.append(row);stream.write(json.dumps(row,allow_nan=False)+"\n");stream.flush()
                with gzip.open(OUT/"traces"/f"{case_id}__{method}.jsonl.gz","wt") as f:
                    for entry in sim.trace:f.write(json.dumps(entry,separators=(",",":"))+"\n")
                if failure or not row["all_cleared"]:print("FAIL",case_id,method,failure,row["missed_channels"],flush=True)
            if (ci+1)%5==0 or split=="stress":print(f"{ci+1}/93 cases, {len(rows)} executions, {time.perf_counter()-began:.1f}s",flush=True)
    write_csv(OUT/"trials.csv",rows)
    write_json(OUT/"completion.json",{"executions":len(rows),"all_cleared":sum(r["all_cleared"] for r in rows),"errors":sum(bool(r["failure"]) for r in rows),"wall_s":time.perf_counter()-began})
    summarize()


def summarize():
    completion=json.loads((OUT/"completion.json").read_text())
    rows=[json.loads(line) for line in (OUT/"trials.jsonl").read_text().splitlines()];summary=[];regressions=[]
    for split in ("ordinary","stress"):
        baseline={r["case_id"]:r for r in rows if r["split"]==split and r["method"]=="baseline_peer9"}
        for method in SPECS:
            group=[r for r in rows if r["split"]==split and r["method"]==method]
            times=[r["total_virtual_s"] for r in group]
            record={"split":split,"method":method,"runs":len(group),"all_cleared":sum(r["all_cleared"] for r in group),
                    "mean_total_s":np.mean(times),"mean_per_source_s":np.mean([r["per_source_s"] or 0 for r in group]),"max_total_s":max(times),"p95_total_s":np.quantile(times,.95),
                    "mean_commands":np.mean([r["commands"] for r in group]),"mean_wall_s":np.mean([r["wall_s"] for r in group]),"max_wall_s":max(r["wall_s"] for r in group),
                    "mean_cpu_s":np.mean([r["cpu_s"] for r in group]),"slower_cases":sum(r["total_virtual_s"]>baseline[r["case_id"]]["total_virtual_s"]+1e-6 for r in group),
                    "largest_slowdown_s":max(0,max(r["total_virtual_s"]-baseline[r["case_id"]]["total_virtual_s"] for r in group))}
            summary.append(record)
            for r in group:
                if r["total_virtual_s"]>baseline[r["case_id"]]["total_virtual_s"]+1e-6:
                    regressions.append({"case_id":r["case_id"],"method":method,"split":split,"delta_s":r["total_virtual_s"]-baseline[r["case_id"]]["total_virtual_s"]})
    write_csv(OUT/"summary.csv",summary);write_json(OUT/"regressions.json",sorted(regressions,key=lambda r:r["delta_s"],reverse=True))
    write_json(OUT/"failures.json",[r for r in rows if not r["all_cleared"] or r["failure"]])
    lines=["# 联合策略训练比较", "", "这里是重复使用探索场景的训练消融，尚不是独立确认。", "", "|场景|策略|全清|平均总秒|平均每源秒|最慢总秒|平均指令|平均/最大墙钟秒|慢于基线局数|", "|---|---|---:|---:|---:|---:|---:|---:|---:|"]
    for s in summary:lines.append(f"|{s['split']}|{s['method']}|{s['all_cleared']}/{s['runs']}|{s['mean_total_s']:.2f}|{s['mean_per_source_s']:.2f}|{s['max_total_s']:.2f}|{s['mean_commands']:.2f}|{s['mean_wall_s']:.4f}/{s['max_wall_s']:.4f}|{s['slower_cases']}|")
    lines += ["",json.dumps(completion),"", "所有指标分别检查；失败和逐局回退另存。基线不是缺失的论文完整源码，是其环形布点加我们的稳健策略。"]
    (OUT/"summary.md").write_text("\n".join(lines)+"\n")
    print(json.dumps(completion),flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--check",action="store_true");p.add_argument("--launch",action="store_true");p.add_argument("--summarize",action="store_true");p.add_argument("--output")
    args=p.parse_args();global OUT
    if args.output:
        OUT=Path(args.output).resolve()
        if not OUT.is_relative_to(ROOT):p.error("B/ writes only")
    OUT.mkdir(parents=True,exist_ok=True)
    if args.check:check();return
    if args.summarize:summarize();return
    if args.launch:
        if (OUT/"run_config.json").exists():raise RuntimeError("Existing run preserved")
        env=os.environ.copy();env.update(PYTHONDONTWRITEBYTECODE="1",OPENBLAS_NUM_THREADS="1",OMP_NUM_THREADS="1",MPLCONFIGDIR=str(ROOT/".mplconfig"),XDG_CACHE_HOME=str(ROOT/".cache"))
        with (OUT/"log.txt").open("a") as f:
            proc=subprocess.Popen([sys.executable,"-B",str(Path(__file__).resolve()),"--output",str(OUT)],cwd=ROOT.parent,env=env,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
        (OUT/"background.pid").write_text(str(proc.pid)+"\n");print("Background PID",proc.pid)
    else:evaluate()


if __name__=="__main__":main()
