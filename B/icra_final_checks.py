"""Independent certificate checks, exact feedback replay and archive manifest."""
import ast
from collections import Counter
import gzip
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import sys
import time
import numpy as np
from client import Client
from icra_confirmation import OUT,SPECS,all_paths
from replacement_experiments import build
from visibility_certificate import verify_cells

ROOT=Path(__file__).resolve().parent
RUNS={"joint-search":1488,"layout-alternatives":1488,"spatial-decisions":1767,
      "joint-task-routing":1488,"convex-visibility":1209,"icra-confirmation":1950}


def partition_check(certificate):
    if certificate.get("arena_radius") != 1800.:
        raise ValueError("partition requires arena_radius=1800")
    cells = certificate.get("cells")
    if cells is None or not len(cells):
        raise ValueError("missing nonempty partition leaves")
    leaves = set()
    ancestors = set()
    for cell in cells:
        if len(cell) != 4:
            raise ValueError("malformed partition leaf")
        x,y,h = cell[:3]
        if not np.isfinite([x,y,h]).all() or h <= 0:
            raise ValueError("partition leaf must be finite with positive half-width")
        key = (x,y,h)
        if key in leaves:
            raise ValueError("duplicate partition leaves")
        leaves.add(key)
        cx,cy,ch = 0.,0.,1800.
        # Only ancestors of submitted leaves can need subdivision. Validate each
        # path first so tiny/off-tree inputs cannot trigger an exponential search.
        # From radius 1800, binary64 reaches zero within 1086 halvings.
        for _ in range(1086):
            if (cx,cy,ch) == key:
                break
            half = ch/2
            if ch <= h or half == 0 or half == ch:
                raise ValueError("partition contains non-quadtree leaves")
            ancestors.add((cx,cy,ch))
            cx += half if x > cx else -half
            cy += half if y > cy else -half
            ch = half
        else:
            raise ValueError("partition leaf exceeds binary64 subdivision depth")
    r=1800.;stack=[(0.,0.,r)];seen=set();visited=0
    while stack:
        x,y,h=stack.pop();visited+=1
        if (x,y,h) in leaves:seen.add((x,y,h));continue
        nearest=np.maximum(np.abs([x,y])-h,0.)
        if nearest@nearest>r*r+1e-6:continue
        if (x,y,h) not in ancestors:
            raise ValueError(f"incomplete partition: uncovered quadtree cell {(x,y,h)}")
        half=h/2;stack.extend((x+dx*half,y+dy*half,half) for dx in (-1,1) for dy in (-1,1))
    if seen!=leaves:
        raise ValueError("partition contains overlapping or non-quadtree leaves")
    return dict(cells=len(seen),partition_nodes=visited)


def truth_margin(poly, point):
    """Signed containment margin in metres for a convex, CCW recorded region."""
    poly = np.asarray(poly, dtype=float)
    point = np.asarray(point, dtype=float)
    if (poly.ndim != 2 or poly.shape[1] != 2 or not len(poly)
            or not np.isfinite(poly).all() or point.shape != (2,)
            or not np.isfinite(point).all()):
        raise ValueError("truth containment requires a nonempty finite region and point")
    # Use the extreme endpoints for collinear regions, including repeated vertices.
    # Two opposite edge half-planes alone constrain a line, not a finite segment.
    axis = int(np.ptp(poly, axis=0).argmax())
    a = poly[poly[:,axis].argmin()]
    b = poly[poly[:,axis].argmax()]
    edge = b-a
    length = float(np.linalg.norm(edge))
    if length == 0:
        return -float(np.linalg.norm(point-a))
    offsets = poly-a
    cross = edge[0]*offsets[:,1]-edge[1]*offsets[:,0]
    if np.all(cross == 0):
        projection = float((point-a)@edge/(length*length))
        closest = a+min(1.,max(0.,projection))*edge
        return -float(np.linalg.norm(point-closest))
    edges = np.roll(poly,-1,axis=0)-poly
    norms = np.linalg.norm(edges,axis=1)
    good = norms > 0
    relative = point-poly
    crosses = edges[:,0]*relative[:,1]-edges[:,1]*relative[:,0]
    return float((crosses[good]/norms[good]).min())


