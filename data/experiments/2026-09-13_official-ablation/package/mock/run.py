"""Run one unchanged strategy through a backend configuration, optionally recording."""
import argparse
import json
from pathlib import Path
from .backends import RecordingBackend, create_backend
from .client_or_inproc import load_strategy, run_strategy


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--backend-config', required=True)
    p.add_argument('--strategy', default='mock.strategy:Baseline')
    p.add_argument('--seed', type=int, default=0, help='strategy RNG seed only; scenario seed is in backend config')
    p.add_argument('--record', help='new JSONL file; existing file is never overwritten')
    p.add_argument('--max-actions', type=int, default=10000)
    p.add_argument('--output', default='mock/results/run.json')
    args=p.parse_args()
    backend=create_backend(args.backend_config)
    if args.record: backend=RecordingBackend(backend,args.record)
    try: result=run_strategy(backend,load_strategy(args.strategy,args.seed),args.max_actions)
    finally: backend.close()
    out=Path(args.output);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(vars(result),ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in vars(result).items() if k!='trace'},ensure_ascii=False,indent=2))

if __name__=='__main__': main()
