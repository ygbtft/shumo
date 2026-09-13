"""Training of optically feasible stopping regions against center-only clearance."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import numpy as np
from client import Client
from clearance_policy import ClearanceJointPolicy,ClearanceProbePolicy,closest_clearance_point
from geometry import hull,minimum_circle
from peer_benchmark import PeerTransport,Simulator,ErrorField,Limits,Protocol
from layout_alternative_experiments import training_cases
from metaheuristic_experiments import write_json
import reception_layout_experiments as builders
import spatial_decision_experiments as engine

ROOT=Path(__file__).resolve().parent
OUT=ROOT/"experiments/runs/2026-09-11_clearance-neighborhood"
SPECS={3:{
    "fast7":dict(kind="efficient",layout="ring7"),
    "clearance7":dict(kind="clearance",layout="ring7"),
    "clearance9":dict(kind="clearance",layout="ring9"),
},4:{
    "quarter_cd22":dict(kind="probe",layout="convex22",fraction=.25,share_cooldown=150.),
    "clearance_quarter22":dict(kind="clearance_probe",layout="convex22",fraction=.25,share_cooldown=150.),
    "clearance_f015_22":dict(kind="clearance_probe",layout="convex22",fraction=.15,share_cooldown=150.),
    "clearance_f03_22":dict(kind="clearance_probe",layout="convex22",fraction=.3,share_cooldown=150.),
    "clearance_quarter25":dict(kind="clearance_probe",layout="polar25",fraction=.25,share_cooldown=150.),
}}
_prior_freeze=engine.freeze


def paths():return builders.paths()


def build(client,spec,problem,all_paths):
    kind=spec["kind"]
    if kind not in ("clearance","clearance_probe"):return builders.build(client,spec,problem,all_paths)
    params=spec.copy();params.pop("kind");points=all_paths[params.pop("layout")]
    if problem==4:params.setdefault("trial_radius",40.)
    cls=ClearanceJointPolicy if kind=="clearance" else ClearanceProbePolicy
    return cls(client,points,mixed=problem==4,**params)


def freeze(all_paths):
    _prior_freeze(all_paths)
    config=json.loads((OUT/"run_config.json").read_text())
    for name in ("clearance_experiments.py","clearance_policy.py","reception_layout_experiments.py","safe_sensing_policy.py","rotating_layout_policy.py","signal_minimax.py","asymmetric_probe_experiments.py","efficient_joint_policy.py","joint_task_policy.py","replacement_experiments.py","replacement_policy.py","coverage_replacement.py","visibility_certificate.py"):
        raw=(ROOT/name).read_bytes();(OUT/"code_snapshot"/name).write_bytes(raw);config["code_sha256"][name]=hashlib.sha256(raw).hexdigest()
    config.update(expected_executions=744,untouched_future_seeds=list(range(87,97)),optical_radius_used=20.-1e-6,
        engine_reuse="spatial_decision_experiments.run with explicit globals replaced by clearance_experiments.py")
    write_json(OUT/"run_config.json",config)
    (OUT/"precheck.md").write_text("# 运行前检查\n\n80个随机凸区域通过光学包含及独立凸投影法锥最优性证书，另有4个退化用例和30个完整协议压力用例。SLSQP参考求解未稳定收敛，已记录并改用法锥证书。8候选×93已见场景=744，先冻结参数/快照，正式请求0。\n")


def check():
    # Independent first-order certificate: current-q must be a nonnegative
    # combination of the outward normals of active disks. With feasibility,
    # this is the global projection condition for the convex intersection.
    from scipy.optimize import nnls
    rng=np.random.default_rng(42);checks=[]
    for i in range(80):
        p=hull(rng.normal(size=(rng.integers(3,15),2)));c,r=minimum_circle(p)
        p=(p-c)*rng.uniform(1,19.8)/r+rng.uniform(-1500,1500,2);current=rng.uniform(-1800,1800,2)
        q=closest_clearance_point(p,current);center,r=minimum_circle(p)
        assert np.linalg.norm(p-q,axis=1).max()<=20.+1e-7
        distances=np.linalg.norm(q-p,axis=1);active=np.abs(distances-(20.-1e-6))<1e-7
        objective=current-q
        if np.linalg.norm(objective)>1e-8:
            assert active.any()
            normals=(q-p[active])/distances[active,None]
            multipliers,residual=nnls(normals.T,objective/np.linalg.norm(objective))
            assert residual<1e-6,(i,residual)
        else:residual=0.
        checks.append(dict(test=f"optical_disk_intersection_independent_normal_cone_certificate_{i}",passed=True,unit_normal_residual=residual))
    for i,p in enumerate((np.array([[0.,0.]]),np.array([[-15.,0.],[15.,0.]]),np.array([[-20.,0.],[20.,0.]]),np.array([[0.,0.],[0.,0.],[0.,0.]]))):
        current=np.array([40.,50.]);q=closest_clearance_point(p,current)
        assert np.linalg.norm(p-q,axis=1).max()<=20.+1e-8
        assert np.linalg.norm(q-current)<=np.linalg.norm(minimum_circle(p)[0]-current)+1e-8
        checks.append(dict(test=f"optical_feasible_point_segment_tangent_duplicate_{i}",passed=True))
    all_paths=paths()
    for problem,names in {3:("clearance7","clearance9"),4:("clearance_quarter22","clearance_f015_22","clearance_quarter25")}.items():
        selected=[c for c in training_cases(problem) if c[2]=="stress" and c[0].endswith(("n16__negative","n10__spatial"))]
        for case_id,category,split,scenario,error in selected:
            for name in names:
                sim=Simulator(scenario,ErrorField(scenario.seed,error),Limits(countdown_s=0))
                policy=build(Client(PeerTransport(Protocol(sim)),robot_id="mock-robot"),SPECS[problem][name],problem,all_paths)
                stats=policy.run();assert len(sim.cleared)==len(scenario.sources),(case_id,name)
                checks.append(dict(test=f"complete_protocol_{name}_{case_id}",passed=True,total_s=sim.virtual_time_s,local_saved_m=stats["optical_local_move_saved_m"]))
    write_json(OUT/"checks.json",dict(passed=len(checks),failed=0,checks=checks,scored_execution_count=0));print("Passed",len(checks),"checks",flush=True)


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
