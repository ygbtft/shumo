"""Audit new frozen missions using recorded feedback and independent physics.

No new scored scenes, simulator instances, HTTP calls, or official services.
"""
import argparse
import ast
from collections import Counter
import gzip
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import time

import numpy as np

from client import Client
from clearance_experiments import build
from icra_final_checks import RecordedRegions, partition_check
from mission_confirmation import OUT, SPECS, all_paths
from visibility_certificate import verify_cells

ROOT = Path(__file__).resolve().parent
RUNS = {"asymmetric-probes": 1860, "reception-layout": 1674,
        "clearance-neighborhood": 744, "mission-confirmation": 2145}
REPORTS = ("REPORT.md", "REPORT_MISSION_UPDATE.md", "ICRA_CONNECTION.md",
           "C_SIG_AND_MINIMAX.md", "ROBUST_GUARANTEES_UPDATE.md", "GOAL.md")


def read(path):
    return json.loads(path.read_text())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_trace(path):
    with gzip.open(path, "rt") as stream:
        return [json.loads(line) for line in stream]


def feedback_replay(problem, method, case_id, paths):
    case = f"q{problem}__{case_id}"
    trace = load_trace(OUT / "traces" / f"{case}__{method}.jsonl.gz")
    index = 0
    certified_stack = []
    certified_regions = near_certificates = 0

    def replay(endpoint, raw):
        nonlocal index, certified_regions, near_certificates
        entry = trace[index]
        request = json.loads(raw)
        assert endpoint == entry["path"] and request == entry["request"], (case, method, index)
        if endpoint == "/clear" and certified_stack and certified_stack[-1]:
            ch = request["channel"]
            q = np.array([request["position"]["x"], request["position"]["y"]])
            # Near is itself a public <=5 m certificate, even when the retained
            # angular polygon has not been shrunk by this special feedback.
            previous = trace[index - 1]
            is_near = (previous["path"] == "/measure"
                       and previous["request"]["channel"] == ch
                       and previous["response"]["measure_result"] == "near"
                       and previous["request"]["position"] == request["position"])
            if is_near:
                near_certificates += 1
            else:
                assert ch in policy.regions
                bound = float(np.linalg.norm(policy.regions[ch] - q, axis=1).max())
                assert bound <= 20. + 1e-7, (case, method, ch, bound)
                certified_regions += 1
            assert entry["response"]["clear_result"] == "success"
        index += 1
        return 200, entry["response"]

    policy = build(Client(replay, robot_id="mock-robot"), SPECS[problem][method], problem, paths)
    recorded = RecordedRegions()
    policy.regions = recorded
    original_clear = policy.clear

    def observed_clear(p, ch, certified=False):
        certified_stack.append(certified)
        try:
            return original_clear(p, ch, certified)
        finally:
            certified_stack.pop()

    policy.clear = observed_clear
    stats = policy.run()
    assert index == len(trace)
    # Read truth strictly after the policy has completed its feedback replay.
    fixture = read(OUT / "scenarios_scoring_only" / f"{case}.json")
    sources = {s["channel"]: np.array([s["x"], s["y"]]) for s in fixture["scenario"]["sources"]}
    assert set(sources) == policy.cleared
    min_margin = math.inf
    for ch, poly in recorded.history:
        edges = np.roll(poly, -1, axis=0) - poly
        norm = np.linalg.norm(edges, axis=1)
        good = norm > 1e-9
        if good.any():
            relative = sources[ch] - poly
            cross = edges[:, 0] * relative[:, 1] - edges[:, 1] * relative[:, 0]
            margin = float((cross[good] / norm[good]).min())
            min_margin = min(min_margin, margin)
            assert margin >= -1e-5, (case, method, ch, margin)
    return dict(test=f"public_replay_regions_and_optical_certificates_{case}_{method}",
                passed=True, commands=index, region_updates=len(recorded.history),
                minimum_truth_margin_m=min_margin, certified_region_clears=certified_regions,
                certified_near_clears=near_certificates, stop_reason=stats["stop_reason"])


