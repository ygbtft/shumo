"""Audit deferred movement, logical negatives, exact computation and artifacts."""
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

import mission_final_checks as replay_checks
import deferred_skip_experiments as deferred
import batched_history_experiments as batched
import cheap_prediction_experiments as cheap
from deferred_replay import expanded_plan,verify_actual_cost
from deferred_confirmation import ROOT,OUT,SPECS,all_paths,build
from icra_final_checks import partition_check
from visibility_certificate import verify_cells

RUNS={"deferred-scans":2232,"batched-history":930,"cheap-prediction":1116,"deferred-confirmation":3900}
GEOMETRY_RUNS={}
REPORTS=("REPORT.md","REPORT_DEFERRED_UPDATE.md","DEFERRED_SCAN_GUARANTEE.md","BATCHED_HISTORY_EQUIVALENCE.md",
         "CHEAP_PREDICTION_GUARD.md","GOAL.md","ICRA_CONNECTION.md","COMMANDS.md")
HTTP_METHODS=((3,"deferred_area7"),(4,"cheap_predict8_width015"),(4,"cheap_predict8_arc05_width015"),(4,"batch_history_first8_width015"))
BASIC_CASES=("uniform__iid__137","boundary_outward__n10__negative","near_collinear__n16__positive","range_transition__n13__negative")


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rows_for(folder):
    return [json.loads(line) for line in (folder / "trials.jsonl").read_text().splitlines()]


def no_skip_reference(problem,method):
    if problem==3:return "area_return1_7"
    if method.endswith("arc05_width015"):return "arc05_noskip_width015"
    if method.endswith("locked_width015"):return "locked_noskip_width015"
    return "width40_f015_22"


def certified_deletion_audit(folder,specs,factory,paths):
    rows=rows_for(folder)
    reference_folder=deferred.OUT if folder==cheap.OUT else folder
    references={(r["problem"],r["method"],r["case_id"]):r for r in rows_for(reference_folder)}
    records=[]
    station_audits=[]
    def watched_factory(client,spec,problem,paths):
        client.transcript=[]
        policy=factory(client,spec,problem,paths)
        scan=policy.scan_station
        def observed_scan(q,key):
            initial_unknown={ch for ch in range(1,21) if ch not in policy.regions and ch not in policy.cleared}
            before=len(client.transcript)
            scan(q,key)
            actual={e["request"]["channel"] for e in client.transcript[before:] if e["path"]=="/measure"
                    and e["request"]["position"]==dict(x=float(q[0]),y=float(q[1]))}
            assert len(initial_unknown)>=4 and initial_unknown<=actual
            station_audits.append(len(initial_unknown))
        policy.scan_station=observed_scan
        return policy
    for row in rows:
        problem,method,case=row["problem"],row["method"],row["case_id"]
        spec=specs[problem][method]
        if not spec["kind"].startswith(("deferred_","cheap_prediction_")):
            continue
        baseline=no_skip_reference(problem,method)
        reference=references[problem,baseline,case]
        fixture=f"q{problem}__{case}.json"
        assert read(folder / "scenarios_scoring_only" / fixture)==read(reference_folder / "scenarios_scoring_only" / fixture)
        a=replay_checks.load_trace(reference_folder / "traces" / f"q{problem}__{case}__{baseline}.jsonl.gz")
        b=replay_checks.load_trace(folder / "traces" / f"q{problem}__{case}__{method}.jsonl.gz")
        detail=expanded_plan(a,spec,problem,paths,watched_factory)
        cost=verify_actual_cost(a,b,detail,reference["total_virtual_s"],row["total_virtual_s"])
        assert detail["skipped"]==row["certified_scan_skips"]
        assert detail["pair_skips"]==row["predicted_pair_skips"]
        assert detail["nonstationary_skips"]==row["deferred_nonstationary_skips"]
        records.append(dict(problem=problem,method=method,baseline=baseline,case_id=case,split=row["split"],
                            range_skips=detail["range_skips"],pair_skips=detail["pair_skips"],
                            nonstationary_skips=detail["nonstationary_skips"],**cost))
    expected=1755 if folder==OUT else 1116
    assert len(records)==expected
    result=dict(passed=len(records),failed=0,checks=records,independent_scan_segments=len(station_audits),
                minimum_actual_unknown=min(station_audits),skipped=sum(r["skipped"] for r in records),
                pair_skips=sum(r["pair_skips"] for r in records),nonstationary_skips=sum(r["nonstationary_skips"] for r in records),
                saved_s=sum(r["virtual_saved_s"] for r in records),scored_execution_count=0,official_calls=0)
    (folder / "certified_deletion_audit.json").write_text(json.dumps(result,indent=2))
    return dict(test=f"all_deferred_public_plans_geometry_and_cost_{folder.name}",passed=True,
                expanded_replays=len(records),independent_scan_segments=len(station_audits),
                skipped=result["skipped"],pair_skips=result["pair_skips"],nonstationary_skips=result["nonstationary_skips"])


