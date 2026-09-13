"""Paired metrics and seed-block intervals for existing scored files only."""
import json
from pathlib import Path
import numpy as np


def analyze(folder,pairs,output="paired_analysis.json"):
    rows=[json.loads(line) for line in (folder/"trials.jsonl").read_text().splitlines()]
    rng=np.random.default_rng(42);records=[]
    for problem,candidate,baseline in pairs:
        for split in ("ordinary","stress"):
            current=[r for r in rows if (r["problem"],r["method"],r["split"])==(problem,candidate,split)]
            old={r["case_id"]:r for r in rows if (r["problem"],r["method"],r["split"])==(problem,baseline,split)}
            assert len(current)==len(old)>0
            delta=np.array([r["total_virtual_s"]-old[r["case_id"]]["total_virtual_s"] for r in current])
            result=dict(problem=problem,candidate=candidate,baseline=baseline,split=split,runs=len(current),
                mean_per_source_reduction=1-np.mean([r["per_source_s"] for r in current])/np.mean([r["per_source_s"] for r in old.values()]),
                mean_cpu_reduction=1-np.mean([r["cpu_s"] for r in current])/np.mean([r["cpu_s"] for r in old.values()]),
                mean_wall_reduction=1-np.mean([r["wall_s"] for r in current])/np.mean([r["wall_s"] for r in old.values()]),
                mean_command_change=float(np.mean([r["commands"]-old[r["case_id"]]["commands"] for r in current])),
                faster=int((delta<-1e-6).sum()),slower=int((delta>1e-6).sum()),tied=int((abs(delta)<=1e-6).sum()),
                worst_regression_s=float(max(0,delta.max())),worst_case=current[int(delta.argmax())]["case_id"] if delta.max()>1e-6 else None,
                regressions=[dict(case_id=r["case_id"],delta_s=float(d),candidate_s=r["total_virtual_s"],baseline_s=old[r["case_id"]]["total_virtual_s"])
                             for r,d in zip(current,delta) if d>1e-6])
            if split=="ordinary":
                seeds=sorted({r["seed"] for r in current})
                a=np.array([np.mean([r["per_source_s"] for r in current if r["seed"]==seed]) for seed in seeds])
                b=np.array([np.mean([r["per_source_s"] for r in old.values() if r["seed"]==seed]) for seed in seeds])
                ids=rng.integers(0,len(seeds),size=(10000,len(seeds)))
                result["seed_block_bootstrap_95_interval"]=np.quantile(1-a[ids].mean(axis=1)/b[ids].mean(axis=1),[.025,.975]).tolist()
                result["seed_blocks"]=len(seeds)
            records.append(result)
    result=dict(base_seed=42,replicates=10000,comparisons=records,scored_executions=0,official_calls=0,
                inference="Exploratory paired seed-block bootstrap; no multiple-comparison correction; handmade stress cases are not a probability model")
    (folder/output).write_text(json.dumps(result,indent=2))
    return result


if __name__=="__main__":
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument("--training",action="store_true");args=parser.parse_args()
    if args.training:
        from cover21_experiments import OUT,LAYOUTS,TEMPLATES
        pairs=[(4,f"{label}_{layout}",f"{label}_convex22") for layout in LAYOUTS[1:] for label in TEMPLATES]
        pairs += [(4,f"{label}_{layout}",f"range_convex22") for layout in LAYOUTS for label in TEMPLATES if f"{label}_{layout}"!="range_convex22"]
        result=analyze(OUT,list(dict.fromkeys(pairs)))
        print("Saved",len(result["comparisons"]),"paired training comparisons")
    else:
        from cover21_confirmation import OUT,COMPARISONS
        result=analyze(OUT,COMPARISONS)
        print("Saved",len(result["comparisons"]),"paired confirmation comparisons")
