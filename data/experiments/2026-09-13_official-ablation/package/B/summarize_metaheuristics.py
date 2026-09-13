"""Summaries keep ordinary cases, stress cases and untouched confirmation separate."""
from collections import defaultdict
import csv
import json
import os
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parent
OUT=ROOT/"experiments/runs/2026-09-10_metaheuristics"
LABELS={"greedy":"最近邻贪心","insertion_greedy":"插入贪心","two_opt":"原2-opt",
        "genetic":"增强遗传+2-opt","immune":"免疫+2-opt","ant_colony":"蚁群+2-opt",
        "particle_swarm":"粒子群+2-opt","fireworks":"烟花+2-opt","iterated_search":"迭代搜索+2-opt",
        "adaptive_greedy":"在线贪心重排","adaptive_two_opt":"在线2-opt重排"}


def csvwrite(path,rows):
    with path.open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=sorted(set().union(*(r.keys() for r in rows))))
        w.writeheader();w.writerows(rows)


def summarize(rows):
    grouped=defaultdict(list)
    for r in rows:
        grouped[(r["task"],r["method"],r["split"],r.get("role",""))].append(r)
        if r["split"]!="confirmation":
            grouped[(r["task"],r["method"],"all_comparison","")].append(r)
    result=[]
    for (task,method,split,role),rs in grouped.items():
        def arr(field): return np.array([r[field] for r in rs],float)
        v=arr("total_virtual_s")
        result.append({"task":task,"method":method,"split":split,"role":role,"n":len(rs),
            "all_cleared":sum(r["all_cleared"] for r in rs),"errors":sum(bool(r["failure"]) for r in rs),
            "all_clear_rate":float(np.mean([r["all_cleared"] for r in rs])),
            "mean_total_s":float(v.mean()),"p95_total_s":float(np.percentile(v,95)),"worst_total_s":float(v.max()),
            "mean_per_source_s":float(arr("per_source_s").mean()),"worst_per_source_s":float(arr("per_source_s").max()),
            "pooled_per_source_s":float(v.sum()/arr("cleared").sum()),"mean_commands":float(arr("commands").mean()),
            "max_commands":int(arr("commands").max()),"mean_move_m":float(arr("move_m").mean()),
            "mean_measurements":float(arr("measurements").mean()),"mean_clear_calls":float(arr("clear_calls").mean()),
            "mean_switches":float(arr("switches").mean()),"mean_wall_s":float(arr("wall_s").mean()),
            "p95_wall_s":float(np.percentile(arr("wall_s"),95)),"max_wall_s":float(arr("wall_s").max()),
            "mean_cpu_s":float(arr("cpu_s").mean()),"sum_cpu_s":float(arr("cpu_s").sum()),
            "mean_stations":float(arr("stations_visited").mean()),
            "stop_at_16":sum(r["stop_reason"]=="public_upper_bound_16" for r in rs),
            "stop_full_coverage":sum(r["stop_reason"]=="full_coverage_and_all_discovered_cleared" for r in rs),
            "worst_case_id":max(rs,key=lambda r:r["total_virtual_s"])["case_id"]})
    return result


