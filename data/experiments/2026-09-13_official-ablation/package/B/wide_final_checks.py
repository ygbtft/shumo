"""Audit wide-pair and completion experiments without counting replays or protocol checks as scores."""
import argparse
import ast
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time

import mission_final_checks as replay_checks
from wide_confirmation import ROOT, OUT, SPECS, all_paths, build
from icra_final_checks import partition_check
from visibility_certificate import verify_cells

RUNS = {"wide-probes": 1674, "completion-width": 1581, "wide-confirmation": 2145}
REPORTS = ("REPORT.md", "REPORT_WIDE_UPDATE.md", "WIDE_PROBE_GUARANTEE.md", "GOAL.md", "ICRA_CONNECTION.md", "COMMANDS.md")


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify():
    if (OUT / "final_checks.json").exists():
        raise RuntimeError("Preserving completed verification; --finalize checks documents only")
    began = time.perf_counter()
    replay_checks.OUT, replay_checks.SPECS, replay_checks.build = OUT, SPECS, build
    paths = all_paths()
    checks = []
    for problem, methods in SPECS.items():
        for method in methods:
            for case_id in ("uniform__iid__107", "boundary_outward__n10__negative", "near_collinear__n16__positive", "cluster_far20__n13__spatial"):
                checks.append(replay_checks.feedback_replay(problem, method, case_id, paths))
    print("44 exact public-feedback region and clearance replays passed", flush=True)
    completed = []
    for name, expected in RUNS.items():
        folder = ROOT / "experiments/runs" / f"2026-09-11_{name}"
        completion = read(folder / "completion.json")
        config = read(folder / "run_config.json")
        rows = [json.loads(line) for line in (folder / "trials.jsonl").read_text().splitlines()]
        assert completion["executions"] == completion["all_cleared"] == len(rows) == expected
        assert completion["errors"] == 0
        assert all(r["all_cleared"] and not r["failure"] for r in rows)
        assert all(r.get("inconsistent_updates", 0) == r.get("bracket_cut_inconsistencies", 0) == 0 for r in rows)
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
        if name == "wide-confirmation":
            assert sorted({r["seed"] for r in rows if r["split"] == "ordinary"}) == list(range(107, 117))
            assert config["freeze_before_truth_generation"]
            checks.append(replay_checks.physics_audit(rows))
    print("5400 scored rows, lifetime budgets and all 2145 confirmation traces passed", flush=True)
    current = read(OUT / "run_config.json")
    for name in ("wide_probe_policy.py", "completion_sensing_policy.py", "bounded_width_policy.py",
                 "wide_confirmation.py", "completion_width_experiments.py", "wide_probe_experiments.py",
                 "interleaved_policy.py", "efficient_joint_policy.py", "clearance_policy.py", "joint_task_policy.py",
                 "joint_policy.py", "policies.py", "geometry.py", "client.py"):
        assert sha(ROOT / name) == current["code_sha256"][name]
    checks.append(dict(test="all_frozen_decision_files_unchanged_since_before_truth_generation", passed=True))
    for name, expected in (("wide-probes", 285), ("completion-width", 267)):
        result = read(ROOT / "experiments/runs" / f"2026-09-11_{name}" / "checks.json")
        assert result["passed"] == expected and result["failed"] == 0 and result["scored_execution_count"] == 0
        checks.append(dict(test=f"saved_protocol_and_zero_effect_checks_{name}", passed=True, checks=expected))
    for name, item in read(ROOT / "experiments/runs/2026-09-11_convex-visibility/certified_layouts.json").items():
        checks.append(dict(test=f"unchanged_continuous_coverage_partition_{name}", passed=True,
                           **verify_cells(item["points"], item["certificate"]), **partition_check(item["certificate"])))
    http = read(OUT / "http_checks.json")
    assert http["passed"] == 4 and http["failed"] == http["official_calls"] == http["scored_execution_count"] == 0
    for problem, method in ((3, "area_return1_7"), (3, "expanded_area_return1_7"), (4, "packet_wide5_22"), (4, "width_uncertainty100_22")):
        a = replay_checks.load_trace(OUT / f"protocol_{problem}_{method}_inprocess.jsonl.gz")
        b = replay_checks.load_trace(OUT / f"protocol_{problem}_{method}_owned_loopback_http.jsonl.gz")
        extract = lambda trace: [(e["path"], e["request"], e["response"]["virtual_time_s"]) for e in trace]
        assert extract(a) == extract(b)
    checks.append(dict(test="four_owned_loopback_http_equivalences", passed=True, official_calls=0))
    smokes = []
    for problem, method in ((3, "area_return1_7"), (4, "width_uncertainty100_22")):
        folder = Path((OUT / f"smoke{problem}_log.txt").read_text().splitlines()[-1])
        result = read(folder / "summary.json")
        assert result["series"] == "wide" and result["method"] == method and result["seed"] == 42
        assert result["all_cleared"] and result["official_calls"] == 0
        smokes.append(dict(problem=problem, method=method, folder=str(folder.relative_to(ROOT)), commands=result["commands"]))
    (OUT / "cli_smokes.json").write_text(json.dumps(dict(checks=smokes, scored_executions=0, official_calls=0), indent=2))
    checks.append(dict(test="two_wide_cli_entrypoint_smokes", passed=True))
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
                  feedback_replays=44, new_scored_executions=5400,
                  official_calls=0, wall_s=time.perf_counter() - began)
    (OUT / "final_checks.json").write_text(json.dumps(result, indent=2, ensure_ascii=False))
    print(json.dumps({k: v for k, v in result.items() if k not in ("checks", "completed_runs")}, indent=2))


