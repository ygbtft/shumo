"""Paired training of count stopping, asymmetric probes and boundary priority."""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import numpy as np
from client import Client
from efficient_joint_policy import EfficientJointPolicy,ProbeJointPolicy
from joint_task_policy import JointTaskPolicy
from peer_benchmark import PeerTransport,Simulator,ErrorField,Limits,Protocol
from layout_alternative_experiments import training_cases
from metaheuristic_experiments import write_json
import replacement_experiments as builders
import spatial_decision_experiments as engine

ROOT=Path(__file__).resolve().parent
OUT=ROOT/"experiments/runs/2026-09-11_asymmetric-probes"
OLD=ROOT/"experiments/runs/2026-09-11_icra-confirmation"
SPECS={3:{
    "joint7":dict(kind="task",layout="ring7"),
    "fast7":dict(kind="efficient",layout="ring7"),
    "fast9":dict(kind="efficient",layout="ring9"),
},4:{
    "joint22":dict(kind="task",layout="convex22",trial_radius=40.),
    "fast22":dict(kind="efficient",layout="convex22",trial_radius=40.),
    "probe05_22":dict(kind="probe",layout="convex22"),
    "first025_22":dict(kind="probe",layout="convex22",fraction=.25,first_only=True),
    "quarter22":dict(kind="probe",layout="convex22",fraction=.25),
    "third22":dict(kind="probe",layout="convex22",fraction=.35),
    "march150_22":dict(kind="probe",layout="convex22",march=150.),
    "march300_22":dict(kind="probe",layout="convex22",march=300.),
    "cooldown150_22":dict(kind="probe",layout="convex22",share_cooldown=150.),
    "first025_cd22":dict(kind="probe",layout="convex22",fraction=.25,first_only=True,share_cooldown=150.),
    "quarter_cd22":dict(kind="probe",layout="convex22",fraction=.25,share_cooldown=150.),
    "quarter_prediction22":dict(kind="probe",layout="convex22",fraction=.25,share_cooldown=150.,task_prediction="probe"),
    "outer05_22":dict(kind="probe",layout="convex22",scan_stage="outer"),
    "outer_first025_22":dict(kind="probe",layout="convex22",fraction=.25,first_only=True,share_cooldown=150.,scan_stage="outer"),
    "sparse_first025_22":dict(kind="probe",layout="convex22",fraction=.25,first_only=True,share_cooldown=150.,scan_stage="outer_if_sparse"),
    "outer_first025_25":dict(kind="probe",layout="polar25",fraction=.25,first_only=True,share_cooldown=150.,scan_stage="outer"),
    "first025_cd25":dict(kind="probe",layout="polar25",fraction=.25,first_only=True,share_cooldown=150.),
}}
_prior_freeze=engine.freeze


def paths():return builders.paths()


def build(client,spec,problem,all_paths):
    kind=spec["kind"]
    if kind not in ("efficient","probe"):return builders.build(client,spec,problem,all_paths)
    params=spec.copy();params.pop("kind");p=all_paths[params.pop("layout")]
    if kind=="probe":params.setdefault("trial_radius",40.)
    cls=ProbeJointPolicy if kind=="probe" else EfficientJointPolicy
    return cls(client,p,mixed=problem==4,**params)


def freeze(all_paths):
    _prior_freeze(all_paths)
    config=json.loads((OUT/"run_config.json").read_text())
    for name in ("asymmetric_probe_experiments.py","efficient_joint_policy.py","joint_task_policy.py","replacement_experiments.py","replacement_policy.py","coverage_replacement.py","visibility_certificate.py"):
        raw=(ROOT/name).read_bytes();(OUT/"code_snapshot"/name).write_bytes(raw);config["code_sha256"][name]=hashlib.sha256(raw).hexdigest()
    config.update(expected_executions=1860,untouched_future_seeds=list(range(87,97)),
        engine_reuse="spatial_decision_experiments.run with OUT/SPECS/build/freeze/all_layouts replaced explicitly",
        prior_confirmation_role="195 Q4 replacement22 traces replayed for mechanism equivalence only; known regression reused for diagnosis, not a new confirmation",
        probe_budget=10,share_limit=6,asymmetric_proof="same paired-probe implication for arbitrary l>0; candidates keep l within current projected interval",
        semantics_note="Probe class shares once after each primary measure; the .5 control isolates this from asymmetric length changes")
    write_json(OUT/"run_config.json",config)
    checked=json.loads((OUT/"checks.json").read_text())
    (OUT/"precheck.md").write_text(f"# 运行前检查\n\n{checked['passed']}项检查通过，含公开16上限独立实现与195条旧记录的逐请求等价重放；新参数在完整协议压力样本全清且无区域/裁剪异常。原成对探测证明不要求中点。\n\n20候选×93已见训练场景=1860次。87—96与新压力流未生成。先冻结，后台CPU单线程，正式请求0。\n")


