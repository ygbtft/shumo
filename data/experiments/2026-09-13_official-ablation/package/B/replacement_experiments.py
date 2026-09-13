"""Paired training of certified discovery-station replacement and 22-point Q4."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import numpy as np
from client import Client
from replacement_policy import ReplacementPolicy
from coverage_replacement import ReplacementCover
from joint_task_policy import JointTaskPolicy
from peer_benchmark import PeerTransport,Simulator,ErrorField,Limits,Protocol
from layout_alternative_experiments import training_cases
from visibility_certificate import rectangle_certificate,verify_cells,directional_witness
from metaheuristic_experiments import write_json
import spatial_decision_experiments as engine

ROOT=Path(__file__).resolve().parent
OUT=ROOT/"experiments/runs/2026-09-11_convex-visibility"
SPECS={3:{
    "baseline_task7":dict(kind="task",layout="ring7"),
    "replace7":dict(kind="replace",layout="ring7"),
    "replace7_nearest":dict(kind="replace",layout="ring7",task_order="nearest"),
    "replace9":dict(kind="replace",layout="ring9"),
    "replace9_nearest":dict(kind="replace",layout="ring9",task_order="nearest"),
},4:{
    "baseline_conservative25":dict(kind="base",layout="polar25",active=False),
    "baseline_task25":dict(kind="task",layout="polar25",trial_radius=40.),
    "static_task22":dict(kind="task",layout="convex22",trial_radius=40.),
    "replace25":dict(kind="replace",layout="polar25",trial_radius=40.),
    "replace25_nearest":dict(kind="replace",layout="polar25",trial_radius=40.,task_order="nearest"),
    "replace22":dict(kind="replace",layout="convex22",trial_radius=40.),
    "replace22_nearest":dict(kind="replace",layout="convex22",trial_radius=40.,task_order="nearest"),
    "replace22_noshare":dict(kind="replace",layout="convex22",trial_radius=40.,share=False),
}}
_prior_build=engine.build;_prior_freeze=engine.freeze;_prior_paths=engine.all_layouts
CERTIFICATES={}


def paths():
    result=_prior_paths()
    certified=json.loads((OUT/"certified_layouts.json").read_text())
    result["convex22"]=np.array(certified["convex22_72"]["route"])
    CERTIFICATES["convex22"]=certified["convex22_72"]["certificate"]
    # Cell certificates depend on the coordinate set, not station-index order;
    # algorithms recompute eligibility from route coordinates. Rebind exported
    # leaf station indices if independently verifying this reordered route.
    polar_path=OUT/"polar25_rectangle_certificate.json"
    if polar_path.exists():CERTIFICATES["polar25"]=json.loads(polar_path.read_text())
    else:
        certificate=rectangle_certificate(result["polar25"]);assert certificate["covered"]
        write_json(polar_path,certificate);CERTIFICATES["polar25"]=certificate
    return result


def build(client,spec,problem,all_paths):
    if spec["kind"] not in ("task","replace"):return _prior_build(client,spec,problem,all_paths)
    params=spec.copy();kind=params.pop("kind");name=params.pop("layout")
    if kind=="task":return JointTaskPolicy(client,all_paths[name],mixed=problem==4,**params)
    return ReplacementPolicy(client,all_paths[name],certificate=CERTIFICATES.get(name),mixed=problem==4,**params)


def freeze(all_paths):
    _prior_freeze(all_paths)
    config=json.loads((OUT/"run_config.json").read_text())
    for name in ("replacement_experiments.py","replacement_policy.py","coverage_replacement.py","visibility_certificate.py","joint_task_policy.py"):
        raw=(ROOT/name).read_bytes();(OUT/"code_snapshot"/name).write_bytes(raw)
        config["code_sha256"][name]=hashlib.sha256(raw).hexdigest()
    config["engine_reuse"]="spatial_decision_experiments.run with OUT/SPECS/build/freeze/all_layouts explicitly replaced by replacement_experiments.py"
    config["wall_clock_scope"]="policy.run; imports, certificate loading and policy construction excluded, as in earlier training. Confirmation will report initialization separately."
    write_json(OUT/"run_config.json",config)
    checked=json.loads((OUT/"checks.json").read_text())
    (OUT/"precheck.md").write_text(f"# 运行前检查\n\n{checked['passed']}项检查通过，包括角间隙删除与独立方格凸包核对、新策略压力全清、最后只用实际完整扫描点重新构造连续证书。\n\n13候选×93训练场景=1209次。新22点布局有2414方格的全域证书，非采样覆盖结论。种子42派生，正式请求0。\n")


def check():
    all_paths=paths();checks=[];rng=np.random.default_rng(42)
    p=all_paths["polar25"];cover=ReplacementCover(p,CERTIFICATES["polar25"])
    unused=list(range(len(p)))
    for i in range(6):
        q=p[(i*3)%len(p)]+rng.uniform(-80,80,2)
        cover.append(q);cover.remove_greedily(unused,q);cover.validate()
        # Recompute direct convex hulls and farthest-corner distances at every
        # frozen leaf after removals; independent from angular gap deletion.
        cert=CERTIFICATES["polar25"];leaves=[];active=cover.points[cover.active]
        for x,y,h,ids in cert["cells"]:
            far=np.linalg.norm(np.abs(active-[x,y])+h,axis=1)
            leaves.append([x,y,h,np.flatnonzero(far<1000.-1e-5).tolist()])
        verify_cells(active,{**cert,"cells":leaves})
        checks.append(dict(test=f"angular_gap_removal_vs_independent_cell_hulls_{i}",passed=True,removed=len(p)-len(unused)))
    for problem,names in {3:("replace7","replace9_nearest"),4:("replace25","replace22","replace22_nearest")}.items():
        chosen=[c for c in training_cases(problem) if c[2]=="stress" and c[0].endswith(("n16__negative","n10__spatial"))]
        for case_id,category,split,scenario,error in chosen:
            for name in names:
                sim=Simulator(scenario,ErrorField(scenario.seed,error),Limits(countdown_s=0))
                policy=build(Client(PeerTransport(Protocol(sim)),robot_id="mock-robot"),SPECS[problem][name],problem,all_paths)
                stats=policy.run();assert len(sim.cleared)==len(scenario.sources),(problem,name,case_id)
                assert not stats.get("inconsistent_updates",0) and not stats.get("bracket_cut_inconsistencies",0)
                if problem==4 and len(sim.cleared)<16:
                    cert=rectangle_certificate(policy.full_survey_points,save_cells=False)
                    assert cert["covered"],cert
                checks.append(dict(test=f"full_protocol_q{problem}_{name}_{case_id}",passed=True,virtual_s=sim.virtual_time_s,replaced=stats.get("replaced_stations",0)))
    write_json(OUT/"checks.json",dict(passed=len(checks),failed=0,checks=checks,scored_execution_count=0))
    print("Passed",len(checks),"checks",flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--check",action="store_true");p.add_argument("--launch",action="store_true");args=p.parse_args()
    engine.OUT,engine.SPECS,engine.build,engine.freeze,engine.all_layouts=OUT,SPECS,build,freeze,paths
    if args.check:check();return
    if args.launch:
        if (OUT/"run_config.json").exists():raise RuntimeError("Preserving prior evaluation")
        env=os.environ.copy();env.update(PYTHONDONTWRITEBYTECODE="1",OPENBLAS_NUM_THREADS="1",OMP_NUM_THREADS="1",MPLCONFIGDIR=str(ROOT/".mplconfig"),XDG_CACHE_HOME=str(ROOT/".cache"))
        with (OUT/"log.txt").open("a") as f:
            proc=subprocess.Popen([sys.executable,"-B",str(Path(__file__).resolve())],cwd=ROOT.parent,env=env,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
        (OUT/"background.pid").write_text(str(proc.pid)+"\n");print("Background PID",proc.pid)
    else:engine.run()


if __name__=="__main__":main()
