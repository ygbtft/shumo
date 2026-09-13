"""Execute one frozen assignment against the official practice HTTP interface."""
import os
for key in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):
    os.environ[key] = '1'
import argparse
from datetime import datetime
import json
from pathlib import Path
import sys
import time
import traceback

from client import Client, HttpTransport
import official_sensitivity_config as config

ROOT = Path(__file__).resolve().parent


class Journal:
    def __init__(self, path):
        self.path = path
        self.count = 0
    def append(self, row):
        with self.path.open('a',encoding='utf8') as f:
            f.write(json.dumps(row,ensure_ascii=False)+'\n')
        self.count += 1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--assignment-id',type=int,required=True)
    parser.add_argument('--problem',type=int,choices=(3,4),required=True)
    parser.add_argument('--method',required=True)
    parser.add_argument('--mode',choices=['practice'],required=True)
    parser.add_argument('--base-url',choices=['http://127.0.0.1:2026'],required=True)
    parser.add_argument('--robot-id',required=True)
    parser.add_argument('--confirm-practice',action='store_true',required=True)
    args = parser.parse_args()
    frozen = json.loads((ROOT/'experiment.json').read_text())
    assignment = frozen['schedule'][args.assignment_id-1]
    assert assignment['order'] == args.assignment_id and assignment['problem'] == args.problem
    assert assignment['method'] == args.method
    folder = ROOT/'robot_runs'/(datetime.now().strftime('%Y%m%d-%H%M%S-%f')+'-bounded-practice')
    folder.mkdir(parents=True,exist_ok=False)
    def write(name, value):
        (folder/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
    write('config.json',dict(**vars(args),assignment=assignment,backend='official-practice',mock_executions=0,
          assignment_sha256=config.canonical_hash(assignment)))
    journal = Journal(folder/'requests.jsonl')
    client = Client(HttpTransport(args.base_url),robot_id=args.robot_id,transcript=journal)
    policy = config.construct(args.problem,client,assignment['changes'])
    assert not any(k == 'mock' or k.startswith('mock.') for k in sys.modules)
    write('policy.json',dict(class_name=type(policy).__name__,parameters=config.actual_parameters(policy,args.problem),
          stations=policy.stations.tolist()))
    write('endpoint.json',dict(base_url=args.base_url,owned_mock=False))
    started = time.perf_counter()
    failure = ''
    status = 'policy-completed'
    try:
        policy.run()
    except Exception as exc:
        failure = repr(exc)
        status = 'unexpected-error'
        (folder/'failure.txt').write_text(traceback.format_exc())
    finally:
        rounds = {str(k):int(v) for k,v in getattr(policy,'_rounds',{}).items()}
        budget = policy.max_active if args.problem == 3 else policy.bracket_steps
        write('summary.json',dict(status=status,error=failure,mode='practice',problem=args.problem,
            assignment=assignment,parameters=config.actual_parameters(policy,args.problem),policy=policy.stats,
            total_virtual_s=client.virtual_s,cleared=len(policy.cleared),official_calls=journal.count,mock_executions=0,
            wall_s=time.perf_counter()-started,source_rounds=rounds,
            sources_at_round_budget=sum(v>=budget for v in rounds.values()),
            primary_rf={str(k):int(v) for k,v in getattr(policy,'_primary_counts',{}).items()},
            scoring='Official practice statistics are authoritative.'))
    if failure:
        raise RuntimeError(failure)
    print('Official sensitivity run completed:',folder,flush=True)


if __name__ == '__main__':
    main()
