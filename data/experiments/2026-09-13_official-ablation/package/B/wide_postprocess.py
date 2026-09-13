"""Compute paired wide-policy effects without changing frozen candidates."""
import csv
import json
from pathlib import Path
import numpy as np
from wide_confirmation import OUT, SPECS

ROOT = Path(__file__).resolve().parent


def main():
    completion = json.loads((OUT / "completion.json").read_text())
    assert completion["executions"] == completion["all_cleared"] == 2145
    rows = [json.loads(line) for line in (OUT / "trials.jsonl").read_text().splitlines()]
    summary = list(csv.DictReader((OUT / "summary.csv").open()))
    comparisons = {3: (("area_return1_7", "clearance7"), ("expanded_area_return1_7", "clearance7"),
                       ("area_return1_7", "peer_layout9_proxy")),
                   4: tuple((m, base) for base in ("quarter22", "packet_center22", "clearance_f015_22")
                            for m in ("packet_wide5_22", "width40_22", "width_uncertainty100_22", "width40_f015_22"))}
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
    for folder_name, title in (("wide-probes", "宽成对探测：已见训练比较"), ("completion-width", "完工评分和横移限幅：已见训练比较")):
        folder = ROOT / "experiments/runs" / f"2026-09-11_{folder_name}"
        path = folder / "summary.md"
        text = path.read_text()
        path.write_text("# " + title + "\n" + text.split("\n", 1)[1])
        (folder / "documentation_corrections.json").write_text(json.dumps(dict(change="Replace inherited shared-probe heading with actual experiment title; scores and frozen source unchanged"), indent=2))
    (OUT / "report_table.md").write_text("\n".join(table) + "\n")
    print("Saved paired comparisons, seed-block intervals and complete report table")


if __name__ == "__main__":
    main()
