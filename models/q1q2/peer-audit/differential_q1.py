"""Seeded Q1 differential audit. Only this directory is written; neither solver is truth.

Every WRONG is deletion-minimized preserving both side verdicts and failed fields.
The minimized corpus contains every failing case, not just selected examples.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
from dataclasses import asdict
from fractions import Fraction as F
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import random
import sys
import time
import numpy as np

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
from models.q1q2 import geometry as ours_g, circle as ours_c

def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m

# Reuse its native mixed-width adapter and serialization; never its PASS/FAIL judge.
adapter = module('peer_adapter_q1', HERE / 'benchmark_peer.py')
peer = adapter.peer
go = adapter.ORACLES['q1_geometry']
co = adapter.ORACLES['q1_circle_cover']
policy = ours_g.NumericPolicy()
MAPPING = dict(empty='EMPTY', unbounded='UNBOUNDED', point='POINT', segment='SEGMENT', bounded='POLYGON', numerically_unresolved='UNRESOLVED')
CATEGORIES = ['BOTH_OK','BOTH_OK_DIFF_REPR','OURS_WRONG','THEIRS_WRONG','BOTH_WRONG','BOTH_UNRESOLVED','OURS_UNRESOLVED_THEIRS_OK','OURS_OK_THEIRS_UNRESOLVED','API_UNPROVIDED']

def clean(x):
    if isinstance(x, F): return str(x)
    return adapter.clean(x)

def dumps(x):
    return json.dumps(clean(x), ensure_ascii=False, allow_nan=False, sort_keys=True)

def exact_region(rows):
    # Same independent generator's exact core. Omit only its diagnostic HiGHS
    # run: an approximate LP is neither needed nor used as the judge.
    p = go.feasible(rows)
    gt = dict(kind='EMPTY', vertices=[], diameter=None, diameter_squared=None, feasible_point=go.encode(p), recession_direction=None)
    if p is None: return gt
    r = go.recession(rows)
    if r is not None:
        gt.update(kind='UNBOUNDED', recession_direction=go.encode(r))
        return gt
    vertices = set()
    from itertools import combinations
    for a,b in combinations(rows,2):
        d = go.det(a,b)
        if not d: continue
        q = ((a[2]*b[1]-a[1]*b[2])/d, (a[0]*b[2]-a[2]*b[0])/d)
        if all(x*q[0]+y*q[1] <= z for x,y,z in rows): vertices.add(q)
    v = go.hull(vertices)
    assert v
    gt.update(go.vertex_truth(v))
    gt['kind'] = 'POINT' if len(v)==1 else 'SEGMENT' if len(v)==2 else 'POLYGON'
    return gt

def length_tols(gt, coordinates, circle=False):
    d = gt['diameter'] or 0.
    coords = [float(F(x)) for p in coordinates for x in p]
    ulp = max((math.ulp(x) for x in coords),default=math.ulp(0.))
    return (1e-9*d + 32*ulp, (2e-9+2e-10*d+8*ulp) if circle else (1e-8+1e-9*d+32*ulp))

def near(a,b,tol):
    return a is not None and math.isfinite(a) and abs(a-b)<=tol

def circle_checks(a,gt,pts,tol):
    center,radius = a.get('center'),a.get('radius')
    center_ok = center is not None and len(center)==2 and all(near(x,y,tol) for x,y in zip(center,gt['center']))
    residual = max((math.dist(center,p)-radius for p in pts), default=0.) if center is not None and radius is not None else math.inf
    return dict(center=center_ok,radius=near(radius,gt['radius'],tol),containment=math.isfinite(residual) and residual<=tol), residual

def region_checks(a,gt,tol):
    checks = dict(kind=a.get('kind')==gt['kind'])
    if gt['kind']=='EMPTY': checks['diameter']=a.get('diameter') is None
    elif gt['kind']=='UNBOUNDED': checks['diameter']=a.get('diameter')==math.inf
    else:
        checks['diameter']=near(a.get('diameter'),gt['diameter'],tol)
        v=adapter.vertex_check(a.get('vertices',[]),gt['vertices'],tol)
        checks['vertices']=v['geometry_match']
    return checks

def state(a,checks):
    if a.get('status')=='API_UNPROVIDED': return 'API_UNPROVIDED'
    if a.get('status') in ('NUMERICAL_UNRESOLVED','UNRESOLVED','numerically_unresolved'): return 'UNRESOLVED'
    if a.get('exception'): return 'ERROR'
    return 'OK' if all(checks.values()) else 'WRONG'

def category(o,t,repr_diff=False):
    if o in ('WRONG','ERROR') and t in ('WRONG','ERROR'): return 'BOTH_WRONG'
    if o in ('WRONG','ERROR'): return 'OURS_WRONG'
    if t in ('WRONG','ERROR'): return 'THEIRS_WRONG'
    if 'API_UNPROVIDED' in (o,t): return 'API_UNPROVIDED'
    if o==t=='UNRESOLVED': return 'BOTH_UNRESOLVED'
    if o=='UNRESOLVED': return 'OURS_UNRESOLVED_THEIRS_OK'
    if t=='UNRESOLVED': return 'OURS_OK_THEIRS_UNRESOLVED'
    return 'BOTH_OK_DIFF_REPR' if repr_diff else 'BOTH_OK'

def attempt(fn):
    try: return fn()
    except Exception as e: return dict(status='ERROR',exception=repr(e))

def evaluate(case):
    inp=case['input']; typ=case['type']
    if typ=='geometry':
        if 'observations' in inp: rows=go.observation_rows(inp['observations'])
        elif 'halfplanes' in inp: rows=[tuple(F(x) for x in r) for r in inp['halfplanes']]
        else: rows=None
        if rows is None:
            gt=go.vertex_truth(go.hull([tuple(F(x) for x in p) for p in inp['points']]))
            gt['kind']='POINT' if len(gt['vertices'])==1 else 'SEGMENT' if len(gt['vertices'])==2 else 'POLYGON'
        else: gt=exact_region(rows)
        def ours():
            if rows is None:
                v=ours_g.convex_hull(inp['points'],policy)
                reg=ours_g.Region(ours_g.RegionKind.POINT if len(v)==1 else ours_g.RegionKind.SEGMENT if len(v)==2 else ours_g.RegionKind.POLYGON,v)
            else:
                hp=[h for o in inp['observations'] for h in ours_g.wedge_halfplanes(ours_g.BearingMeasurement(**o))] if 'observations' in inp else [ours_g.HalfPlane(tuple(r[:2]),r[2]) for r in inp['halfplanes']]
                reg=ours_g.intersect_halfplanes(hp,policy)
            d=ours_g.diameter(reg)
            return dict(status=reg.status,kind=reg.kind.value if reg.kind else None,vertices=reg.vertices,diameter=d.length,region=asdict(reg),diameter_result=asdict(d))
        def theirs():
            if any(o['half_width_deg']>=90 for o in inp.get('observations',[])): return dict(status='API_UNPROVIDED')
            if rows is None:
                v=peer.hull(inp['points']);d,p=peer.diameter(v)
                ans=dict(status='point' if len(v)==1 else 'segment' if len(v)==2 else 'bounded',vertices=v,diameter=d,diameter_endpoints=p)
            elif 'observations' in inp: ans=adapter.bearings(inp['observations'])
            else:
                ab=np.asarray(inp['halfplanes'],float).reshape(-1,3)
                ans=peer.halfplane_region(ab[:,:2],ab[:,2])
            return dict(ans,kind=MAPPING[ans['status']])
        o,t=attempt(ours),attempt(theirs)
        coords=inp.get('points', [x['position'] for x in inp.get('observations',[])])+[[float(F(x)) for x in p] for p in gt['vertices']]
        strict,baseline=length_tols(gt,coords)
        oc,tc=region_checks(o,gt,strict),region_checks(t,gt,strict)
        ob,tb=region_checks(o,gt,baseline),region_checks(t,gt,baseline)
        repr_diff=False;repr_detail=None
        if state(o,oc)==state(t,tc)=='OK' and gt['vertices']:
            av,bv=o['vertices'],t['vertices']
            ordered=len(av)==len(bv) and all(math.dist(a,b)<=strict for a,b in zip(av,bv))
            repr_diff=not ordered
            repr_detail=dict(ours_count=len(av),theirs_count=len(bv),ordered_match=ordered,count_difference=len(av)!=len(bv))
        baseline_repr_diff=False
        if state(o,ob)==state(t,tb)=='OK' and gt['vertices']:
            av,bv=o['vertices'],t['vertices']
            baseline_repr_diff=len(av)!=len(bv) or not all(math.dist(a,b)<=baseline for a,b in zip(av,bv))
        extra={}
        # End-to-end MEC on each bounded common region: the oracle's exact
        # rational vertices go only to the oracle, never to either solver.
        if gt['vertices'] and t.get('status')!='API_UNPROVIDED':
            cgt=co.oracle([[F(x) for x in v] for v in gt['vertices']])
            ov=o.get('vertices',[]);tv=t.get('vertices',[])
            om=attempt(lambda:asdict(ours_c.minimum_circle(ov, 0))) if o.get('status')=='OK' and len(ov) else dict(status=o.get('status'),center=None,radius=None)
            if t.get('status')=='numerically_unresolved':tm=dict(status='UNRESOLVED')
            elif 'center' in t:tm=dict(status=t['status'],center=t['center'],radius=t.get('radius'))
            elif len(tv):
                def tmc():
                    center,radius=peer.minimum_circle(tv)
                    return dict(status='OK',center=center,radius=radius)
                tm=attempt(tmc)
            else:tm=dict(status=t.get('status'),center=None,radius=None)
            truth_points=[[float(F(x)) for x in v] for v in gt['vertices']]
            opc,opr=circle_checks(om,cgt,truth_points,strict);tpc,tpr=circle_checks(tm,cgt,truth_points,strict)
            opb,_=circle_checks(om,cgt,truth_points,baseline);tpb,_=circle_checks(tm,cgt,truth_points,baseline)
            extra['pipeline_circle']=dict(oracle=cgt,ours=om,theirs=tm,checks=dict(ours=opc,theirs=tpc),side_states=dict(ours=state(om,opc),theirs=state(tm,tpc)),category=category(state(om,opc),state(tm,tpc)),baseline_category=category(state(om,opb),state(tm,tpb)),containment_residual=dict(ours=opr,theirs=tpr))
    else:
        pts=inp['points'];gt=co.oracle(pts)
        o=attempt(lambda:asdict(ours_c.minimum_circle(pts, case.get('circle_seed',0))))
        def theirs():
            center,radius=peer.minimum_circle(np.asarray(pts,float))
            return dict(status='OK',center=center,radius=radius)
        t=attempt(theirs)
        strict,baseline=length_tols(gt,pts,True)
        oc,ores=circle_checks(o,gt,pts,strict);tc,tres=circle_checks(t,gt,pts,strict)
        ob,_=circle_checks(o,gt,pts,baseline);tb,_=circle_checks(t,gt,pts,baseline)
        # Independent point-cloud diameter test; hull receives original input,
        # no oracle vertices are fed into either production algorithm.
        def odia():
            v=ours_g.convex_hull(pts,policy)
            reg=ours_g.Region(ours_g.RegionKind.POINT if len(v)==1 else ours_g.RegionKind.SEGMENT if len(v)==2 else ours_g.RegionKind.POLYGON,v)
            return asdict(ours_g.diameter(reg))
        od=attempt(odia);td=attempt(lambda:dict(length=peer.diameter(np.asarray(pts))[0]))
        extra=dict(containment_residual=dict(ours=ores,theirs=tres),isolated_diameter=dict(ours=od,theirs=td,ours_ok=near(od.get('length'),gt['diameter'],strict),theirs_ok=near(td.get('length'),gt['diameter'],strict)))
        # Isolate coverage from diameter failure: oracle independently selects
        # a farthest pair on the original cloud, as the existing cover runner.
        i,j=gt['pair'];d=ours_g.DiameterResult(gt['diameter'],gt['diameter_squared'],(tuple(pts[i]),tuple(pts[j])),(i,j))
        reg=ours_g.Region(ours_g.RegionKind.POINT if gt['diameter']==0 else ours_g.RegionKind.POLYGON,tuple(map(tuple,pts)))
        cov=attempt(lambda:asdict(ours_c.diameter_circle_cover(reg, d, policy, ours_c.minimum_circle(reg.vertices, seed=0))))
        cov_checks=dict(status=cov.get('status') in gt['allowed_cover_status'])
        for k in ('kappa','eta'):
            val=cov.get(k);expected=gt[k]
            cov_checks[k]=(val is None) if expected is None else (val is None and k=='kappa') or near(val,expected,2e-8)
        extra['coverage']=dict(ours=cov,theirs='API_UNPROVIDED',checks=cov_checks,unresolved=cov.get('status')=='UNRESOLVED',kappa_unavailable=cov.get('kappa') is None and gt['kappa'] is not None)
        repr_diff=False;repr_detail=None;baseline_repr_diff=False
    os,ts=state(o,oc),state(t,tc)
    return dict(case_id=case['case_id'],type=typ,family=case['family'],input=inp,circle_seed=case.get('circle_seed',0),oracle=gt,ours=o,theirs=t,checks=dict(ours=oc,theirs=tc),side_states=dict(ours=os,theirs=ts),baseline_side_states=dict(ours=state(o,ob),theirs=state(t,tb)),baseline_checks=dict(ours=ob,theirs=tb),category=category(os,ts,repr_diff),baseline_category=category(state(o,ob),state(t,tb),baseline_repr_diff),tolerance=dict(strict=strict,baseline=baseline),representation=repr_detail,**extra)

def obs(x,y,t,e): return dict(position=[x,y],bearing_deg=t,half_width_deg=e)

def generate(seed,n):
    rng=random.Random(seed)
    for i in range(n):
        s=rng.choice([1e-12,1e-9,1e-7,1e-4,1.,100.,1e6,1e9])
        family=i%10
        if i%2==0:
            # alternate observations and rational/binary64 halfplanes
            k=(i//2)%10
            if k<7:
                if k==0:
                    oo=[obs(rng.uniform(-s,s),rng.uniform(-s,s),rng.uniform(-720,720),rng.choice([0.,1e-12,1.,30.,89.999999])) for _ in range(rng.randint(1,8))];name='random_angles'
                elif k==1:
                    target=[rng.uniform(-s,s),rng.uniform(-s,s)];oo=[]
                    for _ in range(rng.randint(2,8)):
                        x,y=rng.uniform(-10*s,10*s),rng.uniform(-10*s,10*s);e=rng.choice([.001,1.,10.,45.])
                        oo.append(obs(x,y,math.degrees(math.atan2(target[1]-y,target[0]-x))+rng.uniform(-.8,.8)*e,e))
                    name='target_consistent'
                elif k==2:
                    a=rng.randint(1,9)*s;e=rng.choice([0.,1e-14,1e-10,1.,45.]);oo=[obs(0,0,0,e),obs(a,0,180,e)];name='facing_collinear'
                elif k==3:
                    gap=rng.choice([1e-14,1e-12,1e-10,1e-8])*s;oo=[obs(0,0,180,rng.choice([0.,1.,45.])),obs(gap,0,0,rng.choice([0.,1.,45.]))];name='away_tiny_gap'
                elif k==4:
                    e=rng.choice([1e-14,1e-12,1e-10,1e-6]);oo=[obs(-s,0,0,e),obs(0,-s,90,e)];name='near_parallel_bearings'
                elif k==5:
                    t=rng.choice([-720.1,-.1,0.,359.9,360.,719.9]);oo=[obs(-s,0,t,1.),obs(0,-s,90,1.)];name='cross_zero'
                else:
                    a=rng.randint(1,8)*s;b=rng.randint(1,8)*s
                    oo=rng.choice([[obs(0,b,0,0),obs(a,0,90,0)],[obs(-a,-b,45,45),obs(a,b,225,45)],[obs(0,0,0,90),obs(s,0,180,90)]])
                    name='point_square_halfplane'
                if rng.random()<.2:oo+=oo[:1]
                rng.shuffle(oo);inp=dict(observations=oo)
            else:
                delta=rng.choice([1e-14,1e-12,1e-10,1e-8,1e-4])
                if k==7:rr=[[1.,0.,0.],[-1.,0.,-delta*s]];name='halfplane_tiny_gap'
                elif k==8:rr=[[0.,-1.,0.],[-delta,1.,0.],[delta,1.,s]];name='halfplane_long_triangle'
                else:
                    w=rng.choice([0.,delta*s,s]);h=rng.choice([0.,delta*s,s]);x=rng.randint(-3,3)*s;y=rng.randint(-3,3)*s
                    rr=[[1.,0.,x+w],[-1.,0.,-x],[0.,1.,y+h],[0.,-1.,-y]];name='halfplane_rectangle_degenerate'
                if rng.random()<.2:rr+=rr[:1]
                rng.shuffle(rr);inp=dict(halfplanes=rr)
            yield dict(case_id=f'random_g_{i:05d}',type='geometry',family=name,input=inp)
        else:
            k=(i//2)%8;npts=rng.randint(1,10)
            if k==0:pts=[[rng.uniform(-s,s),rng.uniform(-s,s)] for _ in range(npts)];name='cloud'
            elif k==1:pts=[[rng.uniform(-s,s),0.] for _ in range(npts)];name='collinear'
            elif k==2:pts=[[rng.uniform(-s,s),rng.uniform(-s,s)*rng.choice([1e-14,1e-10,1e-6])] for _ in range(npts)];name='near_collinear'
            elif k==3:pts=[[0.,0.],[s,0.],[s/2,math.sqrt(3)*s/2]];name='equilateral_all_scales'
            elif k==4:pts=[[0.,0.],[s,0.],[rng.random()*s,rng.choice([1e-14,1e-10,.5])*s]];name='tiny_triangle'
            elif k==5:pts=[[0.,0.],[s,0.]];name='segment_all_scales'
            elif k==6:
                shift=rng.choice([1e6,1e9,1e12]);pts=[[shift+rng.randint(-4,4)*s,-shift+rng.randint(-4,4)*s] for _ in range(npts)];name='large_translation'
            else:pts=[[rng.randint(-3,3)*s,rng.randint(-3,3)*s] for _ in range(npts)];name='duplicate_grid'
            if rng.random()<.5:pts+=pts[:rng.randint(1,3)]
            rng.shuffle(pts)
            yield dict(case_id=f'random_c_{i:05d}',type='circle',family=name,input=dict(points=pts),circle_seed=rng.randrange(2**32))

def fixtures():
    for typ,area in [('geometry','q1_geometry'),('circle','q1_circle_cover')]:
        for c in map(json.loads,(HERE.parent/'benchmarks'/area/'cases.jsonl').read_text().splitlines()):
            raw=c['input'];inp={}
            for key in ['points','halfplanes','observations']:
                if key in raw:inp[key]=raw[key] if key=='observations' else [[float(F(x)) for x in p] for p in raw[key]]
            if not inp: continue
            yield dict(case_id='fixture_'+typ+'_'+c['case_id'],type=typ,family='fixture',input=inp,circle_seed=0)

def signature(r):
    return (r['type'],r['category'],tuple(r['side_states'].values()),r['oracle'].get('kind'),r['ours'].get('kind'),r['theirs'].get('kind'),tuple(k for k,v in r['checks']['ours'].items() if not v),tuple(k for k,v in r['checks']['theirs'].items() if not v))

def shrink(r, sigfn=signature):
    original=r;case={k:r[k] for k in ['case_id','type','family','input','circle_seed']}
    key=next(iter(case['input']));values=list(case['input'][key]);sig=sigfn(r);calls=0
    changed=True
    while changed:
        changed=False
        for i in range(len(values)):
            if key=='points' and len(values)<=1:break
            small=values[:i]+values[i+1:]
            trial=dict(case,input={key:small})
            result=evaluate(trial);calls+=1
            if sigfn(result)==sig:
                values=small;r=result;changed=True;break
    # Exhaustive final one-element deletion validation is contained in the last
    # no-change pass. This is 1-minimal, not a claim of global numeric minimality.
    return dict(original_case_id=original['case_id'],original_size=len(case['input'][key]),minimal_size=len(values),minimality='1-minimal under deleting one observation/halfplane/point; failure signature preserved; coordinates not optimized',evaluations=calls,result=r)

def auxiliary_signature(r):
    if r['type']=='geometry':
        p=r.get('pipeline_circle')
        if p is None:return None
        return ('pipeline',p['category'],tuple(p['side_states'].values()),tuple(k for k,v in p['checks']['ours'].items() if not v),tuple(k for k,v in p['checks']['theirs'].items() if not v))
    c=r['coverage'];d=r['isolated_diameter']
    return ('circle_aux',tuple(k for k,v in c['checks'].items() if not v),d['ours_ok'],d['theirs_ok'])

def auxiliary_wrong(r):
    if r['type']=='geometry':return 'WRONG' in r.get('pipeline_circle',{}).get('category','')
    return not all(r['coverage']['checks'].values()) or not r['isolated_diameter']['ours_ok'] or not r['isolated_diameter']['theirs_ok']

def self_checks():
    assert exact_region([(F(1),F(0),F(0)),(F(-1),F(0),F(-1,10**14))])['kind']=='EMPTY'
    assert exact_region([])['kind']=='UNBOUNDED'
    gt=co.oracle([[0.,0.],[1e-12,0.]])
    tol,_=length_tols(gt,[[0.,0.],[1e-12,0.]],True)
    assert not all(circle_checks(dict(center=[0.,0.],radius=0.),gt,[[0.,0.],[1e-12,0.]],tol)[0].values())
    assert category('UNRESOLVED','WRONG')=='THEIRS_WRONG'
    assert category('WRONG','UNRESOLVED')=='OURS_WRONG'
    assert category('UNRESOLVED','UNRESOLVED')=='BOTH_UNRESOLVED'
    assert category('OK','OK',True)=='BOTH_OK_DIFF_REPR'
    # Wrapper's exact core must agree with the unmodified generator oracle.
    for rows in [[],[(F(1),F(0),F(0)),(F(-1),F(0),F(-1,10**14))],[(F(1),F(0),F(1)),(F(-1),F(0),F(0)),(F(0),F(1),F(1)),(F(0),F(-1),F(0))]]:
        a,b=exact_region(rows),go.oracle(rows)
        assert all(a[k]==b[k] for k in a)


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--seed',type=int,default=2026091107)
    ap.add_argument('--random-cases',type=int,default=8000)
    ap.add_argument('--replay',help='case id from results, or counterexample original_case_id')
    ap.add_argument('--auxiliary',action='store_true',help='replay minimized auxiliary failure')
    ap.add_argument('--minimal',action='store_true',help='replay minimized input')
    args=ap.parse_args()
    if args.replay:
        path=HERE/('differential-q1-aux-counterexamples.jsonl' if args.auxiliary else 'differential-q1-counterexamples.jsonl' if args.minimal else 'differential-q1-results.jsonl')
        for line in path.open():
            r=json.loads(line);r=r['result'] if args.minimal or args.auxiliary else r
            if r['case_id']==args.replay:
                print(dumps(evaluate(r)));return
        raise SystemExit('case not found')
    before=adapter.protected_hashes();started=time.monotonic();self_checks()
    rows=[];seen_ids=set()
    with (HERE/'differential-q1-results.jsonl').open('w') as f:
        for case in list(fixtures())+list(generate(args.seed,args.random_cases)):
            assert case['case_id'] not in seen_ids, 'duplicate case id'
            seen_ids.add(case['case_id'])
            r=evaluate(case);rows.append(r);f.write(dumps(r)+'\n')
            if len(rows)%200==0:print('evaluated',len(rows),dict(Counter(x['category'] for x in rows)),'seconds',round(time.monotonic()-started),flush=True)
    wrong=[r for r in rows if 'WRONG' in r['category']]
    minimized=[]
    with (HERE/'differential-q1-counterexamples.jsonl').open('w') as f:
        for r in wrong:
            m=shrink(r);minimized.append(m);f.write(dumps(m)+'\n')
            if len(minimized)%100==0:print('minimized',len(minimized),'/',len(wrong),'seconds',round(time.monotonic()-started),flush=True)
    auxmins=[]
    with (HERE/'differential-q1-aux-counterexamples.jsonl').open('w') as f:
        for r in rows:
            if auxiliary_wrong(r):
                m=shrink(r,auxiliary_signature);auxmins.append(m);f.write(dumps(m)+'\n')
                if len(auxmins)%100==0:print('aux minimized',len(auxmins),'seconds',round(time.monotonic()-started),flush=True)
    after=adapter.protected_hashes()
    summary=dict(script_sha256=adapter.sha(Path(__file__)),environment=dict(python=sys.version,numpy=np.__version__,scipy=adapter.scipy.__version__,ours_geometry=ours_g.__file__,ours_circle=ours_c.__file__,peer_geometry=peer.__file__),auxiliary_wrong_inputs=len(auxmins),main_wrong_inputs=len(minimized),seed=args.seed,random_cases=args.random_cases,total=len(rows),seconds=time.monotonic()-started,counts=dict(Counter(r['category'] for r in rows)),baseline_counts=dict(Counter(r['baseline_category'] for r in rows)),source_hashes_before=before,source_hashes_after=after,sources_unchanged=before==after,command=sys.argv)
    (HERE/'differential-q1-summary.json').write_text(dumps(summary)+'\n')
    write_report(rows,minimized,summary,auxmins)
    assert before==after,'source changed during audit'
    print(dumps({k:v for k,v in summary.items() if not k.startswith('source')}),flush=True)


def write_report(rows,mins,s,auxmins):
    ow=sum(r['side_states']['ours']=='WRONG' for r in rows);tw=sum(r['side_states']['theirs']=='WRONG' for r in rows)
    obw=sum(r['baseline_side_states']['ours']=='WRONG' for r in rows);tbw=sum(r['baseline_side_states']['theirs']=='WRONG' for r in rows)
    lines=['# Q1 独立精确 oracle 随机对拍', '',f'结论：严格尺度口径下，我方 **{ow}** 个、同学 **{tw}** 个错误确定答案；按原 benchmark 容差仍有 **{obw} / {tbw}** 个错误。两方均不能确认全域正确，我方也存在返回 OK 的退化错误。错误实例数包含重复机制与尺度变体，不等于独立 bug 数。','',f"种子 `{s['seed']}`；随机 {s['random_cases']} 例，加现有 Q1 几何/点集夹具 {len(rows)-s['random_cases']} 例，共 **{len(rows)}** 例。耗时 {s['seconds']:.1f} 秒。两方源码与原基准文件执行前后 SHA256 {'全部一致' if s['sources_unchanged'] else '发生变化，请查看摘要'}。",'',
    '真值仅来自两个 generate.py 的 Fraction 精确消元、衰退判断、交点、Jarvis 凸包、全对平方直径和 1/2/3 点支撑最小圆枚举；没有调用任何一方作为裁判。几何包装仅省略生成器附加的 HiGHS 诊断，其精确核心在启动自检中与原 oracle 对照。', '',
    '观测输入沿用 oracle 的十进制字符串解释、80 位计算后保留 65 位有理三角系数；因此是该有理近似系统的精确真值，并非超越数的符号证明。半平面和圆点集先提交 binary64，再以 Fraction 精确解释同一输入；丢失于输入浮点舍入之前的几何特征不计错。', '',
    '共同契约：区域类别严格相等，有限区域顶点集 Hausdorff 距离与直径；独立点集最小圆检查圆心、半径、包含。主分类使用 `1e-9 D + 32 max ulp(坐标)` 长度容差，无固定米级下限。几何坐标取检测点与 oracle 顶点，圆取输入点。另列旧 benchmark 容差（几何 `1e-8 + 1e-9 D + 32 ulp`；圆 `2e-9 + 2e-10 D + 8 ulp`）。两者都是数值正确性标准，不要求浮点结果逐位等于有理真值。', '',
    '明确返回 UNRESOLVED 的结果不因缺失数值计错；确定状态 OK/类别但超差才计 WRONG。运行异常单列 ERROR，归入失败而不冒充诚实未决。错误优先于另一方未决/API 缺失；所以还列各方状态独立计数，防止类别掩盖未解出。', '',
    '| 分类 | 几何 | 最小圆 | 合计 | 原 benchmark 容差合计 |','|---|---:|---:|---:|---:|']
    for cat in CATEGORIES:
        lines.append(f"| {cat} | {sum(r['category']==cat and r['type']=='geometry' for r in rows)} | {sum(r['category']==cat and r['type']=='circle' for r in rows)} | {s['counts'].get(cat,0)} | {s['baseline_counts'].get(cat,0)} |")
    lines+=['','| 各方状态（主容差） | 我方 | 同学 |','|---|---:|---:|']
    for st in ['OK','WRONG','UNRESOLVED','API_UNPROVIDED','ERROR']:
        lines.append(f"| {st} | {sum(r['side_states']['ours']==st for r in rows)} | {sum(r['side_states']['theirs']==st for r in rows)} |")
    lines+=['','| 输入族 | 数量 | 我方 WRONG | 同学 WRONG | 我方未决 | 同学未决 |','|---|---:|---:|---:|---:|---:|']
    for family in sorted(set(r['family'] for r in rows)):
        rr=[r for r in rows if r['family']==family]
        lines.append(f"| {family} | {len(rr)} | {sum(r['side_states']['ours']=='WRONG' for r in rr)} | {sum(r['side_states']['theirs']=='WRONG' for r in rr)} | {sum(r['side_states']['ours']=='UNRESOLVED' for r in rr)} | {sum(r['side_states']['theirs']=='UNRESOLVED' for r in rr)} |")
    fixed=[r for r in rows if r['family']=='fixture' and r['type']=='geometry' and r['baseline_side_states']['theirs']=='WRONG']
    lines+=['',f"原 benchmark 中同学的 11 个几何失败，本轮按原容差复现 {len(fixed)} 个："+', '.join('`'+r['case_id']+'`' for r in fixed)+'。','',
        '主表的独立最小圆在原容差下：'+dumps(Counter(r['baseline_side_states']['ours'] for r in rows if r['type']=='circle'))+'（我方），'+dumps(Counter(r['baseline_side_states']['theirs'] for r in rows if r['type']=='circle'))+'（同学）。严格口径与原容差是不同验收标准，不能省略容差直接宣称同等数量的任务级错误。', '']
    lines+=['','**区域覆盖与表示差异**','']
    lines.append('几何 oracle 类别计数：`'+dumps(Counter(r['oracle']['kind'] for r in rows if r['type']=='geometry'))+'`。')
    reprs=[r for r in rows if r['category']=='BOTH_OK_DIFF_REPR']
    lines.append(f"双方都正确但顶点表示不同 {len(reprs)} 例，其中顶点数不同 {sum(r['representation']['count_difference'] for r in reprs)} 例，其余为定序不同；浮点尾数差别在逐顶点容差内不另计表示分歧。")
    circles=[r for r in rows if r['type']=='circle']
    lines+=['','**附加直径、覆盖与 API 差异**','',f"原始圆点集另做独立直径检查：我方 {sum(r['isolated_diameter']['ours_ok'] for r in circles)}/{len(circles)}、同学 {sum(r['isolated_diameter']['theirs_ok'] for r in circles)}/{len(circles)} 通过。这是附加子程序指标，不重复计入 MEC 主分类。",'',
    f"覆盖/κ/η 在全部 {len(circles)} 个圆点集上测试我方；同学均为 API_UNPROVIDED，不算其错。覆盖单测由独立 oracle 选定原点集中的最远对，隔离上游直径误差，未把 oracle MEC 输出灌入实现。我方覆盖状态不符合原生成器允许集合 {sum(not r['coverage']['checks']['status'] for r in circles)} 例；κ 超差 {sum(not r['coverage']['checks']['kappa'] for r in circles)} 例；η 超差 {sum(not r['coverage']['checks']['eta'] for r in circles)} 例；覆盖 UNRESOLVED {sum(r['coverage']['unresolved'] for r in circles)} 例，κ 未提供 {sum(r['coverage']['kappa_unavailable'] for r in circles)} 例。比例容差 2e-8；κ 缺失作为未决单列，不按正确数值通过。",'',
    'ε=90° 的测向输入是同学明确不支持的 API，单列未提供；混合半宽使用其 bearing_planes + halfplane_region，统一半宽使用 solve_bearings 并显式传半宽。支撑索引、κη、正式覆盖布尔值等缺失不通过合成结果伪装为同学 API。', '',
    '**WRONG 完整清单与缩减反例**','',
    f"共 {len(mins)} 个 WRONG 输入，均已逐一缩减并重新三方运行。完整最小输入、三方输出、精确 oracle 证据、失败字段存于 [逐例最小反例](differential-q1-counterexamples.jsonl)，原输入与结果在 [全部结果](differential-q1-results.jsonl)。每例的最后一轮逐元素删除均不再保持原分歧签名，故为删除意义下 1-minimal；不是全局最少约束证明，也未声称坐标数值已最简。",'',
    '为避免数千段重复输出淹没定位信息，下表按“类型/双方状态/真类别/返回类别/失败字段”分组，展示每组最短代表；下方两份逐例索引列出全部 WRONG 的 ID，JSONL 提供各自完整最小输入。','']
    groups=defaultdict(list)
    for m in mins:groups[signature(m['result'])].append(m)
    for idx,(sig,mm) in enumerate(sorted(groups.items(),key=lambda kv:str(kv[0])),1):
        m=min(mm,key=lambda x:(x['minimal_size'],len(dumps(x['result']['input']))));r=m['result']
        lines += [f"**反例组 {idx}：{r['category']} / {r['type']}（{len(mm)} 例）**",'',f"代表 `{r['case_id']}`，{m['original_size']} → {m['minimal_size']} 个元素。",'','```json',dumps(dict(input=r['input'],circle_seed=r['circle_seed'])),'```','',
        '三方关键输出：','', '```json',dumps(dict(oracle={k:v for k,v in r['oracle'].items() if k in ['kind','diameter','diameter_squared','center','radius','radius_squared_exact','vertices','feasible_point','recession_direction']},ours={k:v for k,v in r['ours'].items() if k in ['status','kind','vertices','diameter','center','radius','exception']},theirs={k:v for k,v in r['theirs'].items() if k in ['status','kind','vertices','diameter','center','radius','exception']},side_states=r['side_states'],checks=r['checks'],tolerance=r['tolerance'])),'```','']
    def short_output(r,side):
        a=r['oracle'] if side=='oracle' else r[side]
        if r['type']=='geometry':return dumps({k:a[k] for k in ['status','kind','diameter'] if k in a})
        return dumps({k:a[k] for k in ['status','center','radius'] if k in a})
    for side,label in [('ours','我方'),('theirs','同学')]:
        rr=[m for m in mins if m['result']['side_states'][side] in ('WRONG','ERROR')]
        lines += [f'**{label} WRONG 全量索引（{len(rr)}）**','', '每个 ID 对应 JSONL 同名记录；括号为缩减后元素数。','', '<details><summary>展开每例最小输入与三方关键输出</summary>','',
            '| ID / 元素数 | 删除最小输入 | Oracle | 我方 | 同学 |','|---|---|---|---|---|']
        for m in rr:
            r=m['result']
            lines.append(f"| `{r['case_id']}` / {m['minimal_size']} | `{dumps(r['input'])}` | `{short_output(r,'oracle')}` | `{short_output(r,'ours')}` | `{short_output(r,'theirs')}` |")
        lines+=['','</details>','']
    lines += ['**附加接口/流水线失败的完整反例**','',
        f'附加测试中 {len(auxmins)} 个输入失败（与主表有重叠，不相加）；各自删除最小反例、原始 ID 与三方输出在 [附加反例 JSONL](differential-q1-aux-counterexamples.jsonl)。覆盖接口的同学输出始终是 API_UNPROVIDED。', '']
    pipeline=[r for r in rows if 'pipeline_circle' in r]
    lines += [f"有界且双方支持的 {len(pipeline)} 个区域，还对端到端 MEC 作了独立检查：我方仅将自己的区域顶点传给自己的 minimum_circle；同学使用 halfplane_region 原生圆输出（孤立点云使用其 hull + minimum_circle）；真值圆对 oracle 的 Fraction 顶点枚举。两方从未收到 oracle 顶点。上游诚实未决继续传播为未决；类别错误的确定输出不会被改写为未决。", '',
        '严格流水线分类：`'+dumps(Counter(r['pipeline_circle']['category'] for r in pipeline))+'`。',
        '原 benchmark 几何长度容差流水线分类：`'+dumps(Counter(r['pipeline_circle']['baseline_category'] for r in pipeline))+'`。','']
    ag=defaultdict(list)
    for m in auxmins:ag[auxiliary_signature(m['result'])].append(m)
    for idx,(sig,mm) in enumerate(sorted(ag.items(),key=lambda kv:str(kv[0])),1):
        m=min(mm,key=lambda m:(m['minimal_size'],len(dumps(m['result']['input']))));r=m['result']
        evidence=r.get('pipeline_circle',dict(oracle=r['oracle'],coverage=r.get('coverage'),isolated_diameter=r.get('isolated_diameter')))
        lines += [f"附加反例组 {idx}（{len(mm)} 例），代表 `{r['case_id']}`：",'', '```json',dumps(dict(input=r['input'],circle_seed=r['circle_seed'],evidence=evidence)),'```','']
    lines += ['附加失败全量索引（完整三方数值见附加 JSONL）：','', '<details><summary>展开每例附加失败最小输入</summary>','', '| ID / 元素数 | 删除最小输入 | 失败签名 |','|---|---|---|']
    for m in auxmins:
        r=m['result'];lines.append(f"| `{r['case_id']}` / {m['minimal_size']} | `{dumps(r['input'])}` | `{dumps(auxiliary_signature(r))}` |")
    lines+=['','</details>','']
    ow=sum(r['side_states']['ours']=='WRONG' for r in rows);tw=sum(r['side_states']['theirs']=='WRONG' for r in rows)
    ou=sum(r['side_states']['ours']=='UNRESOLVED' for r in rows);tu=sum(r['side_states']['theirs']=='UNRESOLVED' for r in rows)
    obw=sum(r['baseline_side_states']['ours']=='WRONG' for r in rows);tbw=sum(r['baseline_side_states']['theirs']=='WRONG' for r in rows)
    lines += ['**两份实现的正确性画像**','',
        f'我方主测试有 {ow} 个错误确定答案、{ou} 个诚实未决；原 benchmark 容差下仍有 {obw} 个错误确定答案。不能确认“我方退化均诚实未决”：交叉的零宽射线在微小尺度下会被枚举容差膨胀为多边形；微小点集可能返回 OK 的零半径或漏包圆。κ 的微小尺度错误与内部 MEC 有关联；边界覆盖 YES 的错误则来自需要精确符号的零附近判定。', '',
        f'同学主测试有 {tw} 个错误确定答案、{tu} 个诚实未决；原 benchmark 容差下仍有 {tbw} 个错误确定答案。随机搜索扩大了 tiny-gap 空集判非空、有限区域判无界、退化维数误判与微小 MEC 非最小的反例。其原始点集直径本轮全部通过（我方有 3 个微小点集 hull + diameter 流程低估，见附加反例；该计数来自本轮固定种子），说明多数几何失败在区域构造/分类；不能用直径子程序通过为错误区域背书。', '',
        '两方的普通尺度与压力尺度必须分开解释。尤其两个返回值相同不代表正确，BOTH_WRONG 由第三方 oracle 独立判定；测向 ε=90° 和覆盖/κ/η 未提供不计同学错误。', '']
    lines += ['**结论与复现**','',
    '本次是有限样本的正确性审计，不构成全输入证明。主表与米级容差副表应同时阅读：尺度压力下错误确定答案不能被写成诚实未决，也不能直接外推为正常米级任务同等失败率。具体新的分歧是否在普通尺度出现，可按输入族、原始输入、失败字段复核；几何误分类和小尺度 MEC 误差是不同问题。', '',
    '```bash',"cd '/Users/flower/math/2026/B题'",f"PYTHONDONTWRITEBYTECODE=1 models/q1q2/.venv/bin/python -B models/q1q2/peer-audit/differential_q1.py --seed {s['seed']} --random-cases {s['random_cases']}","# 将 CASE_ID 换成报告任一 ID；只重跑一个最小反例，不重写产物",'PYTHONDONTWRITEBYTECODE=1 models/q1q2/.venv/bin/python -B models/q1q2/peer-audit/differential_q1.py --replay CASE_ID --minimal', '# 附加覆盖/直径/端到端圆反例', 'PYTHONDONTWRITEBYTECODE=1 models/q1q2/.venv/bin/python -B models/q1q2/peer-audit/differential_q1.py --replay CASE_ID --auxiliary','```','',
    '脚本退出 0 表示完成审计，不代表两方全部正确。原始数据、最小反例和 [摘要/源文件哈希](differential-q1-summary.json) 可机器复核。随机 N 为 1–8（另有重复约束及现有较大 N 夹具），点集为 1–10 加重复点；尺度 1e-12–1e9，平移最高 1e12；未测试非凸 ε>90°、非法 NaN/Inf 或空点集 MEC 的共同契约。']
    (HERE/'differential-q1.md').write_text('\n'.join(lines)+'\n')

if __name__=='__main__':main()
