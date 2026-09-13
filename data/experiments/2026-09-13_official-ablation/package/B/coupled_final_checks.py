"""Audit coupled dispatch and negative-feedback experiments without counting replays or protocol checks as scores."""
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
from client import Client

import mission_final_checks as replay_checks
from coupled_confirmation import ROOT, OUT, SPECS, all_paths, build
from icra_final_checks import partition_check
from visibility_certificate import verify_cells

RUNS = {"coupled-dispatch": 1674, "negative-hull": 1116, "fast-dispatch": 744, "coupled-confirmation": 1950}
REPORTS = ("REPORT.md", "REPORT_COUPLED_UPDATE.md", "COUPLED_DISPATCH_GUARANTEE.md", "NEGATIVE_FEEDBACK_GEOMETRY.md", "GOAL.md", "ICRA_CONNECTION.md", "COMMANDS.md")


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def range_skip_replay(problem,method,case_id,paths):
    trace=replay_checks.load_trace(OUT / "traces" / f"q{problem}__{case_id}__{method}.jsonl.gz")
    index=0
    skips=[]
    def transport(endpoint,raw):
        nonlocal index
        entry=trace[index]
        assert endpoint==entry["path"] and json.loads(raw)==entry["request"]
        index+=1
        return 200,entry["response"]
    policy=build(Client(transport,robot_id="mock-robot"),SPECS[problem][method],problem,paths)
    original=policy.measure
    def measure(q,ch):
        before=(np.array(policy.client.position,copy=True),policy.client.channel,policy.client.virtual_s)
        poly=policy.regions[ch].copy() if ch in policy.regions else None
        was_surveying=policy._surveying
        result=original(q,ch)
        if result=="certified_no_reception":
            assert was_surveying and poly is not None
            assert np.array_equal(before[0],policy.client.position) and before[1:]==(policy.client.channel,policy.client.virtual_s)
            skips.append((ch,np.asarray(q).copy(),poly))
        return result
    policy.measure=measure
    stats=policy.run()
    assert index==len(trace) and len(skips)==stats["certified_range_scan_skips"] and skips
    # Source truth is read only after every public-feedback action has ended.
    fixture=read(OUT / "scenarios_scoring_only" / f"q{problem}__{case_id}.json")
    sources={x["channel"]:x for x in fixture["scenario"]["sources"]}
    minimum=float("inf")
    for ch,q,poly in skips:
        edges=np.roll(poly,-1,axis=0)-poly
        norm2=np.sum(edges*edges,axis=1)
        relative=q-poly
        factors=np.sum(relative*edges,axis=1)/np.maximum(1e-30,norm2)
        closest=poly+np.clip(factors,0,1)[:,None]*edges
        distance=float(np.linalg.norm(closest-q,axis=1).min())
        local=poly-poly[0]
        area=abs(np.sum(local[:,0]*np.roll(local,-1,axis=0)[:,1]-local[:,1]*np.roll(local,-1,axis=0)[:,0]))/2
        if area>1e-8 and np.min(edges[:,0]*relative[:,1]-edges[:,1]*relative[:,0])>=0:
            distance=0.
        assert distance>1500.-1e-5
        minimum=min(minimum,distance)
        source=sources[ch]
        assert np.linalg.norm(q-np.array([source["x"],source["y"]]))>source["radius"]
    return dict(test=f"independent_continuous_range_skip_q{problem}_{method}_{case_id}",passed=True,
                skips=len(skips),minimum_distance_to_entire_polygon_m=minimum,no_client_state_fabrication=True)


