"""Read-only peer audit; run with the q1q2 venv and -B. No official calls."""
import copy
import hashlib
import json
import sys
from pathlib import Path
import numpy as np

ROOT = Path('/Users/flower/math/2026/NTJ_B_wt/B')
sys.path.insert(0, str(ROOT))
from visibility_certificate import rectangle_certificate, verify_cells
from integer_visibility_certificate import certify_integer_stations, verify_integer_certificate
from icra_final_checks import partition_check
from negative_hull_policy import exclude_shadow
from negative_hull_experiments import contains
from geometry import hull
from service_aware_policy import service_route
from vector_service_policy import vector_service_route

result = {'python': sys.version, 'numpy': np.__version__, 'official_calls': 0}
names = ['negative_hull_policy.py', 'negative_hull_experiments.py',
         'visibility_certificate.py', 'integer_visibility_certificate.py',
         'layout_certificates.py', 'rotating_layout_policy.py',
         'reception_layout_experiments.py', 'visibility_layout_search.py',
         'vector_service_policy.py', 'interleaved_policy.py', 'bounded_width_policy.py']
result['read_source_sha256'] = {n: hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in names}
rounded = json.loads((ROOT/'experiments/runs/2026-09-11_rounded-cover21/certified_layouts.json').read_text())
closed = json.loads((ROOT/'experiments/runs/2026-09-11_closed-cover21/certified_layouts.json').read_text())
item = rounded['grid21_29']
p = np.asarray(item['points'])
cert = item['certificate']
result['grid21_29_stored'] = {**verify_cells(p, cert), **partition_check(cert)}
result['grid21_29_default_depth'] = rectangle_certificate(p, save_cells=False)
fresh = rectangle_certificate(p, max_depth=16)
assert fresh['covered']
result['grid21_29_fresh'] = {k:v for k,v in fresh.items() if k != 'cells'}
result['grid21_29_exact_fresh'] = verify_integer_certificate(p, certify_integer_stations(p))
c = closed['closed21_3']
result['closed21_3_stored'] = verify_integer_certificate(c['points'], c['certificate'])
damaged = copy.deepcopy(cert)
damaged['cells'] = damaged['cells'][:1]
result['incomplete_cells_local_check'] = verify_cells(p, damaged)
try:
    partition_check(damaged)
    raise RuntimeError('Partition checker missed deleted leaves')
except AssertionError:
    result['incomplete_cells_partition_rejected'] = True
result['empty_cells_local_check'] = verify_cells(p, {'cells': [], 'receive_radius':1000.})
p_bad = np.array([[1200.,0.],[1300.,0.],[1200.,100.]])
bad = rectangle_certificate(p_bad, arena_radius=500., receive_radius=2000., max_depth=0)
w = bad['witness']; g = np.array(w['position']); theta = np.deg2rad(w['direction_deg'])
actually_visible = (np.linalg.norm(p_bad-g,axis=1)<=2000)&((p_bad-g)@np.array([np.cos(theta),np.sin(theta)])>=0)
assert actually_visible.any()
result['wrong_radius_witness'] = {'returned':bad, 'actually_receiving_stations':np.flatnonzero(actually_visible).tolist()}
result['segment_midpoint_contains'] = bool(contains(np.array([[0.,0.],[2.,0.]]),np.array([1.,0.])))
assert not result['segment_midpoint_contains']

rng = np.random.default_rng(42)
shrunk = 0
for i in range(1000):
    g = rng.uniform(-1000,1000,2)
    n = np.array([np.cos(a:=rng.uniform(0,2*np.pi)), np.sin(a)])
    rho = rng.uniform(1000,1500)
    def receiving(q):
        d = q-g
        return np.linalg.norm(d)<=rho and (i%3==0 or n@d>=0)
    successful=[]
    while len(successful)<2:
        q = g+rng.uniform(-rho,rho,2)
        if receiving(q): successful.append(q)
    while True:
        q = g+rng.uniform(-1.5*rho,1.5*rho,2)
        if not receiving(q): break
    poly = hull(np.vstack([g,g+rng.normal(size=(12,2))*1000]))
    new = exclude_shadow(poly,q,*successful)
    edges=np.roll(new,-1,axis=0)-new
    delta=g-new
    assert len(new)>=3 and np.min((edges[:,0]*delta[:,1]-edges[:,1]*delta[:,0])/np.linalg.norm(edges,axis=1))>=-1e-6
    shrunk += new is not poly
result['independent_shadow_trials'] = {'passed':1000, 'changed_regions':shrunk}

t=np.tan(np.deg2rad(1.02))
for i in range(10000):
    x=rng.uniform(5,1500); y=rng.uniform(-t*x,t*x); length=rng.uniform(.001,x)
    k=rng.uniform(t,np.tan(np.deg2rad(30)))
    g=np.array([x,y]); q=np.array([[length,k*length],[length,-k*length]])
    assert np.all(np.sum((q-g)**2,axis=1)<=g@g+1e-7)
    a=rng.uniform(0,2*np.pi); n=np.array([np.cos(a),np.sin(a)])
    if n@(-g)<0: n=-n
    assert np.max((q-g)@n)>=-1e-8
result['wide_pair_trials'] = 10000
for i in range(200):
    n=int(rng.integers(2,22)); count=int(rng.integers(0,n+1))
    entries=rng.normal(size=(n,2))*1800; exits=rng.normal(size=(n,2))*1800
    current=rng.normal(size=2)*1000; precedence=rng.uniform(0,50,(n,n))
    for mode in ('free','locked'):
        a=service_route(entries,exits,current,precedence,count,mode)
        b=vector_service_route(entries,exits,current,precedence,count,mode)
        assert np.array_equal(a,b)
result['vector_scalar_route_pairs'] = 400
print(json.dumps(result,ensure_ascii=False,indent=2))
