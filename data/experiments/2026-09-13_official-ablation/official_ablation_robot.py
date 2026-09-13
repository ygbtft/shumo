"""Run a frozen experimental policy against the official PRACTICE HTTP endpoint.

Only the policy constructor is reused from the local experiment. No local world,
scenario generator, simulator or mock transport is instantiated.
"""
import os
for key in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):
    os.environ[key]='1'
import argparse
from datetime import datetime
import json
from pathlib import Path
import time
import traceback
import ablation_data_suite as suite
from client import Client, HttpTransport


class Journal:
    def __init__(self,path): self.path=path;self.rows=[]
    def append(self,row):
        self.rows.append(row)
        with self.path.open('a',encoding='utf8') as stream:
            stream.write(json.dumps(row,ensure_ascii=False)+'\n')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--problem',type=int,choices=(3,4),required=True)
    parser.add_argument('--variant',required=True)
    parser.add_argument('--method',required=True)
    parser.add_argument('--mode',choices=['practice'],required=True)
    parser.add_argument('--base-url',choices=['http://127.0.0.1:2026'],required=True)
    parser.add_argument('--robot-id',required=True)
    parser.add_argument('--confirm-practice',action='store_true',required=True)
    args=parser.parse_args()
    variant=next((v for v in suite.variants(args.problem) if v['id']==args.variant),None)
    if variant is None: parser.error('Unknown frozen variant')
    folder=Path('robot_runs')/(datetime.now().strftime('%Y%m%d-%H%M%S-%f')+'-bounded-practice')
    folder.mkdir(parents=True,exist_ok=False)
    def write(name,value): (folder/name).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf8')
    write('config.json',dict(**vars(args),variant_spec=variant,backend='official-practice',mock_executions=0,
                            policy_specs=suite.old.harness.builders.SPECS))
    write('endpoint.json',dict(base_url=args.base_url,owned_mock=False))
    journal=Journal(folder/'requests.jsonl')
    client=Client(HttpTransport(args.base_url),robot_id=args.robot_id,transcript=journal)
    policy=suite.construct(args.problem,client,variant)
    write('policy.json',dict(class_name=type(policy).__name__,stations=policy.stations.tolist(),variant=variant))
    started=time.perf_counter();failure='';unavailable=False
    try:
        stats=policy.run()
    except suite.old.ComponentUnavailable as exc:
        # The removed completion step is the experimental failure, not a mock score.
        failure=str(exc);unavailable=True;stats=policy.stats.copy()
        client.exit()
    except Exception as exc:
        failure=repr(exc);stats=policy.stats.copy()
        (folder/'failure.txt').write_text(traceback.format_exc(),encoding='utf8')
        write('summary.json',dict(status='unexpected-error',error=failure,mode='practice',variant=variant,
              total_virtual_s=client.virtual_s,cleared=len(policy.cleared),official_calls=len(journal.rows),mock_executions=0))
        raise
    write('summary.json',dict(status='component-unavailable' if unavailable else 'policy-completed',
        mode='practice',problem=args.problem,variant=variant,policy=stats,reason=failure,
        total_virtual_s=client.virtual_s,cleared=len(policy.cleared),wall_s=time.perf_counter()-started,
        official_calls=len(journal.rows),mock_executions=0,
        scoring='Use simulator authoritative practice statistics, not this client summary.'))
    print('Official practice robot completed:',folder,flush=True)


if __name__=='__main__':main()
