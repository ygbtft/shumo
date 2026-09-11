"""Add completed algorithm findings to REPORT; preserve the historic audit manifest."""
import ast
import csv
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT=Path(__file__).resolve().parent
OUT=ROOT/"experiments/runs/2026-09-10_metaheuristics"
PREFIX="experiments/runs/2026-09-10_metaheuristics"
LABELS={"greedy":"最近邻贪心","insertion_greedy":"插入贪心","two_opt":"原2-opt","genetic":"增强遗传+2-opt",
        "immune":"免疫+2-opt","ant_colony":"蚁群+2-opt","particle_swarm":"粒子群+2-opt","fireworks":"烟花+2-opt",
        "iterated_search":"迭代搜索+2-opt","adaptive_greedy":"在线贪心重排","adaptive_two_opt":"在线2-opt重排"}


def main():
    check=json.loads((OUT/"final_checks.json").read_text())
    assert check["failed"]==0
    ordinary=list(csv.DictReader((OUT/"summary.csv").open()))
    confirmation=list(csv.DictReader((OUT/"confirmation/summary.csv").open()))
    paired=list(csv.DictReader((OUT/"confirmation/paired_summary.csv").open()))
    choices=json.loads((OUT/"confirmation_selection.json").read_text())["selection"]
    text=f"""**2026-09-11新增：已完成免疫、蚁群、粒子群、烟花、增强遗传、贪心及动态重排实验。** 新增3969次离线执行（3069次比较+900次冻结确认），全部清除；连同首轮共5901次。正式/官方请求仍为0。完整表格、压力例、消融和配对统计见[新增算法报告]({PREFIX}/summary.md)。

**找到更优解：Q4三角格30424.73m → 29700m，减少724.73m，约2.38%。** 31个点的任意相邻距离至少990m，需要30条边，下界是29700m；新路线达到该固定点集的全局最短。免疫、蚁群、粒子群、烟花、增强遗传和迭代搜索的混合版本在5个种子中均达到下界，插入贪心也达到。其余三个既定点集原2-opt已经最短，不能继续靠重排缩短静态路长。

各算法搜索过程中使用相同的有限2-opt改进，属于显式混合算法。10000比较预算的消融中，移除这个改进后，免疫、遗传、粒子群、烟花均为0/5次达到下界，蚁群2/5次。因此群体机制与局部搜索贡献必须分别说明。[实现与参数]({PREFIX}/algorithm_notes.md)、[源代码](route_algorithms.py)、[动态重排](adaptive_routes.py)均已保存。

**新的完整任务结果：独立确认集每配置150场景。** 先在比较集筛选全清且普通/压力两类样本最慢时间不劣于基线的候选，再冻结选择并使用全新种子57..66确认；确认后不调参。

| 任务 | 冻结候选 | 每源均值：原2-opt→候选/s | 改善 | 最慢总时间：原2-opt→候选/s | 全清 |
|---|---|---:|---:|---:|---:|
"""
    for task in ("q3_active","q4_active","q4_conservative"):
        method=choices[task]["method"]
        base=next(r for r in confirmation if r["task"]==task and r["role"]=="baseline")
        cand=next(r for r in confirmation if r["task"]==task and r["role"]=="selected")
        gain=next(r for r in paired if r["task"]==task)
        text+=f"| {task} | {LABELS[method]} | {float(base['mean_per_source_s']):.1f}→{float(cand['mean_per_source_s']):.1f} | {float(gain['gain_per_source_pct']):.2f}% | {float(base['worst_total_s']):.1f}→{float(cand['worst_total_s']):.1f} | {cand['all_cleared']}/{cand['n']} |\n"
    q4base=next(r for r in confirmation if r["task"]=="q4_active" and r["role"]=="baseline")
    q4cand=next(r for r in confirmation if r["task"]=="q4_active" and r["role"]=="selected")
    q4pair=next(r for r in paired if r["task"]=="q4_active")
    text+=f"""
**烟花的尾部优势没有在确认集保持。** 最慢总时间增加{float(q4cand['worst_total_s'])-float(q4base['worst_total_s']):.1f}s；{q4pair['slower_cases']}/150例比原2-opt慢，最大单例增加{float(q4pair['worst_regression_s']):.1f}s。因此它是有均值收益和尾部代价的候选，不能宣称全面超过2-opt，也不因此替换原Q4保守配置。

Q3与Q4保守的冻结选择仍是基线，表中0%是相同策略的重复执行，不能当作新算法泛化证据。动态重排的均值虽改善，但压力尾部未通过预设门槛，因此暂不替换这两个配置。900次确认里600次属于这些重复基线，Q4主动为150对不同策略的比较。

静态最短不等于完整任务最快：插入贪心和蚁群虽生成29700m最短路线，在主比较普通场景中平均每源时间反而高于旧2-opt；清除绕行、检测和发现顺序会改变总时间。每例都更快的承诺也不成立，[确认集退化案例]({PREFIX}/confirmation/performance_regressions.csv)完整列出了反例。

静态算法保留全部必需顶点；动态算法每次从未访问集合选一站并删除。几何覆盖、每源有限光学兜底、16源公开上界/完整覆盖结束证书，以及原宽松238102秒虚拟时间上界均保留。本轮新增65项算法检查及{check['passed']}项最终复核通过，含12条只用反馈的完整请求重放；原题面/附件、公共探索代码和两个上游副本均未改变。[复核记录]({PREFIX}/final_checks.json)。

本机可直接试新候选（仅运行同学离线benchmark）：

```bash
/Users/dingdingzai/anaconda3/bin/python -B B/run_smart_robot.py --task q3_active
/Users/dingdingzai/anaconda3/bin/python -B B/run_smart_robot.py --task q4_active --method fireworks
/Users/dingdingzai/anaconda3/bin/python -B B/run_smart_robot.py --task q4_conservative
```

仍推荐把B列为主候选；国奖判断尚缺本队官方演练和论文质量证据。这些合成统计不构成官方成绩。新入口没有HTTP/正式模式，旧Windows策略包保留原版本；官方运行仍需用户实际提供Windows/VM、官方软件、本队演练与日志条件后进行。
"""
    (ROOT/"REPORT_ALGORITHM_UPDATE.md").write_text(text)
    subprocess.run([sys.executable,"-B",str(ROOT/"write_report.py")],check=True)
    old=ROOT/"FINAL_MANIFEST.json"
    preserved=OUT/"previous_final_manifest_1932.json"
    if not preserved.exists():preserved.write_bytes(old.read_bytes())
    # Files added after the main launch are also preserved, with a separate hash set.
    later=OUT/"final_code_snapshot"
    later.mkdir(exist_ok=True)
    hashes={}
    parsed=0
    for path in sorted(ROOT.glob("*.py")):
        ast.parse(path.read_text(),filename=str(path)); parsed+=1
        raw=path.read_bytes();(later/path.name).write_bytes(raw)
        hashes[str(path.relative_to(ROOT.parent))]=hashlib.sha256(raw).hexdigest()
    broken=[]
    for path in (ROOT/"REPORT.md",OUT/"summary.md"):
        for match in re.finditer(r"\]\(([^)]+)\)",path.read_text()):
            target=match.group(1).split("#",1)[0]
            if not target or "://" in target:continue
            if not (path.parent/target).exists():broken.append({"file":str(path),"target":target})
    assert not broken,broken
    for path in (ROOT/"REPORT.md",ROOT/"REPORT_ALGORITHM_UPDATE.md",OUT/"summary.md",OUT/"selected_routes.json",OUT/"final_checks.json"):
        hashes[str(path.relative_to(ROOT.parent))]=hashlib.sha256(path.read_bytes()).hexdigest()
    manifest={"python_files_parsed":parsed,"broken_report_links":broken,"main_executions":732,"peer_executions":1200,
              "new_comparison_executions":3069,"new_confirmation_executions":900,"total_offline_executions":5901,
              "count_scope":"Completed scored benchmark executions; excludes unit checks, feedback replay and CLI smoke runs",
              "official_calls":0,"all_scored_runs_cleared":True,"previous_manifest":str(preserved.relative_to(ROOT)),"sha256":hashes}
    old.write_text(json.dumps(manifest,indent=2))
    (OUT/"final_manifest.json").write_text(json.dumps(manifest,indent=2))
    print(json.dumps({"total_offline_executions":5901,"parsed":parsed,"broken_links":broken}))


if __name__=="__main__":main()
