"""Audit new coverage/scan controls, every confirmation command, and artifacts."""
import argparse
import ast
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time
import numpy as np
import mission_final_checks as feedback
from deferred_replay import expanded_plan as expanded_known,verify_actual_cost
from public_count_replay import expanded_plan as expanded_count
import deferred_skip_experiments as old
import lean_scan_experiments as lean
import public_count_experiments as count
import cover21_experiments as training
from cover21_confirmation import ROOT,OUT,SPECS,build,all_paths

RUNS={"lean-scan":1116,"public-count-scan":744,"cover21-training":1860,"cover21-confirmation":3900}
GEOMETRY_RUNS=("odd-ring-cover","rounded-cover21","closed-cover21")
REPORTS=("REPORT.md","REPORT_COVER21_UPDATE.md","REGULAR_RING_OBSTRUCTION.md","PUBLIC_COUNT_SCAN_GUARANTEE.md",
         "INTEGER_COVERAGE_GUARANTEE.md","GOAL.md","ICRA_CONNECTION.md","COMMANDS.md")
BASIC_CASES=("uniform__iid__147","boundary_outward__n10__negative","near_collinear__n16__positive","range_transition__n13__negative")
HTTP_METHODS=((3,"lean_deferred_area7"),(4,"range_grid21_29"),(4,"predict_grid21_29"),(4,"count_locked_grid21_29"))


def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def rows_for(folder):return [json.loads(line) for line in (folder/"trials.jsonl").read_text().splitlines()]


def exact_pairs(folder,pairs):
    rows=rows_for(folder);lookup={(r["problem"],r["method"],r["case_id"]):r for r in rows};records=[]
    for problem,candidate,baseline in pairs:
        for row in rows:
            if row["problem"]!=problem or row["method"]!=candidate:continue
            previous=lookup[problem,baseline,row["case_id"]]
            assert row["total_virtual_s"]==previous["total_virtual_s"] and row["commands"]==previous["commands"]
            a=feedback.load_trace(folder/"traces"/f"q{problem}__{row['case_id']}__{baseline}.jsonl.gz")
            b=feedback.load_trace(folder/"traces"/f"q{problem}__{row['case_id']}__{candidate}.jsonl.gz")
            def extract(trace):
                return [(e["path"],e["request"],e["response"]["virtual_time_s"],e["response"].get("measure_result"),
                         e["response"].get("svd_deg"),e["response"].get("clear_result")) for e in trace]
            assert extract(a)==extract(b)
            records.append(dict(problem=problem,candidate=candidate,baseline=baseline,case_id=row["case_id"],passed=True))
    result=dict(passed=len(records),failed=0,checks=records,scored_executions=0,official_calls=0)
    (folder/"exact_computation_audit.json").write_text(json.dumps(result,indent=2))
    return dict(test=f"actual_same_decision_pairs_{folder.name}",passed=True,pairs=len(records))


