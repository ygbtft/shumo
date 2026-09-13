import json,sys,time
from pathlib import Path
out=Path(sys.argv[1]);sys.path.insert(0,str(out/'host'))
from official_sensitivity_analysis import audit_trial
seen={}
while True:
 try:
  runs=[json.loads(l) for l in (out/'runs.jsonl').read_text().splitlines()] if (out/'runs.jsonl').exists() else []
  for run in runs:
   if run['order'] not in seen:
    row=audit_trial(run)
    seen[run['order']]=dict(order=run['order'],problem=row['problem'],phase=row['phase'],case_code=row['case_code'],completed=row['completed'],sources=row['sources'],cleared=row['cleared'],misses=row['misses'],max_action_ledger_error_s=row['max_action_ledger_error_s'])
  state=dict(audited=len(seen),all_clear=sum(r['completed'] for r in seen.values()),sources=sum(r['sources'] for r in seen.values()),max_action_ledger_error_s=max((r['max_action_ledger_error_s'] for r in seen.values()),default=0),by_problem={str(p):dict(runs=sum(r['problem']==p for r in seen.values()),all_clear=sum(r['completed'] for r in seen.values() if r['problem']==p)) for p in (3,4)})
  temp=out/'live_audit.tmp';temp.write_text(json.dumps(state,indent=2));temp.replace(out/'live_audit.json')
  if (out/'completion.json').exists() or (out/'interruption.json').exists() or (out/'cutoff.json').exists():
   (out/'live_audit_trials.json').write_text(json.dumps(list(seen.values()),indent=2));break
 except json.JSONDecodeError:
  time.sleep(.2);continue
 except Exception as exc:
  (out/'live_audit_error.json').write_text(json.dumps(dict(error=repr(exc),last_audited=max(seen,default=0)),indent=2));raise
 time.sleep(5)
