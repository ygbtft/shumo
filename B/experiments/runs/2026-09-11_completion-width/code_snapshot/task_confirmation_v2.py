"""Resume the same frozen candidates after a result-collector naming collision.

The earlier attempt produced zero scored rows. Policy parameters are unchanged;
only the duplicate initialization timing key is removed from policy statistics.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import task_confirmation as original
import discovery_priority_experiments as builders
import replacement_experiments as certificates
import icra_confirmation as engine
from metaheuristic_experiments import write_json

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "experiments/runs/2026-09-11_task-confirmation-v2"
OLD = original.OUT
SPECS, cases, all_paths = original.SPECS, original.cases, original.all_paths
_base_freeze, _base_summary = engine.freeze, engine.summarize


def build(client, spec, problem, paths):
    policy = builders.build(client, spec, problem, paths)
    # The confirmation runner measures construction externally. Training's
    # extra statistic must not collide with that runner's explicit dict key.
    policy.stats.pop("initialization_s", None)
    return policy


def freeze(paths):
    old = json.loads((OLD / "run_config.json").read_text())
    assert old["specs"] == {str(k): v for k, v in SPECS.items()}
    # Verify all policies retain the pre-first-generation frozen bytes.
    decisions = ("interleaved_policy.py", "discovery_priority_policy.py", "efficient_joint_policy.py",
                 "clearance_policy.py", "joint_task_policy.py", "joint_policy.py", "policies.py",
                 "geometry.py", "client.py", "task_confirmation.py")
    for name in decisions:
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == old["code_sha256"][name]
    assert not (OLD / "trials.jsonl").read_text().strip()
    _base_freeze(paths)
    config = json.loads((OUT / "run_config.json").read_text())
    config.update(confirmation_seeds=list(range(97, 107)), expected_executions=2145,
        derivation="42+55+repeat,0..9; held out from training; first q3/uniform/iid/97 fixture was generated in aborted collector attempt",
        stress_derivation="SeedSequence([42,115,problem,layout_index,count]); errors42+1700+100*problem+index",
        freeze_before_truth_generation=False, all_policies_frozen_before_first_truth_generation=True,
        collection_restart=dict(previous_attempt=str(OLD.relative_to(ROOT)), previous_scored_rows=0,
                                cause="duplicate initialization_s keyword during row construction",
                                only_change="Remove policy statistic initialization_s; runner continues measuring construction externally",
                                no_algorithm_or_parameter_changes=True, no_scores_used_for_selection=True),
        engine_reuse="icra_confirmation.run with explicit OUT/SPECS/builders/all_paths/cases/freeze/summarize replacements",
        selection="Exactly the eleven candidates frozen in original task-confirmation before first fixture generation",
        virtual_upper_bound_s=314016, instruction_upper_bound=9766)
    write_json(OUT / "run_config.json", config)
    (OUT / "precheck.md").write_text("# 采集修复后的确认前检查\n\n原尝试因initialization_s重复写入dict而退出，0计分行、0轨迹文件，仅生成q3/uniform/iid/97。旧目录及日志完整保留。核对11候选参数及全部决策文件SHA仍与第一次生成前冻结版本一致；只移除策略统计中重复字段，外层仍独立记录初始化。原分包252项、发现排序276项检查通过；修复后启动前做两条训练记录反馈等价检查。97—106未用于训练或选择，2145次，正式请求0。\n")


def summarize(rows):
    _base_summary(rows)
    path = OUT / "summary.md"
    text = path.read_text().replace("seed42派生77—86", "seed42派生97—106").replace("Q4旧方格保守", "Q4已有四分之一探测")
    text = text.replace("# 冻结后确认：未用于调参的场景", "# 分包任务与发现排序：采集修复后的冻结确认")
    path.write_text(text + "\n原attempt因统计字段重名在首条结果落盘前退出；算法和参数与首个真值生成前的冻结版本完全相同。失败记录保留，重启仅修采集，不按确认结果调参。\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--launch", action="store_true")
    args = parser.parse_args()
    engine.OUT, engine.SPECS, engine.all_paths, engine.cases = OUT, SPECS, all_paths, cases
    engine.freeze, engine.summarize = freeze, summarize
    engine.builders = SimpleNamespace(build=build, CERTIFICATES=certificates.CERTIFICATES)
    if args.launch:
        if (OUT / "run_config.json").exists():
            raise RuntimeError("Preserving confirmation")
        env = os.environ.copy()
        env.update(PYTHONDONTWRITEBYTECODE="1", OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1",
                   MPLCONFIGDIR=str(ROOT / ".mplconfig"), XDG_CACHE_HOME=str(ROOT / ".cache"))
        with (OUT / "log.txt").open("a") as stream:
            process = subprocess.Popen([sys.executable, "-B", str(Path(__file__).resolve())], cwd=ROOT.parent,
                                       env=env, stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
        (OUT / "background.pid").write_text(str(process.pid) + "\n")
        print("Background PID", process.pid)
    else:
        engine.run()


if __name__ == "__main__":
    main()
