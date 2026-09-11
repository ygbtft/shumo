"""Standalone research figures from frozen coordinates and scored summaries."""
import csv
import hashlib
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Circle
from cover21_confirmation import ROOT,OUT


def main():
    data=json.loads((OUT/"selected_layouts.json").read_text())
    rows=list(csv.DictReader((OUT/"summary.csv").open()))
    plt.rcParams.update({"font.family":"DejaVu Sans","font.size":10,"axes.spines.top":False,"axes.spines.right":False})
    dest=ROOT/"figures";dest.mkdir(exist_ok=True)
    fig,axes=plt.subplots(1,2,figsize=(11.5,5.4),layout="constrained")
    for ax,name,title in zip(axes,("convex22","grid21_29"),("Previous: 22 stations","Certified integer design: 21 stations")):
        item=data[name];points=np.array(item["points"]);route=np.array(item["route"])
        ax.add_patch(Circle((0,0),1800,facecolor="#edf3fa",edgecolor="#394b61",linewidth=1.5))
        ax.plot(route[:,0],route[:,1],color="#8c98a8",linestyle="--",linewidth=1,zorder=1)
        groups=np.linalg.norm(points,axis=1)
        for mask,label,color in ((groups<1,"Center","#111827"),((groups>1)&(groups<1500),"Inner stations","#1873b8"),(groups>1500,"Outer stations","#d46a21")):
            ax.scatter(points[mask,0],points[mask,1],s=32,color=color,label=label,zorder=4)
        for i,p in enumerate(points):ax.annotate(str(i),p,xytext=(4,4),textcoords="offset points",fontsize=8,color="#26354a")
        length=np.linalg.norm(np.diff(route,axis=0),axis=1).sum()
        ax.set_title(f"{title}\nStatic open route: {length:,.2f} m")
        ax.set(xlim=(-2150,2150),ylim=(-2150,2150),xlabel="x (m)",ylabel="y (m)",aspect="equal")
        ax.grid(alpha=.15)
    axes[1].legend(loc="upper center",bbox_to_anchor=(.5,-.13),ncol=3,frameon=False)
    fig.suptitle("Source disk radius 1,800 m; minimum receiving radius 1,000 m\nCoverage is proved continuously; route length alone does not rank complete missions",fontsize=12)
    for suffix in ("png","pdf"):fig.savefig(dest/f"cover21_layouts.{suffix}",dpi=180,bbox_inches="tight")
    plt.close(fig)
    methods=("range_convex22","range_grid21_29","predict_grid21_29","lean_locked_grid21_29","count_locked_grid21_29","range_grid21_7")
    labels=("R22","R21","P21","L21","C21","A21")
    colors=("#555e6d","#1873b8","#28a07d","#986ab5","#cc6a24","#bf5466")
    fig,axes=plt.subplots(1,2,figsize=(11.5,4.7),layout="constrained")
    for ax,split,title in zip(axes,("ordinary","stress"),("150 ordinary cases per method","45 designed stress cases per method")):
        for method,label,color in zip(methods,labels,colors):
            r=next(r for r in rows if r["problem"]=="4" and r["method"]==method and r["split"]==split)
            x=1000*float(r["mean_cpu_s"]);y=float(r["mean_per_source_s"])
            ax.scatter(x,y,color=color,s=52,zorder=3)
            offsets={"R22":(6,6),"R21":(-24,6),"P21":(5,5),"L21":(-22,9),"C21":(5,-10),"A21":(5,6)}
            ax.annotate(label,(x,y),xytext=offsets[label],textcoords="offset points",color=color,fontweight="bold")
        if split=="ordinary":ax.axhline(460,color="#a0a6af",linestyle="--",linewidth=1,label="Ordinary target")
        ax.set(title=title,xlabel="Mean CPU time per mission (ms)",ylabel="Mean virtual time per source (s)")
        ax.grid(alpha=.18);ax.margins(x=.15,y=.2)
    fig.suptitle("Q4: mean time and compute tradeoff; all methods cleared every case\nR22 old range; R21 new range; P21 prediction; L21 fixed order; C21 + public count; A21 alternate layout",fontsize=11)
    for suffix in ("png","pdf"):fig.savefig(dest/f"cover21_tradeoffs.{suffix}",dpi=180,bbox_inches="tight")
    plt.close(fig)
    metadata=dict(source_summary_sha256=hashlib.sha256((OUT/"summary.csv").read_bytes()).hexdigest(),
                  selected_layouts_sha256=hashlib.sha256((OUT/"selected_layouts.json").read_bytes()).hexdigest(),
                  figure_files=[f"figures/{stem}.{suffix}" for stem in ("cover21_layouts","cover21_tradeoffs") for suffix in ("png","pdf")],
                  means_only=True,does_not_replace_tail_or_pointwise_evidence=True,scored_executions=0,official_calls=0)
    (OUT/"figure_data.json").write_text(json.dumps(metadata,indent=2))
    print("Saved two PNG/PDF figures and source hashes")


if __name__=="__main__":main()
