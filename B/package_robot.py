"""Package only the two formal-test-2 policies and their runtime dependencies."""
import ast
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parent

def runtime_files():
    seen = set()
    pending = ['run_q34_official.py', 'run_q3_fused_formal.py', 'run_q4_nearest_formal.py']
    while pending:
        name = pending.pop()
        if name in seen:
            continue
        seen.add(name)
        for node in ast.walk(ast.parse((ROOT / name).read_text())):
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else ([node.module] if isinstance(node, ast.ImportFrom) and node.module else [])
            for module in names:
                local = module.split('.')[0] + '.py'
                if (ROOT / local).is_file():
                    pending.append(local)
    return sorted(seen | {'layouts/grid21_29.json'})

def main():
    dest = ROOT / 'dist'
    dest.mkdir(exist_ok=True)
    files = runtime_files()
    forbidden = {'simulator.py', 'run_robot.py', 'official_sensitivity_config.py'}
    assert not forbidden.intersection(files)
    manifest = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in files}
    archive = dest / 'q34-formal2.zip'
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
        for name in files:
            z.write(ROOT / name, 'q34-formal2/' + name)
        z.writestr('q34-formal2/requirements.txt', 'numpy\nscipy\n')
        z.writestr('q34-formal2/manifest.json', json.dumps(manifest, indent=2))
        z.writestr('q34-formal2/README.md', (ROOT / 'Q34_CURRENT.md').read_text())
    result = dict(archive=archive.name, formal_version=2, files=manifest,
                  sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),
                  includes_mock=False, includes_official_logs=False, includes_team_identity=False)
    (dest / 'manifest.json').write_text(json.dumps(result, indent=2) + '\n')
    print(archive)

if __name__ == '__main__':
    main()