class RecordedRegions(dict):
    """Observe public-derived regions without giving the policy any truth."""
    def __init__(self):super().__init__();self.history=[]
    def __setitem__(self,ch,poly):
        self.history.append((ch,np.asarray(poly).copy()));super().__setitem__(ch,poly)


def main():
    checks=[];paths=all_paths();cfg=json.loads((OUT/"run_config.json").read_text())
    for problem,methods in SPECS.items():
        for method,spec in methods.items():
            for case_id in ("uniform__iid__77","boundary_outward__n10__negative","near_collinear__n16__positive","cluster_far20__n13__spatial"):
                case=f"q{problem}__{case_id}"
                with gzip.open(OUT/"traces"/f"{case}__{method}.jsonl.gz","rt") as f:trace=[json.loads(line) for line in f]
                index=0
                def replay(endpoint,raw):
                    nonlocal index
                    entry=trace[index]
                    if not (endpoint==entry["path"] and json.loads(raw)==entry["request"]):
                        raise ValueError((method,index))
                    index+=1;return 200,entry["response"]
                policy=build(Client(replay,robot_id="mock-robot"),spec,problem,paths)
                recorded=RecordedRegions();policy.regions=recorded
                stats=policy.run()
                if not (index==len(trace)):
                    raise ValueError('replay did not consume the full trace')
                # Only AFTER the feedback-only replay, read scoring truth.
                fixture=json.loads((OUT/"scenarios_scoring_only"/f"{case}.json").read_text())
                sources={s["channel"]:np.array([s["x"],s["y"]]) for s in fixture["scenario"]["sources"]}
                min_margin=math.inf
                for ch,poly in recorded.history:
                    margin=truth_margin(poly,sources[ch]);min_margin=min(min_margin,margin)
                    if margin < -1e-5:
                        raise ValueError(f"truth outside recorded region: {(problem,method,case_id,ch,margin)}")
                checks.append(dict(test=f"feedback_only_replay_and_region_containment_q{problem}_{method}_{case_id}",passed=True,commands=index,region_updates=len(recorded.history),minimum_truth_margin_m=min_margin))
    certified=json.loads((ROOT/"experiments/runs/2026-09-11_convex-visibility/certified_layouts.json").read_text())
    for name,item in certified.items():
        verification=verify_cells(item["points"],item["certificate"]);partition=partition_check(item["certificate"])
        checks.append(dict(test=f"continuous_partition_and_independent_hulls_{name}",passed=True,**verification,**partition))
    # Snapshot hashes refer to the code actually frozen for each run, even if
    # a later file appends a separate helper; no old experiment is overwritten.
    completed=[]
    for name,count in RUNS.items():
        folder=ROOT/"experiments/runs"/f"2026-09-11_{name}"
        completion=json.loads((folder/"completion.json").read_text())
        if not (completion["executions"]==count):
            raise ValueError('archive execution count mismatch')
        rows=[json.loads(line) for line in (folder/"trials.jsonl").read_text().splitlines()]
        if not (len(rows)==count and all(r["all_cleared"] and not r["failure"] for r in rows)):
            raise ValueError('archive rows must match the count and all clear without failures')
        if not (all(r.get("inconsistent_updates",0)==0 and r.get("bracket_cut_inconsistencies",0)==0 for r in rows)):
            raise ValueError('archive contains inconsistent region updates')
        if not (all(r["cleared"]==16 for r in rows if r["stop_reason"]=="public_upper_bound_16")):
            raise ValueError('public upper-bound stop requires 16 cleared sources')
        if not (all(r["total_virtual_s"]<360000 and r["commands"]<=9766 for r in rows)):
            raise ValueError('archive exceeds virtual time or command limits')
        config_name="evaluation_config.json" if name=="layout-alternatives" else "run_config.json"
        snapshot_name="evaluation_code_snapshot" if name=="layout-alternatives" else "code_snapshot"
        config=json.loads((folder/config_name).read_text())
        for filename,sha in config["code_sha256"].items():
            if not (hashlib.sha256((folder/snapshot_name/filename).read_bytes()).hexdigest()==sha):
                raise ValueError((name,filename))
        completed.append(dict(run=name,executions=count,all_cleared=count,stop_reasons=dict(Counter(r["stop_reason"] for r in rows))))
        checks.append(dict(test=f"completed_archive_counts_stops_snapshots_{name}",passed=True,executions=count))
    for relative,sha in json.loads((ROOT/"inputs_readonly_extract/input_sha256.json").read_text()).items():
        if not (hashlib.sha256((ROOT.parent/relative).read_bytes()).hexdigest()==sha):
            raise ValueError('original input hash mismatch')
    old=json.loads((ROOT/"experiments/runs/2026-09-10_independent/run_config.json").read_text())
    public="project/topic_probes/b_probe.py"
    if not (hashlib.sha256((ROOT.parent/public).read_bytes()).hexdigest()==old["input_sha256"][public]):
        raise ValueError('public probe hash mismatch')
    for item in json.loads((ROOT/"experiments/runs/2026-09-11_peer-paper-review/paper_sha256.json").read_text()):
        if not (hashlib.sha256((ROOT/"别人的结果/同学一"/item["name"]).read_bytes()).hexdigest()==item["sha256"]):
            raise ValueError('peer paper hash mismatch')
    for repo in ("shumo-b","shumo-b-macos-handoff"):
        process=subprocess.run(["git","-C",str(ROOT/"reference"/repo),"status","--porcelain"],capture_output=True,text=True,check=True)
        if process.stdout.strip():
            raise ValueError('upstream clone has local changes')
    checks.append(dict(test="original_documents_35_peer_images_public_probe_and_upstream_clones_unchanged",passed=True))
    for p in ROOT.glob("*.py"):ast.parse(p.read_text(),filename=str(p))
    checks.append(dict(test="all_top_level_python_parses",passed=True))
    report_files=[ROOT/name for name in ("REPORT.md","ICRA_CONNECTION.md","ROBUST_GUARANTEES_UPDATE.md","REPORT_ICRA_UPDATE.md","GOAL.md")]
    broken=[]
    for p in report_files:
        for target in re.findall(r"\]\(([^)]+)\)",p.read_text()):
            if target.startswith(("https:","http:","#")):continue
            if not (p.parent/target.split("#")[0]).exists():broken.append([p.name,target])
    if broken:
        raise ValueError(broken)
    checks.append(dict(test="report_links_resolve",passed=True))
    result=dict(passed=len(checks),failed=0,checks=checks,completed_runs=completed,official_calls=0,feedback_replays=40,new_scored_executions=sum(RUNS.values()))
    (OUT/"final_checks.json").write_text(json.dumps(result,indent=2,ensure_ascii=False))
    previous=OUT/"previous_final_manifest_6741.json"
    if not previous.exists():previous.write_bytes((ROOT/"FINAL_MANIFEST.json").read_bytes())
    prior=json.loads(previous.read_text())
    if not (prior["total_offline_executions"]==6741):
        raise ValueError('previous manifest execution count mismatch')
    artifacts=list(ROOT.glob("*.py"))+report_files+[OUT/"summary.md",OUT/"trials.csv",OUT/"run_config.json",OUT/"final_checks.json"]
    manifest={**{k:v for k,v in prior.items() if k!="sha256"},"python_files_parsed":len(list(ROOT.glob("*.py"))),
        "icra_related_training_and_confirmation_executions":sum(RUNS.values()),"total_offline_executions":6741+sum(RUNS.values()),
        "all_scored_runs_cleared":True,"previous_manifest":str(previous.relative_to(ROOT)),"official_calls":0,
        "sha256":{str(p.relative_to(ROOT.parent)):hashlib.sha256(p.read_bytes()).hexdigest() for p in artifacts}}
    (ROOT/"FINAL_MANIFEST.json").write_text(json.dumps(manifest,indent=2,ensure_ascii=False))
    print(json.dumps({k:v for k,v in result.items() if k not in ("checks","completed_runs")},indent=2))


if __name__=="__main__":main()