def paired(rows):
    baseline={(r["task"],r["case_id"]):r for r in rows if r["method"]=="two_opt" and r.get("role","baseline")=="baseline"}
    groups=defaultdict(list)
    failures=[]
    for r in rows:
        if r["method"]=="two_opt" and r.get("role","baseline")=="baseline": continue
        b=baseline[(r["task"],r["case_id"])]
        item={"task":r["task"],"method":r["method"],"split":r["split"],"case_id":r["case_id"],
              "category":r["category"],"seed":r["seed"],"baseline_s":b["total_virtual_s"],"candidate_s":r["total_virtual_s"],
              "delta_s":r["total_virtual_s"]-b["total_virtual_s"],"baseline_per_source_s":b["per_source_s"],
              "candidate_per_source_s":r["per_source_s"],"sources":r["sources"],"all_cleared":r["all_cleared"]}
        groups[(r["task"],r["method"],r["split"])].append(item)
        if item["delta_s"]>1e-6: failures.append(item)
    result=[]
    for index,((task,method,split),rs) in enumerate(sorted(groups.items())):
        delta=np.array([r["delta_s"] for r in rs])
        base=np.array([r["baseline_per_source_s"] for r in rs])
        cand=np.array([r["candidate_per_source_s"] for r in rs])
        row={"task":task,"method":method,"split":split,"n":len(rs),
             "gain_per_source_pct":float(100*(1-cand.mean()/base.mean())),
             "mean_delta_total_s":float(delta.mean()),"faster_cases":int((delta<-1e-6).sum()),
             "tied_cases":int((np.abs(delta)<=1e-6).sum()),"slower_cases":int((delta>1e-6).sum()),
             "worst_regression_s":float(delta.max()),"worst_regression_case":rs[int(np.argmax(delta))]["case_id"]}
        if split in ("ordinary","confirmation"):
            # Error fields on one source layout are correlated: resample entire layouts.
            blocks=defaultdict(list)
            for j,r in enumerate(rs):
                blocks[(r["category"].split("__")[0],r["seed"])].append(j)
            block_values=list(blocks.values())
            rng=np.random.default_rng(np.random.SeedSequence([42,30,index]))
            values=[]
            for _ in range(2000):
                ids=np.concatenate([block_values[int(i)] for i in rng.integers(len(block_values),size=len(block_values))])
                values.append(100*(1-cand[ids].mean()/base[ids].mean()))
            row.update(layout_blocks=len(blocks),bootstrap_gain_pct_low=float(np.percentile(values,2.5)),
                       bootstrap_gain_pct_high=float(np.percentile(values,97.5)))
        result.append(row)
    return result, sorted(failures,key=lambda r:r["delta_s"],reverse=True)


def table(summary,task,split,methods=None):
    lines=["| 算法 | 全清 | 总虚拟时间均值/s | 每源均值/s | 最慢总时间/s | 平均指令 | 平均/最大墙钟/s |",
           "|---|---:|---:|---:|---:|---:|---:|"]
    for r in summary:
        if r["task"]!=task or r["split"]!=split or (methods is not None and r["method"] not in methods): continue
        label=LABELS[r['method']]+("（冻结选择）" if r.get("role")=="selected" else "")
        lines.append(f"| {label} | {r['all_cleared']}/{r['n']} | {r['mean_total_s']:.1f} | {r['mean_per_source_s']:.1f} | {r['worst_total_s']:.1f} | {r['mean_commands']:.1f} | {r['mean_wall_s']:.3f}/{r['max_wall_s']:.3f} |")
    return "\n".join(lines)


