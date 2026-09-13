"""Report frozen confirmation, paired regressions and independent-seed blocks."""
import csv
import json
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parent
OUT=ROOT/"experiments/runs/2026-09-11_icra-confirmation"


def main():
    rows=[json.loads(line) for line in (OUT/"trials.jsonl").read_text().splitlines()]
    pairs={3:(("joint7","peer_layout9_proxy"),("joint9","peer_layout9_proxy"),("joint7","joint9")),
           4:(("joint22","square45_conservative"),("replacement22","square45_conservative"),
              ("joint22","polar25_conservative"),("replacement22","joint22"),("joint22","joint25"))}
    analyses=[];rng=np.random.default_rng(42)
    for problem,comparisons in pairs.items():
        for candidate,baseline in comparisons:
            for split in ("ordinary","stress"):
                group=[r for r in rows if r["problem"]==problem and r["method"]==candidate and r["split"]==split]
                base={r["case_id"]:r for r in rows if r["problem"]==problem and r["method"]==baseline and r["split"]==split}
                delta=np.array([r["total_virtual_s"]-base[r["case_id"]]["total_virtual_s"] for r in group])
                item=dict(problem=problem,candidate=candidate,baseline=baseline,split=split,runs=len(group),
                    mean_per_source_improvement_fraction=1-np.mean([r["per_source_s"] for r in group])/np.mean([r["per_source_s"] for r in base.values()]),
                    faster=int((delta<-1e-6).sum()),slower=int((delta>1e-6).sum()),tied=int((abs(delta)<=1e-6).sum()),
                    worst_regression_s=float(max(0.,delta.max())),worst_case=group[int(delta.argmax())]["case_id"] if delta.max()>1e-6 else None,
                    maximum_paired_delta_s=float(delta.max()),
                    command_increases=sum(r["commands"]>base[r["case_id"]]["commands"] for r in group),
                    regressions=[dict(case_id=r["case_id"],delta_s=float(d),candidate_s=r["total_virtual_s"],baseline_s=base[r["case_id"]]["total_virtual_s"]) for r,d in zip(group,delta) if d>1e-6])
                if split=="ordinary":
                    # Repeat errors for a seed are correlated; resample ten seed
                    # blocks, preserving all 15 layout/error settings together.
                    seeds=sorted({r["seed"] for r in group});a=[];b=[]
                    for seed in seeds:
                        subset=[r for r in group if r["seed"]==seed]
                        a.append(np.mean([r["per_source_s"] for r in subset]));b.append(np.mean([base[r["case_id"]]["per_source_s"] for r in subset]))
                    indices=rng.integers(0,len(seeds),(10000,len(seeds)))
                    effect=1-np.array(a)[indices].mean(axis=1)/np.array(b)[indices].mean(axis=1)
                    item["seed_block_bootstrap_95_interval"]=np.quantile(effect,[.025,.975]).tolist()
                analyses.append(item)
    (OUT/"paired_analysis.json").write_text(json.dumps(dict(base_seed=42,replicates=10000,cluster="seed; preserve 15 layout/error conditions; 10 clusters only",comparisons=analyses),indent=2))
    by_category=[]
    for problem in (3,4):
        for method in sorted({r["method"] for r in rows if r["problem"]==problem}):
            for category in sorted({r["category"] for r in rows if r["problem"]==problem}):
                g=[r for r in rows if r["problem"]==problem and r["method"]==method and r["category"]==category]
                by_category.append(dict(problem=problem,method=method,category=category,runs=len(g),all_cleared=sum(r["all_cleared"] for r in g),mean_per_source_s=np.mean([r["per_source_s"] for r in g]),max_per_source_s=max(r["per_source_s"] for r in g),max_total_s=max(r["total_virtual_s"] for r in g),mean_commands=np.mean([r["commands"] for r in g])))
    with (OUT/"category_metrics.csv").open("w") as f:
        writer=csv.DictWriter(f,fieldnames=by_category[0].keys());writer.writeheader();writer.writerows(by_category)
    selected=[(3,"peer_layout9_proxy"),(3,"joint7"),(3,"joint9"),(4,"square45_conservative"),(4,"joint25"),(4,"joint22"),(4,"replacement22")]
    table=["|问题/策略|普通全清|普通每源秒|压力全清|压力每源秒|普通/压力最大总秒|普通/压力平均指令|普通/压力最大策略墙钟秒|", "|---|---:|---:|---:|---:|---:|---:|---:|"]
    summary=list(csv.DictReader((OUT/"summary.csv").open()))
    for problem,method in selected:
        a=next(r for r in summary if int(r["problem"])==problem and r["method"]==method and r["split"]=="ordinary")
        b=next(r for r in summary if int(r["problem"])==problem and r["method"]==method and r["split"]=="stress")
        table.append(f"|Q{problem} {method}|{a['all_cleared']}/{a['runs']}|{float(a['mean_per_source_s']):.2f}|{b['all_cleared']}/{b['runs']}|{float(b['mean_per_source_s']):.2f}|{float(a['max_total_s']):.2f}/{float(b['max_total_s']):.2f}|{float(a['mean_commands']):.2f}/{float(b['mean_commands']):.2f}|{float(a['max_wall_s']):.4f}/{float(b['max_wall_s']):.4f}|")
    update="""## 2026-09-11：ICRA联系、联合策略与未查看场景确认

当前仍推荐B作为可认真选择的主候选；已从只优化固定路线，推进到有界误差定位、共享测向、联合扫描/清除调度和更少的定向覆盖点。**尚未达到“全面且大幅超过截图”的goal，保持active。** 没有本队官方成绩，也没有同学一完整源码，不能宣称打败其完整实现或给出国奖概率。

### 论文启发与实际实现

已完整读取Tokekar–Isler的6页ICRA2013论文并保存作者原文。它与B题相似的是有界角误差、可行区域及最坏几何，不是准确直线交点；静态传感器数量目标与其可见性假设不能直接替代B题的移动、有限半径、180°盲区和未知数量。[具体联系、来源和独立推导](ICRA_CONNECTION.md)。

这次新增三项实质算法：①在已到达位置共享有用测向，把未来扫描站与已发现源的可行集中心放入同一动态路线；②为定向源推导成对前向探测，两次合法无信号才产生安全位置上界；③直接用局部接收站点的凸包证明全方向覆盖，找到22点布局。可行集中心只预测路线，真实清除仍用MEC包含或带有限兜底的明确试探。[联合任务实现](joint_task_policy.py)、[成对探测](bracket_policy.py)、[方向覆盖证书](visibility_certificate.py)。

### 独立确认结果

参数先冻结，随后生成seed77—86及新的45种压力组合；共**1950次执行全部清除，无异常**，用时108.48s。每种策略有150个普通、45个压力场景，源数10/13/16等未知，压力包括边界朝外、切向、最小半径、近共线、远处频道20和端点/空间误差。真实位置只用于后端与事后评分。

"""+"\n".join(table)+"""

全表含平均总时间、P95、源数加权每源时间、CPU和初始化：[确认结果](experiments/runs/2026-09-11_icra-confirmation/summary.md)。墙钟为同机单线程的策略运行时间，含本地Client/后端，不含导入、生成和写日志；初始化另列，不能直接等同截图的官方程序耗时。所有逐例变慢记录与按种子分块的区间估计见[配对分析](experiments/runs/2026-09-11_icra-confirmation/paired_analysis.json)。

[确认结果图](experiments/runs/2026-09-11_icra-confirmation/confirmation_comparison.png)与[可导出PDF](experiments/runs/2026-09-11_icra-confirmation/confirmation_comparison.pdf)分开显示普通和压力均值；[22点覆盖证书图](experiments/runs/2026-09-11_icra-confirmation/directional22_certificate.pdf)显示全部2414个保留方格。

Q3七点联合策略普通集比同后端九点布局代理的平均每源时间低28.47%，150例均更快；压力45例中9例反而变慢。九点联合策略普通均值略差但普通最大总时间更小，压力仅2例慢于代理。Q3推荐同时保留七点效率版与九点更宽覆盖余量版；目前没有逐例或所有指标同时占优的单一版本。

Q4二十二点联合策略比旧方格保守在普通和压力均值上明显改善，全部195例虚拟时间更短；然而与更强的二十五点联合策略比较，普通均值较好、压力均值及最大时间较差。二十二点替代版的普通均值更低，但额外覆盖计算增加CPU和墙钟；这一权衡不能称为全面改善。未知总数与16个已发现频道的公开上限产生的节省必须与“替代扫描”的机制分开统计。

确认中的替代版实际替代扫描和替代站点均为0；普通/压力分别跳过309/35个站点，全部来自已发现16个唯一频道的公开上限。下一轮应将此规则独立实现，再用新场景确认；不能把其收益归给没有触发的动态凸包替代算法。

### 截图目标仍未达成

截图自报Q3 341.05s、Q4 658.00s；其40/40不是可确认的40局，缺逐局日志与口径。[当前goal](GOAL.md)暂定普通平均每源240/460s，同时报告压力尾部。确认中Q3七点为243.96s，Q4最低候选为488.36s，**均未达到这个固定口径**；压力仍约286/617s。Q3按源数加权为239.24s，但不能临时换聚合方式宣称达标。九点代理恰为341.07s与截图接近，也只是本次合成数据的数值巧合，不能作为复现官方成绩的证据。

### 保证、负结果和复现入口

覆盖、成对无信号、动态替代与有限停止的完整证明见[保证更新](ROBUST_GUARANTEES_UPDATE.md)。新家族固定预算下的宽松虚拟上界264096s≈73.36h<100h；它不是运行均值，也不是任意病态浮点/硬件墙钟的形式化保证。

[60项最终复核](experiments/runs/2026-09-11_icra-confirmation/final_checks.json)通过，包括40条只经已记录公开反馈的完整请求重放、重放后真值对所有保留区域的包含核查、11个布局全部方格的独立凸包/距离及完整分割检查、原件和上游只读校验。

负结果均保留：仅缩短静态路线不保证整局更快；方格/交错单环没有全面胜出；纯延后清除在压力尾部退步；协方差排名可显著降低CPU但不能作置信证书；成对探测单独使用的普通均值可能变差；途中替代在Q4普通训练并未节省虚拟时间。训练记录：[联合调度](experiments/runs/2026-09-11_joint-search/summary.md)、[非单环布局](experiments/runs/2026-09-11_layout-alternatives/summary.md)、[共享与成对](experiments/runs/2026-09-11_spatial-decisions/summary.md)、[联合任务路线](experiments/runs/2026-09-11_joint-task-routing/summary.md)、[22点与替代](experiments/runs/2026-09-11_convex-visibility/summary.md)。

新增独立离线入口[run_bounded_robot.py](run_bounded_robot.py)：`python -B B/run_bounded_robot.py --problem 3 --method joint7 --seed 42`；第四问可选`--problem 4 --method joint22`。实际Python仍使用用户指定的`/Users/dingdingzai/anaconda3/bin/python`；入口没有正式HTTP模式，输出B/robot_runs。原HttpTransport协议客户端继续保留，当前不调用正式服务。

累计完成的计分离线执行为**16131次**，其中本轮六组新增9390次（含1950确认）；重复训练场景上的不同策略执行不等于独立场景数，更不是官方成绩。单元检查、反馈重放、CLI冒烟均不计入。后续继续优化需使用独立的新确认流，不能把77—86反复调成“测试集最优”。本队官方验证尚缺当前机器可运行的Windows/官方软件、用户实际提供的演练条件与合法登录状态、真实端到端日志；未注册账号、未使用报名身份、正式请求0。
"""
    (ROOT/"REPORT_ICRA_UPDATE.md").write_text(update)
    print("Wrote paired analysis, category metrics and REPORT_ICRA_UPDATE.md")


if __name__=="__main__":main()
