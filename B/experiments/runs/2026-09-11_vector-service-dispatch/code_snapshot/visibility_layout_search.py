"""Deterministic search of offset two-ring Q4 layouts, with continuous proof."""
import hashlib
import json
import math
from pathlib import Path
import sys
import time
import numpy as np
from coverage import route,route_length
from visibility_certificate import sample_reject,rectangle_certificate,verify_cells

ROOT=Path(__file__).resolve().parent
OUT=ROOT/"experiments/runs/2026-09-11_convex-visibility"


def points(n,m,r,s,phase):
    a=np.arange(n)*2*math.pi/n;b=np.arange(m)*2*math.pi/m+phase*2*math.pi/m
    return np.vstack([np.zeros((1,2)),r*np.column_stack([np.cos(a),np.sin(a)]),s*np.column_stack([np.cos(b),np.sin(b)])])


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    if (OUT/"search_config.json").exists():raise RuntimeError("Preserving prior search")
    specs=[(n,m,r,1800/math.cos(math.pi/m)+margin,phase)
           for n,m in ((6,12),(6,14),(7,12),(7,14),(8,12),(8,14),(8,16),(9,14))
           for r in (700.,800.,900.,990.,1050.) for margin in (5.,35.) for phase in (0.,.5)]
    snapshot=OUT/"search_code_snapshot";snapshot.mkdir();hashes={}
    for name in ("visibility_layout_search.py","visibility_certificate.py","coverage.py","geometry.py"):
        raw=(ROOT/name).read_bytes();(snapshot/name).write_bytes(raw);hashes[name]=hashlib.sha256(raw).hexdigest()
    (OUT/"search_config.json").write_text(json.dumps(dict(base_seed=42,deterministic_enumeration=True,specs=specs,source_radius=1800,receive_min=1000,max_depth=13,code_sha256=hashes,python=sys.executable),indent=2))
    began=time.perf_counter();rows=[];certified={}
    with (OUT/"search_log.jsonl").open("x") as stream:
        for i,spec in enumerate(specs):
            p=points(*spec);witness=sample_reject(p);cert=None
            if witness is None:cert=rectangle_certificate(p)
            row=dict(index=i,spec=spec,stations=len(p),sample_counterexample=witness,certified=bool(cert and cert["covered"]))
            if cert and not cert["covered"]:row["certificate_rejection"]=cert
            if row["certified"]:
                verification=verify_cells(p,cert);r=route(p,True);row["route_length_m"]=route_length(r)
                row["leaves"]=cert["leaf_count"];name=f"convex{len(p)}_{i}"
                certified[name]=dict(points=p.tolist(),route=r.tolist(),certificate=cert,verification=verification,spec=spec)
                print("CERTIFIED",name,round(row["route_length_m"],2),cert["leaf_count"],flush=True)
            rows.append(row);stream.write(json.dumps(row)+"\n");stream.flush()
            if (i+1)%20==0:print(i+1,"/",len(specs),"passed",len(certified),"wall",round(time.perf_counter()-began,1),flush=True)
    (OUT/"certified_layouts.json").write_text(json.dumps(certified,indent=2))
    (OUT/"search_completion.json").write_text(json.dumps(dict(candidates=len(rows),certified=len(certified),wall_s=time.perf_counter()-began,scored_executions=0),indent=2))
    best=sorted((r for r in rows if r["certified"]),key=lambda r:(r["route_length_m"],r["stations"]))
    (OUT/"search_summary.md").write_text("# 直接方向覆盖搜索\n\n采样仅用于生成反例；通过候选另有连续方格凸包证书。\n\n|索引|点数|静态路线米|参数(n,m,内半径,外半径,错相比例)|\n|---|---:|---:|---|\n"+"\n".join(f"|{r['index']}|{r['stations']}|{r['route_length_m']:.2f}|{r['spec']}|" for r in best)+"\n")


if __name__=="__main__":main()
