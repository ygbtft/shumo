from pathlib import Path
import json,os,subprocess,sys,time
out=Path(__file__).resolve().parents[1]
while not (out/'finalization.json').exists():
    if (out/'interruption.json').exists() or (out/'live_audit_error.json').exists():
        raise SystemExit('Official execution/audit interrupted; no delivery completion written.')
    try: os.kill(int((out/'batch.pid').read_text()),0)
    except ProcessLookupError: raise SystemExit('Executor ended without finalization; inspect batch.log.')
    time.sleep(30)
if not json.loads((out/'finalization.json').read_text())['complete']:
    raise SystemExit('Partial experiment; do not mark delivery complete.')
subprocess.run([sys.executable,'-B',str(out/'operations/official_sensitivity_delivery.py'),str(out)],check=True)
