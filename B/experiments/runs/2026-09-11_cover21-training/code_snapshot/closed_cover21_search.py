"""Resolve tangent integer layouts using exact closed convex-hull predicates."""
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
from integer_visibility_certificate import certify_integer_stations,verify_integer_certificate

ROOT=Path(__file__).resolve().parent
OUT=ROOT/"experiments/runs/2026-09-11_closed-cover21"
ROUND=ROOT/"experiments/runs/2026-09-11_rounded-cover21"
SOURCE=ROOT/"experiments/runs/2026-09-11_odd-ring-cover/certified_layouts.json"


def run():
    if (OUT/"search_config.json").exists():raise RuntimeError("Preserving exact search")
    source=json.loads(SOURCE.read_text());rows=[json.loads(s) for s in (ROUND/"search_log.jsonl").read_text().splitlines()]
    pending=[r for r in rows if "unresolved_certificate" in r]
    snapshot=OUT/"code_snapshot";snapshot.mkdir();hashes={}
    for name in ("closed_cover21_search.py","integer_visibility_certificate.py","coverage.py","geometry.py"):
        raw=(ROOT/name).read_bytes();(snapshot/name).write_bytes(raw);hashes[name]=hashlib.sha256(raw).hexdigest()
    config=dict(base_seed=42,candidates=pending,code_sha256=hashes,max_depth=16,
                source_sha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest(),scored_executions=0,official_calls=0)
    (OUT/"search_config.json").write_text(json.dumps(config,indent=2))
    (OUT/"precheck.md").write_text("# 精确闭凸包证书前冻结\n\n旧四个未决整数布局都有轴向支撑恰为1800m；严格凸包内缩排除了合法切点。此处固定这些候选，用整数点积/平方距离和二进制矩形坐标判定闭凸包。独立验证改用角点在选定站点三角形内的整数面积符号，整域分割也用整数。保留旧未决记录，不将它改写为反例。\n")
    began=time.perf_counter();certified={};records=[]
    for item in pending:
        spec=item["spec"];assert spec["decimals"]==0
        p=np.round(source[spec["source"]]["points"],0)
        cert=certify_integer_stations(p);row=dict(source_index=item["index"],certified=cert["covered"])
        if cert["covered"]:
            verification=verify_integer_certificate(p,cert);ordered=route(p,True);name=f"closed21_{item['index']}"
            certified[name]=dict(spec=spec,source_spec=source[spec["source"]]["spec"],points=p.tolist(),route=ordered.tolist(),certificate=cert,verification=verification)
            row.update(name=name,route_length_m=route_length(ordered),leaves=cert["leaf_count"])
            print("CERTIFIED",name,row["route_length_m"],row["leaves"],flush=True)
        else:row["unresolved_certificate"]=cert
        records.append(row)
    (OUT/"search_results.json").write_text(json.dumps(records,indent=2))
    (OUT/"certified_layouts.json").write_text(json.dumps(certified,indent=2))
    done=dict(candidates=len(records),certified=len(certified),wall_s=time.perf_counter()-began,scored_executions=0,official_calls=0)
    (OUT/"completion.json").write_text(json.dumps(done,indent=2))
    (OUT/"summary.md").write_text("# 切点的精确整数连续证书\n\n"+json.dumps(done)+"\n\n"+json.dumps(records,indent=2)+"\n")
    print("COMPLETED",json.dumps(done),flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--launch",action="store_true");args=parser.parse_args()
    if args.launch:
        if (OUT/"search_config.json").exists():raise RuntimeError("Preserving run")
        env=os.environ.copy();env.update(PYTHONDONTWRITEBYTECODE="1",OPENBLAS_NUM_THREADS="1",OMP_NUM_THREADS="1",
                                         MPLCONFIGDIR=str(ROOT/".mplconfig"),XDG_CACHE_HOME=str(ROOT/".cache"))
        with (OUT/"log.txt").open("a") as stream:
            p=subprocess.Popen([sys.executable,"-B",str(Path(__file__).resolve())],cwd=ROOT.parent,env=env,
                               stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
        (OUT/"background.pid").write_text(str(p.pid)+"\n");print("Background PID",p.pid)
    else:run()