def finalize():
    audit = read(OUT / "final_checks.json")
    assert audit["failed"] == 0 and audit["new_scored_executions"] == 5400
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
    assert diagnosis["replay_count"] == sum(len(case["records"]) for case in diagnosis["results"]) == 7
    for case in diagnosis["results"]:
        for comparison in case["comparisons"]:
            assert abs(sum(v["virtual_s"] for v in comparison["task_cost_delta"].values()) - comparison["total_delta_s"]) < 1e-6
    checks.append(dict(test="seven_post_confirmation_public_only_cost_diagnoses", passed=True))
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
    previous = OUT / "previous_final_manifest_27489.json"
    if not previous.exists():
        previous.write_bytes((ROOT / "FINAL_MANIFEST.json").read_bytes())
    prior = read(previous)
    assert prior["total_offline_executions"] == 27489
    checks.append(dict(test="previous_27489_manifest_preserved", passed=True))
    (OUT / "artifact_checks.json").write_text(json.dumps(dict(passed=len(checks), failed=0, checks=checks), indent=2))
    artifacts = scripts + [ROOT / name for name in REPORTS]
    for name in RUNS:
        folder = ROOT / "experiments/runs" / f"2026-09-11_{name}"
        artifacts.extend(p for p in folder.iterdir() if p.is_file() and p.suffix in (".json", ".csv", ".md", ".sh", ".txt"))
    manifest = {**{k: v for k, v in prior.items() if k != "sha256"},
                "previous_manifest": str(previous.relative_to(ROOT)), "python_files_parsed": len(scripts),
                "wide_training_and_confirmation_executions": 5400, "total_offline_executions": 32889,
                "excluded_aborted_collector_attempts": 1, "all_scored_runs_cleared": True,
                "count_scope": "Completed scored strategy executions, including reused training scenes; excludes aborted collector attempt, geometry checks, feedback replays, HTTP tests and CLI smokes; not independent scene count or official tests",
                "final_verification_checks": audit["passed"], "artifact_checks": len(checks), "official_calls": 0,
                "sha256": {str(p.relative_to(ROOT.parent)): sha(p) for p in artifacts}}
    (ROOT / "FINAL_MANIFEST.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    print(json.dumps(dict(total_offline_executions=32889, final_checks=audit["passed"], artifact_checks=len(checks),
                          python_files_parsed=len(scripts), official_calls=0), indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--finalize", action="store_true")
    args = parser.parse_args()
    finalize() if args.finalize else verify()
