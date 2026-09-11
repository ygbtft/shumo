"""Analyze an explicitly reused regression trace; never supplies truth to policy."""
import gzip
import json
import math
from pathlib import Path
import numpy as np
from geometry import update_region,minimum_circle

ROOT=Path(__file__).resolve().parent
OLD=ROOT/"experiments/runs/2026-09-11_icra-confirmation"
OUT=ROOT/"experiments/runs/2026-09-11_asymmetric-probes"


def main():
    case="q4__boundary_outward__n16__positive";result={}
    config=json.loads((OLD/"run_config.json").read_text())
    for method in ("joint22","joint25","replacement22","bracket25"):
        with gzip.open(OLD/"traces"/f"{case}__{method}.jsonl.gz","rt") as f:trace=[json.loads(line) for line in f]
        points=np.array(config["paths"][config["specs"]["4"][method]["layout"]])
        last=np.zeros(2);events=[];movement=dict(survey=0.,measure=0.,clear=0.);regions={};cleared=set()
        for i,entry in enumerate(trace):
            req,resp=entry["request"],entry["response"];path=entry["path"]
            if "position" not in req:continue
            p=np.array([req["position"]["x"],req["position"]["y"]]);ch=req["channel"]
            kind="survey" if path=="/measure" and np.linalg.norm(points-p,axis=1).min()<1e-4 else "measure" if path=="/measure" else "clear"
            distance=float(np.linalg.norm(p-last));movement[kind]+=distance;last=p
            before=minimum_circle(regions[ch])[1] if ch in regions else None
            if resp.get("measure_result")=="direction":regions[ch]=update_region(regions.get(ch),p,resp["svd_deg"])
            if resp.get("clear_result")=="success":cleared.add(ch)
            if distance>1e-4 or kind!="survey":
                events.append(dict(index=i,kind=kind,channel=ch,position=p.tolist(),move_m=distance,
                    result=resp.get("measure_result",resp.get("clear_result")),angle=resp.get("svd_deg"),
                    region_radius_before_m=before,virtual_s=resp["virtual_time_s"],cleared=len(cleared)))
        result[method]=dict(movement_m=movement,commands=len(trace),virtual_s=trace[-1]["response"]["virtual_time_s"],events=events)
    (OUT/"reused_regression_diagnosis.json").write_text(json.dumps(dict(case=case,role="diagnosis of previously seen confirmation failure-of-speed; not a new holdout",methods=result),indent=2))
    for method,item in result.items():print(method,item["virtual_s"],item["commands"],{k:round(v,1) for k,v in item["movement_m"].items()})
    print("joint22 first active movements:")
    print(json.dumps([r for r in result["joint22"]["events"] if r["kind"]!="survey"][:14],indent=2))


if __name__=="__main__":main()
