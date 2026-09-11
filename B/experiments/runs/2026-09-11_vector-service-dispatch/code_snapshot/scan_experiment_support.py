"""Recorded single-process training harness for the new scan variants."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from metaheuristic_experiments import write_json
import spatial_decision_experiments as engine

ROOT=Path(__file__).resolve().parent


def freeze(out,specs,paths,note,extra=None):
    if (out/"run_config.json").exists():raise RuntimeError("Preserving scored archive")
    checked=json.loads((out/"checks.json").read_text());assert checked["failed"]==0
    snapshot=out/"code_snapshot";snapshot.mkdir();hashes={}
    for p in ROOT.glob("*.py"):
        raw=p.read_bytes();(snapshot/p.name).write_bytes(raw);hashes[p.name]=hashlib.sha256(raw).hexdigest()
    count=sum(map(len,specs.values()))*93
    config=dict(base_seed=42,training_seeds=list(range(67,72)),
        derivation="42+25+repeat; reused training scenes",stress_derivation="Q3 [42,35,layout_index,count], Q4 [42,20,layout_index,count]",
        untouched_future_seeds=list(range(147,157)),specs=specs,paths={k:v.tolist() for k,v in paths.items()},
        expected_executions=count,selection=note,virtual_upper_bound_s=335136,instruction_upper_bound=9766,
        code_sha256=hashes,python=sys.executable,cpu_threads=1,truth_to_policy=False,official_calls=0,
        peer_commit="c477d3660368f27c7131a0591426b4c4f107ea5d")
    if extra:config.update(extra)
    write_json(out/"run_config.json",config)
    (out/"precheck.md").write_text(f"# 训练前检查\n\n{checked['passed']}项通过；{count}次计分，75普通+18压力/方法。{note} 未来147—156未生成，正式请求0。\n")


def main(out,specs,build,paths,check,freeze,script):
    parser=argparse.ArgumentParser();parser.add_argument("--check",action="store_true");parser.add_argument("--launch",action="store_true")
    args=parser.parse_args();engine.OUT,engine.SPECS,engine.build,engine.freeze,engine.all_layouts=out,specs,build,freeze,paths
    if args.check:check()
    elif args.launch:
        if (out/"run_config.json").exists():raise RuntimeError("Preserving scored archive")
        env=os.environ.copy();env.update(PYTHONDONTWRITEBYTECODE="1",OPENBLAS_NUM_THREADS="1",OMP_NUM_THREADS="1",
                                         MPLCONFIGDIR=str(ROOT/".mplconfig"),XDG_CACHE_HOME=str(ROOT/".cache"))
        with (out/"log.txt").open("a") as stream:
            p=subprocess.Popen([sys.executable,"-B",str(Path(script).resolve())],cwd=ROOT.parent,env=env,
                               stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
        (out/"background.pid").write_text(str(p.pid)+"\n");print("Background PID",p.pid)
    else:engine.run()
