"""Rebuild descriptive cross-batch aggregates and a full current metric table."""
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "experiments/runs/2026-09-11_history-confirmation"


def main():
    results = []
    for problem,method in ((3,"range_area7"),(4,"range_width015")):
        data = []
        for name in ("coupled-confirmation","history-confirmation"):
            folder = OUT.parent / f"2026-09-11_{name}"
            data.extend(json.loads(line) for line in (folder / "trials.jsonl").read_text().splitlines())
        group = [r for r in data if r["problem"] == problem and r["method"] == method and r["split"] == "ordinary"]
        assert len(group) == 300
        results.append(dict(problem=problem,method=method,cases=len(group),ordinary_seeds=list(range(117,137)),
                            mean_per_source_s=sum(r["per_source_s"] for r in group)/len(group),
                            all_cleared=all(r["all_cleared"] for r in group)))
    (OUT / "cross_batch_reference.json").write_text(json.dumps(dict(
        role="Descriptive aggregate of unchanged methods across two existing confirmation batches; not a new holdout or evidence for faithful variants",
        results=results,scored_execution_count=0,official_calls=0),indent=2))
    summary = list(csv.DictReader((OUT / "summary.csv").open()))
    table = ["|问题/方法|普通/压力每源秒|普通/压力平均总秒|普通/压力P95总秒|普通/压力最大总秒|普通/压力指令|普通/压力平均墙钟秒|",
             "|---|---:|---:|---:|---:|---:|---:|"]
    for problem in (3,4):
        methods = [r["method"] for r in summary if int(r["problem"]) == problem and r["split"] == "ordinary"]
        for method in methods:
            pair = [next(r for r in summary if int(r["problem"]) == problem and r["method"] == method and r["split"] == split)
                    for split in ("ordinary","stress")]
            cells = [f"Q{problem} {method}"]
            for key in ("mean_per_source_s","mean_total_s","p95_total_s","max_total_s","mean_commands","mean_wall_s"):
                digits = 4 if key == "mean_wall_s" else 2
                cells.append("/".join(f"{float(r[key]):.{digits}f}" for r in pair))
            table.append("|"+"|".join(cells)+"|")
    (OUT / "full_metric_table.md").write_text("\n".join(table)+"\n")
    stats = []
    for name in ("historical-negatives","faithful-skips","history-confirmation"):
        folder = OUT.parent / f"2026-09-11_{name}"
        rows = [json.loads(line) for line in (folder / "trials.jsonl").read_text().splitlines()]
        stats.append(dict(run=name,scored=len(rows),all_cleared=sum(r["all_cleared"] for r in rows),
                          active_historical_executions=sum(r.get("historical_pair_cuts",0)>0 for r in rows),
                          historical_cuts=sum(r.get("historical_pair_cuts",0) for r in rows),
                          faithful_skips=sum(r.get("faithful_stationary_skips",0) for r in rows)))
    (OUT / "stage_accounting.json").write_text(json.dumps(dict(runs=stats,new_scored_executions=5343,
        total_scored_executions=43716,previous_goal_turn="progress",current_goal_turn="progress",
        goal_status="active",ordinary_current_batch_thresholds_met=True,
        unresolved="All-metric/pointwise superiority over competing routes, stable cross-batch 240/460, official comparison and complete peer source remain unestablished",
        scored_execution_count=0,official_calls=0),indent=2))
    print("Rebuilt cross-batch reference, full metrics and stage accounting")


if __name__ == "__main__":
    main()
