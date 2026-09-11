"""Summarize the frozen, paired Q3 ring-layout experiment without hiding tails."""
import csv
import json
from pathlib import Path
import numpy as np
from metaheuristic_experiments import write_json, write_csv

ROOT=Path(__file__).resolve().parent
OUT=ROOT/"experiments/runs/2026-09-11_peer-paper-review"


def main():
    completion=json.loads((OUT/"ring_completion.json").read_text())
    rows=[json.loads(s) for s in (OUT/"ring_trials.jsonl").read_text().splitlines()]
    assert len(rows)==completion["executions"]==840
    config=json.loads((OUT/"ring_run_config.json").read_text())
    methods=list(config["paths"])
    stats=[];paired=[];regressions=[]
    for split in ("ordinary","stress"):
        baseline={r["case_id"]:r for r in rows if r["split"]==split and r["method"]=="old_triangle19"}
        for method in methods:
            group=[r for r in rows if r["split"]==split and r["method"]==method]
            total=np.array([r["total_virtual_s"] for r in group])
            per=np.array([r["per_source_s"] for r in group])
            old=np.array([baseline[r["case_id"]]["total_virtual_s"] for r in group])
            oldper=np.array([baseline[r["case_id"]]["per_source_s"] for r in group])
            record={"split":split,"method":method,"runs":len(group),"all_cleared":sum(r["all_cleared"] for r in group),
                    "all_cleared_rate":np.mean([r["all_cleared"] for r in group]),"mean_total_s":total.mean(),"mean_per_source_s":per.mean(),
                    "max_total_s":total.max(),"p95_total_s":np.quantile(total,.95),
                    "mean_commands":np.mean([r["commands"] for r in group]),"mean_wall_s":np.mean([r["wall_s"] for r in group]),
                    "max_wall_s":max(r["wall_s"] for r in group),"mean_measurements":np.mean([r["measurements"] for r in group]),
                    "mean_move_m":np.mean([r["move_m"] for r in group]),"mean_switches":np.mean([r["switches"] for r in group]),
                    "per_source_gain_percent":100*(1-per.mean()/oldper.mean()),"worst_case_id":group[int(np.argmax(total))]["case_id"]}
            stats.append(record)
            pair={"split":split,"method":method,"faster_cases":int(np.sum(total<old-1e-6)),"slower_cases":int(np.sum(total>old+1e-6)),
                  "tied_cases":int(np.sum(abs(total-old)<=1e-6)),"largest_slowdown_s":float(max(0,(total-old).max())),
                  "largest_improvement_s":float((old-total).max()),"mean_paired_saved_s":float((old-total).mean())}
            if split=="ordinary":
                # Cluster bootstrap by source-generator seed, retaining 15 related conditions.
                seeds=sorted({r["seed"] for r in group});newmeans=[];oldmeans=[]
                for seed in seeds:
                    sub=[r for r in group if r["seed"]==seed]
                    newmeans.append(np.mean([r["per_source_s"] for r in sub]))
                    oldmeans.append(np.mean([baseline[r["case_id"]]["per_source_s"] for r in sub]))
                rng=np.random.default_rng(np.random.SeedSequence([42,36]))
                ids=rng.integers(0,len(seeds),(10000,len(seeds)))
                gains=100*(1-np.array(newmeans)[ids].mean(axis=1)/np.array(oldmeans)[ids].mean(axis=1))
                pair["seed_cluster_bootstrap_gain_95_low_percent"]=float(np.quantile(gains,.025))
                pair["seed_cluster_bootstrap_gain_95_high_percent"]=float(np.quantile(gains,.975))
            paired.append(pair)
            for r in group:
                b=baseline[r["case_id"]]
                if r["total_virtual_s"]>b["total_virtual_s"]+1e-6:
                    regressions.append({"case_id":r["case_id"],"split":split,"method":method,"old_s":b["total_virtual_s"],"new_s":r["total_virtual_s"],"delta_s":r["total_virtual_s"]-b["total_virtual_s"]})
    write_csv(OUT/"ring_summary.csv",stats);write_csv(OUT/"ring_paired.csv",paired)
    write_json(OUT/"ring_regressions.json",sorted(regressions,key=lambda r:r["delta_s"],reverse=True))
    write_json(OUT/"ring_failures.json",[r for r in rows if r["failure"] or not r["all_cleared"]])
    # All candidates were frozen beforehand. Observed winner is NOT claimed global optimum.
    best=min((s for s in stats if s["split"]=="ordinary" and s["all_cleared"]==s["runs"]),key=lambda s:s["mean_per_source_s"])
    write_json(OUT/"ring_observed_selection.json",{"method":best["method"],"criterion":"Smallest ordinary-set mean per-source virtual time among five fixed candidates, all-clear required; exploratory comparison, not an untouched post-selection test", "ordinary":best,
        "stress":next(s for s in stats if s["split"]=="stress" and s["method"]==best["method"]),"official_verified":False,"global_optimality_claimed":False})
    labels={"old_triangle19":"Old lattice (19)","peer_ring9_r1300":"Peer ring (9, 1300m)","ring7_r1140":"Ring (7, 1140m)","ring9_r960":"Ring (9, 960m)","ring13_r870":"Ring (13, 870m)"}
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(1,2,figsize=(12,4.5),constrained_layout=True)
    for ax,split in zip(axes,("ordinary","stress")):
        sub=[s for s in stats if s["split"]==split]
        bars=ax.barh([labels[s["method"]] for s in sub],[s["mean_per_source_s"] for s in sub],color=["#7b8898","#dfad4c","#398bb8","#42886c","#9472ac"])
        ax.invert_yaxis();ax.set_xlabel("Mean virtual seconds per source");ax.set_title(f"{split}: {sub[0]['runs']} paired cases per method")
        ax.bar_label(bars,fmt="%.1f",padding=3);ax.set_xlim(0,max(s["mean_per_source_s"] for s in sub)*1.16)
    fig.savefig(OUT/"ring_results.png",dpi=180);fig.savefig(OUT/"ring_results.pdf");plt.close(fig)
    fig,axes=plt.subplots(1,3,figsize=(12,4),constrained_layout=True)
    for ax,name in zip(axes,("old_triangle19","peer_ring9_r1300",best["method"])):
        pts=np.array(config["paths"][name]);ax.add_patch(plt.Circle((0,0),1800,fill=False,color="black",linestyle="--"))
        for p in pts:ax.add_patch(plt.Circle(p,1000,fill=False,color="#8bb6cd",alpha=.3))
        ax.plot(pts[:,0],pts[:,1],"o-",markersize=3,color="#28779c");ax.plot(0,0,"r*")
        ax.set_title(labels[name]);ax.set_aspect("equal");ax.set_xlim(-3600,3600);ax.set_ylim(-3600,3600);ax.set_xlabel("x (m)")
    fig.savefig(OUT/"ring_layouts.png",dpi=180);fig.savefig(OUT/"ring_layouts.pdf");plt.close(fig)
    lines=["# 环形布局配对离线比较", "", "840次执行，共168个配对场景，每场5种预先冻结布局。全部使用原有主动定位、光学兜底和未知数量结束策略；仅复现对方布点思想，不是其完整算法。", "",
           "|场景|布局|全清局数|平均总秒|平均每源秒|最慢总秒|平均指令|平均/最大墙钟秒|", "|---|---|---:|---:|---:|---:|---:|---:|"]
    for s in stats:
        lines.append(f"|{s['split']}|{s['method']}|{s['all_cleared']}/{s['runs']}|{s['mean_total_s']:.2f}|{s['mean_per_source_s']:.2f}|{s['max_total_s']:.2f}|{s['mean_commands']:.2f}|{s['mean_wall_s']:.3f}/{s['max_wall_s']:.3f}|")
    lines += ["",f"本批普通场景平均每源时间最小：{best['method']}；相对旧布局下降{best['per_source_gain_percent']:.2f}%。这不是连续空间全局最优，也未使用新的保留场景对筛选结果再次确认。", "",f"整批评分墙钟耗时{completion['wall_s']:.2f}秒，源码/配置/全部指令轨迹已冻结。失败列表与成对变慢案例均另存；不能把合成全清率写成官方成绩。", "", "图表：ring_results.png/pdf、ring_layouts.png/pdf。几何反例与覆盖检查见paper_numeric_checks.json、checks.json。"]
    (OUT/"summary.md").write_text("\n".join(lines)+"\n")
    print(json.dumps({"completion":completion,"stats":stats,"selected":best["method"]},ensure_ascii=False,indent=2))


if __name__=="__main__":main()
