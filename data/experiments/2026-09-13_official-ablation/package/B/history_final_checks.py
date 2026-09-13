"""Audit geometry, history cuts, faithful plans, physics and offline artifacts."""
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
import coupled_final_checks as range_checks
import faithful_skip_experiments as faithful
import historical_pair_experiments as historical
from history_confirmation import ROOT, OUT, SPECS, all_paths, build
from icra_final_checks import partition_check
from visibility_certificate import verify_cells

RUNS = {"historical-negatives": 1302, "faithful-skips": 1116, "history-confirmation": 2925}
GEOMETRY_RUNS = {"multicore-cover-search": 216, "multicore-cover-smallcore": 192}
REPORTS = ("REPORT.md", "REPORT_HISTORY_UPDATE.md", "FAITHFUL_SKIP_GUARANTEE.md", "HISTORICAL_PAIR_GUARANTEE.md",
           "GOAL.md", "ICRA_CONNECTION.md", "COMMANDS.md")
HTTP_METHODS = ((3,"faithful_area7"),(4,"faithful_width015"),(4,"faithful_arc05_width015"),(4,"history_first8_width015"))
DOMINANCE_PAIRS = ((3,"faithful_area7","area_return1_7"),
                   (4,"faithful_width015","width40_f015_22"),
                   (4,"faithful_arc05_width015","arc05_noskip_width015"),
                   (4,"faithful_locked_width015","locked_noskip_width015"))
BASIC_CASES = ("uniform__iid__127", "boundary_outward__n10__negative", "near_collinear__n16__positive", "cluster_far20__n13__spatial")


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rows_for(folder):
    return [json.loads(line) for line in (folder / "trials.jsonl").read_text().splitlines()]


def dominance_audit(folder, specs, paths):
    rows = rows_for(folder)
    lookup = {(r["problem"],r["method"],r["case_id"]):r for r in rows}
    records = []
    for problem, candidate, baseline in DOMINANCE_PAIRS:
        for row in rows:
            if row["problem"] != problem or row["method"] != candidate:
                continue
            case = row["case_id"]
            reference = lookup[problem,baseline,case]
            a = replay_checks.load_trace(folder / "traces" / f"q{problem}__{case}__{baseline}.jsonl.gz")
            b = replay_checks.load_trace(folder / "traces" / f"q{problem}__{case}__{candidate}.jsonl.gz")
            result = faithful.expanded_plan_replay(a, specs[problem][candidate], problem, paths)
            omitted = set(result["skipped_indices"])
            assert [faithful.request_identity(e) for i,e in enumerate(a) if i not in omitted] == [faithful.request_identity(e) for e in b]
            k = result["skipped"]
            assert k == row["faithful_stationary_skips"]
            assert row["commands"] == reference["commands"]-k
            def switches(trace):
                channels = [1]+[e["request"]["channel"] for e in trace if e["path"] == "/measure"]
                return sum(x != y for x,y in zip(channels,channels[1:]))
            delta_switch = switches(a)-switches(b)
            assert delta_switch >= 0
            saved = reference["total_virtual_s"]-row["total_virtual_s"]
            assert abs(saved-(5*k+delta_switch)) < 1e-6, (problem,candidate,case,saved,k,delta_switch)
            records.append(dict(problem=problem,candidate=candidate,baseline=baseline,case_id=case,split=row["split"],
                                skipped=k,saved_s=saved,switches_saved=delta_switch,expanded_plan_equal=True))
    expected = 372 if folder == faithful.OUT else 780
    assert len(records) == expected
    result = dict(passed=len(records),failed=0,checks=records,skipped=sum(r["skipped"] for r in records),
                  total_saved_s=sum(r["saved_s"] for r in records),scored_executions=0,official_calls=0)
    (folder / "faithful_dominance_audit.json").write_text(json.dumps(result,indent=2))
    return dict(test=f"all_four_faithful_plan_pairs_{folder.name}",passed=True,
                expanded_replays=len(records),skips=result["skipped"],actual_time_formula_matches=True)


