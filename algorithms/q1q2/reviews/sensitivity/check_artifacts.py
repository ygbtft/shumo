"""Read-only consistency checks over final sensitivity artifacts."""
import gzip
import hashlib
import json
from pathlib import Path
import sys

folder=Path(sys.argv[1]); checks=0; cases=[]
for path in folder.glob('*.json'):
    r=json.loads(path.read_text())
    if 'search' not in r:
        continue
    cases.append(path.stem)
    assert all(s['scanned']<=s['planned'] for s in r['scan'])
    for row in [r['fixed_old'],r['reselected'],*r['final_candidates']]:
        if row is None:
            continue
        if row['admissibility']['status']!='IN':
            assert row['score'] is None and row['clearance'] is None
        if row['score']:
            assert row['score']['J_hat']>=0
        checks+=1
    assert r['reselected'] is None or r['reselected']['admissibility']['status']=='IN'
    if path.stem.endswith('_S1'):
        assert r['source_set']['first']['half_width_deg']==r['config']['second_half_width_deg']==1.005
    if 'known_rho_' in path.stem:
        rho=float(path.stem.split('known_rho_')[1])
        assert r['source_set']['physics']['rho_lo']==r['source_set']['physics']['rho_hi']==rho
    if 'raw_search_archive' in r:
        archive=r['raw_search_archive']
        raw=gzip.decompress((folder/archive['path']).read_bytes())
        assert hashlib.sha256(raw).hexdigest()==archive['sha256_uncompressed']
    checks+=1
assert len(cases)==20
s2=json.loads((folder/'S2.json').read_text())
assert s2['shapes']['triangle']['R']>20>s2['shapes']['segment']['R']
assert not s2['shapes']['triangle']['single_clear_possible']
states={c['status'] for r in s2['rows'].values() for row in r['final_candidates'] for c in row['representative_feedbacks']}
assert {'ON_SITE','MOVE_TO_COVER_CENTER','NOT_YET_GUARANTEED'}<=states
s3=json.loads((folder/'S3_inconsistent.json').read_text())
assert s3['known_radius_models']['1000.0']['status']!='OK'
s8=json.loads((folder/'F11_S8.json').read_text())
assert s8['rows']['same_station_unbounded_control']['stages'][0]['kind']=='UNBOUNDED'
f9=json.loads((folder/'F9_shared.json').read_text())
assert f9['analytic_B10_standard_only']['lower_bound_m']==1000
for group in f9['groups'].values():
    previous=float('inf')
    for row in group['curve']:
        if row['reselected']:
            value=row['reselected']['score']['J_hat']
            assert value<=previous+.100001
            previous=value
            assert row['budget_m'] is None or row['reselected']['movement_m']<=row['budget_m']+1e-8
            checks+=1
manifest=json.loads((folder/'manifest.json').read_text())
root=Path(__file__).resolve().parents[2]
for name,digest in manifest['source_hashes'].items():
    assert hashlib.sha256((root/name).read_bytes()).hexdigest()==digest
    checks+=1
print(json.dumps(dict(status='PASS',case_count=len(cases),row_and_hash_checks=checks,
    all_three_conditional_states=sorted(states),archives='SHA256 verified',
    source_hashes='match run manifest'),ensure_ascii=False))