def deletion_audit(folder,specs,factory,paths):
    rows=rows_for(folder);reference_folder=old.OUT if folder==count.OUT else folder
    references={(r["problem"],r["method"],r["case_id"]):r for r in rows_for(reference_folder)}
    records=[];station_audits=[]
    def observed_factory(client,spec,problem,paths):
        client.transcript=[];policy=factory(client,spec,problem,paths)
        original_measure=policy.measure;original_scan=policy.scan_station;empty_events=[]
        def observed_measure(q,ch):
            before=client.position
            result=original_measure(q,ch)
            if result=="certified_no_reception" and policy._last_skip_certificate["kind"]=="public_16_bound":
                actual_positive={e["request"]["channel"] for e in client.transcript if e["path"]=="/measure" and e["response"]["measure_result"] in ("direction","near")}
                assert len(actual_positive)==16 and ch not in actual_positive
                assert set(policy._last_skip_certificate["discovered_channels"])==actual_positive
                assert np.array_equal(before,q) and np.array_equal(client.position,before)
                empty_events.append((ch,tuple(q)))
            return result
        policy.measure=observed_measure
        def observed_scan(q,key):
            initial_unknown={ch for ch in range(1,21) if ch not in policy.regions and ch not in policy.cleared}
            before=len(client.transcript);empty_start=len(empty_events);position_before=client.position
            original_scan(q,key)
            actual={e["request"]["channel"] for e in client.transcript[before:] if e["path"]=="/measure" and e["request"]["position"]==dict(x=float(q[0]),y=float(q[1]))}
            declared={ch for ch,pos in empty_events[empty_start:] if pos==tuple(q)}
            assert len(initial_unknown)>=4 and initial_unknown<=actual|declared
            if not client.transcript[before:]:assert np.array_equal(position_before,q)
            station_audits.append(dict(initial_unknown=len(initial_unknown),actual_unknown=len(initial_unknown&actual),declared_empty=len(declared)))
        policy.scan_station=observed_scan
        return policy
    for row in rows:
        problem,method,case=row["problem"],row["method"],row["case_id"]
        spec=specs[problem][method];kind=spec["kind"]
        if not kind.startswith(("deferred_","cheap_prediction_","lean_","public_count_")):continue
        if folder==count.OUT and not kind.startswith("public_count_"):continue
        if folder==count.OUT:
            baseline="area_return1_7" if problem==3 else "locked_noskip_width015" if spec.get("dispatch_model")=="locked" else "width40_f015_22"
        elif problem==3:baseline="area_return1_7"
        else:baseline=("locked_full_" if spec.get("dispatch_model")=="locked" else "width_")+spec["layout"]
        previous=references[problem,baseline,case]
        fixture=f"q{problem}__{case}.json"
        assert read(folder/"scenarios_scoring_only"/fixture)==read(reference_folder/"scenarios_scoring_only"/fixture)
        a=feedback.load_trace(reference_folder/"traces"/f"q{problem}__{case}__{baseline}.jsonl.gz")
        b=feedback.load_trace(folder/"traces"/f"q{problem}__{case}__{method}.jsonl.gz")
        expand=expanded_count if kind.startswith("public_count_") else expanded_known
        detail=expand(a,spec,problem,paths,observed_factory)
        cost=verify_actual_cost(a,b,detail,previous["total_virtual_s"],row["total_virtual_s"])
        assert detail["skipped"]==row["certified_scan_skips"]
        assert detail["pair_skips"]==row["predicted_pair_skips"]
        assert detail.get("public_empty_skips",0)==row.get("public_empty_scan_skips",0)
        if row["sources"]<16:assert detail.get("public_empty_skips",0)==0
        records.append(dict(problem=problem,method=method,baseline=baseline,case_id=case,split=row["split"],
                            pair_skips=detail["pair_skips"],public_empty_skips=detail.get("public_empty_skips",0),
                            nonstationary_skips=detail["nonstationary_skips"],**cost))
    expected=372 if folder==count.OUT else 744 if folder==training.OUT else 1755
    assert len(records)==expected,(folder,len(records),expected)
    result=dict(passed=len(records),failed=0,checks=records,scan_segments=len(station_audits),
                minimum_actual_unknown=min(s["actual_unknown"] for s in station_audits),
                minimum_unknown_coverage_actions=min(s["actual_unknown"]+s["declared_empty"] for s in station_audits),
                public_empty_skips=sum(r["public_empty_skips"] for r in records),pair_skips=sum(r["pair_skips"] for r in records),
                skipped=sum(r["skipped"] for r in records),nonstationary_skips=sum(r["nonstationary_skips"] for r in records),
                saved_s=sum(r["virtual_saved_s"] for r in records),scored_executions=0,official_calls=0)
    (folder/"certified_deletion_audit.json").write_text(json.dumps(result,indent=2))
    return dict(test=f"expanded_public_plans_and_exact_cost_{folder.name}",passed=True,
                expanded_replays=len(records),scan_segments=len(station_audits),public_empty_skips=result["public_empty_skips"],skipped=result["skipped"])


