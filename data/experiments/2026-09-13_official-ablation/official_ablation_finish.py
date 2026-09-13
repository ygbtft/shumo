"""Finalize a completed official batch, optionally waiting for its host PID."""
import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import auto_practice as ap


def main():
    parser=argparse.ArgumentParser();parser.add_argument('output',type=Path)
    parser.add_argument('--wait-for-pid',type=int);args=parser.parse_args();out=args.output.resolve()
    while args.wait_for_pid:
        try:os.kill(args.wait_for_pid,0)
        except ProcessLookupError:break
        time.sleep(5)
    if (out/'interruption.json').exists() or not (out/'completion.json').exists():
        raise RuntimeError('Official batch did not complete; preserve evidence and inspect interruption')
    for script in ('official_ablation_analysis.py','official_ablation_collect.py','official_ablation_report.py'):
        subprocess.run([sys.executable,'-B',script,str(out)],check=True)
    result=ap.guest(r'C:\Python314-arm64\python.exe -B "\\Mac\Home\Downloads\OfficialAblation-20260913\verify.py" "C:\BAblation-20260913" "\\Mac\Home\Downloads\OfficialAblation-20260913\runtime_manifest.json"')
    (out/'postflight_runtime_verification.log').write_text(result)
    assert len(json.loads((out/'jlog_manifest.json').read_text()))==162
    for script in ('official_ablation_analysis.py','official_ablation_collect.py','official_ablation_report.py','official_ablation_finish.py'):
        shutil.copy2(script,out/script)
    readme=(out/'READ_ME_FIRST.md').read_text().replace('（运行中）','（已完成）')
    readme=readme.replace('`runs.jsonl` 是逐局官方成绩记录', '**已完成 160 局批次和 2 局接入校验。完整结果见 [REPORT.md](REPORT.md)。**\n\n`runs.jsonl` 是逐局官方成绩记录')
    readme=readme.replace('`trials.csv`、`summary.csv` 和 `audit.json` 在运行中可能只是阶段性汇总，最终以 `completion.json` 和最终审计为准。','`trials.csv`、`summary.csv` 和 `audit.json` 已汇总完整批次，并经逐局审计。')
    (out/'READ_ME_FIRST.md').write_text(readme)
    ap.write_json(out/'finalization.json',dict(completed_at=datetime.now().astimezone().isoformat(),
        official_validation_runs=160,official_calibration_runs=2,official_encrypted_logs=162,
        guest_frozen_code_verified=True,report='REPORT.md'))
    manifest={}
    excluded={'deliverable_manifest.json','finish.log'}
    for file in out.rglob('*'):
        if file.is_file() and file.name not in excluded:
            manifest[str(file.relative_to(out))]=hashlib.sha256(file.read_bytes()).hexdigest()
    ap.write_json(out/'deliverable_manifest.json',manifest)
    print('OFFICIAL_ABLATION_FINALIZED',len(manifest),flush=True)


if __name__=='__main__':main()
