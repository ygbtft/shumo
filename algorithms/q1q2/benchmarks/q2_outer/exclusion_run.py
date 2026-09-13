"""Additive outer-certificate CLI. Never invokes the existing paper stage."""
import argparse
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import platform
from ...optional.outer_exclusion import certify_outer
from .check_exclusion import verify


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False)+'\n')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('stage', choices=('solve', 'verify'))
    p.add_argument('--output', type=Path, default=Path(__file__).with_name('exclusion'))
    p.add_argument('--tau', default='0.01')
    p.add_argument('--max-nodes', type=int, default=10000)
    p.add_argument('--seconds', type=float, default=120.)
    a = p.parse_args()
    artifact = a.output/'certificate.json'
    if a.stage == 'solve':
        result = certify_outer(tau=a.tau, max_nodes=a.max_nodes, time_limit_s=a.seconds)
        root = Path(__file__).resolve().parents[2]
        result['environment'] = dict(python=platform.python_version(),
                                     **{n: version(n) for n in ('numpy', 'mpmath')})
        result['sha256'] = {str(n): hashlib.sha256((root/n).read_bytes()).hexdigest()
                            for n in ('optional/outer_exclusion.py', 'optional/certified.py',
                                      'benchmarks/q2_outer/check_exclusion.py', 'q2.py', 'geometry.py',
                                      'circle.py', 'feasible.py')}
        save(artifact, result)
        print(json.dumps({k: v for k, v in result.items() if k not in ('leaves', 'fixed_certificate')}, indent=2))
    else:
        result = verify(json.loads(artifact.read_text()))
        result['artifact_sha256'] = hashlib.sha256(artifact.read_bytes()).hexdigest()
        save(a.output/'verification.json', result)
        print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
