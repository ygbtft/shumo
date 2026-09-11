"""Paired training of stronger reception tests, minimax sensing and rotations."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import numpy as np
from client import Client
from safe_sensing_policy import SafeSensingPolicy
from rotating_layout_policy import RotatingSafePolicy,RotatingEfficientPolicy,RotatingProbePolicy
from peer_benchmark import PeerTransport,Simulator,ErrorField,Limits,Protocol
from layout_alternative_experiments import training_cases
from layout_certificates import critical_cover_radius
from visibility_certificate import rectangle_certificate
from metaheuristic_experiments import write_json
import asymmetric_probe_experiments as builders
import spatial_decision_experiments as engine

ROOT=Path(__file__).resolve().parent
OUT=ROOT/"experiments/runs/2026-09-11_reception-layout"
SPECS={3:{
    "fast7":dict(kind="efficient",layout="ring7"),
    "full_reception7":dict(kind="safe",layout="ring7"),
    "expanded7":dict(kind="safe",layout="ring7",expanded=True),
    "expanded_weight03_7":dict(kind="safe",layout="ring7",expanded=True,sensing_weight=.3),
    "minimax7":dict(kind="safe",layout="ring7",ranker="minimax"),
    "minimax_weight03_7":dict(kind="safe",layout="ring7",ranker="minimax",sensing_weight=.3),
    "rotate_fast7":dict(kind="rotate_efficient",layout="ring7",symmetry=6),
    "rotate_full7":dict(kind="rotate_safe",layout="ring7",symmetry=6),
    "rotate_expanded7":dict(kind="rotate_safe",layout="ring7",symmetry=6,expanded=True),
    "rotate_fast9":dict(kind="rotate_efficient",layout="ring9",symmetry=8),
},4:{
    "quarter_cd22":dict(kind="probe",layout="convex22",fraction=.25,share_cooldown=150.),
    "fraction015_22":dict(kind="probe",layout="convex22",fraction=.15,share_cooldown=150.),
    "fraction020_22":dict(kind="probe",layout="convex22",fraction=.2,share_cooldown=150.),
    "fraction030_22":dict(kind="probe",layout="convex22",fraction=.3,share_cooldown=150.),
    "quarter_cd300_22":dict(kind="probe",layout="convex22",fraction=.25,share_cooldown=300.),
    "rotate_quarter22":dict(kind="rotate_probe",layout="convex22",symmetry=7,fraction=.25,share_cooldown=150.),
    "rotate_first025_22":dict(kind="rotate_probe",layout="convex22",symmetry=7,fraction=.25,first_only=True,share_cooldown=150.),
    "rotate_quarter25":dict(kind="rotate_probe",layout="polar25",symmetry=8,fraction=.25,share_cooldown=150.),
}}
_prior_freeze=engine.freeze


def paths():return builders.paths()


def build(client,spec,problem,all_paths):
    kind=spec["kind"]
    if kind not in ("safe","rotate_safe","rotate_efficient","rotate_probe"):return builders.build(client,spec,problem,all_paths)
    params=spec.copy();params.pop("kind");p=all_paths[params.pop("layout")]
    if problem==4:params.setdefault("trial_radius",40.)
    cls={"safe":SafeSensingPolicy,"rotate_safe":RotatingSafePolicy,"rotate_efficient":RotatingEfficientPolicy,"rotate_probe":RotatingProbePolicy}[kind]
    return cls(client,p,mixed=problem==4,**params)


def freeze(all_paths):
    _prior_freeze(all_paths)
    config=json.loads((OUT/"run_config.json").read_text())
    for name in ("reception_layout_experiments.py","safe_sensing_policy.py","rotating_layout_policy.py","signal_minimax.py","asymmetric_probe_experiments.py","efficient_joint_policy.py","joint_task_policy.py","replacement_experiments.py","replacement_policy.py","coverage_replacement.py","visibility_certificate.py"):
        raw=(ROOT/name).read_bytes();(OUT/"code_snapshot"/name).write_bytes(raw);config["code_sha256"][name]=hashlib.sha256(raw).hexdigest()
    config.update(expected_executions=1674,untouched_future_seeds=list(range(87,97)),
        engine_reuse="spatial_decision_experiments.run with explicit OUT/SPECS/build/freeze/all_layouts replacements",
        minimax_scope="continuous possible bearing bins for four covariance-screened candidate actions, not a global action optimum",rotation_phases=8,
        rotation_proof="one rigid rotation about arena center after origin survey; all original coverage guarantees invariant")
    write_json(OUT/"run_config.json",config)
    checked=json.loads((OUT/"checks.json").read_text())
    (OUT/"precheck.md").write_text(f"# 运行前检查\n\n{checked['passed']}项检查通过，包括旋转后的全域Q3/Q4覆盖、完整协议压力清除以及新Q3保收候选无意外失收。独立Q2连续界与候选扩展另有1340合法示向样本检查。\n\n18候选×93已见训练场景=1674次。87—96仍未生成，CPU单线程，正式请求0。\n")


def check():
    all_paths=paths();checks=[]
    for problem,names in {3:("full_reception7","expanded7","minimax7","rotate_full7"),4:("fraction015_22","rotate_quarter22","rotate_quarter25")}.items():
        selected=[c for c in training_cases(problem) if c[2]=="stress" and c[0].endswith(("n16__negative","n10__spatial"))]
        for case_id,category,split,scenario,error in selected:
            for name in names:
                sim=Simulator(scenario,ErrorField(scenario.seed,error),Limits(countdown_s=0))
                policy=build(Client(PeerTransport(Protocol(sim)),robot_id="mock-robot"),SPECS[problem][name],problem,all_paths)
                stats=policy.run();assert len(sim.cleared)==len(scenario.sources),(case_id,name)
                assert not stats.get("inconsistent_updates",0) and not stats.get("bracket_cut_inconsistencies",0)
                if problem==3:assert stats["active_no_signal"]==0
                if problem==3:assert critical_cover_radius(policy.stations)<1000.
                elif "rotate" in name:assert rectangle_certificate(policy.stations,save_cells=False)["covered"]
                checks.append(dict(test=f"q{problem}_{name}_{case_id}",passed=True,total_s=sim.virtual_time_s,commands=len(sim.trace),rotation_deg=stats.get("layout_rotation_deg",0.)))
    write_json(OUT/"checks.json",dict(passed=len(checks),failed=0,checks=checks,scored_execution_count=0))
    print("Passed",len(checks),"complete protocol and coverage checks",flush=True)


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
