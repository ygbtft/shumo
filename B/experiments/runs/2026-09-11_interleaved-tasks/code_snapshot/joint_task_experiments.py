"""Frozen paired training of joint scan/clear task routing on the peer protocol."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from client import Client
from joint_task_policy import JointTaskPolicy
from peer_benchmark import PeerTransport,Simulator,ErrorField,Limits,Protocol
from layout_alternative_experiments import training_cases
from metaheuristic_experiments import write_json
import spatial_decision_experiments as engine

ROOT=Path(__file__).resolve().parent
OUT=ROOT/"experiments/runs/2026-09-11_joint-task-routing"
SPECS={3:{
    "baseline_peer9":dict(kind="base",layout="ring9"),
    "baseline_co_known9":dict(kind="coop",layout="ring9",share_known=True,discover_gain=None,prune=False),
    "task_nearest9":dict(kind="task",layout="ring9",task_order="nearest"),
    "task_two_opt9":dict(kind="task",layout="ring9"),
    "task_no_share9":dict(kind="task",layout="ring9",share=False),
    "task_weight05_9":dict(kind="task",layout="ring9",localization_weight=.5),
    "task_weight1_9":dict(kind="task",layout="ring9",localization_weight=1.),
    "task_trial40_9":dict(kind="task",layout="ring9",trial_radius=40.),
    "task_two_opt7":dict(kind="task",layout="ring7"),
},4:{
    "baseline_polar25_conservative":dict(kind="base",layout="polar25",active=False),
    "baseline_bracket25":dict(kind="bracket",layout="polar25",trial_radius=40.),
    "task_nearest25":dict(kind="task",layout="polar25",task_order="nearest",trial_radius=40.),
    "task_two_opt25":dict(kind="task",layout="polar25",trial_radius=40.),
    "task_no_share25":dict(kind="task",layout="polar25",share=False,trial_radius=40.),
    "task_trial80_25":dict(kind="task",layout="polar25",trial_radius=80.),
    "task_share3_25":dict(kind="task",layout="polar25",share_limit=3,trial_radius=40.),
}}
_prior_build=engine.build
_prior_freeze=engine.freeze


def build(client,spec,problem,paths):
    if spec["kind"]!="task":return _prior_build(client,spec,problem,paths)
    params=spec.copy();params.pop("kind");points=paths[params.pop("layout")]
    return JointTaskPolicy(client,points,mixed=problem==4,**params)


def freeze(paths):
    _prior_freeze(paths)
    config=json.loads((OUT/"run_config.json").read_text())
    for name in ("joint_task_experiments.py","joint_task_policy.py"):
        raw=(ROOT/name).read_bytes();(OUT/"code_snapshot"/name).write_bytes(raw)
        config["code_sha256"][name]=hashlib.sha256(raw).hexdigest()
    config["engine_reuse"]="spatial_decision_experiments.run with explicit OUT/SPECS/build/freeze replacement in joint_task_experiments.py; original files unchanged"
    write_json(OUT/"run_config.json",config)
    checks=json.loads((OUT/"checks.json").read_text())
    (OUT/"precheck.md").write_text(f"# 运行前检查\n\n{checks['passed']}项新联合调度完整协议检查通过；每个实例全清且无空区域/错误成对裁剪。先前成对探测1050组合与覆盖证书沿用已冻结验证。\n\n16候选×93已查看训练场景=1488次。只经公共Client反馈，真值只由评分器读取。种子42派生67—71及旧压力集，77—86仍未使用。单线程CPU，正式请求0。\n")


def check():
    checks=[];paths=engine.all_layouts()
    for problem,names in {3:("task_nearest9","task_two_opt9","task_weight1_9"),
                          4:("task_nearest25","task_two_opt25","task_no_share25")}.items():
        chosen=[c for c in training_cases(problem) if c[2]=="stress" and c[0].endswith(("n16__negative","n10__spatial"))]
        for case_id,category,split,scenario,error in chosen:
            for name in names:
                sim=Simulator(scenario,ErrorField(scenario.seed,error),Limits(countdown_s=0))
                policy=build(Client(PeerTransport(Protocol(sim)),robot_id="mock-robot"),SPECS[problem][name],problem,paths)
                stats=policy.run()
                assert len(sim.cleared)==len(scenario.sources),(problem,name,case_id)
                assert not stats.get("bracket_cut_inconsistencies",0) and not stats.get("inconsistent_updates",0)
                assert stats["shared_known_measurements"]<=16*22*6
                checks.append(dict(test=f"q{problem}_{name}_{case_id}",passed=True,virtual_s=sim.virtual_time_s,commands=len(sim.trace)))
    write_json(OUT/"checks.json",dict(passed=len(checks),failed=0,checks=checks,scored_execution_count=0))
    print("Passed",len(checks),"full protocol checks",flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--check",action="store_true");p.add_argument("--launch",action="store_true");args=p.parse_args()
    OUT.mkdir(parents=True,exist_ok=True)
    engine.OUT,engine.SPECS,engine.build,engine.freeze=OUT,SPECS,build,freeze
    if args.check:check();return
    if args.launch:
        if (OUT/"run_config.json").exists():raise RuntimeError("Preserving completed run")
        env=os.environ.copy();env.update(PYTHONDONTWRITEBYTECODE="1",OPENBLAS_NUM_THREADS="1",OMP_NUM_THREADS="1",MPLCONFIGDIR=str(ROOT/".mplconfig"),XDG_CACHE_HOME=str(ROOT/".cache"))
        with (OUT/"log.txt").open("a") as f:
            proc=subprocess.Popen([sys.executable,"-B",str(Path(__file__).resolve())],cwd=ROOT.parent,env=env,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
        (OUT/"background.pid").write_text(str(proc.pid)+"\n");print("Background PID",proc.pid)
    else:engine.run()


if __name__=="__main__":main()