def physics_audit(rows):
    """Recompute every confirmation trace without calling backend physics."""
    commands = direction_replies = near_replies = repeated_locations = 0
    max_abs_error = 0.
    fixtures = {}
    for row in rows:
        case = f"q{row['problem']}__{row['case_id']}"
        if case not in fixtures:
            fixture = read(OUT / "scenarios_scoring_only" / f"{case}.json")
            fixtures[case] = {s["channel"]: s for s in fixture["scenario"]["sources"]}
        sources = fixtures[case]
        trace = load_trace(OUT / "traces" / f"{case}__{row['method']}.jsonl.gz")
        point, current_channel, time_us, cleared, readings = (0., 0.), 1, 0, set(), {}
        assert trace[0]["path"] == "/enter" and trace[-1]["path"] == "/exit"
        for index, entry in enumerate(trace):
            path, request, reply = entry["path"], entry["request"], entry["response"]
            assert reply["accepted"] is True
            if path in ("/measure", "/clear"):
                q = (request["position"]["x"], request["position"]["y"])
                ch = request["channel"]
                move_us = math.floor(math.dist(point, q) / 5. * 1e6 + .5)
                source = sources.get(ch) if ch not in cleared else None
                distance = math.dist(q, (source["x"], source["y"])) if source else math.inf
                if path == "/measure":
                    visible = bool(source and distance <= source["radius"])
                    if visible and source["direction_deg"] is not None and distance > 0.:
                        facing = math.radians(source["direction_deg"])
                        projection = ((q[0] - source["x"]) * math.cos(facing)
                                      + (q[1] - source["y"]) * math.sin(facing)) / distance
                        # Independent dot-product form of the closed 180-degree
                        # beam, allowing the backend's documented boundary epsilon.
                        if abs(projection) > 3e-12:
                            visible = projection > 0.
                        else:
                            visible = reply["measure_result"] != "no_signal"
                    expected = "no_signal" if not visible else "near" if distance <= 5. else "direction"
                    assert reply["measure_result"] == expected, (case, row["method"], index, expected)
                    key = (ch, *q)
                    value = (expected, reply.get("svd_deg"))
                    if ch not in cleared:
                        if key in readings:
                            assert readings[key] == value
                            repeated_locations += 1
                        readings[key] = value
                    if expected == "direction":
                        true_bearing = math.degrees(math.atan2(source["y"] - q[1], source["x"] - q[0]))
                        error = (reply["svd_deg"] - true_bearing + 180.) % 360. - 180.
                        assert abs(error) <= 1.005 + 1e-8, (case, ch, error)
                        assert abs(reply["svd_deg"] * 100 - round(reply["svd_deg"] * 100)) < 1e-7
                        max_abs_error = max(max_abs_error, abs(error))
                        direction_replies += 1
                    near_replies += int(expected == "near")
                    action_s = 5 + int(ch != current_channel)
                    current_channel = ch
                else:
                    success = source is not None and distance <= 20.
                    assert (reply["clear_result"] == "success") == success
                    action_s = 5 if success else 3
                    if success:
                        cleared.add(ch)
                point = q
                time_us += move_us + action_s * 1000000
            else:
                assert path in ("/enter", "/exit")
            assert abs(reply["virtual_time_s"] * 1e6 - time_us) < .01, (case, index)
            assert math.dist(entry["position"], point) < 1e-8
        assert cleared == set(sources) and len(trace) == row["commands"]
        assert abs(time_us / 1e6 - row["total_virtual_s"]) < 1e-7
        commands += len(trace)
    return dict(test="all_confirmation_trace_physics_timing_quantization_and_fixed_errors",
                passed=True, executions=len(rows), commands=commands, direction_replies=direction_replies,
                near_replies=near_replies, repeated_location_replies=repeated_locations,
                maximum_absolute_bearing_error_deg=max_abs_error,
                directional_boundary_tolerance="Within 3e-12 normalized dot product, accept either side of floating boundary")