def verify():
    if (OUT / "final_checks.json").exists():
        raise RuntimeError("Preserving finished audit")
    began = time.perf_counter()
    paths = all_paths()
    checks, completed = [], []
    replay_checks.OUT, replay_checks.SPECS, replay_checks.build = OUT, SPECS, build
    for problem, methods in SPECS.items():
        for method in methods:
            for case in BASIC_CASES:
                checks.append(replay_checks.feedback_replay(problem,method,case,paths))
    print("60 exact public-feedback region and clearance replays passed",flush=True)
    for name, expected in RUNS.items():
        folder = ROOT / "experiments/runs" / f"2026-09-11_{name}"
        completion, config = read(folder / "completion.json"), read(folder / "run_config.json")
        rows = rows_for(folder)
        assert completion["executions"] == completion["all_cleared"] == len(rows) == expected
        assert completion["errors"] == 0
        assert all(r["all_cleared"] and not r["failure"] for r in rows)
        assert all(r.get("inconsistent_updates",0) == r.get("bracket_cut_inconsistencies",0) == r.get("historical_inconsistent_cuts",0) == 0 for r in rows)
        assert all(r["cleared"] == 16 for r in rows if r["stop_reason"] == "public_upper_bound_16")
        assert all(r["total_virtual_s"] < 335136 and r["commands"] <= 9766 for r in rows)
        assert config["base_seed"] == 42 and config["official_calls"] == 0
        for filename, frozen_hash in config["code_sha256"].items():
            assert sha(folder / "code_snapshot" / filename) == frozen_hash, (name,filename)
        for r in rows:
            if "source_interruptions" not in r:
                continue
            spec = config["specs"][str(r["problem"])][r["method"]]
            assert r["source_interruptions"] <= spec.get("pause_limit",16)
            assert r["maximum_source_rounds"] <= (10 if r["problem"] == 4 else 3)
            assert r["maximum_source_primary_rf"] <= (20 if r["problem"] == 4 else 3)
            assert r["source_packets"] <= r["sources"]*(11 if r["problem"] == 4 else 4)
        checks.append(dict(test=f"scored_archive_stops_lifetime_budgets_and_hashes_{name}",passed=True,executions=expected))
        completed.append(dict(run=name,executions=expected,all_cleared=expected,
                              stop_reasons=dict(Counter(r["stop_reason"] for r in rows))))
        if name == "history-confirmation":
            assert sorted({r["seed"] for r in rows if r["split"] == "ordinary"}) == list(range(127,137))
            assert config["freeze_before_truth_generation"]
            checks.append(replay_checks.physics_audit(rows))
    confirmation_rows = rows
    print("5343 scored rows and all 2925 confirmation trace physics passed",flush=True)
    active_history = additional_replays = 0
    for folder, specs, factory in ((historical.OUT,historical.SPECS,historical.build),(OUT,SPECS,build)):
        replay_checks.OUT,replay_checks.SPECS,replay_checks.build = folder,specs,factory
        for row in rows_for(folder):
            if not row.get("historical_pair_cuts",0):
                continue
            active_history += 1
            if folder == OUT and row["case_id"] in BASIC_CASES:
                continue
            item = replay_checks.feedback_replay(row["problem"],row["method"],row["case_id"],paths)
            item["stage"] = folder.name
            checks.append(item)
            additional_replays += 1
    print("All",active_history,"active historical-cut executions retained true sources",flush=True)
    replay_checks.OUT,replay_checks.SPECS,replay_checks.build = OUT,SPECS,build
    for folder, specs in ((faithful.OUT,faithful.SPECS),(OUT,SPECS)):
        checks.append(dominance_audit(folder,specs,paths))
        print("Expanded plan and actual cost dominance:",folder.name,flush=True)
    range_checks.OUT,range_checks.SPECS,range_checks.build = OUT,SPECS,build
    for problem, methods in SPECS.items():
        for method, spec in methods.items():
            if not spec.get("range_skip",False) and not spec["kind"].startswith("faithful_"):
                continue
            chosen = max((r for r in confirmation_rows if r["problem"] == problem and r["method"] == method),
                         key=lambda r:r.get("certified_range_scan_skips",0))
            if chosen.get("certified_range_scan_skips",0):
                checks.append(range_checks.range_skip_replay(problem,method,chosen["case_id"],paths))
    config = read(OUT / "run_config.json")
    critical = [name for name in config["code_sha256"] if name.endswith("_policy.py")]
    critical += ["policies.py","geometry.py","client.py","history_confirmation.py","historical_pair_experiments.py",
                 "faithful_skip_experiments.py","run_bounded_robot.py"]
    for filename in critical:
        assert sha(ROOT / filename) == config["code_sha256"][filename], filename
    checks.append(dict(test="frozen_decision_files_unchanged_since_before_truth_generation",passed=True,files=len(set(critical))))
    for name, expected in (("historical-negatives",665),("faithful-skips",848)):
        result = read(ROOT / "experiments/runs" / f"2026-09-11_{name}" / "checks.json")
        assert result["passed"] == expected and result["failed"] == result["scored_execution_count"] == 0
        checks.append(dict(test=f"saved_prechecks_{name}",passed=True,checks=expected))
    for name, expected in GEOMETRY_RUNS.items():
        folder = ROOT / "experiments/runs" / f"2026-09-11_{name}"
        result, config = read(folder / "witness_verification.json"),read(folder / "search_config.json")
        assert result["passed"] == expected and result["failed"] == result["scored_execution_count"] == 0
        for filename, frozen_hash in config["code_sha256"].items():
            assert sha(folder / "code_snapshot" / filename) == frozen_hash
        assert read(folder / "completion.json")["certified"] == 0
        checks.append(dict(test=f"actual_blind_witnesses_and_search_freeze_{name}",passed=True,actual_counterexamples=expected))
    for name,item in read(ROOT / "experiments/runs/2026-09-11_convex-visibility/certified_layouts.json").items():
        checks.append(dict(test=f"unchanged_continuous_coverage_partition_{name}",passed=True,
                           **verify_cells(item["points"],item["certificate"]),**partition_check(item["certificate"])))
    http = read(OUT / "http_checks.json")
    assert http["passed"] == 4 and http["failed"] == http["official_calls"] == http["scored_execution_count"] == 0
    for problem,method in HTTP_METHODS:
        a = replay_checks.load_trace(OUT / f"protocol_{problem}_{method}_inprocess.jsonl.gz")
        b = replay_checks.load_trace(OUT / f"protocol_{problem}_{method}_owned_loopback_http.jsonl.gz")
        extract = lambda t:[(e["path"],e["request"],e["response"]["virtual_time_s"]) for e in t]
        assert extract(a) == extract(b)
    checks.append(dict(test="four_owned_ephemeral_loopback_http_equivalences",passed=True,official_calls=0))
    smokes = []
    for problem,method in ((3,"faithful_area7"),(4,"history_first8_width015")):
        folder = Path((OUT / f"smoke{problem}_log.txt").read_text().splitlines()[-1])
        result = read(folder / "summary.json")
        assert result["series"] == "history" and result["method"] == method and result["seed"] == 42
        assert result["all_cleared"] and result["official_calls"] == 0
        smokes.append(dict(problem=problem,method=method,folder=str(folder.relative_to(ROOT)),commands=result["commands"]))
    (OUT / "cli_smokes.json").write_text(json.dumps(dict(checks=smokes,scored_executions=0,official_calls=0),indent=2))
    checks.append(dict(test="two_history_cli_entrypoint_smokes",passed=True))
    for relative,frozen_hash in read(ROOT / "inputs_readonly_extract/input_sha256.json").items():
        assert sha(ROOT.parent / relative) == frozen_hash
    public = "project/topic_probes/b_probe.py"
    assert sha(ROOT.parent / public) == read(ROOT / "experiments/runs/2026-09-10_independent/run_config.json")["input_sha256"][public]
    for item in read(ROOT / "experiments/runs/2026-09-11_peer-paper-review/paper_sha256.json"):
        assert sha(ROOT / "别人的结果/同学一" / item["name"]) == item["sha256"]
    for name in ("shumo-b","shumo-b-macos-handoff"):
        result = subprocess.run(["git","-C",str(ROOT / "reference" / name),"status","--porcelain"],capture_output=True,text=True,check=True)
        assert not result.stdout.strip()
    checks.append(dict(test="original_inputs_peer_images_public_probe_and_upstreams_unchanged",passed=True))
    result = dict(passed=len(checks),failed=0,checks=checks,completed_runs=completed,
                  feedback_region_replays=60+additional_replays,active_historical_executions_verified=active_history,
                  faithful_expanded_replays=1152,new_scored_executions=5343,
                  official_calls=0,wall_s=time.perf_counter()-began)
    (OUT / "final_checks.json").write_text(json.dumps(result,indent=2,ensure_ascii=False))
    print(json.dumps({k:v for k,v in result.items() if k not in ("checks","completed_runs")},indent=2))

