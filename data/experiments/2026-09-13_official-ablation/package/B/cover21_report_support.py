"""Reproducible tables, coordinate export, and descriptive old-batch aggregates."""
import csv
import hashlib
import json
from pathlib import Path
import numpy as np
from cover21_confirmation import ROOT,OUT,SPECS


def main():
    summary=list(csv.DictReader((OUT/"summary.csv").open()))
    table=["|问题/方法|普通/压力每源秒|普通/压力平均总秒|普通/压力P95总秒|普通/压力最大总秒|普通/压力指令|普通/压力平均CPU秒|普通/压力平均墙钟秒|",
           "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for problem,methods in SPECS.items():
        for method in methods:
            a,b=[next(r for r in summary if int(r["problem"])==problem and r["method"]==method and r["split"]==split) for split in ("ordinary","stress")]
            cells=[f"Q{problem} {method}"]
            for key,digits in (("mean_per_source_s",2),("mean_total_s",2),("p95_total_s",2),("max_total_s",2),("mean_commands",2),("mean_cpu_s",5),("mean_wall_s",5)):
                cells.append(f"{float(a[key]):.{digits}f}/{float(b[key]):.{digits}f}")
            table.append("|"+"|".join(cells)+"|")
    (OUT/"full_metric_table.md").write_text("\n".join(table)+"\n")
    current_config=json.loads((OUT/"run_config.json").read_text())
    combined=[]
    for problem,current_method,old_method in ((3,"range_area7","range_area7"),(4,"range_convex22","range_width015")):
        records=[]
        for name in ("coupled-confirmation","history-confirmation","deferred-confirmation","cover21-confirmation"):
            folder=ROOT/"experiments/runs"/f"2026-09-11_{name}"
            method=current_method if folder==OUT else old_method
            config=json.loads((folder/"run_config.json").read_text())
            assert config["specs"][str(problem)][method]==current_config["specs"][str(problem)][current_method]
            rows=[json.loads(line) for line in (folder/"trials.jsonl").read_text().splitlines()]
            selected=[r for r in rows if (r["problem"],r["method"],r["split"])==(problem,method,"ordinary")]
            assert len(selected)==150 and all(r["all_cleared"] for r in selected)
            records.extend(selected)
        combined.append(dict(problem=problem,method=current_method,cases=len(records),ordinary_seeds=sorted({r["seed"] for r in records}),
                             mean_per_source_s=float(np.mean([r["per_source_s"] for r in records])),all_cleared=True))
    (OUT/"cross_batch_reference.json").write_text(json.dumps(dict(role="Existing four-batch descriptive aggregate of unchanged strategies; not a new holdout, and not cross-batch evidence for new 21-site policies",results=combined,scored_executions=0,official_calls=0),indent=2))
    stages=[]
    for name in ("lean-scan","public-count-scan","cover21-training","cover21-confirmation"):
        folder=ROOT/"experiments/runs"/f"2026-09-11_{name}";rows=[json.loads(s) for s in (folder/"trials.jsonl").read_text().splitlines()]
        stages.append(dict(run=name,scored=len(rows),all_cleared=sum(r["all_cleared"] for r in rows),public_empty_skips=sum(r.get("public_empty_scan_skips",0) for r in rows)))
    (OUT/"stage_accounting.json").write_text(json.dumps(dict(runs=stages,new_scored_executions=7620,total_scored_executions=59514,
        previous_goal_turn="progress",current_goal_turn="progress",goal_status="active",ordinary_current_batch_thresholds_met=True,
        unresolved="Cross-batch 240/460 stability, per-case and tail/CPU dominance, complete peer implementation and official validation remain unestablished",scored_executions=0,official_calls=0),indent=2))
    selected=json.loads((OUT/"selected_layouts.json").read_text())["grid21_29"]
    with (OUT/"layout_grid21_29_coordinates.csv").open("w",newline="") as stream:
        writer=csv.writer(stream);writer.writerow(("station_id","x_m","y_m","group"))
        for i,(x,y) in enumerate(selected["points"]):writer.writerow((i,int(x),int(y),"center" if i==0 else "inner" if i<=8 else "outer"))
    for name,title in (("lean-scan","相同决策的延迟求值：训练"),("public-count-scan","公开16源后的空频道删除：训练"),("cover21-training","21站整数布局与完整任务：训练")):
        p=ROOT/"experiments/runs"/f"2026-09-11_{name}"/"summary.md"
        content=p.read_text();p.write_text("# "+title+"\n"+content.split("\n",1)[1])
    print(json.dumps(dict(cross_batch=combined,stage_counts=stages,scored_executions=0,official_calls=0),indent=2))


if __name__=="__main__":main()
