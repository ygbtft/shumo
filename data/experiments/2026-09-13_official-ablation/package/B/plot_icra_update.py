"""Standalone scientific figures from the frozen confirmation and certificate."""
import csv
import json
import math
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import PatchCollection
from matplotlib.patches import Rectangle,Circle

ROOT=Path(__file__).resolve().parent
OUT=ROOT/"experiments/runs/2026-09-11_icra-confirmation"


def main():
    rows=list(csv.DictReader((OUT/"summary.csv").open()))
    fig,axes=plt.subplots(1,2,figsize=(13,4.8),constrained_layout=True)
    methods={3:("peer_layout9_proxy","shared9","joint7","joint9"),4:("square45_conservative","polar25_conservative","bracket25","joint25","joint22","replacement22")}
    labels={3:("Peer layout\nproxy","Shared 9","Joint 7","Joint 9"),4:("Square 45","Polar 25","Bracket 25","Joint 25","Joint 22","Replace 22")}
    for problem,ax in zip((3,4),axes):
        for split,shift,color in (("ordinary",-.19,"#2563a6"),("stress",.19,"#cf6b31")):
            value=[float(next(r for r in rows if int(r["problem"])==problem and r["method"]==method and r["split"]==split)["mean_per_source_s"]) for method in methods[problem]]
            bars=ax.bar(np.arange(len(value))+shift,value,width=.36,label=f"{split} ({150 if split=='ordinary' else 45} cases)",color=color)
            ax.bar_label(bars,fmt="%.0f",fontsize=8,padding=3)
        target=240 if problem==3 else 460
        ax.axhline(target,color="#b51b2a",linestyle="--",linewidth=1.2,label=f"Offline target {target} s")
        ax.set_xticks(np.arange(len(methods[problem])),labels[problem],fontsize=8)
        ax.set_ylabel("Mean virtual seconds per source")
        ax.set_title(f"Q{problem}: frozen, unseen-scene confirmation")
        ax.grid(axis="y",alpha=.2);ax.set_axisbelow(True);ax.legend(fontsize=8,loc="upper right")
        ax.set_ylim(0,450 if problem==3 else 1170)
    fig.suptitle("All 1,950 executions cleared every source; mean gains do not imply worst-case dominance",fontsize=11)
    for suffix in ("png","pdf"):fig.savefig(OUT/f"confirmation_comparison.{suffix}",dpi=180)
    plt.close(fig)
    item=json.loads((ROOT/"experiments/runs/2026-09-11_convex-visibility/certified_layouts.json").read_text())["convex22_72"]
    p=np.array(item["points"]);route=np.array(item["route"]);cert=item["certificate"]
    fig,ax=plt.subplots(figsize=(6.6,6.6),constrained_layout=True)
    patches=[Rectangle((x-h,y-h),2*h,2*h) for x,y,h,ids in cert["cells"]]
    ax.add_collection(PatchCollection(patches,facecolor="#d5e8f3",edgecolor="#83b3cc",linewidth=.15,alpha=.7))
    ax.add_patch(Circle((0,0),1800,fill=False,color="#1d4b68",lw=1.5,label="Source disk R = 1,800 m"))
    ax.plot(route[:,0],route[:,1],color="#b5b5b5",lw=.7,label="Static open route (17,716.55 m)")
    ax.scatter(p[1:8,0],p[1:8,1],c="#2563a6",s=30,label="7 inner sites, r = 990 m",zorder=4)
    ax.scatter(p[8:,0],p[8:,1],c="#cf6b31",s=30,label="14 outer sites, r = 1,851.29 m",zorder=4)
    ax.scatter([0],[0],marker="*",s=110,c="#222222",label="Origin",zorder=5)
    ax.set(xlim=(-2040,2040),ylim=(-2040,2040),xlabel="x (m)",ylabel="y (m)",title="22-site all-direction cover: 2,414 certified cells")
    ax.set_aspect("equal");ax.legend(fontsize=8,loc="lower left");ax.grid(alpha=.12)
    for suffix in ("png","pdf"):fig.savefig(OUT/f"directional22_certificate.{suffix}",dpi=180)
    plt.close(fig)
    print("Wrote comparison and coverage PNG/PDF figures")


if __name__=="__main__":main()