def check():
    all_paths=paths();checks=[]
    old_rows=[json.loads(l) for l in (OLD/"trials.jsonl").read_text().splitlines()]
    replayed=0
    for row in old_rows:
        if row["problem"]!=4 or row["method"]!="replacement22":continue
        assert row["replacement_surveys"]==0
        with gzip.open(OLD/"traces"/f"q4__{row['case_id']}__replacement22.jsonl.gz","rt") as f:trace=[json.loads(line) for line in f]
        index=0
        def replay(endpoint,raw):
            nonlocal index
            e=trace[index];assert endpoint==e["path"] and json.loads(raw)==e["request"],(row["case_id"],index)
            index+=1;return 200,e["response"]
        policy=build(Client(replay,robot_id="mock-robot"),SPECS[4]["fast22"],4,all_paths)
        stats=policy.run();assert index==len(trace);replayed+=1
        assert stats["known_upper_bound_skips"]==row["known_upper_bound_skips"]
    assert replayed==195;checks.append(dict(test="fast_count_stop_exact_public_feedback_equivalence",passed=True,replayed_cases=replayed))
    selected=[c for c in training_cases(4) if c[2]=="stress" and c[0].endswith(("n16__negative","n10__spatial"))]
    names=("probe05_22","first025_22","quarter22","march150_22","quarter_prediction22","outer_first025_22","sparse_first025_22","outer_first025_25")
    for case_id,category,split,scenario,error in selected:
        for name in names:
            sim=Simulator(scenario,ErrorField(scenario.seed,error),Limits(countdown_s=0))
            policy=build(Client(PeerTransport(Protocol(sim)),robot_id="mock-robot"),SPECS[4][name],4,all_paths)
            stats=policy.run();assert len(sim.cleared)==len(scenario.sources),(case_id,name)
            assert not stats.get("inconsistent_updates",0) and not stats.get("bracket_cut_inconsistencies",0)
            assert stats["bracket_measurements"]<=20*16
            checks.append(dict(test=f"new_probe_complete_protocol_{name}_{case_id}",passed=True,total_s=sim.virtual_time_s,commands=len(sim.trace)))
    write_json(OUT/"checks.json",dict(passed=len(checks),failed=0,checks=checks,scored_execution_count=0))
    print("Passed",len(checks),"checks including195 exact feedback replays",flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--check",action="store_true");p.add_argument("--launch",action="store_true");args=p.parse_args()
    engine.OUT,engine.SPECS,engine.build,engine.freeze,engine.all_layouts=OUT,SPECS,build,freeze,paths
    if args.check:check();return
    if args.launch:
        if (OUT/"run_config.json").exists():raise RuntimeError("Preserving prior results")
        env=os.environ.copy();env.update(PYTHONDONTWRITEBYTECODE="1",OPENBLAS_NUM_THREADS="1",OMP_NUM_THREADS="1",MPLCONFIGDIR=str(ROOT/".mplconfig"),XDG_CACHE_HOME=str(ROOT/".cache"))
        with (OUT/"log.txt").open("a") as f:
            proc=subprocess.Popen([sys.executable,"-B",str(Path(__file__).resolve())],cwd=ROOT.parent,env=env,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
        (OUT/"background.pid").write_text(str(proc.pid)+"\n");print("Background PID",proc.pid)
    else:engine.run()


if __name__=="__main__":main()
