"""从实验配置选择一组参数，在官方模拟器中运行一局演练。"""
import argparse
import json
import os
from pathlib import Path
import sys
import time

os.environ['OPENBLAS_NUM_THREADS'] = '1'
os.environ['OMP_NUM_THREADS'] = '1'
os.environ['MKL_NUM_THREADS'] = '1'

ROOT = Path(__file__).resolve().parents[1]
BATCHES = {
    'ablation': '2026-09-13_official-ablation',
    'sensitivity': '2026-09-13_official-sensitivity',
}
sys.path.insert(0, str(ROOT / 'interfaces'))
from recording import RequestLog, create_output, write_json


def construct_policy(experiment, problem, setting, client):
    # 两类实验各用自己的原始实现。每个进程只加载一个冻结包。
    if experiment == 'ablation':
        import ablation_data_suite
        for variant in ablation_data_suite.variants(problem):
            if variant['id'] == setting['variant']:
                return ablation_data_suite.construct(problem, client, variant)
    else:
        import official_sensitivity_config
        return official_sensitivity_config.construct(problem, client, setting['changes'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('experiment', choices=BATCHES)
    parser.add_argument('--problem', type=int, choices=(3, 4), required=True)
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument('--setting', help='原配置中的设置名，使用 --list 查看')
    selection.add_argument('--schedule-row', type=int, help='原计划第几行，从 1 开始')
    action = parser.add_mutually_exclusive_group()
    action.add_argument('--list', action='store_true')
    action.add_argument('--check-config', action='store_true')
    action.add_argument('--run', action='store_true')
    parser.add_argument('--robot-id')
    parser.add_argument('--case-code')
    args = parser.parse_args()

    batch = ROOT / 'data/experiments' / BATCHES[args.experiment]
    config = json.loads((batch / 'config.json').read_text(encoding='utf8'))
    settings = []
    for item in config['settings']:
        if item['problem'] == args.problem:
            settings.append(item)
    if args.list:
        print(json.dumps(settings, ensure_ascii=False, indent=2))
        return

    # 消融配置把设置名记为 variant，参数实验记为 setting。
    field = 'variant' if args.experiment == 'ablation' else 'setting'
    if args.schedule_row is not None:
        setting = config['schedule'][args.schedule_row - 1]
        if args.schedule_row < 1 or setting['problem'] != args.problem:
            parser.error('计划行必须从 1 开始，且题号与 --problem 一致')
    elif args.setting is None:
        setting = settings[0]
    else:
        settings_by_name = {}
        for item in settings:
            settings_by_name[item[field]] = item
        setting = settings_by_name[args.setting]

    # 不走当前交付参数，也不改写冻结源码；哈希核验由 tools/audit_data.py 完成。
    package = batch / 'package'
    sys.path.insert(0, str(package))
    sys.path.insert(0, str(package / 'B'))
    from client import Client, HttpTransport

    if not args.run:
        policy = construct_policy(args.experiment, args.problem, setting, Client(None))
        print(json.dumps({
            'experiment': args.experiment,
            'problem': args.problem,
            'setting': setting[field],
            'schedule_row': args.schedule_row,
            'archived_setting': setting,
            'policy_class': type(policy).__name__,
            'official_requests': 0,
            'mock_executions': 0,
        }, ensure_ascii=False))
        return

    if not args.robot_id or not args.case_code:
        parser.error('运行时需要 --robot-id 和 --case-code')

    # 案例由用户在官方界面打开；本程序只使用机器人公开接口。
    folder = create_output(ROOT / 'outputs/experiments', args.case_code)
    journal = RequestLog(folder / 'requests.jsonl')
    transport = HttpTransport('http://127.0.0.1:2026')
    client = Client(transport, robot_id=args.robot_id, transcript=journal)
    policy = construct_policy(args.experiment, args.problem, setting, client)
    write_json(folder / 'config.json', {
        'experiment': args.experiment,
        'problem': args.problem,
        'setting': setting,
        'source_batch': BATCHES[args.experiment],
        'schedule_row': args.schedule_row,
        'mode': 'practice',
        'case_code': args.case_code,
        'robot_id': args.robot_id,
    })

    started = time.perf_counter()
    completed = False
    try:
        policy.run()
        completed = True
    finally:
        result = journal.summary(policy, client, started, completed)
        write_json(folder / 'summary.json', result)
        print('Local logs:', folder)


if __name__ == '__main__':
    main()
