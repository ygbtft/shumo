"""Audit task experiments without counting replays or protocol checks as scores."""
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
from task_confirmation_v2 import ROOT, OUT, OLD, SPECS, all_paths, build
from icra_final_checks import partition_check
from visibility_certificate import verify_cells

RUNS = {"interleaved-tasks": 1209, "discovery-priority": 1581, "task-confirmation-v2": 2145}
REPORTS = ("REPORT.md", "REPORT_TASK_UPDATE.md", "ROBUST_GUARANTEES_UPDATE.md", "GOAL.md")


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
            for case_id in ("uniform__iid__97", "boundary_outward__n10__negative", "near_collinear__n16__positive", "cluster_far20__n13__spatial"):
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
        assert all(r["total_virtual_s"] < 314016 and r["commands"] <= 9766 for r in rows)
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
        if name == "task-confirmation-v2":
            assert sorted({r["seed"] for r in rows if r["split"] == "ordinary"}) == list(range(97, 107))
            assert config["all_policies_frozen_before_first_truth_generation"]
            assert config["collection_restart"]["no_algorithm_or_parameter_changes"]
            checks.append(replay_checks.physics_audit(rows))
    print("4935 scored rows, lifetime budgets and all 2145 confirmation traces passed", flush=True)
    original = read(OLD / "run_config.json")
    current = read(OUT / "run_config.json")
    assert original["specs"] == current["specs"]
    for name in ("interleaved_policy.py", "discovery_priority_policy.py", "efficient_joint_policy.py", "clearance_policy.py",
                 "joint_task_policy.py", "joint_policy.py", "policies.py", "geometry.py", "client.py", "task_confirmation.py"):
        assert sha(ROOT / name) == original["code_sha256"][name] == current["code_sha256"][name]
    assert not (OLD / "trials.jsonl").read_text().strip()
    assert not list((OLD / "traces").iterdir())
    assert [p.name for p in (OLD / "scenarios_scoring_only").iterdir()] == ["q3__uniform__iid__97.json"]
    assert read(OUT / "collector_checks.json")["passed"] == 2
    checks.append(dict(test="aborted_collector_preserved_no_score_based_reselection_exact_policy_hashes", passed=True,
                       aborted_scored_rows=0, collector_only_repair_checks=2))
    for name, expected in (("interleaved-tasks", 252), ("discovery-priority", 276)):
        result = read(ROOT / "experiments/runs" / f"2026-09-11_{name}" / "checks.json")
        assert result["passed"] == expected and result["failed"] == 0 and result["scored_execution_count"] == 0
        checks.append(dict(test=f"saved_protocol_and_zero_effect_checks_{name}", passed=True, checks=expected))
    for name, item in read(ROOT / "experiments/runs/2026-09-11_convex-visibility/certified_layouts.json").items():
        checks.append(dict(test=f"unchanged_continuous_coverage_partition_{name}", passed=True,
                           **verify_cells(item["points"], item["certificate"]), **partition_check(item["certificate"])))
    http = read(OUT / "http_checks.json")
    assert http["passed"] == 4 and http["failed"] == http["official_calls"] == http["scored_execution_count"] == 0
    for problem, method in ((3, "packet_center7"), (4, "packet_center22"), (4, "packet_action24_22"), (4, "packet_discover300_22")):
        a = replay_checks.load_trace(OUT / f"protocol_{problem}_{method}_inprocess.jsonl.gz")
        b = replay_checks.load_trace(OUT / f"protocol_{problem}_{method}_owned_loopback_http.jsonl.gz")
        extract = lambda trace: [(e["path"], e["request"], e["response"]["virtual_time_s"]) for e in trace]
        assert extract(a) == extract(b)
    checks.append(dict(test="four_owned_loopback_http_equivalences", passed=True, official_calls=0))
    smokes = []
    for problem, method in ((3, "packet_center7"), (4, "packet_center22")):
        folder = Path((OUT / f"smoke{problem}_log.txt").read_text().splitlines()[-1])
        result = read(folder / "summary.json")
        assert result["series"] == "task" and result["method"] == method and result["seed"] == 42
        assert result["all_cleared"] and result["official_calls"] == 0
        smokes.append(dict(problem=problem, method=method, folder=str(folder.relative_to(ROOT)), commands=result["commands"]))
    (OUT / "cli_smokes.json").write_text(json.dumps(dict(checks=smokes, scored_executions=0, official_calls=0), indent=2))
    checks.append(dict(test="two_task_cli_entrypoint_smokes", passed=True))
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
                  feedback_replays=44, new_scored_executions=4935, excluded_aborted_collector_attempts=1,
                  official_calls=0, wall_s=time.perf_counter() - began)
    (OUT / "final_checks.json").write_text(json.dumps(result, indent=2, ensure_ascii=False))
    print(json.dumps({k: v for k, v in result.items() if k not in ("checks", "completed_runs")}, indent=2))


def finalize():
    audit = read(OUT / "final_checks.json")
    assert audit["failed"] == 0 and audit["new_scored_executions"] == 4935
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
    for name in (*RUNS, "task-confirmation"):
        folder = ROOT / "experiments/runs" / f"2026-09-11_{name}"
        for filename in ("plan.md", "command.sh", "precheck.md", "log.txt", "summary.md", "next_steps.md"):
            assert (folder / filename).exists(), (name, filename)
    checks.append(dict(test="completed_and_aborted_attempt_records_are_explicit", passed=True))
    previous = OUT / "previous_final_manifest_22554.json"
    if not previous.exists():
        previous.write_bytes((ROOT / "FINAL_MANIFEST.json").read_bytes())
    prior = read(previous)
    assert prior["total_offline_executions"] == 22554
    checks.append(dict(test="previous_22554_manifest_preserved", passed=True))
    (OUT / "artifact_checks.json").write_text(json.dumps(dict(passed=len(checks), failed=0, checks=checks), indent=2))
    artifacts = scripts + [ROOT / name for name in REPORTS]
    for name in (*RUNS, "task-confirmation"):
        folder = ROOT / "experiments/runs" / f"2026-09-11_{name}"
        artifacts.extend(p for p in folder.iterdir() if p.is_file() and p.suffix in (".json", ".csv", ".md", ".sh", ".txt"))
    manifest = {**{k: v for k, v in prior.items() if k != "sha256"},
                "previous_manifest": str(previous.relative_to(ROOT)), "python_files_parsed": len(scripts),
                "task_training_and_confirmation_executions": 4935, "total_offline_executions": 27489,
                "excluded_aborted_collector_attempts": 1, "all_scored_runs_cleared": True,
                "count_scope": "Completed scored strategy executions, including reused training scenes; excludes aborted collector attempt, geometry checks, feedback replays, HTTP tests and CLI smokes; not independent scene count or official tests",
                "final_verification_checks": audit["passed"], "artifact_checks": len(checks), "official_calls": 0,
                "sha256": {str(p.relative_to(ROOT.parent)): sha(p) for p in artifacts}}
    (ROOT / "FINAL_MANIFEST.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    print(json.dumps(dict(total_offline_executions=27489, final_checks=audit["passed"], artifact_checks=len(checks),
                          python_files_parsed=len(scripts), official_calls=0), indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--finalize", action="store_true")
    args = parser.parse_args()
    finalize() if args.finalize else verify()
