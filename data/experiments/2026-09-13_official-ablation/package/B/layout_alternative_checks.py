"""Freeze and certify non-ring Q3 layouts and smaller Q4 directional meshes."""
import hashlib
import json
from pathlib import Path
import numpy as np
from layout_certificates import omni_certificate,directional_mesh_certificate,polar_layers,square9,alternating9
from coverage import route,route_length

ROOT=Path(__file__).resolve().parent
OUT=ROOT/"experiments/runs/2026-09-11_layout-alternatives"


def main():
    paths={f"q3_square9_h{h}":square9(h) for h in (860,900,1000,1100,1200)}
    paths.update({"q3_alternating9":alternating9(1450,850),"q3_alternating9_wide":alternating9(1500,950),
                  "q4_polar25":polar_layers([(8,995),(16,1840)]),
                  "q4_polar28":polar_layers([(9,995),(18,1850)]),
                  "q4_polar38":polar_layers([(6,650),(12,1300),(18,1950)])})
    records={}
    for name,points in paths.items():
        certificate=directional_mesh_certificate(points) if name.startswith("q4") else omni_certificate(points)
        ordered=route(points,optimized=True)
        records[name]={"stations":len(points),"points":points.tolist(),"route":ordered.tolist(),"route_m":route_length(ordered),"certificate":certificate}
        print(name,len(points),"route_m",round(route_length(ordered),2),json.dumps({k:v for k,v in certificate.items() if k not in ("triangles_intersecting_arena","cell_vertices")}),flush=True)
    OUT.mkdir(parents=True,exist_ok=True)
    target=OUT/"certified_layouts.json"
    if target.exists():raise RuntimeError("Existing layout certificates preserved")
    target.write_text(json.dumps(records,indent=2,ensure_ascii=False))
    (OUT/"run_config.json").write_text(json.dumps({"base_seed":42,"selection_uses_online_cases":False,"official_calls":0,
       "code_sha256":{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in ("layout_certificates.py","layout_alternative_checks.py","coverage.py","geometry.py")}},indent=2))
    (OUT/"precheck.md").write_text("# 布局证书检查\n\n仅用公开源域1800m、最小半径1000m和180度闭方向；不输入隐藏源。Q3为源域外包Voronoi单元上界；Q4为三角剖分充分条件。坐标在评价前固定，失败证书的布局不用于保证策略。命令已预存，结果写B/。\n")


if __name__=="__main__":main()
