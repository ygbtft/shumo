"""Verify retained official records and their current, explicit path index offline."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'experiments'))
from build_tables import read_trace


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    formal = json.loads((ROOT/'data/formal/index.json').read_text(encoding='utf8'))
    assert formal['primary_formal_index'] == 2
    assert sorted((r['problem'], r['formal_index']) for r in formal['records']) == [
        (p, i) for p in (3, 4) for i in (1, 2, 3)]
    for r in formal['records']:
        assert r['primary'] == (r['formal_index'] == 2)
        meta = json.loads((ROOT/r['metadata']).read_text(encoding='utf8'))
        for key in ('formal_index', 'case_code'):
            assert meta[key] == r[key]
        assert meta['problem_no'] == r['problem']
        assert digest(ROOT/r['jlog']) == r['jlog_sha256'] == meta['package_sha256']
        metrics = read_trace(ROOT/r['trace'])
        assert metrics['trace_sha256'] == r['trace_sha256']
        assert float(metrics['program_runtime_s']) == r['program_runtime_s']
        assert float(metrics['exit_virtual_s']) == r['total_virtual_s']
        rows = [json.loads(s) for s in (ROOT/r['trace']).read_text(encoding='utf8').splitlines()]
        cleared = {x['request']['channel'] for x in rows
                   if x['path'] == '/clear' and x['response'].get('clear_result') == 'success'}
        assert len(cleared) == r['cleared']
        assert r['seconds_per_cleared_source'] == r['total_virtual_s'] / len(cleared)
    audit = json.loads((ROOT/'data/provenance/practice_audit.json').read_text(encoding='utf8'))
    index = json.loads((ROOT/'data/experiment_index.json').read_text(encoding='utf8'))
    assert len(audit['cases']) == len(index) == 927
    assert len({r['case_code'] for r in audit['cases']}) == 927
    requests = 0
    for r in audit['cases']:
        assert index[r['case_code']]['trace'] == r['trace']
        m = read_trace(ROOT/r['trace'])
        assert m['trace_sha256'] == r['trace_sha256']
        assert str(m['program_runtime_s']) == r['program_runtime_s']
        assert m['exit_virtual_s'] * 1000000 == r['virtual_time_us']
        assert m['accepted_requests'] == r['accepted_requests']
        requests += m['accepted_requests']
    frozen = {}
    for name in ('2026-09-13_official-ablation', '2026-09-13_official-sensitivity'):
        folder = ROOT/'data/experiments'/name
        manifest = json.loads((folder/'runtime_manifest.json').read_text(encoding='utf8'))
        for name_, sha in manifest.items():
            assert digest(folder/'package'/name_) == sha, name_
        frozen[name] = len(manifest)
    core = json.loads((ROOT/'data/provenance/formal2_core.json').read_text(encoding='utf8'))
    for row in core['unchanged_files']:
        assert digest(ROOT/'algorithms/q34'/row['file']) == row['sha256']
        for problem in (3, 4):
            assert digest(ROOT/f'data/formal/q{problem}/attempt2/package/B'/row['file']) == row['sha256']
    result = dict(complete=True, formal_records=6, primary_formal_index=2,
                  practice_cases=len(index), accepted_practice_requests=requests,
                  frozen_files=frozen, unchanged_formal2_core_files=len(core['unchanged_files']),
                  official_requests_sent=0, new_simulations=0)
    target = ROOT/'outputs/data_audit.json'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf8')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
