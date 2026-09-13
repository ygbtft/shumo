"""Generate metric tables and standalone scientific plots from saved executions."""
import csv
import json
import math
import os
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parent
os.environ.setdefault("MPLCONFIGDIR",str(ROOT/".mplconfig"))
os.environ.setdefault("XDG_CACHE_HOME",str(ROOT/".cache"))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Circle

RUNS=[ROOT/"experiments/runs/2026-09-10_independent",ROOT/"experiments/runs/2026-09-10_peer-benchmark"]


def save_csv(path,rows):
    with path.open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)


def aggregate(group):
    return {"runs":len(group),"all_cleared_rate":sum(r["all_cleared"] for r in group)/len(group),
            "min_clear_fraction":min(r["clear_fraction"] for r in group),
            "mean_total_s":float(np.mean([r["total_virtual_s"] for r in group])),
            "p95_total_s":float(np.quantile([r["total_virtual_s"] for r in group],.95)),
            "max_total_s":max(r["total_virtual_s"] for r in group),
            "mean_per_source_s":float(np.mean([r["per_source_s"] for r in group])),
            "max_per_source_s":max(r["per_source_s"] for r in group),
            "mean_commands":float(np.mean([r["commands"] for r in group])),
            "max_commands":max(r["commands"] for r in group),
            "mean_move_m":float(np.mean([r["move_m"] for r in group])),
            "mean_measurements":float(np.mean([r["measurements"] for r in group])),
            "mean_clear_calls":float(np.mean([r["clear_calls"] for r in group])),
            "mean_switches":float(np.mean([r["switches"] for r in group])),
            "mean_wall_s":float(np.mean([r["wall_s"] for r in group])),
            "max_wall_s":max(r["wall_s"] for r in group),
            "cpu_s_sum":sum(r["cpu_s"] for r in group),"exception_count":sum(bool(r["failure"]) for r in group)}


def summarize_run(out):
    rows=[json.loads(line) for line in (out/"trials.jsonl").read_text().splitlines()]
    overall=[]; category=[];paired=[]
    for mixed,strategy in sorted(set((r["mixed"],r["strategy"]) for r in rows)):
        g=[r for r in rows if r["mixed"]==mixed and r["strategy"]==strategy]
        overall.append({"problem":4 if mixed else 3,"strategy":strategy,**aggregate(g)})
        for cat in sorted(set(r["category"] for r in g)):
            category.append({"problem":4 if mixed else 3,"category":cat,"strategy":strategy,
                             **aggregate([r for r in g if r["category"]==cat])})
        if strategy!="square_greedy":
            base={r["case_id"]:r for r in rows if r["mixed"]==mixed and r["strategy"]=="square_greedy"}
            relative=[1-r["total_virtual_s"]/base[r["case_id"]]["total_virtual_s"] for r in g]
            paired.append({"problem":4 if mixed else 3,"strategy":strategy,"reference":"square_greedy",
                           "paired_mean_relative_time_saving":float(np.mean(relative)),
                           "paired_min_relative_time_saving":min(relative),"paired_max_relative_time_saving":max(relative),
                           "faster_case_fraction":float(np.mean(np.array(relative)>1e-10))})
    save_csv(out/"summary.csv",overall);save_csv(out/"by_category.csv",category);save_csv(out/"paired.csv",paired)
    failures=[r for r in rows if not r["all_cleared"] or r["failure"]]
    (out/"failures.json").write_text(json.dumps(failures,indent=2))
    worst={f"q{4 if m else 3}_{s}":max([r for r in rows if r["mixed"]==m and r["strategy"]==s],key=lambda r:r["total_virtual_s"])
           for m,s in sorted(set((r["mixed"],r["strategy"]) for r in rows))}
    (out/"worst_cases.json").write_text(json.dumps(worst,indent=2))
    text=["# 离线结果汇总","", "所有时间均计入最后一次清除之后的搜索；每源时间为每局总时间/该局清除数，再取局均值。", "",
          "| 问题 | 策略 | 局数 | 全清率 | 平均总秒 | 平均每源秒 | 最慢总秒 | 平均指令 | 最大墙钟秒 |",
          "|---|---|---:|---:|---:|---:|---:|---:|---:|"]
    for r in overall:
        text.append(f"| Q{r['problem']} | {r['strategy']} | {r['runs']} | {r['all_cleared_rate']:.0%} | {r['mean_total_s']:.1f} | {r['mean_per_source_s']:.1f} | {r['max_total_s']:.1f} | {r['mean_commands']:.1f} | {r['max_wall_s']:.3f} |")
    text.extend(["",f"运行失败/未全清案例数：{len(failures)}。无失败样本不构成最坏保证，证明及反例见 B/REPORT.md。",
                 "", "详细类别与尾部见 by_category.csv；成对收益见 paired.csv；逐指令反馈见 traces/；场景真值只供评分。"])
    (out/"summary.md").write_text("\n".join(text)+"\n")
    return overall,rows


