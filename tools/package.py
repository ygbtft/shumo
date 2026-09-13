"""打包 VM 运行需要的源码，可选加入冻结实验源码或离线回放资料。"""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--include-experiments', action='store_true')
    parser.add_argument('--include-replay', action='store_true')
    parser.add_argument('--output', type=Path, default=ROOT / 'dist/delivery.zip')
    args = parser.parse_args()

    files = set()
    excluded = {'__pycache__', 'tests', 'benchmarks', 'reviews', 'outputs'}
    for directory in ['algorithms', 'interfaces']:
        for path in (ROOT / directory).rglob('*'):
            if not path.is_file() or path.suffix not in ['.py', '.json']:
                continue
            if excluded.intersection(path.relative_to(ROOT).parts):
                continue
            files.add(path)
    for name in ['requirements.txt', 'README.md', 'HANDOFF.md', 'tools/verify_bundle.py',
                 'docs/q1.md', 'docs/q2.md', 'docs/q3.md', 'docs/q4.md',
                 'docs/q1q2-design.md', 'docs/validation.md', 'docs/delivery-check.md']:
        files.add(ROOT / name)

    # 实验包按各组实际使用的策略与配置打包。
    if args.include_experiments:
        files.add(ROOT / 'experiments/official.py')
        files.add(ROOT / 'experiments/README.md')
        for name in ['2026-09-13_official-ablation', '2026-09-13_official-sensitivity']:
            batch = ROOT / 'data/experiments' / name
            for path in (batch / 'package').rglob('*'):
                if path.is_file():
                    files.add(path)
            files.add(batch / 'config.json')
            files.add(batch / 'runtime_manifest.json')

    # 精确回放只需要 27 局请求响应，不必复制数十 GB 的界面截图。
    if args.include_replay:
        files.add(ROOT / 'tools/replay_official.py')
        audit_path = ROOT / 'paper/tables/逐局审计.json'
        files.add(audit_path)
        audit = json.loads(audit_path.read_text(encoding='utf8'))
        for case in audit['cases']:
            selected = case['batch'] in ['q3_first', 'q3_repeat', 'q4_repeat']
            if case['batch'] == 'ablation' and case['problem'] == 4:
                selected = case['setting'] == 'online_nearest__g35'
            if selected:
                files.add(ROOT / case['trace'])
        for case in audit['formal2_provenance']:
            files.add(ROOT / case['trace'])

    manifest = {}
    for path in sorted(files):
        name = path.relative_to(ROOT).as_posix()
        manifest[name] = hashlib.sha256(path.read_bytes()).hexdigest()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(args.output, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name in manifest:
            archive.write(ROOT / name, name)
        archive.writestr('bundle_manifest.json', json.dumps(manifest, ensure_ascii=False, indent=2))
    print(json.dumps({
        'archive': str(args.output),
        'files': len(files),
        'sha256': hashlib.sha256(args.output.read_bytes()).hexdigest(),
        'includes_frozen_experiments': args.include_experiments,
        'includes_recorded_replay': args.include_replay,
    }, ensure_ascii=False))


if __name__ == '__main__':
    main()