def finalize():
    audit = read(OUT / "final_checks.json")
    assert audit["failed"] == 0 and audit["new_scored_executions"] == 5343
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
    previous = OUT / "previous_final_manifest_38373.json"
    if not previous.exists():
        previous.write_bytes((ROOT / "experiments/runs/2026-09-11_historical-negatives/previous_final_manifest_38373.json").read_bytes())
    prior = read(previous)
    assert prior["total_offline_executions"] == 38373
    checks.append(dict(test="previous_38373_manifest_preserved", passed=True))
    (OUT / "artifact_checks.json").write_text(json.dumps(dict(passed=len(checks), failed=0, checks=checks), indent=2))
    log_result=dict(total_offline_executions=43716,final_checks=audit["passed"],artifact_checks=len(checks),python_files_parsed=len(scripts),official_calls=0)
    (OUT / "finalize_log.txt").write_text(json.dumps(log_result,indent=2)+"\n")
    artifacts = scripts + [ROOT / name for name in REPORTS]
    for name in (*RUNS, *GEOMETRY_RUNS):
        folder = ROOT / "experiments/runs" / f"2026-09-11_{name}"
        artifacts.extend(p for p in folder.iterdir() if p.is_file() and p.suffix in (".json", ".csv", ".md", ".sh", ".txt", ".jsonl"))
    manifest = {**{k: v for k, v in prior.items() if k != "sha256"},
                "previous_manifest": str(previous.relative_to(ROOT)), "python_files_parsed": len(scripts),
                "historical_integrity_note": "experiments/runs/2026-09-11_historical-negatives/entry_integrity_check.json",
                "history_training_and_confirmation_executions": 5343, "total_offline_executions": 43716,
                "excluded_aborted_collector_attempts": 1, "all_scored_runs_cleared": True,
                "count_scope": "Completed scored strategy executions, including reused training scenes; excludes aborted collector attempt, geometry checks, feedback replays, HTTP tests and CLI smokes; not independent scene count or official tests",
                "final_verification_checks": audit["passed"], "artifact_checks": len(checks), "official_calls": 0,
                "sha256": {str(p.relative_to(ROOT.parent)): sha(p) for p in artifacts}}
    (ROOT / "FINAL_MANIFEST.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    assert all(sha(ROOT.parent / relative)==expected for relative,expected in manifest["sha256"].items())
    print(json.dumps(dict(total_offline_executions=43716, final_checks=audit["passed"], artifact_checks=len(checks),
                          python_files_parsed=len(scripts), official_calls=0), indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--finalize", action="store_true")
    args = parser.parse_args()
    finalize() if args.finalize else verify()