def plots(main,peer):
    figures=ROOT/"figures";figures.mkdir(exist_ok=True)
    plt.rcParams.update({"font.size":10,"axes.spines.top":False,"axes.spines.right":False})
    names=["square_greedy","square_cropped_2opt","active_2opt","peer_baseline"]
    labels=["Square + greedy","Cropped + 2-opt","Active + 2-opt","Peer baseline"]
    fig,axes=plt.subplots(1,2,figsize=(11,4.1),layout="constrained")
    for ax,q in zip(axes,[3,4]):
        rows=[next(r for r in peer if r["problem"]==q and r["strategy"]==n) for n in names]
        ax.bar(np.arange(len(rows)),[r["mean_per_source_s"] for r in rows],color=["#8797a8","#58a4a0","#e3a343","#b4b4b4"])
        for i,r in enumerate(rows):ax.text(i,r["mean_per_source_s"]+25,f"{r['mean_per_source_s']:.0f}",ha="center")
        ax.set_xticks(np.arange(4),labels,rotation=18,ha="right")
        ax.set_title(f"Q{q}: independent peer backend (150 cases)");ax.set_ylabel("Mean virtual seconds per cleared source")
        ax.set_ylim(0,2150)
    fig.savefig(figures/"peer_comparison.png",dpi=180);fig.savefig(figures/"peer_comparison.pdf");plt.close(fig)
    packed=json.loads((RUNS[0]/"routes.json").read_text())
    fig,axes=plt.subplots(1,3,figsize=(12,4),layout="constrained")
    for ax,name,title in zip(axes,["square_greedy","q4_triangle_2opt","q3_triangle_2opt"],["Square: 49 stations","Mixed: 31 triangle stations","Omni: 19 triangle stations"]):
        p=np.asarray(packed[name]);p=np.vstack([[0,0],p])
        ax.plot(p[:,0],p[:,1],".-",lw=.9,ms=4);ax.add_patch(Circle((0,0),1800,fill=False,color="black",ls="--"))
        ax.set_aspect("equal");ax.set_title(title);ax.set_xlabel("East / m");ax.set_ylabel("North / m")
    fig.savefig(figures/"coverage_routes.png",dpi=180);fig.savefig(figures/"coverage_routes.pdf");plt.close(fig)
    example=json.loads((RUNS[0]/"q1_triangle_example.json").read_text())["solution"]
    p=np.asarray(example["vertices"]);center=np.asarray(example["center"]);pair=np.asarray(example["diameter_endpoints"])
    fig,ax=plt.subplots(figsize=(5,4),layout="constrained")
    ax.fill(p[:,0],p[:,1],alpha=.18,color="#e3a343");ax.plot(*np.vstack([p,p[0]]).T,"k-")
    ax.add_patch(Circle(pair.mean(axis=0),example["diameter"]/2,fill=False,ls="--",color="#c54949",label="Diameter / 2 = 20 m"))
    ax.add_patch(Circle(center,example["radius"],fill=False,color="#247c79",label="Minimum radius = 23.09 m"))
    ax.scatter(*center,s=20);ax.set_aspect("equal");ax.autoscale();ax.margins(.12)
    ax.set_xlabel("x / m");ax.set_ylabel("y / m");ax.set_title("A feasible bearing-region counterexample");ax.legend(fontsize=8)
    fig.savefig(figures/"q1_counterexample.png",dpi=180);fig.savefig(figures/"q1_counterexample.pdf");plt.close(fig)


if __name__=="__main__":
    main,_=summarize_run(RUNS[0]);peer,_=summarize_run(RUNS[1]);plots(main,peer)
    print("Saved both aggregate/category/paired tables and three standalone PNG/PDF figures.")