def verify():
    if (OUT / "final_checks.json").exists():
        raise RuntimeError("Preserving completed verification; --finalize checks documents only")
    began = time.perf_counter()
    replay_checks.OUT, replay_checks.SPECS, replay_checks.build = OUT, SPECS, build
    paths = all_paths()
    checks = []
    for problem, methods in SPECS.items():
        for method in methods:
            for case_id in ("uniform__iid__117", "boundary_outward__n10__negative", "near_collinear__n16__positive", "cluster_far20__n13__spatial"):
                checks.append(replay_checks.feedback_replay(problem, method, case_id, paths))
    print("40 exact public-feedback region and clearance replays passed", flush=True)
    completed = []
    for name, expected in RUNS.items():
        folder = ROOT / "experiments/runs" / f"2026-09-11_{name}"
        completion = read(folder / "completion.json")
        config = read(folder / "run_config.json")
        rows = [json.loads(line) for line in (folder / "trials.jsonl").read_text().splitlines()]
        assert completion["executions"] == completion["all_cleared"] == len(rows) == expected
        assert completion["errors"] == 0
        assert all(r["all_cleared"] and not r["failure"] for r in rows)
        assert all(r.get("inconsistent_updates",0)==r.get("bracket_cut_inconsistencies",0)==r.get("negative_hull_inconsistent_cuts",0)==0 for r in rows)
        assert all(r["cleared"] == 16 for r in rows if r["stop_reason"] == "public_upper_bound_16")
        assert all(r["total_virtual_s"] < 335136 and r["commands"] <= 9766 for r in rows)
        assert config["base_seed"] == 42 and config["official_calls"] == 0
        for filename, frozen_hash in config["code_sha256"].items():
            assert sha(folder / "code_snapshot" / filename) == frozen_hash, (name, filename)
        for r in rows:
            if "source_interruptions" not in r:
                continue
            spec = config["specs"][str(r["problem"])][r["method"]]
            assert r["source_interruptions"] <= spec.get("pause_limit", 16)
            assert r["maximum_source_rounds"] <= (10 if r["problem"] == 4 else 3)
            assert r["maximum_source_primary_rf"] <= (20 if r["problem"] == 4 else 3)
            assert r["source_packets"] <= r["sources"] * (11 if r["problem"] == 4 else 4)
        checks.append(dict(test=f"scored_archive_stops_lifetime_budgets_and_hashes_{name}", passed=True, executions=expected))
        completed.append(dict(run=name, executions=expected, all_cleared=expected,
                              stop_reasons=dict(Counter(r["stop_reason"] for r in rows))))
        if name == "coupled-confirmation":
            assert sorted({r["seed"] for r in rows if r["split"] == "ordinary"}) == list(range(117, 127))
            assert config["freeze_before_truth_generation"]
            checks.append(replay_checks.physics_audit(rows))
    print("5484 scored rows, lifetime budgets and all 1950 confirmation traces passed", flush=True)
    # Revisit every new geometry reduction, not merely cases where it is idle.
    import negative_hull_experiments as negative
    negative_verified=additional_replays=0
    for folder,methods,factory in ((negative.OUT,negative.SPECS,negative.build),(OUT,SPECS,build)):
        data=[json.loads(line) for line in (folder / "trials.jsonl").read_text().splitlines()]
        replay_checks.OUT,replay_checks.SPECS,replay_checks.build=folder,methods,factory
        for row in data:
            if not row.get("negative_shadow_cuts",0):
                continue
            negative_verified+=1
            basic_case=row["case_id"] in ("uniform__iid__117","boundary_outward__n10__negative","near_collinear__n16__positive","cluster_far20__n13__spatial")
            if folder==OUT and basic_case:
                continue
            item=replay_checks.feedback_replay(row["problem"],row["method"],row["case_id"],paths)
            item["stage"]=folder.name
            checks.append(item)
            additional_replays+=1
    replay_checks.OUT,replay_checks.SPECS,replay_checks.build=OUT,SPECS,build
    for problem,methods in SPECS.items():
        for method,spec in methods.items():
            if not spec.get("range_skip",False):
                continue
            candidates=[r for r in rows if r["problem"]==problem and r["method"]==method]
            chosen=max(candidates,key=lambda r:r.get("certified_range_scan_skips",0))
            checks.append(range_skip_replay(problem,method,chosen["case_id"],paths))
    print(f"All {negative_verified} active negative-inference cases and range-skip state checks passed",flush=True)
    current = read(OUT / "run_config.json")
    for name in ("wide_probe_policy.py","completion_sensing_policy.py","bounded_width_policy.py",
                 "coupled_dispatch_policy.py","negative_hull_policy.py","fast_dispatch_policy.py",
                 "coupled_confirmation.py","coupled_dispatch_experiments.py","negative_hull_experiments.py","fast_dispatch_experiments.py",
                 "interleaved_policy.py","efficient_joint_policy.py","clearance_policy.py","joint_task_policy.py",
                 "joint_policy.py","policies.py","geometry.py","client.py"):
        assert sha(ROOT / name) == current["code_sha256"][name]
    checks.append(dict(test="all_frozen_decision_files_unchanged_since_before_truth_generation", passed=True))
    for name, expected in (("coupled-dispatch",609),("negative-hull",533),("fast-dispatch",532)):
        result = read(ROOT / "experiments/runs" / f"2026-09-11_{name}" / "checks.json")
        assert result["passed"] == expected and result["failed"] == 0 and result["scored_execution_count"] == 0
        checks.append(dict(test=f"saved_protocol_and_zero_effect_checks_{name}", passed=True, checks=expected))
    for name, item in read(ROOT / "experiments/runs/2026-09-11_convex-visibility/certified_layouts.json").items():
        checks.append(dict(test=f"unchanged_continuous_coverage_partition_{name}", passed=True,
                           **verify_cells(item["points"], item["certificate"]), **partition_check(item["certificate"])))
    http = read(OUT / "http_checks.json")
    assert http["passed"] == 4 and http["failed"] == http["official_calls"] == http["scored_execution_count"] == 0
    for problem, method in ((3,"range_area7"),(4,"fast_arc05_width015"),(4,"fast_locked_width015"),(4,"fast_negative_arc05_width015")):
        a = replay_checks.load_trace(OUT / f"protocol_{problem}_{method}_inprocess.jsonl.gz")
        b = replay_checks.load_trace(OUT / f"protocol_{problem}_{method}_owned_loopback_http.jsonl.gz")
        extract = lambda trace: [(e["path"], e["request"], e["response"]["virtual_time_s"]) for e in trace]
        assert extract(a) == extract(b)
    checks.append(dict(test="four_owned_loopback_http_equivalences", passed=True, official_calls=0))
    smokes = []
    for problem, method in ((3,"range_area7"),(4,"fast_arc05_width015")):
        folder = Path((OUT / f"smoke{problem}_log.txt").read_text().splitlines()[-1])
        result = read(folder / "summary.json")
        assert result["series"] == "coupled" and result["method"] == method and result["seed"] == 42
        assert result["all_cleared"] and result["official_calls"] == 0
        smokes.append(dict(problem=problem, method=method, folder=str(folder.relative_to(ROOT)), commands=result["commands"]))
    (OUT / "cli_smokes.json").write_text(json.dumps(dict(checks=smokes, scored_executions=0, official_calls=0), indent=2))
    checks.append(dict(test="two_coupled_cli_entrypoint_smokes", passed=True))
    for relative, frozen_hash in read(ROOT / "inputs_readonly_extract/input_sha256.json").items():
        assert sha(ROOT.parent / relative) == frozen_hash
    public = "project/topic_probes/b_probe.py"
    assert sha(ROOT.parent / public) == read(ROOT / "experiments/runs/2026-09-10_independent/run_config.json")["input_sha256"][public]
    for item in read(ROOT / "experiments/runs/2026-09-11_peer-paper-review/paper_sha256.json"):
        assert sha(ROOT / "别人的结果/同学一" / item["name"]) == item["sha256"]
    for name in ("shumo-b", "shumo-b-macos-handoff"):
        result = subprocess.run(["git", "-C", str(ROOT / "reference" / name), "status", "--porcelain"], capture_output=True, text=True, check=True)
        assert not result.stdout.strip()
    checks.append(dict(test="original_inputs_peer_images_public_probe_and_upstreams_unchanged", passed=True))
    result = dict(passed=len(checks), failed=0, checks=checks, completed_runs=completed,
                  feedback_replays=40+additional_replays, active_negative_cases_verified=negative_verified,
                  new_scored_executions=5484,
                  official_calls=0, wall_s=time.perf_counter() - began)
    (OUT / "final_checks.json").write_text(json.dumps(result, indent=2, ensure_ascii=False))
    print(json.dumps({k: v for k, v in result.items() if k not in ("checks", "completed_runs")}, indent=2))


