"""检查消融、参数宽扫和联合扰动的策略构造，不运行模拟器。"""
import ast
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    results = []
    for experiment in ['ablation', 'sensitivity']:
        batch = ROOT / 'data/experiments' / ('2026-09-13_official-' + experiment)
        config = json.loads((batch / 'config.json').read_text(encoding='utf8'))
        field = 'variant' if experiment == 'ablation' else 'setting'
        choices = []
        for setting in config['settings']:
            choices.append((setting['problem'], ['--setting', setting[field]]))
        if experiment == 'sensitivity':
            for row_number, setting in enumerate(config['schedule'], start=1):
                if setting['phase'] == 'robustness':
                    choices.append((setting['problem'], ['--schedule-row', str(row_number)]))

        # 冻结包使用相同的模块名，逐进程检查可以避免两版模块相互混用。
        for problem, selection in choices:
            command = [sys.executable, '-B', 'experiments/official.py', experiment,
                       '--problem', str(problem)]
            command.extend(selection)
            command.append('--check-config')
            run = subprocess.run(command, cwd=ROOT, capture_output=True, check=True,
                                 text=True, encoding='utf8')
            result = json.loads(run.stdout)
            assert result['official_requests'] == 0
            assert result['mock_executions'] == 0
            results.append(result)

    source_count = 0
    for folder in ['algorithms', 'interfaces', 'experiments', 'tools']:
        for path in (ROOT / folder).rglob('*.py'):
            ast.parse(path.read_text(encoding='utf8'), filename=str(path))
            source_count += 1

    summary = {
        'complete': True,
        'configurations': len(results),
        'parsed_python_files': source_count,
        'official_requests': 0,
        'mock_executions': 0,
    }
    print(json.dumps(summary))
    summary['checks'] = results
    output = ROOT / 'outputs/config_checks.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf8')


if __name__ == '__main__':
    main()
