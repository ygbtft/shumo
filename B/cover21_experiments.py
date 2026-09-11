"""Train certified 21-station layouts with matched source-service policies."""
import gzip
import json
import math
from pathlib import Path
import numpy as np
from client import Client
from coverage import route_length
from integer_visibility_certificate import verify_integer_certificate
from visibility_certificate import verify_cells
from icra_final_checks import partition_check
from layout_alternative_experiments import training_cases
from metaheuristic_experiments import write_json
from peer_benchmark import PeerTransport,Simulator,ErrorField,ErrorConfig,Limits,Protocol
from mock.scenario_gen import Source,Scenario
from mock.geometry import covered
import public_count_experiments as builders
import lean_scan_experiments as lean
import deferred_skip_experiments as deferred
import scan_experiment_support as support

ROOT=Path(__file__).resolve().parent
OUT=ROOT/"experiments/runs/2026-09-11_cover21-training"
LAYOUTS=("convex22","closed21_3","grid21_7","grid21_29")
TEMPLATES={"width":deferred.SPECS[4]["width40_f015_22"],
           "range":deferred.SPECS[4]["range_width015"],
           "predict":lean.SPECS[4]["lean_cheap_predict8_width015"],
           "locked_full":deferred.SPECS[4]["locked_noskip_width015"],
           "count_locked":builders.SPECS[4]["count_cheap_predict8_locked_width015"]}
SPECS={4:{f"{label}_{layout}":dict(spec,layout=layout) for layout in LAYOUTS for label,spec in TEMPLATES.items()}}
EXPECTED=1860
build=builders.build


def certificates():
    rounded=json.loads((ROOT/"experiments/runs/2026-09-11_rounded-cover21/certified_layouts.json").read_text())
    closed=json.loads((ROOT/"experiments/runs/2026-09-11_closed-cover21/certified_layouts.json").read_text())
    old=json.loads((ROOT/"experiments/runs/2026-09-11_convex-visibility/certified_layouts.json").read_text())
    return {"convex22":old["convex22_72"],"closed21_3":closed["closed21_3"],
            "grid21_7":rounded["grid21_7"],"grid21_29":rounded["grid21_29"]}


def paths():
    result=builders.paths()
    result.update({name:np.asarray(item["route"]) for name,item in certificates().items()})
    return result


def axis_cases():
    for count in (10,13,16):
        positions=[(1800.,0.),(0.,1800.),(-1800.,0.),(0.,-1800.)]
        positions += [(800.*math.cos(i*2*math.pi/(count-4)+.31),800.*math.sin(i*2*math.pi/(count-4)+.31)) for i in range(count-4)]
        channels=[20]+list(range(1,count))
        sources=tuple(Source(ch,x,y,1000.,float(90*i) if i<4 else float((i*73)%360)) for i,(ch,(x,y)) in enumerate(zip(channels,positions)))
        for index,sign in enumerate(("positive","negative","spatial")):
            yield f"axis_tangencies__n{count}__{sign}",Scenario(42+4100+10*count+index,sources,dict(role="unscored exact cardinal boundary stress")),ErrorConfig(model="adversarial",adversarial_sign=sign)


def check():
    if (OUT/"checks.json").exists():raise RuntimeError("Preserving checks")
    checks=[];all_paths=paths();selected=certificates()
    for name,item in selected.items():
        p=np.asarray(item["points"]);cert=item["certificate"]
        detail=verify_integer_certificate(p,cert) if cert.get("exact_integer_predicates") else {**verify_cells(p,cert),**partition_check(cert)}
        assert np.linalg.norm(p,axis=1).max()<1950 and len(p)<=22
        assert {tuple(x) for x in p}=={tuple(x) for x in all_paths[name]}
        checks.append(dict(test=f"continuous_certificate_and_actual_route_{name}",passed=True,**detail))
        for i,g in enumerate(((1800.,0.),(0.,1800.),(-1800.,0.),(0.,-1800.))):
            source=Source(1,*g,1000.,float(i*90))
            assert any(covered(source,tuple(q)) for q in all_paths[name])
            checks.append(dict(test=f"unchanged_backend_closed_cardinal_face_{name}_{i}",passed=True))
    boundary=list(axis_cases())
    (OUT/"boundary_precheck_traces").mkdir();(OUT/"boundary_precheck_fixtures").mkdir()
    for case_id,scenario,error in boundary:
        from dataclasses import asdict
        write_json(OUT/"boundary_precheck_fixtures"/f"{case_id}.json",dict(scenario=scenario.to_dict(),error=asdict(error)))
    stress=[(case_id,scenario,error,False) for case_id,category,split,scenario,error in training_cases(4) if split=="stress"]
    stress += [(case_id,scenario,error,True) for case_id,scenario,error in boundary]
    for method,spec in SPECS[4].items():
        for case_id,scenario,error,save_trace in stress:
            sim=Simulator(scenario,ErrorField(scenario.seed,error),Limits(countdown_s=0))
            stats=build(Client(PeerTransport(Protocol(sim)),robot_id="mock-robot"),spec,4,all_paths).run()
            assert len(sim.cleared)==len(scenario.sources) and not stats["inconsistent_updates"] and not stats.get("bracket_cut_inconsistencies",0)
            assert sim.virtual_time_s<335136 and len(sim.trace)<=9766
            if len(scenario.sources)<16:assert stats.get("public_empty_scan_skips",0)==0
            if save_trace:
                with gzip.open(OUT/"boundary_precheck_traces"/f"{case_id}__{method}.jsonl.gz","wt") as stream:
                    for entry in sim.trace:stream.write(json.dumps(entry,separators=(",",":"))+"\n")
            checks.append(dict(test=f"full_protocol_{method}_{case_id}",passed=True,virtual_s=sim.virtual_time_s,commands=len(sim.trace),
                               stop_reason=stats["stop_reason"],public_empty_skips=stats.get("public_empty_scan_skips",0)))
    write_json(OUT/"checks.json",dict(passed=len(checks),failed=0,checks=checks,scored_executions=0,official_calls=0))
    print("Passed",len(checks),flush=True)


def freeze(all_paths):
    selected=certificates()
    write_json(OUT/"selected_layouts.json",selected)
    support.freeze(OUT,SPECS,all_paths,"三种21站整数布局：最短相切、最短严格内含，以及另一内圈/相位。每种与22站使用相同无删除、距离、预测和固定站序策略；静态路长不作为整局优胜依据。",
                   dict(proof_files=["REGULAR_RING_OBSTRUCTION.md","PUBLIC_COUNT_SCAN_GUARANTEE.md"],
                        selection_before_training="closed21_3 shortest integer route including exact tangency; grid21_7 shortest integer route with strict hull certificate; grid21_29 shortest certified integer phase-zero alternative",
                        layout_metadata={name:dict(stations=len(item["points"]),route_length_m=route_length(np.asarray(item["route"])),exact_closed=item["certificate"].get("exact_integer_predicates",False)) for name,item in selected.items()}))


if __name__=="__main__":support.main(OUT,SPECS,build,paths,check,freeze,__file__)