def figures(summary,confirmation):
    os.environ.setdefault("MPLCONFIGDIR",str(ROOT/".mplconfig"))
    os.environ.setdefault("XDG_CACHE_HOME",str(ROOT/".cache"))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    target=OUT/"figures"
    target.mkdir(exist_ok=True)
    paths=json.loads((OUT/"selected_routes.json").read_text())["q4_triangle"]
    fig,axs=plt.subplots(1,3,figsize=(13,4.3),sharex=True,sharey=True)
    for ax,method,title in zip(axs,("two_opt","immune","insertion_greedy"),("Original 2-opt","Immune + 2-opt","Insertion greedy")):
        p=np.array(paths[method]["points"])/1000
        theta=np.linspace(0,2*np.pi,240)
        ax.plot(1.8*np.cos(theta),1.8*np.sin(theta),"--",c=".7",lw=1)
        ax.plot(p[:,0],p[:,1],"o-",ms=3,lw=1)
        ax.scatter([0],[0],marker="*",c="black",s=100,zorder=5)
        ax.scatter(p[-1,0],p[-1,1],marker="s",c="orange",s=50,zorder=5)
        ax.set_aspect("equal")
        ax.set_title(f"{title}\n{paths[method]['length_m']:.2f} m")
        ax.set_xlabel("x / km")
    axs[0].set_ylabel("y / km")
    fig.tight_layout()
    for suffix in ("png","pdf"):fig.savefig(target/f"q4_static_routes.{suffix}",dpi=180)
    plt.close(fig)
    fig,axs=plt.subplots(1,3,figsize=(13,4))
    for ax,task in zip(axs,("q3_active","q4_active","q4_conservative")):
        base=[r for r in confirmation if r["task"]==task and r["role"]=="baseline"]
        selected={r["case_id"]:r for r in confirmation if r["task"]==task and r["role"]=="selected"}
        x=np.array([r["total_virtual_s"] for r in base])/1000
        y=np.array([selected[r["case_id"]]["total_virtual_s"] for r in base])/1000
        lo,hi=min(x.min(),y.min()),max(x.max(),y.max())
        ax.plot([lo,hi],[lo,hi],"--",c=".5")
        ax.scatter(x,y,s=13,alpha=.5)
        ax.set_title(task.replace("_"," "))
        ax.set_xlabel("Baseline / 1000 virtual seconds")
        ax.set_ylabel("Frozen candidate / 1000 virtual seconds")
        ax.set_aspect("equal",adjustable="box")
    fig.tight_layout()
    for suffix in ("png","pdf"):fig.savefig(target/f"confirmation_pairs.{suffix}",dpi=180)
    plt.close(fig)


