"""Freeze tail-constrained selection, then evaluate previously unused scene seeds."""
from dataclasses import asdict
import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback
import numpy as np
from metaheuristic_experiments import ROOT, OUT, TASKS, STRATEGIES, write_json, write_csv, trace_metrics
from peer_benchmark import PeerTransport, ErrorConfig, ErrorField, ScenarioConfig, generate, mandatory_conditions, Simulator, Limits, Protocol
from client import Client
from policies import Policy
from adaptive_routes import AdaptivePolicy


def main():
    if "--launch" in sys.argv:
        env=os.environ.copy()
        env.update(PYTHONDONTWRITEBYTECODE="1",OPENBLAS_NUM_THREADS="1",OMP_NUM_THREADS="1")
        with (OUT/"confirmation.log").open("a") as stream:
            process=subprocess.Popen([sys.executable,"-B",str(Path(__file__).resolve())],cwd=ROOT.parent,env=env,
                    stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
        (OUT/"confirmation.pid").write_text(str(process.pid)+"\n")
        print(f"Confirmation background PID {process.pid}; waits for main completion")
        return
    # Own background process waits; the interactive agent remains available.
    deadline=time.monotonic()+1800
    while not (OUT/"completion.json").exists():
        if time.monotonic()>deadline:
            raise RuntimeError("Main run has not finished after 30 minutes")
        time.sleep(5)
    if (OUT/"confirmation_selection.json").exists():
        raise RuntimeError("Preserve existing confirmation; never select again on its outcomes")
    all_rows=[json.loads(line) for line in (OUT/"trials.jsonl").read_text().splitlines()]
    routes=json.loads((OUT/"selected_routes.json").read_text())
    selection={}
    for task, point_set, mixed, active in TASKS:
        by_method={m:[r for r in all_rows if r["task"]==task and r["method"]==m] for m in STRATEGIES}
        baseline=by_method["two_opt"]
        caps={split:max(r["total_virtual_s"] for r in baseline if r["split"]==split) for split in ("ordinary","stress")}
        eligible=[]
        decisions=[]
        for method in STRATEGIES:
            rows=by_method[method]
            tails={split:max(r["total_virtual_s"] for r in rows if r["split"]==split) for split in ("ordinary","stress")}
            ok=all(r["all_cleared"] and not r["failure"] for r in rows) and all(tails[s]<=caps[s]+1e-6 for s in caps)
            mean=float(np.mean([r["per_source_s"] for r in rows if r["split"]=="ordinary"]))
            decisions.append({"method":method,"eligible":ok,"mean_per_source_s":mean,"tails_s":tails})
            if ok:
                eligible.append((round(mean,8),0 if method=="two_opt" else STRATEGIES.index(method)+1,method))
        chosen=min(eligible)[2]
        selection[task]={"method":chosen,"baseline_caps_s":caps,"decisions":decisions}
    frozen={"selection":selection,"base_seed":42,"confirmation_seeds":list(range(57,67)),
            "derivation":"42 + 15 + trial, trial=0..9", "route_sha256":hashlib.sha256((OUT/"selected_routes.json").read_bytes()).hexdigest(),
            "selection_time":time.strftime("%Y-%m-%d %H:%M:%S"),"confirmation_observed_before_selection":False,
            "source_count_given_to_policy":False,"official_requests":0}
    write_json(OUT/"confirmation_selection.json",frozen)
    print("Frozen selection: "+str({k:v["method"] for k,v in selection.items()}),flush=True)
    dest=OUT/"confirmation"
    dest.mkdir()
    (dest/"traces").mkdir()
    (dest/"scenarios_scoring_only").mkdir()
    rows=[]
    start=time.perf_counter()
    with (dest/"trials.jsonl").open("x") as stream:
        for task,point_set,mixed,active in TASKS:
            cfg=ScenarioConfig(directional_fraction=.5 if mixed else 0.)
            for label,scfg,ecfg in mandatory_conditions(cfg,ErrorConfig()):
                for seed in range(57,67):
                    scenario=generate(seed,scfg)
                    case_id=f"{label}__{seed}"
                    write_json(dest/"scenarios_scoring_only"/f"{task}__{case_id}.json",{"scenario":scenario.to_dict(),"error":asdict(ecfg)})
                    for role,method in (("baseline","two_opt"),("selected",selection[task]["method"])):
                        points=np.array(routes[point_set]["two_opt" if method.startswith("adaptive_") else method]["points"])
                        sim=Simulator(scenario,ErrorField(seed,ecfg),Limits(countdown_s=0))
                        cli=Client(PeerTransport(Protocol(sim)),robot_id="mock-robot")
                        policy=AdaptivePolicy(cli,points,polish=method=="adaptive_two_opt",mixed=mixed,active=active,optimized=True) if method.startswith("adaptive_") else Policy(cli,points,mixed=mixed,active=active,optimized=True)
                        began,cpu=time.perf_counter(),time.process_time()
                        failure,extra="",{}
                        try:
                            extra=policy.run()
                        except Exception as exc:
                            failure=repr(exc)
                            (dest/"traces"/f"{task}__{case_id}__{role}.error.txt").write_text(traceback.format_exc())
                        row={"task":task,"case_id":case_id,"category":label,"split":"confirmation","seed":seed,
                             "method":method,"role":role,"sources":len(scenario.sources),"cleared":len(sim.cleared),
                             "all_cleared":len(scenario.sources)==len(sim.cleared),"total_virtual_s":sim.virtual_time_s,
                             "per_source_s":sim.virtual_time_s/len(sim.cleared) if sim.cleared else None,
                             "commands":len(sim.trace),"wall_s":time.perf_counter()-began,"cpu_s":time.process_time()-cpu,
                             "failure":failure,"missed_channels":sorted(set(sim.sources)-sim.cleared),**trace_metrics(sim.trace),**extra}
                        rows.append(row)
                        stream.write(json.dumps(row)+"\n"); stream.flush()
                        with gzip.open(dest/"traces"/f"{task}__{case_id}__{role}.jsonl.gz","wt") as f:
                            for entry in sim.trace:
                                f.write(json.dumps(entry,separators=(",",":"))+"\n")
                print(f"confirmation {task} {label}: {len(rows)}/900 executions, elapsed {time.perf_counter()-start:.1f}s",flush=True)
    write_csv(dest/"trials.csv",rows)
    write_json(dest/"completion.json",{"executions":len(rows),"all_cleared":sum(r["all_cleared"] for r in rows),
            "errors":sum(bool(r["failure"]) for r in rows),"wall_s":time.perf_counter()-start})


if __name__=="__main__":
    main()