def verify():
    if (OUT/"final_checks.json").exists():raise RuntimeError("Preserving completed audit")
    began=time.perf_counter();paths=all_paths();checks=[];completed=[]
    feedback.OUT,feedback.SPECS,feedback.build=OUT,SPECS,build
    for problem,methods in SPECS.items():
        for method in methods:
            for case in BASIC_CASES:checks.append(feedback.feedback_replay(problem,method,case,paths))
    print("80 public-feedback region and clearance replays passed",flush=True)
    for name,expected in RUNS.items():
        folder=ROOT/"experiments/runs"/f"2026-09-11_{name}";rows=rows_for(folder)
        done=read(folder/"completion.json");config=read(folder/"run_config.json")
        assert done["executions"]==done["all_cleared"]==len(rows)==expected and done["errors"]==0
        assert all(r["all_cleared"] and not r["failure"] and not r.get("inconsistent_updates",0) and not r.get("bracket_cut_inconsistencies",0) for r in rows)
        for r in rows:
            assert r["total_virtual_s"]<335136 and r["commands"]<=9766
            assert r["stop_reason"] in ("public_upper_bound_16","full_coverage_and_all_discovered_cleared")
            if r["stop_reason"]=="public_upper_bound_16":assert r["cleared"]==16
            if r["sources"]<16:assert r.get("public_empty_scan_skips",0)==0
            if "minimum_unknown_actions_per_station" in r:assert r["minimum_unknown_actions_per_station"]>=4
            elif "minimum_actual_unknown_per_station" in r:assert r["minimum_actual_unknown_per_station"]>=4
            if "source_interruptions" in r:
                spec=config["specs"][str(r["problem"])][r["method"]]
                assert r["source_interruptions"]<=spec.get("pause_limit",16)
                assert r["maximum_source_rounds"]<=(10 if r["problem"]==4 else 3)
                assert r["maximum_source_primary_rf"]<=(20 if r["problem"]==4 else 3)
        for filename,value in config["code_sha256"].items():
            frozen=folder/"code_snapshot"/filename;assert sha(frozen)==value;ast.parse(frozen.read_text())
        completed.append(dict(run=name,executions=expected,all_cleared=expected,stop_reasons=dict(Counter(r["stop_reason"] for r in rows))))
        checks.append(dict(test=f"scored_counts_budgets_stops_and_snapshots_{name}",passed=True,executions=expected))
        if name=="cover21-confirmation":
            assert sorted({r["seed"] for r in rows if r["split"]=="ordinary"})==list(range(147,157)) and config["freeze_before_truth_generation"]
            checks.append(feedback.physics_audit(rows))
    print("All 7620 scored rows and 3900 confirmation physical traces passed",flush=True)
    for folder,specs,factory in ((count.OUT,count.SPECS,count.build),(training.OUT,training.SPECS,training.build),(OUT,SPECS,build)):
        checks.append(deletion_audit(folder,specs,factory,paths));print("Expanded/cost",folder.name,flush=True)
    checks.append(exact_pairs(lean.OUT,[(p,"lean_"+m,m) for p,m,_ in lean.FAMILIES]))
    checks.append(exact_pairs(OUT,[(3,"lean_deferred_area7","deferred_area7"),(4,"predict_convex22","original_predict_convex22")]))
    print("948 actual same-decision pairs passed",flush=True)
    geometry=read(ROOT/"experiments/runs/2026-09-11_odd-ring-cover/geometry_audit.json")
    assert geometry["failed"]==0 and geometry["raw_real_witnesses"]==204
    checks.append(dict(test="saved_independent_continuous_and_counterexample_geometry_audit",passed=True,checks=geometry["passed"]))
    for name in GEOMETRY_RUNS:
        folder=ROOT/"experiments/runs"/f"2026-09-11_{name}";config=read(folder/"search_config.json")
        for filename,value in config["code_sha256"].items():assert sha(folder/"code_snapshot"/filename)==value
    checks.append(dict(test="three_geometry_search_snapshots_preserved",passed=True))
    for name,expected in (("lean-scan",570),("public-count-scan",780),("cover21-training",560)):
        result=read(ROOT/"experiments/runs"/f"2026-09-11_{name}"/"checks.json")
        assert result["passed"]==expected and result["failed"]==0
        checks.append(dict(test=f"saved_prechecks_{name}",passed=True,checks=expected))
    config=read(OUT/"run_config.json")
    critical=[n for n in config["code_sha256"] if n.endswith("_policy.py")]
    critical += ["policies.py","geometry.py","client.py","cover21_confirmation.py","cover21_experiments.py",
                 "lean_scan_experiments.py","public_count_experiments.py","run_bounded_robot.py","integer_visibility_certificate.py"]
    for name in critical:assert sha(ROOT/name)==config["code_sha256"][name],name
    for relative,value in config["layout_files_sha256"].items():assert sha(ROOT/relative)==value
    checks.append(dict(test="frozen_decisions_and_layout_coordinates_unchanged_since_before_new_truth",passed=True))
    http=read(OUT/"http_checks.json");assert http["passed"]==4 and http["failed"]==http["official_calls"]==0
    for problem,method in HTTP_METHODS:
        a=feedback.load_trace(OUT/f"protocol_{problem}_{method}_inprocess.jsonl.gz")
        b=feedback.load_trace(OUT/f"protocol_{problem}_{method}_owned_loopback_http.jsonl.gz")
        extract=lambda trace:[(e["path"],e["request"],e["response"]["virtual_time_s"],e["response"].get("measure_result"),e["response"].get("svd_deg"),e["response"].get("clear_result")) for e in trace]
        assert extract(a)==extract(b)
    checks.append(dict(test="four_owned_ephemeral_http_equivalences",passed=True))
    smokes=[]
    for problem,method in ((3,"lean_deferred_area7"),(4,"range_grid21_29")):
        folder=Path((OUT/f"smoke{problem}_log.txt").read_text().splitlines()[-1]);r=read(folder/"summary.json")
        assert r["series"]=="cover21" and r["method"]==method and r["seed"]==42 and r["all_cleared"] and r["official_calls"]==0
        smokes.append(dict(problem=problem,method=method,folder=str(folder.relative_to(ROOT))))
    (OUT/"cli_smokes.json").write_text(json.dumps(dict(checks=smokes,scored_executions=0,official_calls=0),indent=2))
    checks.append(dict(test="two_offline_cover21_cli_entries",passed=True))
    for relative,value in read(ROOT/"inputs_readonly_extract/input_sha256.json").items():assert sha(ROOT.parent/relative)==value
    public="project/topic_probes/b_probe.py"
    assert sha(ROOT.parent/public)==read(ROOT/"experiments/runs/2026-09-10_independent/run_config.json")["input_sha256"][public]
    for item in read(ROOT/"experiments/runs/2026-09-11_peer-paper-review/paper_sha256.json"):
        assert sha(ROOT/"别人的结果/同学一"/item["name"])==item["sha256"]
    for name in ("shumo-b","shumo-b-macos-handoff"):
        result=subprocess.run(["git","-C",str(ROOT/"reference"/name),"status","--porcelain"],capture_output=True,text=True,check=True);assert not result.stdout.strip()
    checks.append(dict(test="original_documents_peer_images_public_probe_and_upstreams_unchanged",passed=True))
    result=dict(passed=len(checks),failed=0,checks=checks,completed_runs=completed,feedback_region_replays=80,
                expanded_deletion_replays=2871,exact_computation_pairs=948,new_scored_executions=7620,official_calls=0,wall_s=time.perf_counter()-began)
    (OUT/"final_checks.json").write_text(json.dumps(result,indent=2,ensure_ascii=False))
    print(json.dumps({k:v for k,v in result.items() if k not in ("checks","completed_runs")},indent=2),flush=True)


