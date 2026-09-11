"""Independently verify the closed archive, without replaying or scoring policies."""
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "experiments/runs/2026-09-11_cover21-confirmation"
RUNS = {"lean-scan": 1116, "public-count-scan": 744,
        "cover21-training": 1860, "cover21-confirmation": 3900}


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    output = OUT / "post_finalize_integrity.json"
    if output.exists():
        raise RuntimeError("Preserving completed independent archive verification")
    manifest_path = ROOT / "FINAL_MANIFEST.json"
    manifest = read(manifest_path)
    assert manifest["total_offline_executions"] == 59514
    assert manifest["cover21_training_and_confirmation_executions"] == 7620
    assert manifest["official_calls"] == 0
    assert manifest["all_scored_runs_cleared"]
    for relative, expected in manifest["sha256"].items():
        assert sha(ROOT.parent / relative) == expected, relative
    previous = read(ROOT / manifest["previous_manifest"])
    assert previous["total_offline_executions"] == 51894
    records = []
    for name, expected in RUNS.items():
        folder = ROOT / "experiments/runs" / f"2026-09-11_{name}"
        data_hashes = read(folder / "scored_data_sha256.json")
        for relative, digest in data_hashes.items():
            assert sha(folder / relative) == digest, (name, relative)
        rows = [json.loads(line) for line in (folder / "trials.jsonl").read_text().splitlines()]
        assert len(rows) == expected
        assert all(r["all_cleared"] and not r["failure"] for r in rows)
        done = read(folder / "completion.json")
        assert done["executions"] == done["all_cleared"] == expected
        assert done["errors"] == 0
        records.append(dict(run=name, scored_rows=expected, data_files=len(data_hashes)))
    assert sum(r["scored_rows"] for r in records) == 7620
    audit, artifacts = read(OUT / "final_checks.json"), read(OUT / "artifact_checks.json")
    assert audit["passed"] == 99 and audit["failed"] == 0
    assert artifacts["passed"] == manifest["artifact_checks"] == 7 and artifacts["failed"] == 0
    subprocess.run(["zsh", "-n", str(OUT / "command.sh")], check=True)
    result = dict(passed=True, manifest_sha256=sha(manifest_path),
                  manifest_files=len(manifest["sha256"]), runs=records,
                  nested_data_files=sum(r["data_files"] for r in records),
                  total_offline_executions=59514, new_scored_executions_verified=7620,
                  runtime_checks=99, artifact_checks=7, launcher_syntax_passed=True,
                  scored_executions=0, official_calls=0,
                  note="Verification reads the closed archive; this record is intentionally outside the manifest it verifies.")
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
