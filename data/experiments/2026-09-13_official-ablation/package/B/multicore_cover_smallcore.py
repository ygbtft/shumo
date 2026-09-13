"""Search 21-site non-single-center layouts; samples reject, cells certify."""
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

ROOT=Path(__file__).resolve().parent
OUT=ROOT / "experiments/runs/2026-09-11_multicore-cover-smallcore"


def ring(n,radius,phase):
    angles=np.arange(n)*2*np.pi/n+np.radians(phase)
    return radius*np.column_stack((np.cos(angles),np.sin(angles)))


def points(spec):
    core,middle,outer,core_phase,middle_phase=spec
    return np.vstack((ring(3,core,core_phase),ring(6,middle,middle_phase),ring(12,outer,0.)))


def run():
    if (OUT / "search_config.json").exists():
        raise RuntimeError("Preserving search")
    specs=[(a,b,c,d,e) for a in (50.,100.,150.,200.) for b in (1070.,1080.,1090.,1100.)
           for c in (1868.,1880.,1900.) for d in (0.,30.) for e in (15.,45.)]
    snapshot=OUT / "code_snapshot"
    snapshot.mkdir()
    hashes={}
    for name in ("multicore_cover_smallcore.py","visibility_certificate.py","coverage.py","geometry.py","icra_final_checks.py"):
        raw=(ROOT/name).read_bytes()
        (snapshot/name).write_bytes(raw)
        hashes[name]=hashlib.sha256(raw).hexdigest()
    (OUT / "search_config.json").write_text(json.dumps(dict(base_seed=42,deterministic_enumeration=True,
        specs=specs,stations=21,source_radius=1800.,receiving_min=1000.,max_action_radius=1950.,
        max_depth=13,code_sha256=hashes,scored_executions=0,official_calls=0),indent=2))
    (OUT / "precheck.md").write_text("# 小内核搜索前检查\n\n首轮216个大内核候选均有采样反例，原配置、见证和日志保留。根据900m附近盲区把内核半径改为50/100/150/200m，中层1070/1080/1090/1100m、错相15/45度，192个新几何组合冻结后搜索。采样只拒绝，必须连续证书及独立核验后才可使用。计分执行和正式请求均为0。\n")

    began=time.perf_counter()
    certified={}
    rows=[]
    with (OUT / "search_log.jsonl").open("x") as stream:
        for i,spec in enumerate(specs):
            p=points(spec)
            witness=sample_reject(p)
            cert=None if witness is not None else rectangle_certificate(p)
            row=dict(index=i,spec=spec,sample_witness=witness,certified=bool(cert and cert["covered"]))
            if cert and not cert["covered"]:
                row["unresolved_certificate"]=cert
            if row["certified"]:
                validation={**verify_cells(p,cert),**partition_check(cert)}
                ordered=route(p,True)
                name=f"multicore21_{i}"
                certified[name]=dict(spec=spec,points=p.tolist(),route=ordered.tolist(),certificate=cert,verification=validation)
                row.update(route_length_m=route_length(ordered),leaves=cert["leaf_count"])
                print("CERTIFIED",name,round(row["route_length_m"],2),row["leaves"],flush=True)
            rows.append(row)
            stream.write(json.dumps(row)+"\n")
            stream.flush()
            if (i+1)%12==0:
                print(i+1,"/",len(specs),"certified",len(certified),"wall",round(time.perf_counter()-began,1),flush=True)
    (OUT / "certified_layouts.json").write_text(json.dumps(certified,indent=2))
    (OUT / "completion.json").write_text(json.dumps(dict(candidates=len(rows),certified=len(certified),wall_s=time.perf_counter()-began,
        scored_executions=0,official_calls=0),indent=2))
    best=sorted((r for r in rows if r["certified"]),key=lambda r:r["route_length_m"])
    (OUT / "summary.md").write_text("# 21站多内核覆盖搜索\n\n采样通过不当证明；通过者另有完整方格分区、距离和凸包核验。静态路长只用于挑选少量训练候选，不等于整局耗时。\n\n|索引|静态路线米|参数(内核/中层/外层半径,内核/中层相位度)|证书单元|\n|---|---:|---|---:|\n"+"\n".join(f"|{r['index']}|{r['route_length_m']:.2f}|{r['spec']}|{r['leaves']}|" for r in best)+"\n")
    print("Completed",len(rows),"candidates",len(certified),"certified",flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--launch",action="store_true")
    args=parser.parse_args()
    if args.launch:
        if (OUT / "search_config.json").exists():
            raise RuntimeError("Preserving search")
        env=os.environ.copy()
        env.update(PYTHONDONTWRITEBYTECODE="1",OPENBLAS_NUM_THREADS="1",OMP_NUM_THREADS="1",
                   MPLCONFIGDIR=str(ROOT / ".mplconfig"),XDG_CACHE_HOME=str(ROOT / ".cache"))
        with (OUT / "log.txt").open("a") as stream:
            process=subprocess.Popen([sys.executable,"-B",str(Path(__file__).resolve())],cwd=ROOT.parent,
                env=env,stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
        (OUT / "background.pid").write_text(str(process.pid)+"\n")
        print("Background PID",process.pid)
    else:
        run()
