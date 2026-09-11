"""Independent continuous Q2 certificate experiment; no mission scoring calls."""
import hashlib
import json
import math
from pathlib import Path
import sys
import time
import numpy as np
from geometry import update_region,bearing_clip,minimum_circle
from intelligent import guaranteed_omni
from signal_minimax import reception_certificate,posterior_radius_upper

ROOT=Path(__file__).resolve().parent
OUT=ROOT/"experiments/runs/2026-09-11_q2-minimax"


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    if (OUT/"run_config.json").exists():raise RuntimeError("Preserving completed math experiment")
    points=[(250.,400.),(400.,400.),(500.,400.),(750.,350.),(750.,550.),(0.,500.),(1000.,1000.)]
    snapshot=OUT/"code_snapshot";snapshot.mkdir();hashes={}
    for name in ("q2_minimax_experiments.py","signal_minimax.py","geometry.py","intelligent.py"):
        raw=(ROOT/name).read_bytes();(snapshot/name).write_bytes(raw);hashes[name]=hashlib.sha256(raw).hexdigest()
    (OUT/"run_config.json").write_text(json.dumps(dict(base_seed=42,anchor=[0.,0.],returned_deg=0.,candidates=points,bins_deg=[2.,1.,.5],geometry_error_deg=1.01,physical_noise_deg=1.,scored_execution_count=0,official_calls=0,code_sha256=hashes,python=sys.executable),indent=2))
    p=update_region(None,np.zeros(2),0.);rows=[];checked=0;began=time.perf_counter()
    for x,y in points:
        q=np.array([x,y]);old=guaranteed_omni(q,p,np.zeros(2));certificate=reception_certificate(q,p,np.zeros(2))
        sample_max=0.;missed=0;sample_count=0
        for distance in (6.,20.,100.,250.,500.,750.,1000.,1250.,1500.):
            for angle in (-1.,-.5,0.,.5,1.):
                g=distance*np.array([math.cos(math.radians(angle)),math.sin(math.radians(angle))]);radius=max(1000.,distance)
                # First returned 0 is legal for these source bearings.
                for error in (-1.,-.5,0.,.5,1.):
                    sample_count+=1;d=np.linalg.norm(g-q)
                    if d>radius+1e-7:missed+=1;continue
                    if d<=5.:sample_max=max(sample_max,5.);continue
                    reading=round(math.degrees(math.atan2(g[1]-q[1],g[0]-q[0]))+error,2)%360
                    post=bearing_clip(p,q,reading);sample_max=max(sample_max,minimum_circle(post)[1]);checked+=1
        if certificate["guaranteed"]:assert missed==0
        estimates=[]
        if certificate["guaranteed"]:
            for width in (2.,1.,.5):
                start=time.perf_counter();estimate=posterior_radius_upper(p,q,width,save_bins=width==.5)
                elapsed=time.perf_counter()-start;assert sample_max<=estimate["radius_upper_m"]+1e-5
                estimates.append({**estimate,"compute_s":elapsed})
        rows.append(dict(q=[x,y],old_union_certificate=old,new_certificate=certificate,sample_count=sample_count,no_signal_samples=missed,
                         legal_sample_max_radius_m=sample_max,move_and_measure_s=float(np.linalg.norm(q))/5+5,continuous_estimates=estimates))
    (OUT/"results.json").write_text(json.dumps(rows,indent=2))
    assert any(r["new_certificate"]["guaranteed"] and not r["old_union_certificate"] for r in rows)
    (OUT/"checks.json").write_text(json.dumps(dict(passed=3,failed=0,legal_direction_updates=checked,guaranteed_candidates_never_missed=True,continuous_bounds_enclose_all_legal_sample_posteriors=True,strictly_expands_old_candidate_union=True,scored_execution_count=0,wall_s=time.perf_counter()-began),indent=2))
    lines=["# Q2保收集合与连续最坏后验界","","原并集证书是充分条件；新判定利用完整定义在外包P上的半平面裁剪。采样最大值仅作下方对照，连续上界来自覆盖全部可能返回角度的小区间。几何实验不计完整任务执行。", "", "|q/m|旧保收|新保收|样本无信号/225|合法样本最大半径m|连续上界m(2°/1°/0.5°)|移动检测s|0.5°计算s|", "|---|---|---|---:|---:|---:|---:|---:|"]
    for r in rows:
        estimates=r["continuous_estimates"];bounds="/".join(f"{e['radius_upper_m']:.2f}" for e in estimates) if estimates else "—"
        lines.append(f"|{r['q']}|{r['old_union_certificate']}|{r['new_certificate']['guaranteed']}|{r['no_signal_samples']}/225|{r['legal_sample_max_radius_m']:.2f}|{bounds}|{r['move_and_measure_s']:.2f}|{estimates[-1]['compute_s'] if estimates else 0.:.4f}|")
    (OUT/"summary.md").write_text("\n".join(lines)+"\n");print("Checked",checked,"legal samples; continuous bounds and candidate expansion saved")


if __name__=="__main__":main()
