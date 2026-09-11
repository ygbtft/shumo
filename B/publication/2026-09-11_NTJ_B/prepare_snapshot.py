"""Create a verified B-research snapshot in the isolated NTJ_B checkout."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import time

PUB = Path(__file__).resolve().parent
ROOT = PUB.parents[1]
WORKSPACE = ROOT.parent
REPO = PUB / "repo"
SKIP_DIRS = {".git", ".swift-module-cache", ".mplconfig", ".cache", "__pycache__",
             ".pytest_cache", ".venv", "node_modules", "publish", "tmp"}


def main():
    started = time.perf_counter()
    destination = REPO / "B"
    destination.mkdir(exist_ok=False)
    files, excluded, problems = [], [], []
    def transfer(source, target, kind="research"):
        data = source.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        if len(data) >= 100*1024**2:
            problems.append(dict(path=str(source.relative_to(WORKSPACE)), reason="GitHub file-size limit"))
            return
        if target.exists():
            raise RuntimeError("Refusing to replace existing checkout file: " + str(target))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        shutil.copystat(source, target)
        actual = hashlib.sha256(target.read_bytes()).hexdigest()
        assert actual == digest
        files.append(dict(path=str(target.relative_to(REPO)), source=str(source.relative_to(WORKSPACE)),
                          bytes=len(data), sha256=digest, kind=kind))
    for here, dirs, names in os.walk(ROOT):
        for name in dirs:
            if name in SKIP_DIRS:
                excluded.append(dict(path=str((Path(here)/name).relative_to(ROOT)), reason="cache, metadata, temporary files, or publication worktree", directory=True))
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        for name in sorted(names):
            source = Path(here)/name
            if source.is_symlink():
                problems.append(dict(path=str(source.relative_to(ROOT)), reason="unexpected symlink outside excluded temporary directories"))
                continue
            if name == ".DS_Store" or name.startswith("._") or source.suffix in {".pid", ".pyc", ".pyo"}:
                excluded.append(dict(path=str(source.relative_to(ROOT)), reason="OS metadata or process/cache file", directory=False))
                continue
            transfer(source, destination/source.relative_to(ROOT))
            if len(files)%10000 == 0:
                print("Copied",len(files),"files",flush=True)
    dependencies = ["CUMCM2026Problems/B题/B题.pdf", "CUMCM2026Problems/B题/附件/附件1.docx",
                    "CUMCM2026Problems/B题/附件/附件2.docx", "project/topic_probes/b_probe.py", "project/topic_probes/common.py"]
    for path in dependencies:
        transfer(WORKSPACE/path, REPO/path, "readonly_compatibility_dependency")
    for name in ("plan.md", "precheck.md", "command.sh", "secret_scan.json", "prepare_snapshot.py", "commit_message.txt"):
        transfer(PUB/name, destination/"publication/2026-09-11_NTJ_B"/name, "publication_record")
    if problems:
        (PUB/"preparation_problems.json").write_text(json.dumps(problems,indent=2,ensure_ascii=False))
        raise RuntimeError("Snapshot needs review; originals untouched")
    scan = json.loads((PUB/"secret_scan.json").read_text())
    assert not scan["high_confidence_findings"] and not scan["review_candidates"]
    manifest = dict(generated_utc=datetime.now(timezone.utc).isoformat(), target_repository="https://github.com/ygbtft/shumo.git",
        target_branch="NTJ_B", base_commit="253bf943a58d6f21de88f14fdc940da66b87ab96",
        all_source_copies_sha256_verified=True, source_files_modified=False, official_calls=0,
        goal_optimization_paused=True, files=files, excluded=excluded, files_count=len(files),
        bytes_total=sum(x["bytes"] for x in files), max_file=max(files,key=lambda x:x["bytes"]),
        metadata_scope="This inventory excludes its own generated manifest; historical manifests retain their original scope and may reference omitted temporary files.",
        secret_scan=scan, wall_s=time.perf_counter()-started)
    (destination/"SNAPSHOT_MANIFEST.json").write_text(json.dumps(manifest,indent=2,ensure_ascii=False))
    (PUB/"snapshot_summary.json").write_text(json.dumps({k:v for k,v in manifest.items() if k not in {"files", "excluded", "secret_scan"}},indent=2,ensure_ascii=False))
    print(json.dumps(dict(files=len(files), bytes=manifest["bytes_total"], max_file_bytes=manifest["max_file"]["bytes"],
                          excluded_entries=len(excluded), wall_s=manifest["wall_s"]),indent=2),flush=True)


if __name__ == "__main__":
    main()
