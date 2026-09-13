"""Fresh post-selection confirmation of bounded mission optimization."""
import argparse
import json
import math
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import numpy as np
from peer_benchmark import ScenarioConfig,ErrorConfig,mandatory_conditions,generate
from mock.scenario_gen import Scenario,Source
from metaheuristic_experiments import write_json
import clearance_experiments as builders
import replacement_experiments as certificates
import icra_confirmation as engine

ROOT=Path(__file__).resolve().parent
OUT=ROOT/"experiments/runs/2026-09-11_mission-confirmation"
SPECS={3:{
    "peer_layout9_proxy":dict(kind="base",layout="ring9"),
    "fast7":dict(kind="efficient",layout="ring7"),
    "clearance7":dict(kind="clearance",layout="ring7"),
    "clearance9":dict(kind="clearance",layout="ring9"),
},4:{
    "square45_conservative":dict(kind="base",layout="square45",active=False),
    "fast22":dict(kind="efficient",layout="convex22",trial_radius=40.),
    "quarter22":dict(kind="probe",layout="convex22",fraction=.25,share_cooldown=150.),
    "quarter_prediction22":dict(kind="probe",layout="convex22",fraction=.25,share_cooldown=150.,task_prediction="probe"),
    "clearance_quarter22":dict(kind="clearance_probe",layout="convex22",fraction=.25,share_cooldown=150.),
    "clearance_f015_22":dict(kind="clearance_probe",layout="convex22",fraction=.15,share_cooldown=150.),
    "clearance_f03_22":dict(kind="clearance_probe",layout="convex22",fraction=.3,share_cooldown=150.),
}}
_prior_freeze=engine.freeze


def all_paths():
    result=builders.paths()
    old=json.loads((ROOT/"experiments/runs/2026-09-10_metaheuristics/selected_routes.json").read_text())
    result["square45"]=np.array(old["square700"]["two_opt"]["points"])
    return result


def cases(problem):
    for label,scfg,ecfg in mandatory_conditions(ScenarioConfig(directional_fraction=.5 if problem==4 else 0.),ErrorConfig()):
        for seed in range(87,97):yield f"{label}__{seed}",label,"ordinary",generate(seed,scfg),ecfg
    index=0
    for li,layout in enumerate(("boundary_outward","boundary_tangent","near_collinear","cluster_far20","range_transition")):
        for count in (10,13,16):
            rng=np.random.default_rng(np.random.SeedSequence([42,114,problem,li,count]))
            channels=list(rng.choice(np.arange(1,20),count-1,replace=False))+[20]
            phase=rng.uniform(0,2*math.pi);angles=np.arange(count)*2*math.pi/count+phase
            if layout.startswith("boundary"):points=1800*np.column_stack([np.cos(angles),np.sin(angles)])
            elif layout=="near_collinear":
                angle=1.147013;u=np.array([math.cos(angle),math.sin(angle)]);v=np.array([-u[1],u[0]])
                points=np.linspace(-1790,1790,count)[:,None]*u+rng.uniform(-.001,.001,count)[:,None]*v
            elif layout=="cluster_far20":
                points=rng.normal(0,120,(count,2));points[-1]=1800*np.array([math.cos(phase),math.sin(phase)])
            else:points=np.linspace(850,1500,count)[:,None]*np.column_stack([np.cos(angles),np.sin(angles)])
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
                seed=42+1400+100*problem+index;index+=1
                scenario=Scenario(seed,tuple(sources),dict(stress_layout=layout,source_rng=[42,114,problem,li,count]))
                yield f"{layout}__n{count}__{sign}",layout,"stress",scenario,ErrorConfig(model="adversarial",adversarial_sign=sign)


def freeze(paths):
    _prior_freeze(paths)
    config=json.loads((OUT/"run_config.json").read_text())
    config.update(confirmation_seeds=list(range(87,97)),derivation="42+45+repeat,repeat0..9; not previously generated",
        stress_derivation="SeedSequence([42,114,problem,layout_index,count]); errors42+1400+100*problem+index",expected_executions=2145,
        engine_reuse="icra_confirmation.run/summarize with explicit OUT/SPECS/builders/all_paths/cases/freeze replacements",
        selection="Frozen after 4278 training executions; no changes based on these confirmation scenes")
    write_json(OUT/"run_config.json",config)
    (OUT/"precheck.md").write_text("# 新确认前冻结\n\n49项非对称探测检查（含195旧反馈等价重放）、42项保收/旋转检查、114项光学位置检查通过；三轮4278训练全清。先冻结全部代码/参数，再生成87—96及新压力流；11候选×195=2145次，正式请求0。\n")


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--launch",action="store_true");args=p.parse_args()
    engine.OUT,engine.SPECS,engine.all_paths,engine.cases,engine.freeze=OUT,SPECS,all_paths,cases,freeze
    engine.builders=SimpleNamespace(build=builders.build,CERTIFICATES=certificates.CERTIFICATES)
    if args.launch:
        if (OUT/"run_config.json").exists():raise RuntimeError("Preserving confirmation")
        env=os.environ.copy();env.update(PYTHONDONTWRITEBYTECODE="1",OPENBLAS_NUM_THREADS="1",OMP_NUM_THREADS="1",MPLCONFIGDIR=str(ROOT/".mplconfig"),XDG_CACHE_HOME=str(ROOT/".cache"))
        with (OUT/"log.txt").open("a") as f:
            proc=subprocess.Popen([sys.executable,"-B",str(Path(__file__).resolve())],cwd=ROOT.parent,env=env,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
        (OUT/"background.pid").write_text(str(proc.pid)+"\n");print("Background PID",proc.pid)
    else:engine.run()


if __name__=="__main__":main()