def verify():
    if (OUT / "final_checks.json").exists():
        raise RuntimeError("Preserving completed checks; use --finalize for document/manifest refresh")
    began = time.perf_counter()
    paths = all_paths()
    checks, completed = [], []
    for problem, methods in SPECS.items():
        for method in methods:
            for case_id in ("uniform__iid__87", "boundary_outward__n10__negative",
                            "near_collinear__n16__positive", "cluster_far20__n13__spatial"):
                checks.append(feedback_replay(problem, method, case_id, paths))
    print("44 exact public-feedback replays and region/optical checks passed", flush=True)
    for name, count in RUNS.items():
        folder = ROOT / "experiments/runs" / f"2026-09-11_{name}"
        completion = read(folder / "completion.json")
        rows = [json.loads(line) for line in (folder / "trials.jsonl").read_text().splitlines()]
        assert completion["executions"] == count == len(rows)
        assert all(r["all_cleared"] and not r["failure"] for r in rows)
        assert all(r.get("inconsistent_updates", 0) == r.get("bracket_cut_inconsistencies", 0) == 0 for r in rows)
        assert all(r["cleared"] == 16 for r in rows if r["stop_reason"] == "public_upper_bound_16")
        assert all(r["total_virtual_s"] < 360000 and r["commands"] <= 9766 for r in rows)
        config = read(folder / "run_config.json")
        assert config["base_seed"] == 42
        for filename, sha in config["code_sha256"].items():
            assert digest(folder / "code_snapshot" / filename) == sha, (name, filename)
        completed.append(dict(run=name, executions=count, all_cleared=count,
                              stop_reasons=dict(Counter(r["stop_reason"] for r in rows))))
        checks.append(dict(test=f"archive_counts_stops_and_frozen_hashes_{name}", passed=True, executions=count))
        if name == "mission-confirmation":
            assert sorted({r["seed"] for r in rows if r["split"] == "ordinary"}) == list(range(87, 97))
            assert all(r["cleared"] in (10, 13, 16) for r in rows if r["split"] == "stress")
            changed = [name for name, sha in config["code_sha256"].items() if digest(ROOT / name) != sha]
            assert set(changed) <= {"run_bounded_robot.py", "write_report.py"}, changed
            checks.append(dict(test="confirmation_freeze_still_matches_runtime_algorithms", passed=True,
                               later_entrypoint_or_document_changes=changed))
            checks.append(physics_audit(rows))
    print("6423 scored archives and every confirmation protocol trace passed", flush=True)
    certified = read(ROOT / "experiments/runs/2026-09-11_convex-visibility/certified_layouts.json")
    for name, item in certified.items():
        checks.append(dict(test=f"continuous_cells_hulls_and_complete_partition_{name}", passed=True,
                           **verify_cells(item["points"], item["certificate"]), **partition_check(item["certificate"])))
    for name, number in (("asymmetric-probes", 49), ("reception-layout", 42), ("clearance-neighborhood", 114), ("q2-minimax", 3)):
        folder = ROOT / "experiments/runs" / f"2026-09-11_{name}"
        result = read(folder / "checks.json")
        assert result["passed"] == number and result["failed"] == 0 and result["scored_execution_count"] == 0
        if name == "clearance-neighborhood":
            assert sum("independent_normal_cone" in c["test"] for c in result["checks"]) == 80
        if name == "q2-minimax":
            assert result["legal_direction_updates"] == 1340
            assert result["guaranteed_candidates_never_missed"] and result["continuous_bounds_enclose_all_legal_sample_posteriors"]
            for filename, sha in read(folder / "run_config.json")["code_sha256"].items():
                assert digest(folder / "code_snapshot" / filename) == sha
        checks.append(dict(test=f"saved_independent_checks_{name}", passed=True, checks=number))
    http = read(OUT / "http_checks.json")
    assert http["passed"] == 4 and http["failed"] == http["official_calls"] == http["scored_execution_count"] == 0
    for problem, method in ((3, "clearance7"), (3, "clearance9"), (4, "quarter22"), (4, "clearance_f015_22")):
        a = load_trace(OUT / f"protocol_{problem}_{method}_inprocess.jsonl.gz")
        b = load_trace(OUT / f"protocol_{problem}_{method}_owned_loopback_http.jsonl.gz")
        assert [(r["path"], r["request"], r["response"]["virtual_time_s"]) for r in a] == [(r["path"], r["request"], r["response"]["virtual_time_s"]) for r in b]
    checks.append(dict(test="four_saved_actual_loopback_http_equivalences", passed=True, official_calls=0))
    for folder, method in (("20260911-033439-116076-bounded-offline", "clearance7"),
                           ("20260911-033439-418711-bounded-offline", "quarter22")):
        result = read(ROOT / "robot_runs" / folder / "summary.json")
        assert result["series"] == "mission" and result["method"] == method and result["seed"] == 42
        assert result["all_cleared"] and result["official_calls"] == 0
    checks.append(dict(test="two_saved_mission_cli_smokes", passed=True, scored_executions=0))
    for relative, sha in read(ROOT / "inputs_readonly_extract/input_sha256.json").items():
        assert digest(ROOT.parent / relative) == sha
    old = read(ROOT / "experiments/runs/2026-09-10_independent/run_config.json")
    public = "project/topic_probes/b_probe.py"
    assert digest(ROOT.parent / public) == old["input_sha256"][public]
    for item in read(ROOT / "experiments/runs/2026-09-11_peer-paper-review/paper_sha256.json"):
        assert digest(ROOT / "别人的结果/同学一" / item["name"]) == item["sha256"]
    for repo in ("shumo-b", "shumo-b-macos-handoff"):
        result = subprocess.run(["git", "-C", str(ROOT / "reference" / repo), "status", "--porcelain"], capture_output=True, text=True, check=True)
        assert not result.stdout.strip()
    assert digest(ROOT / "reference/tokekar2013asensor.pdf") == "f12a5e11d694a85353b019835d6ef2de810a4124f094c16318257f877468d6ca"
    checks.append(dict(test="original_inputs_public_probe_peer_paper_author_pdf_and_upstreams_unchanged", passed=True))
    result = dict(passed=len(checks), failed=0, checks=checks, completed_runs=completed,
                  feedback_replays=44, new_scored_executions=sum(RUNS.values()), official_calls=0,
                  wall_s=time.perf_counter() - began, policy_receives_truth=False)
    (OUT / "final_checks.json").write_text(json.dumps(result, indent=2, ensure_ascii=False))
    print(json.dumps({k: v for k, v in result.items() if k not in ("checks", "completed_runs")}, indent=2), flush=True)


