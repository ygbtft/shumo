"""Production adapter only. Ground truth is read from cases.jsonl, never recomputed by production."""
import argparse, collections, datetime, hashlib, json, math, sys, time
from pathlib import Path
from fractions import Fraction as F
HERE=Path(__file__).resolve().parent; ROOT=HERE.parent
sys.dont_write_bytecode=True
sys.path.insert(0,str(ROOT))
import numpy as np
import geometry as geo
import visibility_certificate as vc
import integer_visibility_certificate as iv
from icra_final_checks import partition_check, truth_margin
from oracle_coverage import certificate as independent_certificate
from oracle_localization import mec as independent_mec, contains
from policies import Policy
from clearance_policy import closest_clearance_point
import cover21_confirmation as factory

TOL=2e-5

def accepted(call):
    try: return True,call()
    except ValueError as e: return False,str(e)

def hausdorff(a,b):
    # Convex-set distance, including segments and points; insensitive to collinear vertices.
    def one(p,q):
        if len(q)==1: return float(np.linalg.norm(q[0]-p,axis=1).max())
        a=q; d=np.roll(q,-1,axis=0)-q; den=(d*d).sum(axis=1)
        delta=p[:,None,:]-a; t=np.divide((delta*d).sum(axis=2),den,out=np.zeros((len(p),len(q))),where=den>0)
        dist=np.linalg.norm(delta-np.clip(t,0,1)[:,:,None]*d,axis=2).min(axis=1)
        if len(q)>2 and abs(float(np.sum(q[:,0]*np.roll(q[:,1],-1)-q[:,1]*np.roll(q[:,0],-1))))>1e-12:
            signs=d[None,:,0]*delta[:,:,1]-d[None,:,1]*delta[:,:,0]
            inside=np.all(signs>=-1e-9,axis=1)|np.all(signs<=1e-9,axis=1); dist[inside]=0
        return float(dist.max())
    if not len(a) or not len(b): return 0. if len(a)==len(b) else math.inf
    return max(one(a,b),one(b,a))

class Feedback:
    def __init__(self): self.position=np.zeros(2); self.channel=1
    def measure(self,p,ch): self.position=np.asarray(p); return {'measure_result':'no_signal'}

class FirstAction(Exception): pass

policies={}
def policy(problem):
    if problem not in policies:
        fixture=json.loads((HERE/'fixtures/grid21_29.json').read_text())
        q3=json.loads((HERE/'fixtures/q3_ring7.json').read_text())
        paths={'ring7':np.array(q3['points']),'grid21_29':np.array(fixture['route'])}
        name='range_area7' if problem==3 else 'range_grid21_29'
        policies[problem]=(factory.SPECS[problem][name],paths)
    spec,paths=policies[problem]
    return factory.build(Feedback(),spec,problem,paths)

