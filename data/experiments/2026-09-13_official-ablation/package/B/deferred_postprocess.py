"""Compute paired historical/faithful effects without changing frozen candidates."""
import csv
import json
from pathlib import Path
import numpy as np
from deferred_confirmation import OUT, SPECS

ROOT = Path(__file__).resolve().parent


def main():
    completion = json.loads((OUT / "completion.json").read_text())
    assert completion["executions"] == completion["all_cleared"] == 3900
    rows = [json.loads(line) for line in (OUT / "trials.jsonl").read_text().splitlines()]
    summary = list(csv.DictReader((OUT / "summary.csv").open()))
    comparisons={3:tuple((m,b) for m in ("range_area7","faithful_area7","deferred_area7") for b in ("area_return1_7","peer_layout9_proxy") )
                           + (("deferred_area7","faithful_area7"),("deferred_area7","range_area7")),
                 4:tuple((m,b) for m in ("deferred_width015","cheap_predict4_width015","cheap_predict8_width015","deferred_arc05_width015","cheap_predict8_arc05_width015","deferred_locked_width015","cheap_predict8_locked_width015","batch_history_first8_width015")
                         for b in ("width40_f015_22","range_width015") )
                    + (("deferred_width015","faithful_width015"),("cheap_predict8_width015","predict8_width015"),
                       ("cheap_predict8_width015","deferred_width015"),("cheap_predict4_width015","deferred_width015"),
                       ("deferred_arc05_width015","arc05_noskip_width015"),("cheap_predict8_arc05_width015","arc05_noskip_width015"),
                       ("deferred_locked_width015","locked_noskip_width015"),("cheap_predict8_locked_width015","locked_noskip_width015"),
                       ("batch_history_first8_width015","history_first8_width015"))}
    rng = np.random.default_rng(42)
    paired = []
    for problem, pairs in comparisons.items():
        for candidate, baseline in pairs:
            for split in ("ordinary", "stress"):
                a = [r for r in rows if r["problem"] == problem and r["method"] == candidate and r["split"] == split]
                b = {r["case_id"]: r for r in rows if r["problem"] == problem and r["method"] == baseline and r["split"] == split}
                delta = np.array([r["total_virtual_s"] - b[r["case_id"]]["total_virtual_s"] for r in a])
                result = dict(problem=problem, candidate=candidate, baseline=baseline, split=split, runs=len(a),
                    mean_per_source_reduction=1 - np.mean([r["per_source_s"] for r in a]) / np.mean([r["per_source_s"] for r in b.values()]),
                    faster=int((delta < -1e-6).sum()), slower=int((delta > 1e-6).sum()), tied=int((abs(delta) <= 1e-6).sum()),
                    mean_command_change=float(np.mean([r["commands"] - b[r["case_id"]]["commands"] for r in a])),
                    mean_cpu_reduction=1-np.mean([r["cpu_s"] for r in a])/np.mean([r["cpu_s"] for r in b.values()]),
                    mean_wall_reduction=1-np.mean([r["wall_s"] for r in a])/np.mean([r["wall_s"] for r in b.values()]),
                    worst_regression_s=float(max(0., delta.max())),
                    worst_case=a[int(delta.argmax())]["case_id"] if delta.max() > 1e-6 else None,
                    regressions=[dict(case_id=r["case_id"], delta_s=float(d), candidate_s=r["total_virtual_s"], baseline_s=b[r["case_id"]]["total_virtual_s"])
                                 for r, d in zip(a, delta) if d > 1e-6])
                if split == "ordinary":
                    seeds = sorted({r["seed"] for r in a})
                    ga = np.array([np.mean([r["per_source_s"] for r in a if r["seed"] == seed]) for seed in seeds])
                    gb = np.array([np.mean([r["per_source_s"] for r in b.values() if r["seed"] == seed]) for seed in seeds])
                    ids = rng.integers(0, len(seeds), (10000, len(seeds)))
                    effect = 1 - ga[ids].mean(axis=1) / gb[ids].mean(axis=1)
                    result["seed_block_bootstrap_95_interval"] = np.quantile(effect, [.025, .975]).tolist()
                paired.append(result)
    (OUT / "paired_analysis.json").write_text(json.dumps(dict(base_seed=42, replicates=10000,
        cluster="ten seed blocks preserving the fifteen ordinary layout/error conditions", comparisons=paired), indent=2))
    table = ["|问题/策略|普通/压力全清|普通/压力每源秒|普通/压力最大总秒|普通/压力指令|普通/压力平均墙钟秒|普通/压力平均初始化秒|",
             "|---|---:|---:|---:|---:|---:|---:|"]
    for problem, methods in SPECS.items():
        for method in methods:
            a, b = [next(r for r in summary if int(r["problem"]) == problem and r["method"] == method and r["split"] == split)
                    for split in ("ordinary", "stress")]
            table.append(f"|Q{problem} {method}|{a['all_cleared']}/{a['runs']}；{b['all_cleared']}/{b['runs']}|"
                         f"{float(a['mean_per_source_s']):.2f}/{float(b['mean_per_source_s']):.2f}|"
                         f"{float(a['max_total_s']):.2f}/{float(b['max_total_s']):.2f}|"
                         f"{float(a['mean_commands']):.2f}/{float(b['mean_commands']):.2f}|"
                         f"{float(a['mean_wall_s']):.4f}/{float(b['mean_wall_s']):.4f}|"
                         f"{float(a['mean_init_s']):.5f}/{float(b['mean_init_s']):.5f}|")
    for folder_name, title in (("deferred-scans","延后移动和负点证书：已见训练比较"),("batched-history","历史约束批量筛选：已见训练比较"),("cheap-prediction","完整预测证书的廉价预筛：已见训练比较")):
        folder = ROOT / "experiments/runs" / f"2026-09-11_{folder_name}"
        path = folder / "summary.md"
        text = path.read_text()
        path.write_text("# " + title + "\n" + text.split("\n", 1)[1])
        (folder / "documentation_corrections.json").write_text(json.dumps(dict(change="Replace inherited shared-probe heading with actual experiment title; scores and frozen source unchanged"), indent=2))
    (OUT / "report_table.md").write_text("\n".join(table) + "\n")
    print("Saved paired comparisons, seed-block intervals and complete report table")


if __name__ == "__main__":
    main()