def finalize():
    audit = read(OUT / "final_checks.json")
    assert audit["failed"] == 0 and audit["new_scored_executions"] == 6423
    checks = []
    scripts = list(ROOT.glob("*.py"))
    for path in scripts:
        ast.parse(path.read_text(), filename=str(path))
    checks.append(dict(test="all_current_top_level_python_parses", passed=True, count=len(scripts)))
    for name in REPORTS:
        path = ROOT / name
        for target in re.findall(r"\]\(([^)]+)\)", path.read_text()):
            if target.startswith(("https:", "http:", "#")):
                continue
            assert (path.parent / target.split("#")[0]).exists(), (name, target)
    checks.append(dict(test="current_report_links_resolve", passed=True))
    for name in (*RUNS, "q2-minimax"):
        folder = ROOT / "experiments/runs" / f"2026-09-11_{name}"
        for filename in ("plan.md", "command.sh", "precheck.md", "log.txt", "summary.md", "next_steps.md"):
            assert (folder / filename).is_file(), (name, filename)
    checks.append(dict(test="per_run_plans_commands_checks_logs_summaries_and_next_steps_exist", passed=True))
    previous = OUT / "previous_final_manifest_16131.json"
    if not previous.exists():
        previous.write_bytes((ROOT / "FINAL_MANIFEST.json").read_bytes())
    prior = read(previous)
    assert prior["total_offline_executions"] == 16131
    checks.append(dict(test="previous_scored_manifest_preserved_before_increment", passed=True))
    artifact_result = dict(passed=len(checks), failed=0, checks=checks, official_calls=0)
    (OUT / "artifact_checks.json").write_text(json.dumps(artifact_result, indent=2))
    artifacts = scripts + [ROOT / name for name in REPORTS]
    for name in (*RUNS, "q2-minimax"):
        folder = ROOT / "experiments/runs" / f"2026-09-11_{name}"
        artifacts.extend(p for p in folder.iterdir() if p.is_file() and p.suffix in (".md", ".json", ".csv", ".sh", ".txt", ".png", ".pdf"))
    manifest = {**{k: v for k, v in prior.items() if k != "sha256"},
                "python_files_parsed": len(scripts), "previous_manifest": str(previous.relative_to(ROOT)),
                "mission_training_and_confirmation_executions": 6423,
                "total_offline_executions": 22554, "all_scored_runs_cleared": True,
                "count_scope": "Completed scored strategy executions, including reused training scenes; excludes geometry checks, feedback replays, local HTTP tests and CLI smokes; not independent scene count or official tests",
                "final_verification_checks": audit["passed"], "artifact_checks": len(checks),
                "official_calls": 0,
                "sha256": {str(p.relative_to(ROOT.parent)): digest(p) for p in artifacts}}
    (ROOT / "FINAL_MANIFEST.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    print(json.dumps(dict(total_offline_executions=22554, all_scored_runs_cleared=True,
                          final_verification_checks=audit["passed"], artifact_checks=len(checks),
                          python_files_parsed=len(scripts), official_calls=0), indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--finalize", action="store_true")
    args = parser.parse_args()
    finalize() if args.finalize else verify()
