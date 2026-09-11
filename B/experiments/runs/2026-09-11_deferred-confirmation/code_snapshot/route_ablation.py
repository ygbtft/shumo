"""Matched-budget removal of local search; separate from the frozen online routes."""
import csv
import json
import os
from pathlib import Path
import subprocess
import sys
from coverage import triangle_stations
from route_algorithms import STOCHASTIC, optimize

ROOT=Path(__file__).resolve().parent
OUT=ROOT/"experiments/runs/2026-09-10_metaheuristics"


def main():
    if "--launch" in sys.argv:
        env=os.environ.copy()
        env.update(PYTHONDONTWRITEBYTECODE="1",OPENBLAS_NUM_THREADS="1",OMP_NUM_THREADS="1")
        with (OUT/"ablation.log").open("a") as stream:
            p=subprocess.Popen([sys.executable,"-B",str(Path(__file__).resolve())],cwd=ROOT.parent,env=env,
                               stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
        (OUT/"ablation.pid").write_text(str(p.pid)+"\n")
        print(f"Ablation background PID {p.pid}")
        return
    if (OUT/"ablation.csv").exists():
        raise RuntimeError("Preserve existing ablation results")
    rows,details=[],{}
    for method in STOCHASTIC:
        for polish in (False,True):
            for seed in range(42,47):
                path,meta=optimize(triangle_stations(990),method,seed=seed,budget=10000,polish=polish)
                rows.append({k:v for k,v in meta.items() if k not in ("history","indices")})
                details[f"{method}__{polish}__{seed}"]={**meta,"points":path.tolist()}
                print(f"{method} polish={polish} seed={seed} {meta['best_m']:.6f}m comparisons={meta['comparisons']} wall={meta['wall_s']:.4f}s",flush=True)
    with (OUT/"ablation.csv").open("x",newline="") as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)
    (OUT/"ablation_runs.json").write_text(json.dumps(details,indent=2))


if __name__=="__main__":
    main()
