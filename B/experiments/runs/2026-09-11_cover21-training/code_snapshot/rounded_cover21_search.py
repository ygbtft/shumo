"""Re-certify actual centimeter and integer station coordinates."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import numpy as np
from coverage import route,route_length
from visibility_certificate import sample_reject,rectangle_certificate,verify_cells
from icra_final_checks import partition_check
from odd_ring_cover_search import verify_witness

ROOT=Path(__file__).resolve().parent
OUT=ROOT/"experiments/runs/2026-09-11_rounded-cover21"
SOURCE=ROOT/"experiments/runs/2026-09-11_odd-ring-cover/certified_layouts.json"


def run():
    if (OUT/"search_config.json").exists():raise RuntimeError("Preserving search")
    source=json.loads(SOURCE.read_text())
    snapshot=OUT/"code_snapshot";snapshot.mkdir();hashes={}
    for name in ("rounded_cover21_search.py","odd_ring_cover_search.py","visibility_certificate.py","coverage.py","geometry.py","icra_final_checks.py"):
        raw=(ROOT/name).read_bytes();(snapshot/name).write_bytes(raw);hashes[name]=hashlib.sha256(raw).hexdigest()
    specs=[dict(source=name,decimals=decimals) for name in source for decimals in (2,0)]
    config=dict(base_seed=42,source_file=str(SOURCE.relative_to(ROOT)),source_sha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
                specs=specs,code_sha256=hashes,arena_radius=1800.,receive_radius=1000.,max_depth=16,
                scored_executions=0,official_calls=0)
    (OUT/"search_config.json").write_text(json.dumps(config,indent=2))
    (OUT/"precheck.md").write_text("# 坐标舍入前冻结\n\n对全部36个已获证21站候选，各自取厘米与整数坐标，共72个。重新进行连续证书，不能套用原浮点站点证明。源圆域/最小接收/朝向条件不改，正式请求0。\n")
    began=time.perf_counter();rows=[];certified={}
    with (OUT/"search_log.jsonl").open("x") as stream:
        for i,spec in enumerate(specs):
            p=np.round(source[spec["source"]]["points"],spec["decimals"])
            assert len(np.unique(p,axis=0))==21 and np.linalg.norm(p,axis=1).max()<1950.
            witness=sample_reject(p)
            cert=None if witness else rectangle_certificate(p,max_depth=16,max_cells=150000)
            row=dict(index=i,spec=spec,witness=witness,certified=bool(cert and cert["covered"]))
            if witness:row["witness_verification"]=verify_witness(p,witness)
            elif cert and not cert["covered"]:row["unresolved_certificate"]=cert
            if row["certified"]:
                validation={**verify_cells(p,cert),**partition_check(cert)}
                ordered=route(p,True);name=f"grid21_{i}"
                certified[name]=dict(spec=spec,source_spec=source[spec["source"]]["spec"],points=p.tolist(),route=ordered.tolist(),certificate=cert,verification=validation)
                row.update(name=name,route_length_m=route_length(ordered),leaves=cert["leaf_count"])
                print("CERTIFIED",name,round(row["route_length_m"],2),spec,flush=True)
            rows.append(row);stream.write(json.dumps(row)+"\n");stream.flush()
            if (i+1)%10==0:print(i+1,"/",len(specs),"wall",round(time.perf_counter()-began,1),flush=True)
    (OUT/"certified_layouts.json").write_text(json.dumps(certified,indent=2))
    done=dict(candidates=len(rows),certified=len(certified),real_counterexamples=sum(r["witness"] is not None for r in rows),
              unresolved=sum("unresolved_certificate" in r for r in rows),wall_s=time.perf_counter()-began,scored_executions=0,official_calls=0)
    (OUT/"completion.json").write_text(json.dumps(done,indent=2))
    (OUT/"summary.md").write_text("# 舍入后的21站布局\n\n"+json.dumps(done,ensure_ascii=False)+
        "\n\n每组实际舍入坐标都有独立连续证书；原坐标的证明没有直接沿用。\n\n|名称|源布局/小数位|路线米|证书单元|\n|---|---|---:|---:|\n"+
        "\n".join(f"|{r['name']}|{r['spec']}|{r['route_length_m']:.2f}|{r['leaves']}|" for r in sorted(rows,key=lambda x:x.get('route_length_m',float('inf'))) if r["certified"])+"\n")
    print("COMPLETED",json.dumps(done),flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--launch",action="store_true");args=parser.parse_args()
    if args.launch:
        if (OUT/"search_config.json").exists():raise RuntimeError("Preserving search")
        env=os.environ.copy();env.update(PYTHONDONTWRITEBYTECODE="1",OPENBLAS_NUM_THREADS="1",OMP_NUM_THREADS="1",
                                         MPLCONFIGDIR=str(ROOT/".mplconfig"),XDG_CACHE_HOME=str(ROOT/".cache"))
        with (OUT/"log.txt").open("a") as stream:
            p=subprocess.Popen([sys.executable,"-B",str(Path(__file__).resolve())],cwd=ROOT.parent,env=env,
                               stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
        (OUT/"background.pid").write_text(str(p.pid)+"\n");print("Background PID",p.pid)
    else:run()
