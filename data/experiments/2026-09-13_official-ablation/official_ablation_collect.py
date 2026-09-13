"""Copy only this experiment's official encrypted practice logs, unchanged."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import auto_practice as ap


def main():
    parser=argparse.ArgumentParser();parser.add_argument('output',type=Path);args=parser.parse_args();out=args.output.resolve()
    rows=[json.loads(l) for l in (out/'runs.jsonl').read_text().splitlines()]
    transfer=Path.home()/'Downloads/OfficialAblation-20260913';(transfer/'jlogs').mkdir(exist_ok=True)
    names=[]
    for r in rows:
        a=r['authoritative'];name=f"practice-p{r['problem']}-{a['practice_run_no']}-{a['case_code']}.jlog"
        assert re.fullmatch(r'practice-p[34]-\d+-[A-Z0-9]{4}(?:-[A-Z0-9]{4}){3}\.jlog',name)
        names.append(name)
    commands=["$ErrorActionPreference='Stop'", "$names=@("+','.join(ap.psquote(n) for n in names)+')',
              r"foreach($name in $names){Copy-Item -LiteralPath ('C:\Jammers\JammersSimulatorData\behavior-logs\'+$name) -Destination ('\\Mac\Home\Downloads\OfficialAblation-20260913\jlogs\'+$name)}",
              "Write-Output ('Copied practice logs: '+$names.Count)"]
    (transfer/'collect.ps1').write_text('\n'.join(commands),encoding='utf-8-sig')
    print(ap.guest(r'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "\\Mac\Home\Downloads\OfficialAblation-20260913\collect.ps1"'))
    dest=out/'jlogs';dest.mkdir(exist_ok=True);manifest={}
    for name in names:
        shutil.copy2(transfer/'jlogs'/name,dest/name)
        assert (dest/name).stat().st_size>0
        manifest[name]=hashlib.sha256((dest/name).read_bytes()).hexdigest()
    (out/'jlog_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    evidence_index={}
    for run in rows:
        original=Path(run['evidence'])
        # A partial collection can race the final host evidence copy; retry at finalization.
        if not list(original.glob('*/robot-run/requests.jsonl')):continue
        case=run['authoritative']['case_code'];bundle=out/'evidence'/case
        bundle.mkdir(parents=True,exist_ok=True)
        selected=[]
        for name in ('summary.json','source-hashes.json','host-decisions.jsonl','ui.ps1','database.py'):
            if (original/name).is_file():selected.append(original/name)
        for pattern in ('*/robot-run/*','*-run/*completed*','*-run/robot.*.log',
                        '*/job.json','*/result.json','*/decisions.jsonl','*-db-*/rows.json'):
            selected.extend(f for f in original.glob(pattern) if f.is_file())
        hashes={}
        for source in sorted(set(selected)):
            target=bundle/source.relative_to(original);target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(source,target)
            hashes[str(target.relative_to(out))]=hashlib.sha256(target.read_bytes()).hexdigest()
        evidence_index[case]=dict(bundle=str(bundle.relative_to(out)),original=str(original),sha256=hashes)
    (out/'evidence_index.json').write_text(json.dumps(evidence_index,ensure_ascii=False,indent=2)+'\n')


if __name__=='__main__':main()