def finalize():
    audit = read(OUT / "final_checks.json")
    assert audit["failed"] == 0 and audit["new_scored_executions"] == 5484
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
    for name in RUNS:
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
    previous = OUT / "previous_final_manifest_32889.json"
    if not previous.exists():
        previous.write_bytes((ROOT / "experiments/runs/2026-09-11_coupled-dispatch/previous_final_manifest_32889.json").read_bytes())
    prior = read(previous)
    assert prior["total_offline_executions"] == 32889
    checks.append(dict(test="previous_32889_manifest_preserved", passed=True))
    (OUT / "artifact_checks.json").write_text(json.dumps(dict(passed=len(checks), failed=0, checks=checks), indent=2))
    log_result=dict(total_offline_executions=38373,final_checks=audit["passed"],artifact_checks=len(checks),python_files_parsed=len(scripts),official_calls=0)
    (OUT / "finalize_log.txt").write_text(json.dumps(log_result,indent=2)+"\n")
    artifacts = scripts + [ROOT / name for name in REPORTS]
    for name in RUNS:
        folder = ROOT / "experiments/runs" / f"2026-09-11_{name}"
        artifacts.extend(p for p in folder.iterdir() if p.is_file() and p.suffix in (".json", ".csv", ".md", ".sh", ".txt"))
    manifest = {**{k: v for k, v in prior.items() if k != "sha256"},
                "previous_manifest": str(previous.relative_to(ROOT)), "python_files_parsed": len(scripts),
                "historical_integrity_note": "experiments/runs/2026-09-11_coupled-dispatch/entry_integrity_check.json",
                "coupled_training_and_confirmation_executions": 5484, "total_offline_executions": 38373,
                "excluded_aborted_collector_attempts": 1, "all_scored_runs_cleared": True,
                "count_scope": "Completed scored strategy executions, including reused training scenes; excludes aborted collector attempt, geometry checks, feedback replays, HTTP tests and CLI smokes; not independent scene count or official tests",
                "final_verification_checks": audit["passed"], "artifact_checks": len(checks), "official_calls": 0,
                "sha256": {str(p.relative_to(ROOT.parent)): sha(p) for p in artifacts}}
    (ROOT / "FINAL_MANIFEST.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    assert all(sha(ROOT.parent / relative)==expected for relative,expected in manifest["sha256"].items())
    print(json.dumps(dict(total_offline_executions=38373, final_checks=audit["passed"], artifact_checks=len(checks),
                          python_files_parsed=len(scripts), official_calls=0), indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--finalize", action="store_true")
    args = parser.parse_args()
    finalize() if args.finalize else verify()
