"""在虚拟机内，直接运行第二次正式测试采用的 Q3/Q4 算法。"""
import argparse
import json
import os
from pathlib import Path
import sys
import time

# 固定数值库线程数，与原正式测试的运行条件一致。
os.environ['OPENBLAS_NUM_THREADS'] = '1'
os.environ['OMP_NUM_THREADS'] = '1'
os.environ['MKL_NUM_THREADS'] = '1'

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'algorithms/q34'))

from client import Client, HttpTransport
from strategy import construct, actual_parameters
from recording import RequestLog, create_output, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--problem', type=int, choices=(3, 4), required=True)
    parser.add_argument('--check-config', action='store_true')
    parser.add_argument('--mode', choices=('practice', 'formal'), default='practice')
    parser.add_argument('--robot-id')
    parser.add_argument('--case-code')
    args = parser.parse_args()

    # 构造策略不调用 HTTP；None 表示这里没有连接模拟器。
    if args.check_config:
        policy = construct(args.problem, Client(None))
        print(json.dumps({
            'problem': args.problem,
            'formal_version': 2,
            'parameters': actual_parameters(policy, args.problem),
            'official_requests': 0,
        }))
        return

    if not args.robot_id or not args.case_code:
        parser.error('运行时需要 --robot-id 和 --case-code')

    # 请先在官方界面打开案例。mode、case_code 用于记录，不会切换官方界面。
    folder = create_output(ROOT / 'outputs/official', args.case_code)
    journal = RequestLog(folder / 'requests.jsonl')
    transport = HttpTransport('http://127.0.0.1:2026')
    client = Client(transport, robot_id=args.robot_id, transcript=journal)
    policy = construct(args.problem, client)
    write_json(folder / 'config.json', {
        'problem': args.problem,
        'mode': args.mode,
        'case_code': args.case_code,
        'robot_id': args.robot_id,
        'formal_version': 2,
        'parameters': actual_parameters(policy, args.problem),
    })

    started = time.perf_counter()
    completed = False
    try:
        policy.run()
        completed = True
    finally:
        # 异常直接交给 Python 报错；已收到的请求和运行指标仍然落盘。
        result = journal.summary(policy, client, started, completed)
        write_json(folder / 'summary.json', result)
        print('Local logs:', folder)


if __name__ == '__main__':
    main()
