"""Compare public-16 empty-channel deletion against the preserved scan plan."""
import gzip
import json
from pathlib import Path
from client import Client
from public_count_scan_policy import PublicCountCompletionPolicy,PublicCountWidthPolicy,PublicCountFastWidthPolicy
from public_count_replay import expanded_plan,verify_actual_cost
from layout_alternative_experiments import training_cases
from metaheuristic_experiments import write_json
from peer_benchmark import PeerTransport,Simulator,ErrorField,Limits,Protocol
import lean_scan_experiments as lean
import deferred_skip_experiments as original
import scan_experiment_support as support

ROOT=Path(__file__).resolve().parent
OUT=ROOT/"experiments/runs/2026-09-11_public-count-scan"
FAMILIES=((3,"lean_deferred_area7","area_return1_7"),
          (4,"lean_deferred_width015","width40_f015_22"),
          (4,"lean_cheap_predict8_width015","width40_f015_22"),
          (4,"lean_cheap_predict8_locked_width015","locked_noskip_width015"))
SPECS={3:{},4:{}}
for problem,name,reference in FAMILIES:
    old=lean.SPECS[problem][name].copy();SPECS[problem][name]=old
    SPECS[problem]["count_"+name[5:]]=dict(old,kind=old["kind"].replace("lean_","public_count_",1))
EXPECTED=744


def paths():return lean.paths()


def build(client,spec,problem,all_paths):
    if not spec["kind"].startswith("public_count_"):return lean.build(client,spec,problem,all_paths)
    params=spec.copy();kind=params.pop("kind");stations=all_paths[params.pop("layout")]
    if problem==4:params.setdefault("trial_radius",40.)
    cls={"public_count_completion":PublicCountCompletionPolicy,"public_count_width":PublicCountWidthPolicy,
         "public_count_fast_width":PublicCountFastWidthPolicy}[kind]
    return cls(client,stations,mixed=problem==4,**params)


def check():
    if (OUT/"checks.json").exists():raise RuntimeError("Preserving checks")
    checks=[];details=[];all_paths=paths()
    for problem,name,reference in FAMILIES:
        candidate="count_"+name[5:]
        for case_id,category,split,scenario,error in training_cases(problem):
            with gzip.open(lean.OUT/"traces"/f"q{problem}__{case_id}__{name}.jsonl.gz","rt") as stream:
                trace=[json.loads(line) for line in stream]
            index=0
            def transport(endpoint,raw):
                nonlocal index
                entry=trace[index];assert endpoint==entry["path"] and json.loads(raw)==entry["request"],(candidate,case_id,index)
                index+=1;return 200,entry["response"]
            stats=build(Client(transport,robot_id="mock-robot"),dict(SPECS[problem][candidate],public_empty_skip=False),problem,all_paths).run()
            assert index==len(trace) and stats["public_empty_scan_skips"]==0
            checks.append(dict(test=f"disabled_public_count_q{problem}_{candidate}_{case_id}",passed=True))
            with gzip.open(original.OUT/"traces"/f"q{problem}__{case_id}__{reference}.jsonl.gz","rt") as stream:
                baseline=[json.loads(line) for line in stream]
            detail=expanded_plan(baseline,SPECS[problem][candidate],problem,all_paths,build)
            if len(scenario.sources)<16:assert detail["public_empty_skips"]==0
            details.append(dict(problem=problem,method=candidate,case_id=case_id,**detail))
            checks.append(dict(test=f"public_feedback_expanded_count_q{problem}_{candidate}_{case_id}",passed=True,public_empty_skips=detail["public_empty_skips"]))
            if split=="stress" and len(scenario.sources)==16:
                sim=Simulator(scenario,ErrorField(scenario.seed,error),Limits(countdown_s=0))
                actual_stats=build(Client(PeerTransport(Protocol(sim)),robot_id="mock-robot"),SPECS[problem][candidate],problem,all_paths).run()
                assert len(sim.cleared)==len(scenario.sources) and not actual_stats["inconsistent_updates"]
                cost=verify_actual_cost(baseline,sim.trace,detail,baseline[-1]["response"]["virtual_time_s"],sim.virtual_time_s)
                checks.append(dict(test=f"actual_count_deletion_cost_q{problem}_{candidate}_{case_id}",passed=True,**cost))
    write_json(OUT/"expanded_plan_checks.json",details)
    write_json(OUT/"checks.json",dict(passed=len(checks),failed=0,checks=checks,scored_executions=0,official_calls=0))
    print("Passed",len(checks),"public-empty deletions",sum(x["public_empty_skips"] for x in details),flush=True)


def freeze(all_paths):
    support.freeze(OUT,SPECS,all_paths,"公开16频道已实际发现后，才可原地删除其余空频道；保留原计划并独立重建正反馈集合与减费。",
                   dict(proof_files=["PUBLIC_COUNT_SCAN_GUARANTEE.md","DEFERRED_SCAN_GUARANTEE.md"]))


if __name__=="__main__":support.main(OUT,SPECS,build,paths,check,freeze,__file__)
