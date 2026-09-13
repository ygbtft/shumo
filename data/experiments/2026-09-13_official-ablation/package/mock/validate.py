"""Offline cross-platform smoke check: local HttpMock -> recorded InProcMock replay.

This command never creates HttpOfficial and never connects to an existing service.
It starts its own mock on an OS-assigned local port.
"""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import threading
from .backends import HttpMock, InProcMock, RecordingBackend
from .client_or_inproc import run_strategy
from .differ import compare
from .error_field import ErrorConfig
from .protocol import Protocol
from .replay import read_jsonl, replay
from .scenario_gen import generate
from .server import MockHTTPServer
from .simulator import Limits, Simulator
from .strategy import Baseline


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',default='mock/results/adapter-validation')
    p.add_argument('--seed',type=int,default=202600)
    args=p.parse_args()
    out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
    case=generate(args.seed)
    sim=Simulator(case,limits=Limits(countdown_s=0))
    server=MockHTTPServer(('127.0.0.1',0),Protocol(sim))
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    recorder=RecordingBackend(HttpMock(f'http://127.0.0.1:{server.server_port}',retries=0),out/'http.jsonl')
    try: result=run_strategy(recorder,Baseline())
    finally:
        recorder.close();server.shutdown();server.server_close();thread.join(2)
    rows=read_jsonl(out/'http.jsonl')
    target=RecordingBackend(InProcMock(seed=args.seed),out/'inproc.jsonl')
    try: errors=replay(rows,target)
    finally: target.close()
    report=compare(rows,read_jsonl(out/'inproc.jsonl'),'known_mock_scene')
    report['run_result']={k:v for k,v in vars(result).items() if k!='trace'}
    (out/'diff.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    (out/'case.json').write_text(json.dumps({'scenario':case.to_dict(),'error':asdict(ErrorConfig()),'trace':sim.trace},ensure_ascii=False,indent=2),encoding='utf-8')
    if errors or not report['deterministic_zero_difference']: raise SystemExit('Offline adapter verification FAILED; inspect diff.json')
    print(json.dumps({'verified_records':len(rows),'deterministic_zero_difference':True,'official_contacted':False,'output':str(out)},indent=2))

if __name__=='__main__': main()
