"""Feedback-only replay, read-only input audit and final artifact bookkeeping."""
import ast
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import re
import subprocess
import numpy as np
from client import Client
from policies import Policy

ROOT=Path(__file__).resolve().parent
OUT=ROOT/"experiments/runs/2026-09-11_peer-paper-review"


def main():
    checks=[]
    cfg=json.loads((OUT/"ring_run_config.json").read_text())
    for method,points in cfg["paths"].items():
        for case in ("uniform__iid__67","boundary_min__n16__negative"):
            with gzip.open(OUT/"ring_traces"/f"{case}__{method}.jsonl.gz","rt") as f:
                trace=[json.loads(line) for line in f]
            index=0
            def replay(endpoint,raw):
                nonlocal index
                entry=trace[index]
                assert endpoint==entry["path"] and json.loads(raw)==entry["request"]
                index+=1
                return 200,entry["response"]
            p=Policy(Client(replay,robot_id="mock-robot"),np.array(points),mixed=False,active=True,optimized=True)
            p.run();assert index==len(trace)
            checks.append({"test":f"feedback_only_replay_{method}_{case}","commands":index,"passed":True})
    for name in ("policies.py","geometry.py","client.py","intelligent.py","coverage.py"):
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==cfg["code_sha256"][name]
    checks.append({"test":"unchanged_shared_policy_geometry", "passed":True})
    for item in json.loads((OUT/"paper_sha256.json").read_text()):
        assert hashlib.sha256((ROOT/"别人的结果/同学一"/item["name"]).read_bytes()).hexdigest()==item["sha256"]
    for relative,sha in json.loads((ROOT/"inputs_readonly_extract/input_sha256.json").read_text()).items():
        assert hashlib.sha256((ROOT.parent/relative).read_bytes()).hexdigest()==sha
    old=json.loads((ROOT/"experiments/runs/2026-09-10_independent/run_config.json").read_text())
    public="project/topic_probes/b_probe.py"
    assert hashlib.sha256((ROOT.parent/public).read_bytes()).hexdigest()==old["input_sha256"][public]
    checks.append({"test":"35_images_original_documents_public_probe_unchanged","passed":True})
    for repo in ("shumo-b","shumo-b-macos-handoff"):
        status=subprocess.run(["git","-C",str(ROOT/"reference"/repo),"status","--porcelain"],capture_output=True,text=True,check=True)
        assert not status.stdout.strip()
    checks.append({"test":"both_upstream_clones_clean","passed":True})
    rows=[json.loads(line) for line in (OUT/"ring_trials.jsonl").read_text().splitlines()]
    assert len(rows)==840 and all(r["all_cleared"] and not r["failure"] for r in rows)
    assert all(r["stop_reason"] in ("public_upper_bound_16","full_coverage_and_all_discovered_cleared") for r in rows)
    assert all(r["cleared"]==16 for r in rows if r["stop_reason"]=="public_upper_bound_16")
    assert all(r["commands"]<=2774 and r["total_virtual_s"]<=238102 for r in rows)
    checks.append({"test":"840_all_clear_valid_public_stops_and_limits","passed":True})
    for p in ROOT.glob("*.py"):ast.parse(p.read_text(),filename=str(p))
    checks.append({"test":"all_top_level_python_parses","passed":True})
    reports=[ROOT/"REPORT.md",ROOT/"PEER_PAPER_REVIEW.md",ROOT/"REPORT_PEER_REVIEW_UPDATE.md"]
    broken=[]
    for path in reports:
        for target in re.findall(r"\]\(([^)]+)\)",path.read_text()):
            if target.startswith(("http:","https:","#")):continue
            if not (path.parent/target.split("#")[0]).exists():broken.append([str(path),target])
    assert not broken,broken
    checks.append({"test":"reports_local_links_resolve","passed":True})
    result={"passed":len(checks),"failed":0,"checks":checks,"executions":840,"all_cleared":840,
            "stop_reasons":dict(Counter(r["stop_reason"] for r in rows)),"official_calls":0}
    (OUT/"final_checks.json").write_text(json.dumps(result,indent=2,ensure_ascii=False))
    previous=OUT/"previous_final_manifest_5901.json"
    if not previous.exists():previous.write_bytes((ROOT/"FINAL_MANIFEST.json").read_bytes())
    old_manifest=json.loads(previous.read_text());assert old_manifest["total_offline_executions"]==5901
    artifact_paths=list(ROOT.glob("*.py"))+reports+[OUT/"summary.md",OUT/"ring_run_config.json",OUT/"ring_trials.csv",OUT/"checks.json",OUT/"final_checks.json"]
    manifest={**{k:v for k,v in old_manifest.items() if k!="sha256"},"python_files_parsed":len(list(ROOT.glob("*.py"))),
              "peer_paper_layout_executions":840,"total_offline_executions":6741,"previous_manifest":str(previous.relative_to(ROOT)),
              "sha256":{str(p.relative_to(ROOT.parent)):hashlib.sha256(p.read_bytes()).hexdigest() for p in artifact_paths}}
    (ROOT/"FINAL_MANIFEST.json").write_text(json.dumps(manifest,indent=2,ensure_ascii=False))
    print(json.dumps({k:v for k,v in result.items() if k!="checks"},indent=2))


if __name__=="__main__":main()
