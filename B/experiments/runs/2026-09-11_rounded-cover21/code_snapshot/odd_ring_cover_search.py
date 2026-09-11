"""Search overlooked 21-station ring families; certify continuous visibility."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time
import numpy as np

from coverage import route, route_length
from visibility_certificate import directional_witness, sample_reject, rectangle_certificate, verify_cells
from icra_final_checks import partition_check

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "experiments/runs/2026-09-11_odd-ring-cover"


def points(spec):
    n,m,r,margin,phase = spec
    s = 1800. / math.cos(math.pi/m) + margin
    a = np.arange(n)*2*math.pi/n
    b = (np.arange(m)+phase)*2*math.pi/m
    return np.vstack((np.zeros((1,2)),r*np.column_stack((np.cos(a),np.sin(a))),
                      s*np.column_stack((np.cos(b),np.sin(b)))))


def gap_witness(spec):
    """Find a point between the inner hull and outer receiving threshold."""
    n,m,r,margin,phase = spec
    s = 1800. / math.cos(math.pi/m) + margin
    inner_mid = (np.arange(n)+.5)*2*math.pi/n
    outer_mid = (np.arange(m)+phase+.5)*2*math.pi/m
    differences = (outer_mid[:,None]-inner_mid[None,:]+math.pi)%(2*math.pi)-math.pi
    i,j = np.unravel_index(np.argmin(abs(differences)),differences.shape)
    inner_reach = r*math.cos(math.pi/n)/math.cos(differences[i,j])
    outer_reach = s*math.cos(math.pi/m)-math.sqrt(1000.**2-(s*math.sin(math.pi/m))**2)
    if outer_reach <= inner_reach + 1e-6:
        return None
    rho = (inner_reach+outer_reach)/2
    g = rho*np.array([math.cos(outer_mid[i]),math.sin(outer_mid[i])])
    witness = directional_witness(points(spec),g)
    assert witness is not None, (spec,inner_reach,outer_reach)
    return {**witness,"inner_hull_radius_m":float(inner_reach),
            "outer_receiving_threshold_m":float(outer_reach),"construction":"outer_edge_midray_inner_hull_gap"}


def verify_witness(p,witness):
    g = np.array(witness["position"])
    face = math.radians(witness["direction_deg"])
    v = np.array([math.cos(face),math.sin(face)])
    delta = p-g
    distances = np.linalg.norm(delta,axis=1)
    dots = delta@v
    assert np.linalg.norm(g) <= 1800.+1e-8
    assert np.all((distances>1000.+1e-8)|(dots < -1e-7))
    return dict(max_receivable_dot_m=float(dots[distances<=1000.].max()) if np.any(distances<=1000.) else None,
                min_distance_m=float(distances.min()),receive_radius_m=1000.)


def run():
    if (OUT/"search_config.json").exists():
        raise RuntimeError("Preserving completed or running search")
    specs=[(n,m,r,margin,phase) for n,m in ((8,12),(7,13),(6,14))
           for r in (995.,998.,999.,999.9) for margin in (.25,1.,2.,5.)
           for phase in (0.,.125,.25,.375,.5)]
    snapshot=OUT/"code_snapshot";snapshot.mkdir();hashes={}
    for name in ("odd_ring_cover_search.py","visibility_certificate.py","coverage.py","geometry.py","icra_final_checks.py"):
        raw=(ROOT/name).read_bytes();(snapshot/name).write_bytes(raw)
        hashes[name]=hashlib.sha256(raw).hexdigest()
    config=dict(base_seed=42,deterministic_enumeration=True,specs=specs,stations=21,
                source_radius_m=1800.,receiving_min_m=1000.,max_depth=16,max_cells=150000,
                code_sha256=hashes,scored_executions=0,official_calls=0)
    (OUT/"search_config.json").write_text(json.dumps(config,indent=2))
    (OUT/"precheck.md").write_text("# 冻结前检查\n\n原51894清单237项匹配，未改旧代码。冻结3家族×4内半径×4外余量×5相位=240候选，角度和坐标都为公开设计变量，不是评分真值。解析间隙见证另由独立点积/距离核验；连续证书同时检查每个单元和整个分割。采样/解析反例、未决、获证分别记录。\n")
    began=time.perf_counter();rows=[];certified={}
    with (OUT/"search_log.jsonl").open("x") as stream:
        for i,spec in enumerate(specs):
            p=points(spec);witness=gap_witness(spec)
            if witness is None:
                witness=sample_reject(p)
            cert=None if witness is not None else rectangle_certificate(p,max_depth=16,max_cells=150000)
            row=dict(index=i,spec=spec,witness=witness,certified=bool(cert and cert["covered"]))
            if witness is not None:
                row["witness_verification"]=verify_witness(p,witness)
            elif cert and not cert["covered"]:
                row["unresolved_certificate"]=cert
            if row["certified"]:
                validation={**verify_cells(p,cert),**partition_check(cert)}
                ordered=route(p,True);name=f"odd21_{i}"
                certified[name]=dict(spec=spec,points=p.tolist(),route=ordered.tolist(),certificate=cert,verification=validation)
                row.update(name=name,route_length_m=route_length(ordered),leaves=cert["leaf_count"])
                print("CERTIFIED",name,round(row["route_length_m"],2),row["leaves"],flush=True)
            rows.append(row);stream.write(json.dumps(row)+"\n");stream.flush()
            if (i+1)%10==0:
                print(i+1,"/",len(specs),"certified",len(certified),"wall",round(time.perf_counter()-began,1),flush=True)
    (OUT/"certified_layouts.json").write_text(json.dumps(certified,indent=2))
    done=dict(candidates=len(rows),certified=len(certified),real_counterexamples=sum(x["witness"] is not None for x in rows),
              unresolved=sum("unresolved_certificate" in x for x in rows),wall_s=time.perf_counter()-began,
              scored_executions=0,official_calls=0)
    (OUT/"completion.json").write_text(json.dumps(done,indent=2))
    best=sorted((x for x in rows if x["certified"]),key=lambda x:x["route_length_m"])
    (OUT/"summary.md").write_text("# 21站两圈布局搜索\n\n"+json.dumps(done,ensure_ascii=False)+
        "\n\n静态路长仅用于筛选少量训练候选；连续保证先于计分。\n\n|布局|路线米|内数/外数/内半径/外余量/相位|证书单元|\n|---|---:|---|---:|\n"+
        "\n".join(f"|{x['name']}|{x['route_length_m']:.2f}|{x['spec']}|{x['leaves']}|" for x in best)+"\n")
    print("COMPLETED",json.dumps(done),flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--launch",action="store_true")
    args=parser.parse_args()
    if args.launch:
        if (OUT/"search_config.json").exists():raise RuntimeError("Preserving search")
        env=os.environ.copy();env.update(PYTHONDONTWRITEBYTECODE="1",OPENBLAS_NUM_THREADS="1",OMP_NUM_THREADS="1",
                                         MPLCONFIGDIR=str(ROOT/".mplconfig"),XDG_CACHE_HOME=str(ROOT/".cache"))
        with (OUT/"log.txt").open("a") as stream:
            process=subprocess.Popen([sys.executable,"-B",str(Path(__file__).resolve())],cwd=ROOT.parent,
                                     env=env,stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
        (OUT/"background.pid").write_text(str(process.pid)+"\n");print("Background PID",process.pid)
    else:run()