def exact_computation_audit(folder,pairs):
    rows=rows_for(folder)
    lookup={(r["method"],r["case_id"]):r for r in rows}
    records=[]
    for candidate,baseline in pairs:
        for row in rows:
            if row["method"]!=candidate:continue
            old=lookup[baseline,row["case_id"]]
            assert row["total_virtual_s"]==old["total_virtual_s"] and row["commands"]==old["commands"]
            for key in ("historical_pair_cuts","historical_pair_updates","historical_pair_checks","certified_scan_skips","predicted_pair_skips","deferred_nonstationary_skips"):
                assert row.get(key)==old.get(key),(candidate,row["case_id"],key)
            name=f"q4__{row['case_id']}"
            a=replay_checks.load_trace(folder / "traces" / f"{name}__{baseline}.jsonl.gz")
            b=replay_checks.load_trace(folder / "traces" / f"{name}__{candidate}.jsonl.gz")
            def extract(trace):
                return [(e["path"],e["request"],e["response"]["virtual_time_s"],e["response"].get("measure_result"),
                         e["response"].get("svd_deg"),e["response"].get("clear_result")) for e in trace]
            assert extract(a)==extract(b)
            records.append(dict(candidate=candidate,baseline=baseline,case_id=row["case_id"],passed=True))
    expected=390 if folder==OUT else 465 if folder==batched.OUT else 558
    assert len(records)==expected
    (folder / "exact_computation_audit.json").write_text(json.dumps(dict(passed=len(records),failed=0,checks=records,
                                                                      scored_execution_count=0,official_calls=0),indent=2))
    return dict(test=f"same_actual_requests_results_and_times_{folder.name}",passed=True,pairs=len(records))