def finalize():
    audit=read(OUT/"final_checks.json");assert audit["failed"]==0 and audit["new_scored_executions"]==7620
    checks=[];scripts=list(ROOT.glob("*.py"))
    for p in scripts:ast.parse(p.read_text(),filename=str(p))
    checks.append(dict(test="all_current_python_parses",passed=True,files=len(scripts)))
    for name in REPORTS:
        p=ROOT/name
        assert "{{FULL_METRIC_TABLE}}" not in p.read_text(),name
        for target in re.findall(r"\]\(([^)]+)\)",p.read_text()):
            if target.startswith(("https:","http:","#")):continue
            assert (p.parent/target.split("#")[0]).exists(),(name,target)
    checks.append(dict(test="report_links_resolve",passed=True))
    figure_data=read(OUT/"figure_data.json")
    assert figure_data["source_summary_sha256"]==sha(OUT/"summary.csv")
    assert figure_data["selected_layouts_sha256"]==sha(OUT/"selected_layouts.json")
    figure_files={f"figures/{name}.{suffix}" for name in ("cover21_layouts","cover21_tradeoffs") for suffix in ("png","pdf")}
    assert set(figure_data["figure_files"])==figure_files
    assert all((ROOT/name).is_file() and (ROOT/name).stat().st_size>0 for name in figure_files)
    assert figure_data["scored_executions"]==figure_data["official_calls"]==0
    checks.append(dict(test="figure_sources_and_four_standalone_artifacts",passed=True,files=sorted(figure_files)))
    for name in (*RUNS,*GEOMETRY_RUNS):
        folder=ROOT/"experiments/runs"/f"2026-09-11_{name}"
        for filename in ("plan.md","command.sh","precheck.md","log.txt","summary.md","next_steps.md"):assert (folder/filename).exists(),(name,filename)
    checks.append(dict(test="all_new_run_records_complete",passed=True))
    diagnosis=read(OUT/"regression_public_diagnosis.json")
    assert diagnosis["scored_executions"]==diagnosis["official_calls"]==0
    assert diagnosis["replay_count"]==sum(len(c["records"]) for c in diagnosis["results"])
    for case in diagnosis["results"]:
        for comparison in case["comparisons"]:
            assert abs(sum(v["virtual_s"] for v in comparison["task_cost_delta"].values())-comparison["total_delta_s"])<1e-6
    checks.append(dict(test="public_only_diagnosis_cost_sums",passed=True))
    archived={}
    for name in RUNS:
        folder=ROOT/"experiments/runs"/f"2026-09-11_{name}"
        files=[folder/"trials.jsonl",*(folder/"traces").iterdir(),*(folder/"scenarios_scoring_only").iterdir()]
        for sub in ("boundary_precheck_traces","boundary_precheck_fixtures"):
            if (folder/sub).exists():files.extend((folder/sub).iterdir())
        hashes={str(p.relative_to(folder)):sha(p) for p in sorted(files) if p.is_file()}
        dest=folder/"scored_data_sha256.json"
        if dest.exists():assert read(dest)==hashes
        else:dest.write_text(json.dumps(hashes,indent=2,ensure_ascii=False))
        archived[name]=len(hashes)
    checks.append(dict(test="scored_and_boundary_data_hash_indices",passed=True,files=archived))
    previous=OUT/"previous_final_manifest_51894.json"
    if not previous.exists():previous.write_bytes((ROOT/"experiments/runs/2026-09-11_odd-ring-cover/previous_final_manifest_51894.json").read_bytes())
    prior=read(previous);assert prior["total_offline_executions"]==51894
    checks.append(dict(test="previous_manifest_preserved",passed=True))
    (OUT/"artifact_checks.json").write_text(json.dumps(dict(passed=len(checks),failed=0,checks=checks),indent=2))
    result=dict(total_offline_executions=59514,new_scored_executions=7620,final_checks=audit["passed"],artifact_checks=len(checks),python_files_parsed=len(scripts),official_calls=0)
    (OUT/"finalize_log.txt").write_text(json.dumps(result,indent=2)+"\n")
    artifacts=scripts+[ROOT/n for n in REPORTS]
    for name in (*RUNS,*GEOMETRY_RUNS):
        folder=ROOT/"experiments/runs"/f"2026-09-11_{name}"
        artifacts.extend(p for p in folder.iterdir() if p.is_file() and p.suffix in (".json",".csv",".md",".sh",".txt",".jsonl"))
    for name in ("cover21_layouts","cover21_tradeoffs"):
        for suffix in ("png","pdf"):
            p=ROOT/"figures"/f"{name}.{suffix}"
            if p.exists():artifacts.append(p)
    manifest={**{k:v for k,v in prior.items() if k!="sha256"},"previous_manifest":str(previous.relative_to(ROOT)),
              "historical_integrity_note":"experiments/runs/2026-09-11_odd-ring-cover/entry_integrity_check.json",
              "cover21_training_and_confirmation_executions":7620,"total_offline_executions":59514,
              "all_scored_runs_cleared":True,"final_verification_checks":audit["passed"],"artifact_checks":len(checks),
              "python_files_parsed":len(scripts),"official_calls":0,
              "sha256":{str(p.relative_to(ROOT.parent)):sha(p) for p in artifacts}}
    (ROOT/"FINAL_MANIFEST.json").write_text(json.dumps(manifest,indent=2,ensure_ascii=False))
    assert all(sha(ROOT.parent/p)==h for p,h in manifest["sha256"].items())
    print(json.dumps(result,indent=2))


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--finalize",action="store_true");args=parser.parse_args()
    finalize() if args.finalize else verify()
