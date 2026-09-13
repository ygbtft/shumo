"""Publish paired task results, negative models and the collector abort."""
import csv
import json
from pathlib import Path
import numpy as np
from task_confirmation_v2 import OUT, SPECS

ROOT = Path(__file__).resolve().parent


def main():
    completion = json.loads((OUT / "completion.json").read_text())
    assert completion["executions"] == completion["all_cleared"] == 2145
    rows = [json.loads(line) for line in (OUT / "trials.jsonl").read_text().splitlines()]
    summary = list(csv.DictReader((OUT / "summary.csv").open()))
    comparisons = {3: (("packet_center7", "clearance7"), ("packet_center9", "clearance9"),
                       ("packet_center7", "peer_layout9_proxy"), ("packet_center9", "peer_layout9_proxy")),
                   4: tuple((method, "quarter22") for method in SPECS[4] if method != "quarter22")}
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
    for folder_name, title in (("interleaved-tasks", "分包任务：已见训练比较"), ("discovery-priority", "发现收益奖励：已见训练比较")):
        folder = ROOT / "experiments/runs" / f"2026-09-11_{folder_name}"
        path = folder / "summary.md"
        text = path.read_text()
        path.write_text("# " + title + "\n" + text.split("\n", 1)[1])
        (folder / "documentation_corrections.json").write_text(json.dumps(dict(change="Replace inherited shared-probe heading with actual experiment title; scores and frozen source unchanged"), indent=2))
    update = """## 分包任务与发现收益：新增4935次执行

本轮1209次分包训练、1581次发现奖励训练和2145次冻结后确认，**4935次计分执行全部清除**；累计**27489次**。首个确认尝试因结果采集字段重名在首条计分行之前退出，旧日志与快照保留；修复只影响采集，候选算法和参数仍与首个真值生成前冻结版本相同。中断尝试没有完整评分/轨迹，不计入上述执行数，也未被用来调参。[异常及修复记录](experiments/runs/2026-09-11_task-confirmation/abort_notes.md)。

### 实际实现与边界

新增分包策略每做一次Q3测向或完整的一组Q4成对探测，就允许重新选择扫描/源任务。每源3次/10轮20次RF预算跨任务累计，光学试探不重置，有限光学兜底保留；整局打断最多24次，预算用完必须继续处理当前源。[实现](interleaved_policy.py)。计入跨源往返后宽松虚拟时间界为314016s<100小时，指令9766；不能把连续定位的1900m内部转移界套给跨源返回。[证明](ROBUST_GUARANTEES_UPDATE.md)。

新增发现优先排序用公开负反馈和有限位置/朝向先验估计下一站的新增发现比例，仅在路线前四个任务中比较。所有原始保证站点仍保留，样本全部排除也不能停止。[实现](discovery_priority_policy.py)。训练中较大发现奖励整体变慢，不能隐藏这一批负结果。

奖励模型审阅还查出错误解释：MEC≤20m频道本来已跳过后续射频，“清除后再节省同一份检测”是重复记账。原消融代码和实测轨迹保留，但该解释不能作为正确成本模型，相关候选不进入本轮确认。[审阅记录](experiments/runs/2026-09-11_discovery-priority/verification_notes.md)。

### 97—106及独立压力流的确认

11候选各150普通、45压力，114.83s完成。候选在首个真值生成前冻结；重启仅修统计字段，无结果驱动调参。表中是同场景比较，不能与上一轮87—96的绝对数值直接判断进退。每源列沿用逐局每源时间的算术平均，源数加权值另列于完整表；不修改240/460目标口径。

""" + "\n".join(table) + """

Q4 packet_center22相对已有quarter22：普通平均每源523.10→512.11s（下降2.10%），压力547.15→540.83s（下降1.16%），平均指令334.35→330.23、354.40→348.02。普通最大总时间7235.64→7007.84s，压力最大8271.73s未变；普通平均策略墙钟约0.0413→0.0409s，压力却0.0398→0.0424s，不能宣称CPU全胜。普通99快/39慢/12平、压力23快/10慢/12平，最坏逐例回退分别626.36/775.61s。

Q3 packet_center7普通254.15→253.25s，只改善0.35%；压力287.35→290.27s变差，最坏逐例回退548.07s，因此不整体取代clearance7。九点布局仍是压力尾部备选。Q4动作预测分包普通收益较小，计算和部分尾部更差；发现奖励300分包普通均值变差1.53%，不推荐为当前主方法。当前Q4以packet_center22作为效率候选，clearance_f015_22压力最大7637.41s更低，但普通、指令和CPU更高，继续单列尾部取舍。

Q3普通提升的10种子块bootstrap区间约为−0.09%—0.85%，包含零；Q4中心预测分包对应1.18%—3.12%。这些区间仅表示这组有限普通场景的均值稳定性，不能消除已记录的压力和逐例回退。

[完整均值、P95、最大、CPU和初始化](experiments/runs/2026-09-11_task-confirmation-v2/summary.md)，[同场景逐例回退及10个种子块区间](experiments/runs/2026-09-11_task-confirmation-v2/paired_analysis.json)。有限场景均值或区间不是任意场景保证，也不是官方成绩。

65项独立核查通过：44条完整反馈轨迹重放并事后检查区域包含与认证光学位置，另对2145条确认轨迹共541960条指令独立重算物理与时间；每源累计预算和整局打断上限均通过。本组没有同地点重复有效读数，因此不把它当固定误差性质的新证据。[核查](experiments/runs/2026-09-11_task-confirmation-v2/final_checks.json)。四个新策略还通过自己启动的随机端口本地HTTP与进程内逐请求等价，两个CLI通过；这些额外运行不计计分执行，也不等于官方软件验证。[HTTP记录](experiments/runs/2026-09-11_task-confirmation-v2/http_checks.json)。

离线复现：`/Users/dingdingzai/anaconda3/bin/python -B B/run_bounded_robot.py --series task --problem 4 --method packet_center22 --seed 42`；Q3分包实验用`--problem 3 --method packet_center7`，原Q3默认候选仍可用mission系列clearance7。入口只运行本地同学后端。

goal保持active：Q3当前效率候选约253—254、Q4约512s/源，仍未达240/460。所有写入仅B/，CPU、基础seed42；正式请求0，无账号、报名身份或正式机会使用。27489为策略计分执行数，包含训练复用，不是独立场景数；同学一没有源码，仍只能比较明确重建的布局代理。官方是否超过截图341.05/658.00仍需实际官方运行条件及可核验同口径记录。

训练：[分包1209次](experiments/runs/2026-09-11_interleaved-tasks/summary.md)、[发现排序1581次](experiments/runs/2026-09-11_discovery-priority/summary.md)。
"""
    (ROOT / "REPORT_TASK_UPDATE.md").write_text(update)
    print("Saved paired analysis, descriptive training headings and report extension")


if __name__ == "__main__":
    main()
