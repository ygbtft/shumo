"""Independent offline trace/cost audit for the service-routing training."""
import ast
import hashlib
import json
import time
from pathlib import Path
import mission_final_checks as feedback
from service_aware_experiments import ROOT, OUT, SPECS, EXPECTED, build, paths


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    if (OUT/"audit.json").exists():
        raise RuntimeError("Preserving completed audit")
    began = time.perf_counter()
    rows = [json.loads(line) for line in (OUT/"trials.jsonl").read_text().splitlines()]
    done, config, checked = read(OUT/"completion.json"), read(OUT/"run_config.json"), read(OUT/"checks.json")
    assert done["executions"] == done["all_cleared"] == len(rows) == EXPECTED and done["errors"] == 0
    assert checked["passed"] == 389 and checked["failed"] == 0
    assert config["untouched_future_seeds"] == list(range(157, 167))
    for name, digest in config["code_sha256"].items():
        assert sha(OUT/"code_snapshot"/name) == digest
        ast.parse((OUT/"code_snapshot"/name).read_text())
    for name in ("service_aware_policy.py", "service_aware_experiments.py", "coupled_dispatch_policy.py",
                 "interleaved_policy.py", "bounded_width_policy.py", "geometry.py", "client.py", "policies.py"):
        assert sha(ROOT/name) == config["code_sha256"][name]
    for node in ast.walk(ast.parse((ROOT/"service_aware_policy.py").read_text())):
        if isinstance(node, ast.Attribute):
            assert node.attr not in {"transport", "_transport", "scenario", "sources", "seed", "simulator"}
    checks = [dict(test="completed_training_prechecks_frozen_policy_and_restricted_state_access", passed=True)]
    for r in rows:
        assert r["all_cleared"] and not r["failure"] and not r["inconsistent_updates"] and not r.get("bracket_cut_inconsistencies", 0)
        assert r["total_virtual_s"] < 335136 and r["commands"] <= 9766
        assert r["stop_reason"] in ("public_upper_bound_16", "full_coverage_and_all_discovered_cleared")
        if r["stop_reason"] == "public_upper_bound_16":
            assert r["cleared"] == 16
        if r["problem"] == 4:
            assert r["maximum_source_rounds"] <= 10 and r["maximum_source_primary_rf"] <= 20 and r["source_interruptions"] <= 16
    checks.append(dict(test="all_training_clearance_stops_and_lifetime_budgets", passed=True, executions=len(rows)))
    feedback.OUT, feedback.SPECS, feedback.build = OUT, SPECS, build
    checks.append(feedback.physics_audit(rows))
    print("All training commands independently audited", flush=True)
    all_paths = paths()
    replay_count = 0
    for p, methods in SPECS.items():
        first = next(iter(methods))
        ordinary = [r["case_id"] for r in rows if r["problem"] == p and r["method"] == first and r["split"] == "ordinary"]
        stress = [r["case_id"] for r in rows if r["problem"] == p and r["method"] == first and r["split"] == "stress"]
        cases = [ordinary[0], ordinary[-1], stress[0], stress[len(stress)//2], stress[-1]]
        for name in methods:
            for case in cases:
                checks.append(feedback.feedback_replay(p, name, case, all_paths))
                replay_count += 1
    assert replay_count == 75
    for relative, value in read(ROOT/"inputs_readonly_extract/input_sha256.json").items():
        assert sha(ROOT.parent/relative) == value
    prior = read(OUT/"previous_final_manifest_59514.json")
    assert all(sha(ROOT.parent/relative) == value for relative, value in prior["sha256"].items())
    checks.append(dict(test="previous_293_artifacts_and_original_documents_unchanged_before_report_append", passed=True))
    result = dict(passed=len(checks), failed=0, checks=checks, scored_rows_verified=EXPECTED,
                  feedback_region_replays=replay_count, official_calls=0, scored_executions=0, wall_s=time.perf_counter()-began)
    (OUT/"audit.json").write_text(json.dumps(result, indent=2, ensure_ascii=False))
    print(json.dumps({k:v for k,v in result.items() if k != "checks"}, indent=2), flush=True)


if __name__ == "__main__":
    main()
