"""Plot frozen Q4 virtual-time/CPU tradeoffs as standalone research artifacts."""
import csv
import hashlib
import json
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parent
OUT=ROOT / "experiments/runs/2026-09-11_deferred-confirmation"


def main():
    source=OUT / "summary.csv"
    rows=list(csv.DictReader(source.open()))
    methods=[("R","range_width015","Range baseline","#444444"),
             ("D","deferred_width015","Deferred movement","#377eb8"),
             ("P","cheap_predict8_width015","Negative prediction","#4daf4a"),
             ("A","cheap_predict8_arc05_width015","Service arcs + prediction","#984ea3"),
             ("L","cheap_predict8_locked_width015","Fixed scan order + prediction","#ff7f00"),
             ("H","batch_history_first8_width015","Batched region exclusion","#e41a1c")]
    fig,axes=plt.subplots(1,2,figsize=(10.5,4.8))
    data=[];handles=[]
    for axis,split in zip(axes,("ordinary","stress")):
        for code,method,label,color in methods:
            row=next(r for r in rows if int(r["problem"])==4 and r["method"]==method and r["split"]==split)
            x,y=float(row["mean_per_source_s"]),1000*float(row["mean_cpu_s"])
            handle=axis.scatter(x,y,s=48,color=color,edgecolor="white",linewidth=.6,zorder=3)
            offset=(-16,-12) if code=="R" else (8,-4) if code=="D" else (7,5)
            axis.annotate(code,(x,y),xytext=offset,textcoords="offset points",fontsize=10,weight="bold")
            data.append(dict(split=split,method=method,mean_per_source_s=x,mean_cpu_ms=y))
            if split=="ordinary":handles.append(handle)
        axis.set_title("Ordinary: 150 cases" if split=="ordinary" else "Stress: 45 cases")
        axis.set_xlabel("Mean virtual time per source (s)")
        axis.set_ylabel("Mean process CPU time (ms)")
        axis.margins(x=.18,y=.20)
        axis.grid(alpha=.23,zorder=0)
    fig.legend(handles,[f"{c}: {label}" for c,m,label,color in methods],loc="lower center",ncol=3,
               bbox_to_anchor=(.5,.04),frameon=False,fontsize=9)
    fig.suptitle("Q4: virtual-time savings and computation costs",fontsize=13)
    fig.text(.5,.012,"Both axes: lower is better. All cases cleared; these means do not bound individual-case regressions.",
             ha="center",fontsize=8.5)
    fig.tight_layout(rect=(0,.18,1,.94))
    directory=ROOT / "figures"
    directory.mkdir(exist_ok=True)
    for suffix in ("png","pdf"):
        fig.savefig(directory / f"deferred_tradeoffs.{suffix}",dpi=180)
    plt.close(fig)
    (OUT / "figure_data.json").write_text(json.dumps(dict(source="summary.csv",source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        rows=data,scope="Selected Q4 frozen ordinary/stress means; full metrics and regressions remain in tables",
        scored_execution_count=0,official_calls=0),indent=2))
    print("Saved figures/deferred_tradeoffs.png and .pdf from frozen summary.csv")


if __name__=="__main__":
    main()