def verify():
    if (OUT / "final_checks.json").exists():raise RuntimeError("Preserving finished audit")
    began=time.perf_counter();paths=all_paths();checks=[];completed=[]
    replay_checks.OUT,replay_checks.SPECS,replay_checks.build=OUT,SPECS,build
    for problem,methods in SPECS.items():
        for method in methods:
            for case in BASIC_CASES:checks.append(replay_checks.feedback_replay(problem,method,case,paths))
    print("80 exact public-feedback region and clearance replays passed",flush=True)
    for name,expected in RUNS.items():
        folder=ROOT / "experiments/runs" / f"2026-09-11_{name}"
        completion,config=read(folder / "completion.json"),read(folder / "run_config.json")
        rows=rows_for(folder)
        assert completion["executions"]==completion["all_cleared"]==len(rows)==expected and completion["errors"]==0
        assert all(r["all_cleared"] and not r["failure"] for r in rows)
        assert all(r.get("inconsistent_updates",0)==r.get("bracket_cut_inconsistencies",0)==r.get("historical_inconsistent_cuts",0)==0 for r in rows)
        assert all(r["total_virtual_s"]<335136 and r["commands"]<=9766 for r in rows)
        assert all(r["cleared"]==16 for r in rows if r["stop_reason"]=="public_upper_bound_16")
        assert config["base_seed"]==42 and config["official_calls"]==0
        for filename,frozen_hash in config["code_sha256"].items():
            p=folder / "code_snapshot" / filename
            assert sha(p)==frozen_hash
            ast.parse(p.read_text())
        for r in rows:
            assert r.get("minimum_actual_unknown_per_station",4)>=4
            if "source_interruptions" not in r:continue
            spec=config["specs"][str(r["problem"])][r["method"]]
            assert r["source_interruptions"]<=spec.get("pause_limit",16)
            assert r["maximum_source_rounds"]<=(10 if r["problem"]==4 else 3)
            assert r["maximum_source_primary_rf"]<=(20 if r["problem"]==4 else 3)
            assert r["source_packets"]<=r["sources"]*(11 if r["problem"]==4 else 4)
        checks.append(dict(test=f"scored_archive_stops_budgets_and_frozen_sources_{name}",passed=True,executions=expected))
        completed.append(dict(run=name,executions=expected,all_cleared=expected,stop_reasons=dict(Counter(r["stop_reason"] for r in rows))))
        if name=="deferred-confirmation":
            assert sorted({r["seed"] for r in rows if r["split"]=="ordinary"})==list(range(137,147))
            assert config["freeze_before_truth_generation"]
            checks.append(replay_checks.physics_audit(rows))
    print("8178 scored rows and all 3900 confirmation trace physics passed",flush=True)
    for folder,specs,factory in ((deferred.OUT,deferred.SPECS,deferred.build),(cheap.OUT,cheap.SPECS,cheap.build),(OUT,SPECS,build)):
        checks.append(certified_deletion_audit(folder,specs,factory,paths))
        print("All expanded plans, negative certificates, actual movement and fees:",folder.name,flush=True)
    for folder,pairs in ((batched.OUT,[("batch_"+name,name) for name in batched.NAMES]),
                         (cheap.OUT,[("cheap_"+name,name) for name in cheap.NAMES]),
                         (OUT,[("cheap_predict8_width015","predict8_width015"),("batch_history_first8_width015","history_first8_width015")])):
        checks.append(exact_computation_audit(folder,pairs))
    print("All 1413 actual paired computation traces equivalent",flush=True)
    active_history=additional=0
    for folder,specs,factory in ((batched.OUT,batched.SPECS,batched.build),(OUT,SPECS,build)):
        replay_checks.OUT,replay_checks.SPECS,replay_checks.build=folder,specs,factory
        for row in rows_for(folder):
            if not row.get("historical_pair_cuts",0):continue
            active_history+=1
            if folder==OUT and row["case_id"] in BASIC_CASES:continue
            item=replay_checks.feedback_replay(row["problem"],row["method"],row["case_id"],paths)
            item["stage"]=folder.name;checks.append(item);additional+=1
    print("All",active_history,"active history executions retained the true source",flush=True)
    replay_checks.OUT,replay_checks.SPECS,replay_checks.build=OUT,SPECS,build
    config=read(OUT / "run_config.json")
    critical=[name for name in config["code_sha256"] if name.endswith("_policy.py")]
    critical += ["policies.py","geometry.py","client.py","deferred_confirmation.py","deferred_skip_experiments.py",
                 "batched_history_experiments.py","cheap_prediction_experiments.py","run_bounded_robot.py"]
    for name in critical:assert sha(ROOT / name)==config["code_sha256"][name],name
    checks.append(dict(test="all_frozen_decisions_unchanged_since_before_truth_generation",passed=True,files=len(set(critical))))
    for name,expected in (("deferred-scans",2016),("batched-history",1091),("cheap-prediction",1038)):
        result=read(ROOT / "experiments/runs" / f"2026-09-11_{name}" / "checks.json")
        assert result["passed"]==expected and result["failed"]==result["scored_execution_count"]==0
        checks.append(dict(test=f"saved_prechecks_{name}",passed=True,checks=expected))
    for name,item in read(ROOT / "experiments/runs/2026-09-11_convex-visibility/certified_layouts.json").items():
        checks.append(dict(test=f"continuous_coverage_partition_{name}",passed=True,
                           **verify_cells(item["points"],item["certificate"]),**partition_check(item["certificate"])))
    http=read(OUT / "http_checks.json")
    assert http["passed"]==4 and http["failed"]==http["official_calls"]==http["scored_execution_count"]==0
    for problem,method in HTTP_METHODS:
        a=replay_checks.load_trace(OUT / f"protocol_{problem}_{method}_inprocess.jsonl.gz")
        b=replay_checks.load_trace(OUT / f"protocol_{problem}_{method}_owned_loopback_http.jsonl.gz")
        extract=lambda t:[(e["path"],e["request"],e["response"]["virtual_time_s"]) for e in t]
        assert extract(a)==extract(b)
    checks.append(dict(test="four_owned_ephemeral_loopback_protocol_equivalences",passed=True,official_calls=0))
    smokes=[]
    for problem,method in ((3,"deferred_area7"),(4,"cheap_predict8_width015")):
        folder=Path((OUT / f"smoke{problem}_log.txt").read_text().splitlines()[-1]);result=read(folder / "summary.json")
        assert result["series"]=="deferred" and result["method"]==method and result["seed"]==42
        assert result["all_cleared"] and result["official_calls"]==0
        smokes.append(dict(problem=problem,method=method,folder=str(folder.relative_to(ROOT)),commands=result["commands"]))
    (OUT / "cli_smokes.json").write_text(json.dumps(dict(checks=smokes,scored_executions=0,official_calls=0),indent=2))
    checks.append(dict(test="two_deferred_cli_entrypoint_smokes",passed=True))
    for relative,frozen_hash in read(ROOT / "inputs_readonly_extract/input_sha256.json").items():assert sha(ROOT.parent / relative)==frozen_hash
    public="project/topic_probes/b_probe.py"
    assert sha(ROOT.parent / public)==read(ROOT / "experiments/runs/2026-09-10_independent/run_config.json")["input_sha256"][public]
    for item in read(ROOT / "experiments/runs/2026-09-11_peer-paper-review/paper_sha256.json"):
        assert sha(ROOT / "别人的结果/同学一" / item["name"])==item["sha256"]
    for name in ("shumo-b","shumo-b-macos-handoff"):
        result=subprocess.run(["git","-C",str(ROOT / "reference" / name),"status","--porcelain"],capture_output=True,text=True,check=True)
        assert not result.stdout.strip()
    checks.append(dict(test="original_inputs_peer_images_public_probe_and_upstreams_unchanged",passed=True))
    result=dict(passed=len(checks),failed=0,checks=checks,completed_runs=completed,feedback_region_replays=80+additional,
                active_history_executions_verified=active_history,expanded_deletion_replays=3987,
                exact_computation_pairs=1413,new_scored_executions=8178,official_calls=0,wall_s=time.perf_counter()-began)
    (OUT / "final_checks.json").write_text(json.dumps(result,indent=2,ensure_ascii=False))
    print(json.dumps({k:v for k,v in result.items() if k not in ("checks","completed_runs")},indent=2))

