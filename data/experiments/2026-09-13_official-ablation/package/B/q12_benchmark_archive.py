"""Verify preserved inputs and bind the Q1/Q2 audit artifacts, without rerunning solvers."""
import ast
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parent
RUN = ROOT / "experiments/runs/2026-09-11_q12-peer-benchmark"
REF = ROOT / "reference/shumo-b-q12-benchmark"
WORK = RUN / "upstream_worktree"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text())


def main():
    records = []
    def check(name, passed, detail=None):
        records.append(dict(name=name, passed=bool(passed), detail=detail))
    for name in ("upstream_input_sha256.json", "mock_input_sha256.json"):
        values = read(RUN/name)
        mismatch = [p for p,digest in values.items() if sha(REF/p) != digest]
        check("reference_"+name, not mismatch, dict(count=len(values), mismatches=mismatch))
        source = {p:digest for p,digest in values.items() if p.endswith(".py") or p.endswith("cases.jsonl")}
        mismatch = [p for p,digest in source.items() if sha(WORK/p) != digest]
        check("working_source_"+name, not mismatch, dict(count=len(source), mismatches=mismatch))
    commit = subprocess.check_output(["git", "-C", str(REF), "rev-parse", "HEAD"], text=True).strip()
    check("reference_commit", commit == "253bf943a58d6f21de88f14fdc940da66b87ab96", commit)
    status = subprocess.check_output(["git", "--no-optional-locks", "-C", str(REF), "-c", "core.fsmonitor=false",
                                      "status", "--porcelain"], text=True)
    check("reference_git_clean", not status, status)
    originals = read(ROOT/"inputs_readonly_extract/input_sha256.json")
    check("original_pdf_docx_unchanged", all(sha(ROOT.parent/p)==digest for p,digest in originals.items()), list(originals))
    for area in ("q1_geometry", "q1_circle_cover", "q2_candidate", "q2_worst_diameter"):
        result = read(RUN/f"our_results/{area}.json")
        check("own_kernels_unchanged_"+area, all(sha(ROOT/p)==digest for p,digest in result["production_sha256"].items()))
        check("fixed_fixture_"+area, sha(REF/f"models/q1q2/benchmarks/{area}/cases.jsonl") == result["cases_sha256"])
    for file in ("attempt-02/upstream_completion.json", "certification/completion.json"):
        record = read(RUN/file)
        check("completion_"+file, record["source_and_cases_unchanged"] and record["official_calls"]==0,
              record["jobs"])
    previous = read(ROOT/"FINAL_MANIFEST.json")
    changed = [p for p,digest in previous["sha256"].items() if not (ROOT.parent/p).is_file() or sha(ROOT.parent/p)!=digest]
    check("historical_changes_only_report_and_builder", set(changed)=={"B/write_report.py", "B/REPORT.md"}, changed)
    files = [ROOT/name for name in ("q12_peer_benchmark.py", "q12_our_benchmark.py", "q12_benchmark_diagnostics.py",
             "q12_certification_run.py", "q12_benchmark_archive.py", "write_q12_report.py", "write_report.py")]
    for file in files:
        ast.parse(file.read_text(), filename=str(file))
    check("python_syntax", True, [str(p.relative_to(ROOT)) for p in files])
    broken = []
    for file in (ROOT/"REPORT_Q12_UPDATE.md", ROOT/"REPORT.md", RUN/"summary.md", RUN/"next_steps.md"):
        data = file.read_text()
        check("no_control_chars_"+file.name, all(ord(c)>=32 or c in "\n\t\r" for c in data))
        for link in re.findall(r"\]\(([^)]+)\)", data):
            if re.match(r"[a-zA-Z]+://|#", link):
                continue
            target = link.split("#",1)[0].strip("<>")
            if target.endswith("/manifest.json") and (file.parent/target).resolve() == RUN/"manifest.json":
                continue
            if not (file.parent/target).exists():
                broken.append(dict(file=str(file.relative_to(ROOT)), target=target))
    check("local_report_links", not broken, broken)
    audit = dict(checks=records, n_checks=len(records), passed=sum(r["passed"] for r in records),
                 failed=sum(not r["passed"] for r in records), historical_manifest_total=previous["total_offline_executions"],
                 historical_manifest_changed_files=changed, official_calls=0, new_scored_mission_executions=0)
    (RUN/"archive_check.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2))
    assert not audit["failed"], [r for r in records if not r["passed"]]
    artifacts = [p for p in RUN.rglob("*") if p.is_file() and p.name not in ("manifest.json", "archive_log.txt")]
    artifacts += files + [ROOT/"REPORT.md", ROOT/"REPORT_Q12_UPDATE.md", ROOT/"geometry.py", ROOT/"signal_minimax.py"]
    manifest = dict(generated_utc=datetime.now(timezone.utc).isoformat(), reference_commit=commit,
        checks_passed=audit["passed"], official_calls=0, scored_mission_executions=0,
        goal_optimization_paused_by_user=True, all_tests_passed=False,
        scope="Q1/Q2 correctness audit only; original solver failures and unsupported APIs are retained",
        historical_manifest=dict(path="B/FINAL_MANIFEST.json", sha256=sha(ROOT/"FINAL_MANIFEST.json"),
            sealed_executions=previous["total_offline_executions"], authorized_later_document_changes=changed,
            interpretation="Historical snapshot, not a claim that its report hashes match the later Q1/Q2 report"),
        sha256={str(p.relative_to(ROOT.parent)):sha(p) for p in sorted(set(artifacts))})
    (RUN/"manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    print(json.dumps(dict(checks_passed=audit["passed"], manifest_files=len(manifest["sha256"]),
                          official_calls=0, scored_mission_executions=0), indent=2))


if __name__ == "__main__":
    main()