def main():
    completion=json.loads((OUT/"completion.json").read_text())
    conf_completion=json.loads((OUT/"confirmation/completion.json").read_text())
    rows=[json.loads(line) for line in (OUT/"trials.jsonl").read_text().splitlines()]
    confirm=[json.loads(line) for line in (OUT/"confirmation/trials.jsonl").read_text().splitlines()]
    summary=summarize(rows)
    csummary=summarize(confirm)
    pairs,regressions=paired(rows)
    cpairs,cregressions=paired(confirm)
    csvwrite(OUT/"summary.csv",summary)
    csvwrite(OUT/"paired_summary.csv",pairs)
    csvwrite(OUT/"performance_regressions.csv",regressions)
    csvwrite(OUT/"confirmation/summary.csv",csummary)
    csvwrite(OUT/"confirmation/paired_summary.csv",cpairs)
    csvwrite(OUT/"confirmation/performance_regressions.csv",cregressions)
    static=list(csv.DictReader((OUT/"static_trials.csv").open()))
    q4=[r for r in static if r["point_set"]=="q4_triangle"]
    smd=["| 算法 | 重复数 | 最好/最差路线/m | 达到下界 | 平均预计算/ms |", "|---|---:|---:|---:|---:|"]
    for method in LABELS:
        rs=[r for r in q4 if r["method"]==method]
        if not rs:continue
        vs=[float(r["best_m"]) for r in rs]
        smd.append(f"| {LABELS[method]} | {len(rs)} | {min(vs):.2f}/{max(vs):.2f} | {sum(r['certified_optimal']=='True' for r in rs)}/{len(rs)} | {1000*np.mean([float(r['wall_s']) for r in rs]):.2f} |")
    abl=list(csv.DictReader((OUT/"ablation.csv").open()))
    amd=["| 算法 | 无局部搜索：达下界/5，平均路长/m | 有局部搜索：达下界/5，平均路长/m |", "|---|---:|---:|"]
    for method in dict.fromkeys(r["method"] for r in abl):
        cells=[]
        for polish in ("False","True"):
            rs=[r for r in abl if r["method"]==method and r["polish_enabled"]==polish]
            cells.append(f"{sum(r['certified_optimal']=='True' for r in rs)}/5，{np.mean([float(r['best_m']) for r in rs]):.2f}")
        amd.append(f"| {LABELS[method].replace('+2-opt','')} | {' | '.join(cells)} |")
    chosen=json.loads((OUT/"confirmation_selection.json").read_text())["selection"]
    text=f"""# 新增智能算法与更优解：离线比较及确认

2026-09-10启动，跨日完成；基础种子42；所有写入B/。本轮新增{completion['executions']}次配对比较及{conf_completion['executions']}次独立确认，共{completion['executions']+conf_completion['executions']}次离线执行。全清次数分别为{completion['all_cleared']}和{conf_completion['all_cleared']}，异常分别为{completion['errors']}和{conf_completion['errors']}。不含任何官方测试。

**结果一：第四问三角格从30424.73m改为29700m，缩短724.73m（2.3820%），达到该31点集的全局最短路长。** 多种群体混合算法和插入贪心均达到下界；不能据本例认定复杂群体算法优于简单插入贪心。固定点集的最优性不代表覆盖点布局或完整任务的全局最优。

**结果二：完整任务收益需要在线评估。** 动态重排只用当前已接受位置和剩余必需站点，补偿主动定位/清除造成的绕行。最短的固定路线与最短的完整任务不是同一个目标。

**实现与预算**

代码：[route_algorithms.py](../../../route_algorithms.py)、[adaptive_routes.py](../../../adaptive_routes.py)。具体克隆、信息素、速度、火花机制和参数见[算法说明](algorithm_notes.md)。六个随机算法为显式混合版本，共用有限2-opt；主试验种子42..46，每算法最多100000次候选比较，达到下界提前停止。完整路径评分与增量评分并非等CPU工作量，墙钟单独报告；初解计算计入墙钟，未计入搜索预算。旧遗传的实现和历史结果保留，本轮增强遗传并非旧参数原样重跑。

{chr(10).join(smd)}

另外三个点集的原2-opt均已达到下界：650方格31200m、700裁剪方格31669.848481m、Q3三角格30600m。它们的随机方法在验证初解达到下界后提前结束，没有声称在那里进行了有效群体搜索。

**最优性证明**

每个必需点互不相同且包含原点，存在最优路线先访问原点；若某路线后访原点，将它提前并用三角不等式跳过其原位置不增路长。因此只需固定原点首站的开放排列。Q4三角格任意两点距离≥990m，31点要走30条边，故L≥29700m；新路线每边恰990m，达到下界。Q3同理18×1700=30600m。650方格48×650=31200m。

裁剪方格需加强下界：以格点坐标和奇偶染色，与原点同色的A有21点、B有24点。从A出发的排列最多容纳21个B段，因此至少24−21=3条同色相邻边。同色最短边≥700√2m，异色边≥700m，故L≥44×700+3×700(√2−1)=31669.848481m，原2-opt恰达到。这里的「最优」针对保留全部既定检测点的开放路线。

![固定点集路线](figures/q4_static_routes.png)

**局部搜索消融**

另做6算法×5种子×2模式，共60次优化，双方比较预算均为10000，仍用共同2-opt初解。这是删除搜索过程中的局部改进，不是删除初解中的2-opt；主实验的100000预算不能与此表直接混排。数据见[ablation.csv](ablation.csv)。

{chr(10).join(amd)}

消融结果用于解释局部搜索的贡献。本轮只优化19/31/45/49点的小型结构点集，没有据此提出新的通用元启发式算法。

**普通场景比较：每策略75例**

同学原版进程内协议，3种位置分布×5种固定空间误差×5个新种子52..56。真实源数、位置、半径、方向不传给策略；只在外部评分器统计全清和每源时间。路线先按静态长度冻结，再开始完整任务，见[routes_frozen_before_evaluation.json](routes_frozen_before_evaluation.json)。同一组下各算法全程定位与光学兜底参数相同。

Q3三角格主动：

{table(summary,'q3_active','ordinary')}

Q4三角格主动：

{table(summary,'q4_active','ordinary')}

Q4裁剪方格保守：

{table(summary,'q4_conservative','ordinary')}

**压力场景：每策略18例，单独报告**

边界朝外且接收半径1000m、近共线且半径1000m、10/16源未知数量且频道20位于远端。每类都配正/负/空间变号的±1°固定误差。Q4每场至少一个全向源，其他源朝外；没有把定向源误当全向。误差是静态压力场，不是针对策略求出的全局最坏攻击。

Q3：

{table(summary,'q3_active','stress')}

Q4主动：

{table(summary,'q4_active','stress')}

Q4保守：

{table(summary,'q4_conservative','stress')}

**冻结选择后的独立确认：每任务150例**

主比较集可用于候选选择，因此单独使用此前未用的种子57..66。先执行[已记录的选择规则](confirmation_plan.md)：全清且普通/压力两类的样本最大时间均不劣于原2-opt，再按普通场景平均每源时间选优。选中的Q3、Q4主动、Q4保守分别为{LABELS[chosen['q3_active']['method']]}、{LABELS[chosen['q4_active']['method']]}、{LABELS[chosen['q4_conservative']['method']]}。选择结果在确认集第一例前写入[冻结记录](confirmation_selection.json)，确认后不调参换路线。

{table(csummary,'q3_active','confirmation')}

{table(csummary,'q4_active','confirmation')}

{table(csummary,'q4_conservative','confirmation')}

"""
    for r in cpairs:
        text+=f"{r['task']}：平均每源时间下降{r['gain_per_source_pct']:.2f}%，按场景布局整体重采样的95%bootstrap区间[{r['bootstrap_gain_pct_low']:.2f}%, {r['bootstrap_gain_pct_high']:.2f}%]；{r['faster_cases']}/{r['n']}例更快，{r['slower_cases']}例更慢，最大单例退化{r['worst_regression_s']:.1f}s（{r['worst_regression_case']}）。\n\n"
    base=next(r for r in csummary if r["task"]=="q4_active" and r["role"]=="baseline")
    cand=next(r for r in csummary if r["task"]=="q4_active" and r["role"]=="selected")
    text+=f"**尾部确认没有保持初筛优势：** Q4烟花在确认集的最慢总时间从基线{base['worst_total_s']:.1f}s变为{cand['worst_total_s']:.1f}s，增加{cand['worst_total_s']-base['worst_total_s']:.1f}s（{100*(cand['worst_total_s']/base['worst_total_s']-1):.2f}%）。这是均值收益与尾部代价的候选，不是对基线逐场景支配的策略；不因均值下降就替换原Q4保守配置。\n\n"
    text+="""若冻结选择仍是原2-opt，该任务的baseline/selected是真实执行两次相同策略，不能当作两个独立算法的比较或额外泛化证据。本次Q3和Q4保守均属此类，900次确认中600次为这两组重复基线；Q4主动的300次才是150对不同策略比较。动态重排的平均收益保留在主比较表，但因压力尾部未通过预设门槛，未在此确认集单独验证。

同一位置/种子的五个误差条件相关，bootstrap按完整布局分块，保留这种相关性；该区间描述合成分布的有限样本不确定性，不是所有场景保证，更不是官方分数区间。平均每源是逐局time/cleared后平均，另存pooled每源口径，二者不混用。

![确认集配对结果](figures/confirmation_pairs.png)

**失败与退化、发现/清除/结束保证**

未清除、异常与性能退化分别记录。即便全清率100%，某些场景仍会更慢；[主比较退化例](performance_regressions.csv)和[确认集退化例](confirmation/performance_regressions.csv)列出全部相对基线更慢的案例，原始轨迹可复放。光学兜底和最大三次主动检测参数未改，不能宣称每例都提速。

静态重排保留每个必需顶点；动态重排每次从剩余集合取一个并删除，最多原点集大小次。全覆盖的几何条件不受顺序影响，未知频道仍逐站扫描，达到16个公开上界或完整覆盖且全部已发现源清除才结束。原有每源≤108个光学兜底点的有限清除保证仍适用。已有宽松238102秒虚拟时间界仅用站点数、转移距离和每源动作上限，未假定特定顺序，故同样适用于本轮重排。它不包含无限断网重试，也不把有限压力样本当成严格最坏证明。

静态优化应在进入会话之前完成。本轮记录单次预计算和在线墙钟；动态重排的计算发生在会话内、CPU与墙钟均计入，但计算本身不增加题面虚拟移动时间。在线测时可能受并行单线程消融和其他主机负载影响，毫秒级差异不宜作为算法优劣依据。

**官方验证与选B建议**

本轮没有官方连接、账户注册、报名身份或正式机会消耗。同学核心代码冻结为c477d366，macOS handoff的ededa9e13版本核心相同；handoff并不意味着这台Mac已具备官方Windows环境。仍需用户真实提供Windows/VM、官方软件和本队演练条件后，验证当前候选的接口、现实限时、最慢运行与官方日志要求。

继续推荐将B作为主候选：目前有可证明的覆盖与结束、四个固定点集的最短路线证书、可复现的群体算法消融和反馈驱动改进。国奖可行性仍由官方真实表现和论文质量决定；合成全清次数不能折算获奖概率。论文应写清“覆盖保证+误差集合定位+动态重排”的问题结构，给复杂算法和简单基线相同评价机会。

原1932次实验及旧策略包保留。本轮新增结果以本目录为准；旧包尚未包含新算法，不应把旧包当作已验证的新候选入口。
"""
    worst=max((r for r in cregressions if r["task"]=="q4_active"),key=lambda r:r["delta_s"])
    cases=[r for r in confirm if r["task"]=="q4_active" and r["case_id"]==worst["case_id"]]
    wb=next(r for r in cases if r["role"]=="baseline")
    wc=next(r for r in cases if r["role"]=="selected")
    text+=f"\n**一个可复核的性能失败例**\n\n{worst['case_id']}中，两策略均清除{wb['cleared']}源；烟花路线使总虚拟时间由{wb['total_virtual_s']:.3f}s升到{wc['total_virtual_s']:.3f}s。移动增加{wc['move_m']-wb['move_m']:.3f}m，测量增加{wc['measurements']-wb['measurements']}次，切换增加{wc['switches']-wb['switches']}次，光学清除调用增加{wc['clear_calls']-wb['clear_calls']}次。按题面计时，约{(wc['move_m']-wb['move_m'])/5:.3f}+{5*(wc['measurements']-wb['measurements'])}+{wc['switches']-wb['switches']}+{3*(wc['clear_calls']-wb['clear_calls'])}={worst['delta_s']:.3f}s，微秒舍入带来小于0.001s的差异。两者成功清除数相同，因此成功附加时间抵消。主动再测无信号次数由{wb['active_no_signal']}升到{wc['active_no_signal']}，光学兜底调用由{wb['optical_fallback_calls']}升到{wc['optical_fallback_calls']}；更短巡检路引出的观察顺序和兜底成本抵消了路长收益。指标与逐条轨迹见[案例记录](confirmation/worst_paired_case.json)。\n"
    (OUT/"summary.md").write_text(text)
    failures=[r for r in rows+confirm if not r["all_cleared"] or r["failure"]]
    (OUT/"failures.json").write_text(json.dumps(failures,indent=2))
    (OUT/"confirmation/worst_paired_case.json").write_text(json.dumps(cases,indent=2))
    (OUT/"next_steps.md").write_text("# 后续\n\n保持冻结候选，等待实际Windows/VM及官方演练条件；当前不进行官方操作。下一阶段先验证现实限时、重试和官方日志，再判断正式测试策略。继续优化应针对完整任务代价，既定站点排列已知的最短下界无需反复搜索。\n")
    figures(summary,confirm)
    print(json.dumps({"comparison":completion,"confirmation":conf_completion,"gains":cpairs},ensure_ascii=False,indent=2))


if __name__=="__main__":main()