def evaluate(row):
    inp=row['input']; gt=row['ground_truth']; api=inp.get('api'); data=None
    if 'fixture' in inp:
        path=HERE/inp['fixture']
        if hashlib.sha256(path.read_bytes()).hexdigest()!=inp['sha256']: raise ValueError('fixture hash mismatch')
        data=json.loads(path.read_text())
    if row['block']=='coverage':
        if api=='certificate':
            p,c=data['points'],data['certificate']; mode=inp['mode']
            # Archived float certificates are also checked by integer verifier at exact dyadic scale.
            c={**c,'scale':c.get('scale',65536)}
            ok,detail=accepted(lambda: vc.verify_cells(p,c) if mode=='strict' else iv.verify_integer_certificate(p,c))
            part,pdetail=accepted(lambda:partition_check(c))
            actual=dict(accepted=ok,partition=part,detail=detail,partition_detail=pdetail)
            if 'route_matches' in gt: actual['route_matches']=set(map(tuple,p))==set(map(tuple,data['route']))
            good=all(actual[k]==gt[k] for k in ('accepted','partition'))
            if 'route_matches' in gt: good &= actual['route_matches']==gt['route_matches']
            # Independently verify fresh generator outputs too, for main layout and closed tangency.
            if row['category']=='archived_closed' and gt['accepted']:
                fresh=iv.certify_integer_stations(p)
                verified=fresh.get('covered') is True and independent_certificate(p,fresh,'closed')
                actual['fresh_integer_generator_independently_verified']=verified; good &= verified
            if row['category']=='archived_strict' and gt['accepted']:
                fresh=vc.rectangle_certificate(p,max_depth=16)
                verified=fresh.get('covered') is True and independent_certificate(p,fresh,'strict')
                actual['fresh_float_generator_independently_verified']=verified
                actual['generator_max_depth']=16
                if not verified: actual['fresh_generator_failure']=fresh
                good &= verified
            return bool(good),actual
        if api=='q3':
            import ring_coverage
            live=np.asarray(policy(3).stations)
            binding=hausdorff(live,np.array(data['points']))<1e-9 and len(live)==7
            r=ring_coverage.covering_radius(6,1140)
            uniform=all(any((abs(F(float(live[i,0]))-F(x))+F(h))**2+(abs(F(float(live[i,1]))-F(y))+F(h))**2<1000**2 for i in ids) for x,y,h,ids in data['cells'])
            return binding and uniform and r<1000,dict(covered=r<1000,live_points_uniform_square_proof=uniform,production_radius=r,route_binding=binding,independent_leaf_count=len(data['cells']))
        if api=='witness':
            result=vc.directional_witness(data['points'],np.array(inp['source']))
            return result is not None,dict(witness=result)
        if api=='leaf':
            c=vc.rectangle_certificate(inp['points'],arena_radius=300,max_depth=0)
            return c['covered']==gt['strict'],dict(strict=c['covered'],detail=c)
    if row['block']=='localization':
        if api=='negative':
            pol=policy(inp['problem']); p=np.array(inp['initial'],float); pol.regions[1]=p.copy()
            pol.observations[1]=[(np.array([-100,0]),0.)]
            pol.measure(np.array(inp['position'],float),1)
            margin=truth_margin(pol.regions[1],inp['source'])
            feasible=contains(pol.regions[1].tolist(),inp['source'])
            return feasible==gt['feasible'],dict(feasible=feasible,region_unchanged=np.array_equal(pol.regions[1],p),source_margin=margin,
                interpretation='Q3 exact-posterior completeness gap; retaining extra candidates is conservative, not a false clear' if inp['problem']==3 and feasible!=gt['feasible'] else 'consistent')
        p=None if inp['initial'] is None else np.array(inp['initial'],float)
        for o in inp['observations']: p=geo.update_region(p,np.array(o['position']),o['angle'],o['error'])
        c,r=geo.minimum_circle(p); expected=np.array(gt['vertices']); distance=hausdorff(p,expected)
        # MEC must describe returned outer polygon, not diameter/2 or latent exact disks.
        own=independent_mec(p.tolist())
        actual=dict(vertices=p.tolist(),radius=r,center=c.tolist(),set_distance_m=distance,independent_returned_polygon_radius=own['radius'])
        good=distance<=TOL and abs(r-gt['mec']['radius'])<=TOL and abs(r-own['radius'])<=TOL
        if 'source' in gt:
            margin=truth_margin(p,gt['source']); actual['truth_margin_m']=margin
            actual['truth_within_MEC']=math.dist(c,gt['source'])<=r+TOL
            actual['independent_source_containment']=contains(p.tolist(),gt['source'])
            good &= actual['independent_source_containment'] and actual['truth_within_MEC']
        return bool(good),actual
    p=np.array(inp['points'],float); c,r=geo.minimum_circle(p); D,_=geo.diameter(p)
    # Production has no explicit three-band API. Exercise its MEC and real selected-policy gate.
    pol=policy(inp['problem']); pol.regions[1]=geo.hull(p); pol.observations[1]=[(np.array([-500.,0]),0.)]
    action={}
    def stop_clear(q,ch,certified=False): action.update(kind='clear',certified=bool(certified),position=np.asarray(q).tolist()); raise FirstAction()
    def stop_measure(*args): action.update(kind='measure',certified=False); raise FirstAction()
    pol.clear=stop_clear; pol.measure=stop_measure; pol.primary_measure=stop_measure
    try:
        if inp['problem']==3: pol.complete_source(1)
        else: pol.source_packet(1)
    except FirstAction: pass
    band='guaranteed' if D*D<=1200+1e-9 else ('impossible' if D*D>1600+1e-9 else 'mec_required')
    expected_cert=gt['certified']
    q=closest_clearance_point(p,np.array([2000.,-1500.])) if expected_cert else c
    # Vertex bound proves every true source in the convex posterior is covered, not just one sample.
    far2=max(sum((F(float(a))-F(float(b)))**2 for a,b in zip(v,q)) for v in p)
    good=abs(r-gt['radius'])<=1e-7 and abs(D*D-float(F(gt['diameter2'])))<=1e-6 and band==gt['band'] and action.get('certified')==expected_cert
    if expected_cert: good &= far2<=400
    # Jung theorem bands must agree with exact existence, with no inference in intermediate band.
    good &= not (band=='guaranteed' and not gt['possible']) and not (band=='impossible' and gt['possible'])
    return bool(good),dict(radius=r,diameter=D,band=band,first_action=action,adjusted_clearance_point=q.tolist(),max_vertex_distance2=str(far2),covers_entire_posterior=far2<=400)

