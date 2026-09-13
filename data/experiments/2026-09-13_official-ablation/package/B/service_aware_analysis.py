"""Save all training metrics and paired regressions; no new source generation."""
import json
import numpy as np
from service_aware_experiments import OUT, SPECS, EXPECTED
from scan_pair_analysis import analyze
from metaheuristic_experiments import write_json, write_csv


def baseline(problem, method):
    return "range_area7" if problem == 3 else "range_convex22" if method.endswith("convex22") else "range_grid21_29"


def main():
    rows = [json.loads(line) for line in (OUT/"trials.jsonl").read_text().splitlines()]
    assert len(rows) == EXPECTED
    pairs = [(p, name, baseline(p, name)) for p, methods in SPECS.items() for name in methods if name != baseline(p, name)]
    pairs += [(4, "service_free1_grid21_29", "service_free0_grid21_29"),
              (4, "service_free2_grid21_29", "service_free0_grid21_29"),
              (4, "service_locked1_grid21_29", "service_locked0_grid21_29"),
              (4, "service_soft20_grid21_29", "service_free1_grid21_29"),
              (4, "service_locked1_grid21_29", "count_locked_grid21_29"),
              (3, "service_free1_area7", "service_free0_area7")]
    paired = analyze(OUT, pairs)
    records = []
    lines = ["# 有向任务规划与扫描费用：已见训练场景", "", "每方法75普通+18压力，均是重复使用的训练场景；不能代替冻结后的未见确认。", "",
             "|问题/方法|场景|全清|每源秒|总秒均值/P95/最大|指令均值|CPU均值秒|墙钟均值/最大秒|相对匹配range变慢局|", "|---|---|---:|---:|---:|---:|---:|---:|---:|"]
    for p, methods in SPECS.items():
        for name in methods:
            for split in ("ordinary", "stress"):
                group = [r for r in rows if (r["problem"], r["method"], r["split"]) == (p, name, split)]
                old = {r["case_id"]:r for r in rows if (r["problem"], r["method"], r["split"]) == (p, baseline(p, name), split)}
                times = np.asarray([r["total_virtual_s"] for r in group])
                item = dict(problem=p, method=name, split=split, runs=len(group), all_cleared=sum(r["all_cleared"] for r in group),
                            mean_per_source_s=float(np.mean([r["per_source_s"] for r in group])), mean_total_s=float(times.mean()),
                            p95_total_s=float(np.quantile(times, .95)), max_total_s=float(times.max()),
                            mean_commands=float(np.mean([r["commands"] for r in group])),
                            mean_cpu_s=float(np.mean([r["cpu_s"] for r in group])), mean_wall_s=float(np.mean([r["wall_s"] for r in group])),
                            max_wall_s=max(r["wall_s"] for r in group), slower=sum(r["total_virtual_s"] > old[r["case_id"]]["total_virtual_s"]+1e-6 for r in group))
                records.append(item)
                lines.append(f"|Q{p} {name}|{split}|{item['all_cleared']}/{len(group)}|{item['mean_per_source_s']:.2f}|{item['mean_total_s']:.2f}/{item['p95_total_s']:.2f}/{item['max_total_s']:.2f}|{item['mean_commands']:.2f}|{item['mean_cpu_s']:.5f}|{item['mean_wall_s']:.5f}/{item['max_wall_s']:.5f}|{item['slower']}|")
    write_csv(OUT/"full_metrics.csv", records)
    (OUT/"summary.md").write_text("\n".join(lines)+"\n")
    # Descriptive only: this is not an automated holdout-selection rule.
    summary = {p:{split:sorted([r for r in records if r["problem"] == p and r["split"] == split], key=lambda r:r["mean_per_source_s"])[0]["method"] for split in ("ordinary", "stress")} for p in SPECS}
    write_json(OUT/"training_rankings.json", dict(best_mean_only=summary, not_frozen_holdout_selection=True,
               heldout_seeds_157_166_generated=False, scored_executions=0, official_calls=0))
    print(json.dumps(dict(scored_rows=len(rows), all_cleared=sum(r["all_cleared"] for r in rows),
                          paired_comparisons=len(paired["comparisons"]), best_mean_only=summary), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
