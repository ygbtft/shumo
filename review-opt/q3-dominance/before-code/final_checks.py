"""Final replay isolation, old-probe audit, package smoke and immutable-input checks."""
import ast
import gzip
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import time
import zipfile
import numpy as np
from client import Client
from policies import Policy

ROOT=Path(__file__).resolve().parent
OUT=ROOT/"experiments/runs/2026-09-10_peer-benchmark"


def main():
    checks=[]
    paths=json.loads((ROOT/"experiments/runs/2026-09-10_independent/routes.json").read_text())
    # Reconstruct policies from feedback alone, without constructing or importing any scene.
    for question,strategy in [(3,"active_2opt"),(4,"active_2opt"),(4,"square_cropped_2opt")]:
        trace=OUT/"traces"/f"q{question}_uniform__iid_42__{strategy}.jsonl.gz"
        with gzip.open(trace,"rt") as f:
            entries=[json.loads(line) for line in f]
        index=0
        def replay(path,raw):
            nonlocal index
            row=entries[index];index+=1
            assert path==row["path"] and json.loads(raw)==row["request"],f"Replay action differs at {index}"
            return 200,row["response"]
        name=f"q{question}_triangle_2opt" if strategy.startswith("active") else strategy
        result=Policy(Client(replay,"mock-robot"),np.array(paths[name]),mixed=question==4,
                      active=strategy.startswith("active"),optimized=True).run()
        assert index==len(entries)
        checks.append({"test":f"feedback_only_replay_q{question}_{strategy}","passed":True,"requests":index,
                       "truth_available":False})
    # Execute only the old class AST in isolation; no common.py import and no public writes.
    legacy=ROOT.parent/"project/topic_probes/b_probe.py"
    tree=ast.parse(legacy.read_text())
    definition=next(node for node in tree.body if isinstance(node,ast.ClassDef) and node.name=="SyntheticEnvironment")
    scope={"np":np,"math":math,"hashlib":hashlib,"time":time}
    exec(compile(ast.Module(body=[definition],type_ignores=[]),str(legacy),"exec"),scope)
    old=scope["SyntheticEnvironment"](42,False)
    old._sources={1:{"point":np.array([1000.,0.]),"radius":1500.,"directed":False,"facing":np.array([1.,0.])}}
    a=old.measure(np.array([0.,0.]),1);b=old.measure(np.array([-0.,0.]),1)
    checks.append({"test":"old_probe_signed_zero_location_key","passed":a==b,
                   "expected":"Same physical location must give the same direction","plus_zero_feedback":a,"minus_zero_feedback":b,
                   "interpretation":"Confirmed old-probe corner case if false; the new simulator and peer merge signed zeros"})
    original=json.loads((ROOT/"inputs_readonly_extract/input_sha256.json").read_text())
    for relative,expected in original.items():
        actual=hashlib.sha256((ROOT.parent/relative).read_bytes()).hexdigest()
        assert actual==expected
    frozen=json.loads((ROOT/"experiments/runs/2026-09-10_independent/run_config.json").read_text())
    assert hashlib.sha256(legacy.read_bytes()).hexdigest()==frozen["input_sha256"][str(legacy.relative_to(ROOT.parent))]
    checks.append({"test":"original_documents_and_public_probe_unchanged","passed":True,"files":4})
    for name in ["shumo-b","shumo-b-macos-handoff"]:
        result=subprocess.run(["git","-C",str(ROOT/"reference"/name),"status","--porcelain"],capture_output=True,text=True,check=True)
        assert not result.stdout.strip()
        checks.append({"test":f"upstream_clone_unchanged_{name}","passed":True})
    package=ROOT/"dist/b-robot-offline-and-practice.zip"
    stage=ROOT/"dist/package-smoke"
    if stage.exists():
        raise RuntimeError("Preserve prior package smoke output; use a new directory")
    stage.mkdir()
    with zipfile.ZipFile(package) as z:
        assert not any(".." in Path(name).parts or Path(name).is_absolute() for name in z.namelist())
        z.extractall(stage)
    executed=subprocess.run([sys.executable,"-B",str(stage/"b-robot/run_robot.py"),"--mode","offline","--problem","3","--strategy","active_2opt"],
                            cwd=stage,capture_output=True,text=True)
    (OUT/"package_smoke.log").write_text(executed.stdout+executed.stderr)
    assert executed.returncode==0
    summaries=list((stage/"b-robot/robot_runs").glob("*/summary.json"))
    assert len(summaries)==1
    score=json.loads(summaries[0].read_text())["source_truth"]
    assert score["all_cleared"]
    checks.append({"test":"portable_package_offline_q3","passed":True,"score":score,"windows_tested":False})
    (OUT/"final_checks.json").write_text(json.dumps({"checks":checks,"known_old_probe_bug_count":sum(not r["passed"] for r in checks)},ensure_ascii=False,indent=2))
    print(json.dumps(checks,ensure_ascii=False,indent=2))


if __name__=="__main__":
    main()