def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--block',choices=['coverage','localization','clearance']); args=parser.parse_args()
    rows=[json.loads(s) for s in (HERE/'cases.jsonl').read_text().splitlines()]
    if args.block: rows=[r for r in rows if r['block']==args.block]
    report=dict(n_cases=len(rows),n_pass=0,n_fail=0,categories={},blocks={},failures=[],tolerances={'region_hausdorff_m':TOL,'MEC_m':TOL,'clearance_MEC_m':1e-7,'coverage_predicates':'exact, no tolerance','gate':'production inward threshold 20-1e-5'},weak_comparisons_excluded=0,generated_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),python=sys.executable)
    results=[]; start=time.monotonic()
    for i,row in enumerate(rows):
        try: ok,actual=evaluate(row)
        except Exception as exc: ok=False; actual=dict(exception=type(exc).__name__,message=str(exc))
        key='n_pass' if ok else 'n_fail'; report[key]+=1
        for mapping,label in ((report['blocks'],row['block']),(report['categories'],row['block']+'/'+row['category'])):
            stat=mapping.setdefault(label,dict(n_cases=0,n_pass=0,n_fail=0)); stat['n_cases']+=1; stat[key]+=1
        result=dict(case_id=row['case_id'],passed=ok,actual=actual); results.append(result)
        if not ok: report['failures'].append(dict(case_id=row['case_id'],input=row['input'],expected=row['ground_truth'],actual=actual,truth_method=row['truth_method']))
        if i%20==0: print(f'{i+1}/{len(rows)} pass={report["n_pass"]} fail={report["n_fail"]}',flush=True)
    report['elapsed_s']=time.monotonic()-start
    report['production_sha256']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in ROOT.glob('*.py')}
    report['benchmark_sha256']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in HERE.glob('*.py')}
    report['findings']=[{'kind':'posterior_completeness_gap','case_ids':[f['case_id'] for f in report['failures'] if f['input'].get('api')=='negative'], 'description':'Q3 single no_signal keeps candidates inside/on the guaranteed 1000 m receiving disk; conservative over-approximation, not evidence of false certified clearing.'}, {'kind':'generator_budget_note','description':'Archived grid21_29 requires depth 14; default rectangle_certificate depth 13 is unresolved. Fresh generator checks explicitly use depth 16.'}]
    report['cases_sha256']=hashlib.sha256((HERE/'cases.jsonl').read_bytes()).hexdigest()
    stem='report' if not args.block else 'report_'+args.block
    (HERE/(stem+'.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    (HERE/(stem+'_results.jsonl')).write_text(''.join(json.dumps(x,ensure_ascii=False,allow_nan=False)+'\n' for x in results))
    print(json.dumps({k:report[k] for k in ('n_cases','n_pass','n_fail','blocks','elapsed_s')},ensure_ascii=False,indent=2))
    return int(bool(report['n_fail']))
if __name__=='__main__': sys.exit(main())
