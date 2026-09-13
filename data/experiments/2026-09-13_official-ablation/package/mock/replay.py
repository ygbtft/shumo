"""Replay recorded attempts unchanged, preserving request IDs and retries."""
import argparse
import json
from pathlib import Path
from .backends import RecordingBackend, create_backend


def read_jsonl(path):
    rows=[]
    with Path(path).open(encoding='utf-8') as stream:
        for line_number,line in enumerate(stream,1):
            if not line.strip(): continue
            try: row=json.loads(line)
            except ValueError as exc: raise ValueError(f'{path}:{line_number}: invalid JSON') from exc
            if not isinstance(row.get('request'),dict) or row.get('action') not in ('/enter','/measure','/clear','/exit'):
                raise ValueError(f'{path}:{line_number}: not a published robot action record')
            rows.append(row)
    if not rows: raise ValueError('empty recording')
    if len({r.get('run_id') for r in rows})!=1: raise ValueError('replay one run at a time')
    return rows


def replay(rows, backend):
    """One recorded attempt -> one replay attempt. No added retries or automatic /exit."""
    errors=[]
    for index,row in enumerate(rows,1):
        try: backend.exchange(row['action'],row['request'])
        except Exception as exc: errors.append({'sequence':index,'type':type(exc).__name__,'message':str(exc)})
    return errors


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('recording')
    p.add_argument('--backend-config',required=True)
    p.add_argument('--record',required=True,help='new replay JSONL output')
    args=p.parse_args()
    rows=read_jsonl(args.recording)
    backend=RecordingBackend(create_backend(args.backend_config),args.record)
    try: errors=replay(rows,backend)
    finally: backend.close()
    print(json.dumps({'attempts':len(rows),'transport_errors':errors},ensure_ascii=False,indent=2))

if __name__=='__main__': main()