def finalize():
    audit = read(OUT / "final_checks.json")
    assert audit["failed"] == 0 and audit["new_scored_executions"] == 8178
    checks = []
    scripts = list(ROOT.glob("*.py"))
    for path in scripts:
        ast.parse(path.read_text(), filename=str(path))
    checks.append(dict(test="all_current_top_level_python_parses", passed=True, files=len(scripts)))
    for name in REPORTS:
        path = ROOT / name
        for target in re.findall(r"\]\(([^)]+)\)", path.read_text()):
            if target.startswith(("https:", "http:", "#")):
                continue
            assert (path.parent / target.split("#")[0]).exists(), (name, target)
    checks.append(dict(test="report_links_resolve", passed=True))
    for name in (*RUNS, *GEOMETRY_RUNS):
        folder = ROOT / "experiments/runs" / f"2026-09-11_{name}"
        for filename in ("plan.md", "command.sh", "precheck.md", "log.txt", "summary.md", "next_steps.md"):
            assert (folder / filename).exists(), (name, filename)
    checks.append(dict(test="completed_run_records_are_complete", passed=True))
    diagnosis = read(OUT / "regression_public_diagnosis.json")
    assert diagnosis["scored_executions"] == diagnosis["official_calls"] == 0
    assert diagnosis["replay_count"] == sum(len(case["records"]) for case in diagnosis["results"])
    for case in diagnosis["results"]:
        for comparison in case["comparisons"]:
            assert abs(sum(v["virtual_s"] for v in comparison["task_cost_delta"].values()) - comparison["total_delta_s"]) < 1e-6
    checks.append(dict(test="post_confirmation_public_only_cost_diagnoses", passed=True))
    archive_counts = {}
    for name in RUNS:
        folder = ROOT / "experiments/runs" / f"2026-09-11_{name}"
        data = [folder / "trials.jsonl", *(folder / "traces").iterdir(), *(folder / "scenarios_scoring_only").iterdir()]
        hashes = {str(path.relative_to(folder)): sha(path) for path in sorted(data) if path.is_file()}
        archive = folder / "scored_data_sha256.json"
        if archive.exists():
            assert read(archive) == hashes
        else:
            archive.write_text(json.dumps(hashes, indent=2, ensure_ascii=False))
        archive_counts[name] = len(hashes)
    checks.append(dict(test="scored_rows_traces_and_scoring_only_fixtures_hashed", passed=True, files=archive_counts))
    previous = OUT / "previous_final_manifest_43716.json"
    if not previous.exists():
        previous.write_bytes((ROOT / "experiments/runs/2026-09-11_deferred-scans/previous_final_manifest_43716.json").read_bytes())
    prior = read(previous)
    assert prior["total_offline_executions"] == 43716
    checks.append(dict(test="previous_43716_manifest_preserved", passed=True))
    (OUT / "artifact_checks.json").write_text(json.dumps(dict(passed=len(checks), failed=0, checks=checks), indent=2))
    log_result=dict(total_offline_executions=51894,final_checks=audit["passed"],artifact_checks=len(checks),python_files_parsed=len(scripts),official_calls=0)
    (OUT / "finalize_log.txt").write_text(json.dumps(log_result,indent=2)+"\n")
    figure_data = read(OUT / "figure_data.json")
    assert figure_data["source_sha256"] == sha(OUT / "summary.csv")
    artifacts = scripts + [ROOT / name for name in REPORTS] + [ROOT / "figures" / f"deferred_tradeoffs.{extension}" for extension in ("png", "pdf")]
    for name in (*RUNS, *GEOMETRY_RUNS):
        folder = ROOT / "experiments/runs" / f"2026-09-11_{name}"
        artifacts.extend(p for p in folder.iterdir() if p.is_file() and p.suffix in (".json", ".csv", ".md", ".sh", ".txt", ".jsonl"))
    manifest = {**{k: v for k, v in prior.items() if k != "sha256"},
                "previous_manifest": str(previous.relative_to(ROOT)), "python_files_parsed": len(scripts),
                "historical_integrity_note": "experiments/runs/2026-09-11_deferred-scans/entry_integrity_check.json",
                "deferred_training_and_confirmation_executions": 8178, "total_offline_executions": 51894,
                "excluded_aborted_collector_attempts": 1, "all_scored_runs_cleared": True,
                "count_scope": "Completed scored strategy executions, including reused training scenes; excludes aborted collector attempt, geometry checks, feedback replays, HTTP tests and CLI smokes; not independent scene count or official tests",
                "final_verification_checks": audit["passed"], "artifact_checks": len(checks), "official_calls": 0,
                "sha256": {str(p.relative_to(ROOT.parent)): sha(p) for p in artifacts}}
    (ROOT / "FINAL_MANIFEST.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    assert all(sha(ROOT.parent / relative)==expected for relative,expected in manifest["sha256"].items())
    print(json.dumps(dict(total_offline_executions=51894, final_checks=audit["passed"], artifact_checks=len(checks),
                          python_files_parsed=len(scripts), official_calls=0), indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--finalize", action="store_true")
    args = parser.parse_args()
    finalize() if args.finalize else verify()
