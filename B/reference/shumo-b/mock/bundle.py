"""Export portable source and sample configs; excludes data, venv and local credentials."""
import argparse
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',default='mock/dist/mock-core.zip')
    args=p.parse_args()
    root=Path(__file__).resolve().parent
    selected=[]
    for path in root.rglob('*'):
        rel=path.relative_to(root)
        if not path.is_file() or any(part.startswith('.') for part in rel.parts): continue
        if rel.parts[0] in ('results','materials','dist','__pycache__'): continue
        if '__pycache__' in rel.parts or path.name.endswith('.local.json'): continue
        if path.suffix=='.py' or (rel.parts[0]=='configs' and path.suffix=='.json') or path.name in ('README.md','requirements.txt','requirements-viz.txt','requirements-dev.txt'):
            selected.append(path)
    out=Path(args.output);out.parent.mkdir(parents=True,exist_ok=True)
    with ZipFile(out,'w',ZIP_DEFLATED) as z:
        for path in sorted(selected): z.write(path,Path('mock')/path.relative_to(root))
    print(f'{out}: {len(selected)} files, {out.stat().st_size} bytes')

if __name__=='__main__': main()
