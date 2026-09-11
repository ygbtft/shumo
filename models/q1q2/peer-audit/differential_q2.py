"""Read-only differential audit. Run from repository root; writes only peer-audit.
Oracle generators never consume production outputs; certified gets raw fields only.
"""
from __future__ import annotations
import argparse
from collections import Counter
from dataclasses import asdict, replace
from fractions import Fraction
import importlib.util
import json
import math
from pathlib import Path
import sys
import time
import tempfile
import heapq
from mpmath.ctx_iv import MPIntervalContext
from types import SimpleNamespace
import numpy as np

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location('peer_adapter', HERE/'benchmark_peer.py')
adapter = importlib.util.module_from_spec(spec); spec.loader.exec_module(adapter)
co = adapter.ORACLES['q2_candidate']; jo = adapter.ORACLES['q2_worst_diameter']
from models.q1q2.feasible import PhysicsConfig, build_source_set, check_candidate, Feedback
from models.q1q2.geometry import BearingMeasurement, NumericPolicy
from models.q1q2.q2 import SearchConfig, sample_sources, score_point, SourceSamples
from models.q1q2.diagnostics import clearance_summary, worst_radius_scale
from models.q1q2.optional.certified import certify

POL = NumericPolicy()
TOL = 1e-6

def build(i):
    return build_source_set(BearingMeasurement(tuple(i['S']), i['theta'], i['eps']),
        PhysicsConfig(arena_center=tuple(i['center']), arena_radius=i['arena_radius'], rho_hi=i['rho_hi']), POL)

def norm(i):
    return co.base(i['q'], **{k:v for k,v in i.items() if k in ('S','theta','center','rho_hi')},
                   eps=i.get('eps',i.get('eps1',1.)), arena_radius=i.get('arena_radius',i.get('radius',1800.)))

def ji(i):
    return dict(i, radius=i['arena_radius'], eps1=i['eps'], eps2=i.get('eps2',1.))

def exact_bad_world(i, p):
    """Squared-range failure on exact submitted binary floats; geometry independently checked."""
    if not co.legal([p],i,boundary_slack=False)[0]: return None
    def sq(a,b): return sum((Fraction(float(x))-Fraction(float(y)))**2 for x,y in zip(a,b))
    r1=sq(p,i['S']); r2=sq(p,i['q']); rho2=max(Fraction(1000000),r1)
    if r2 <= rho2: return None
    return dict(p=list(p),rho=math.sqrt(float(rho2)),rho_squared_exact=str(rho2),
                squared_excess_exact=str(r2-rho2),kind='no_signal',
                note='rho is defined exactly by sqrt(rho_squared_exact); displayed decimal is approximate')

def clipped_in_certificate(i, max_nodes=4096):
    """Independent interval proof of C_sig on clipped radial sector.

    For fixed angle, squared violation is convex below r=1000 and affine above.
    Thus only low/high endpoints of each radial part matter. Interval angular
    bisection covers all rays, including absent/tangent ones. No production API.
    """
    iv=MPIntervalContext();iv.dps=30;V=iv.mpf
    sx,sy=map(V,i['S']);cx,cy=map(V,i['center']);qx,qy=map(V,i['q'])
    hx,hy=qx-sx,qy-sy;zx,zy=sx-cx,sy-cy
    def vmax(a,b):return V([max(a.a,b.a),max(a.b,b.b)])
    def vmin(a,b):return V([min(a.a,b.a),min(a.b,b.b)])
    def bound(a,b):
        t=(V(i['theta'])+V([a,b]))*iv.pi/180;ux,uy=iv.cos(t),iv.sin(t)
        proj=zx*ux+zy*uy;disc=proj**2+V(i['arena_radius'])**2-zx**2-zy**2
        if disc.b<0:return None
        root=iv.sqrt(V([max(V(0),disc.a),disc.b]))
        lo=vmax(V(5),-proj-root);hi=vmin(V(i['rho_hi']),-proj+root)
        if hi.b<=5 or (hi-lo).b<0:return None
        vals=[]
        if lo.a<=1000:
            for r in (lo,vmin(hi,V(1000))):vals.append((hx-r*ux)**2+(hy-r*uy)**2-1000000)
        if hi.b>=1000:
            for r in (vmax(lo,V(1000)),hi):vals.append(hx**2+hy**2-2*r*(hx*ux+hy*uy))
        return max(math.nextafter(float(v.b),math.inf) for v in vals)
    pending=[(-i['eps'],i['eps'])];nodes=0;max_upper=-math.inf
    while pending and nodes<max_nodes:
        a,b=pending.pop();ub=bound(a,b);nodes+=1
        if ub is None:continue
        if ub<=0:max_upper=max(max_upper,ub);continue
        mid=(a+b)/2
        if mid==a or mid==b:return dict(proven=False,nodes=nodes,reason='resolution')
        pending.extend([(a,mid),(mid,b)])
    return dict(proven=not pending,nodes=nodes,max_accepted_upper_m2=max_upper,remaining=len(pending),dps=30)

def oracle_candidate(i, pts=None, supplied=None):
    if supplied is not None: return supplied
    if pts is None: pts,_=co.sample(i)
    pts=pts[co.legal(pts,i,boundary_slack=False)]
    if not len(pts): return dict(signal_status='UNRESOLVED',direction_status='UNRESOLVED',reason='no_sample_not_empty_proof')
    # Include the definition's radial kink r=1000 explicitly; a uniform radial
    # grid can miss its boundary maximum even with 276k worlds.
    angles=np.linspace(-math.radians(i['eps'])*(1-1e-10),math.radians(i['eps'])*(1-1e-10),33)
    unit,lo,hi,valid=co.radial(angles,i)
    kink=np.asarray(i['S'])+1000*unit
    kink=kink[valid & (lo<=1000) & (hi>=1000)]
    kink=kink[co.legal(kink,i,boundary_slack=False)]
    if len(kink):pts=np.vstack((pts,kink))
    # Full-sector extrema are a rigorous superset certificate for a clipped arena.
    gt=co.sector_oracle(i)
    full=math.dist(i['S'],i['center'])+i['rho_hi'] <= i['arena_radius']
    if full:
        # Resolve tolerance-band false positives only with exact legal worlds.
        for p in ([1500.,0.],[1000.,0.]) if i['S']==[0.,0.] and i['theta']==0. else []:
            w=exact_bad_world(i,p)
            if w: return dict(signal_status='OUT',signal_member=False,direction_status='OUT',direction_member=False,counterexample=w,method='exact_squared_world')
        return dict(gt,method='full_sector_closed_form')
    dist=np.linalg.norm(pts-i['q'],axis=1)
    rmin=np.maximum(1000.,np.linalg.norm(pts-i['S'],axis=1))
    ix=int(np.argmax(dist-rmin))
    if dist[ix]-rmin[ix]>1e-7:
        w=exact_bad_world(i,pts[ix])
        if w: return dict(signal_status='OUT',signal_member=False,direction_status='OUT',direction_member=False,counterexample=w,method='sampled_actual_world')
    if gt['signal_status']!='OUT':
        # Direction OUT on the superset is not an OUT proof on F.
        out={k:v for k,v in gt.items() if k in ('signal_status','signal_member')}
        if gt['direction_member']: out.update(direction_status=gt['direction_status'],direction_member=True)
        else:
            ix=int(np.argmin(dist))
            if dist[ix]<=5 and co.legal([pts[ix]],i,boundary_slack=False)[0]:
                out.update(direction_status='OUT',direction_member=False,
                           counterexample=dict(p=pts[ix].tolist(),rho=float(rmin[ix]),kind='near'))
        return dict(out,method='full_sector_superset_IN')
    cert=clipped_in_certificate(i)
    if cert['proven']:
        out=dict(signal_status='IN',signal_member=True,method='independent_clipped_radial_interval_IN',interval=cert)
        ix=int(np.argmin(dist))
        if dist[ix]<=5:out.update(direction_status='OUT',direction_member=False,counterexample=dict(p=pts[ix].tolist(),rho=float(rmin[ix]),kind='near'))
        return out
    return dict(signal_status='UNRESOLVED',direction_status='UNRESOLVED',method='sampling_cannot_prove_IN',interval=cert)

def candidate(cid,i,gt):
    ss=build(i); sig=check_candidate(ss,tuple(i['q']),False,POL); direct=check_candidate(ss,tuple(i['q']),True,POL)
    _,p=adapter.outer_source(i)
    peer=adapter.signal.reception_certificate(np.array(i['q']),p,np.array(i['S'])) if len(p) else None
    tags=[]; blame=[]
    if 'signal_member' not in gt or peer is None: tags.append('API_UNPROVIDED' if peer is None or 'source_status' in gt else 'ORACLE_UNRESOLVED')
    else:
        member=gt['signal_member']
        for side,yes in [('ours',sig.status=='IN'),('theirs',peer['guaranteed'])]:
            if yes and not member: tags.append('DANGEROUS_FALSE_POSITIVE'); blame.append(side)
        if member and (sig.status!='IN' or not peer['guaranteed']): tags.append('CONSERVATIVE')
        if sig.status=='OUT' and member: blame.append('ours')
        if not tags: tags.append('BOTH_OK')
    if 'direction_member' in gt:
        if direct.status=='IN' and not gt['direction_member']: tags.append('DIRECTION_FALSE_POSITIVE'); blame.append('ours')
        if direct.status=='OUT' and gt['direction_member']: blame.append('ours')
    tags += [side.upper()+'_WRONG' for side in set(blame)]
    # Check returned physical witness with oracle geometry, keep metadata distinct.
    wc={}
    for mode,a in [('sig',sig),('dir',direct)]:
        if a.status=='OUT' and a.extremal_source is not None:
            w=np.array(a.extremal_source); d=float(np.linalg.norm(w-i['q']))
            wc[mode]=dict(actual_source=bool(co.legal([w],i)[0]),claimed_attained=a.witness_attained,
                separates_signal=d>max(1000.,float(np.linalg.norm(w-i['S']))),separates_near=d<=5+1e-7)
    return dict(case_id=cid,input=i,oracle=gt,ours=asdict(sig),ours_dir=asdict(direct),theirs=peer,
                outer_vertex_count=len(p),categories=sorted(set(tags)),witness_checks=wc,
                theirs_C_dir='API_UNPROVIDED')

def random_cases(seed,scenes):
    rng=np.random.default_rng(seed); out=[]
    for j in range(scenes):
        mode=j%4; a=float(rng.uniform(-180,180)); u=np.array([math.cos(math.radians(a)),math.sin(math.radians(a))])
        s=np.zeros(2) if mode==0 else (1800. if mode==1 else float(rng.uniform(1801,3100)) if mode==2 else float(rng.uniform(10,250)))*u
        theta=float(rng.uniform(-180,180)) if mode in (0,3) else a+180+float(rng.uniform(-12,12))
        inp=co.base([0,0],S=s.tolist(),theta=theta)
        pts,_=co.sample(inp)
        if not len(pts): continue
        coords=[('same',[0,0]),('short_forward',[.001,0]),('short_back',[-.001,0]),('parallel',[500,1e-5]),
                ('near',[10,0]),('inside',[500,200]),('outside',[2300,1800])]
        coords += [('random_'+str(k),rng.uniform([-1000,-1400],[2100,1400])) for k in range(4)]
        # Four-disk boundary on a ray; full sector exact, clipped F has superset guarantee.
        e=math.radians(1); centers=[r*np.array([math.cos(e),sign*math.sin(e)]) for r in (5,1000) for sign in (-1,1)]
        ang=float(rng.uniform(-1.35,1.35)); v=np.array([math.cos(ang),math.sin(ang)])
        t=min(float(v@c)+math.sqrt(max(0,float(v@c)**2+1000000-float(c@c))) for c in centers)
        coords += [('boundary_'+str(d),(t+d)*v) for d in (-1e-4,0,1e-4)]
        for name,q in coords:
            i=dict(inp,q=co.world(q,inp)); out.append((f'random_{j}_{name}',i,oracle_candidate(i,pts)))
    return out

def closed_band(i,gt):
    """Outward interval evaluation of the independent generator's closed forms."""
    if 'J_exact_m' not in gt:return None
    iv=MPIntervalContext();iv.dps=40;V=iv.mpf
    if i['eps']==0:
        a=V(i['center'][0])-V(i['arena_radius']);b=V(i['center'][0])+V(i['arena_radius'])
        if gt['branch'] in ('near','same_station'):
            exact=Fraction(float(i['arena_radius']))*2
            f=float(exact)
            if Fraction(f)==exact:return [f,f]
            val=b-a
        else:
            h=V(abs(i['q'][1]));inner=h*iv.tan(iv.atan2(b,h)-2*V(i.get('eps2',1.))*iv.pi/180)
            inner=V([max(a.a,inner.a),max(a.b,inner.b)]);val=b-inner
    else:
        e=V(i['eps'])*iv.pi/180
        x=3000*iv.sin(e);y=iv.sqrt(V(1495)**2+30000*iv.sin(e)**2)
        val=V([max(x.a,y.a),max(x.b,y.b)])
    lo=math.nextafter(float(val.a),-math.inf);hi=math.nextafter(float(val.b),math.inf)
    assert lo-1e-7<=gt['J_exact_m']<=hi+1e-7
    return [lo,hi]

def score(cid,i,gt,args):
    ss=build(i);q=tuple(i['q']);eps=i.get('eps2',1.);cfg=SearchConfig(second_half_width_deg=eps)
    prod=sample_sources(ss,2,q,second_half_width_deg=eps)
    a=score_point(ss,q,prod,cfg)
    refined=score_point(ss,q,prod,replace(cfg,refine_pairs=True))
    _,p=adapter.outer_source(i)
    peer_cert=adapter.signal.reception_certificate(np.array(q),p,np.array(i['S']))
    b=adapter.signal.posterior_radius_upper(p,np.array(q),bin_deg=.5,error_deg=eps)
    upper=2*b['radius_upper_m']
    raw=SimpleNamespace(first=SimpleNamespace(position=tuple(i['S']),bearing_deg=i['theta'],half_width_deg=i['eps']),
                        physics=SimpleNamespace(arena_center=tuple(i['center']),arena_radius=i['arena_radius'],rho_hi=i['rho_hi'],near_radius=5.))
    try: cert=certify(raw,q,eps,tol=.1,max_nodes=args.cert_nodes,time_limit_s=30).to_dict()
    except ValueError as exc: cert=dict(error=str(exc))
    if args.extra_cert_nodes>args.cert_nodes and cert.get('upper_m',math.inf)>upper and 'J_exact_m' not in gt:
        try:
            cert=certify(raw,q,eps,tol=.1,max_nodes=args.extra_cert_nodes,time_limit_s=30).to_dict()
            cert['escalated_node_budget']=args.extra_cert_nodes
        except ValueError:pass
    lower=gt['lower_bound_m']; exact=gt.get('J_exact_m')
    closed=closed_band(i,gt)
    L=max(lower,cert.get('lower_m',0),closed[0] if closed else 0); U=min(cert.get('upper_m',math.inf),closed[1] if closed else math.inf)
    cats=[]
    if a.J_hat<L-TOL: cats += ['UNDERESTIMATE','OURS_WRONG']
    if a.J_hat>U+TOL: cats += ['OURS_WRONG']
    if upper<L-TOL: cats += ['UNDERESTIMATE','THEIRS_WRONG']
    upper_proven=upper>=U  # U is independent continuous upper; no inference from passing L.
    if upper_proven and upper>U+TOL: cats += ['CONSERVATIVE']
    if not any(x.endswith('WRONG') for x in cats): cats += ['BOTH_OK']
    pair=gt['pair']; worlds=[]
    for x in pair:
        worlds.append(dict(p=list(x),rho=max(1000.,math.dist(x,i['S'])),
                           independent_source_legal=bool(co.legal([x],i)[0]),second_distance_m=math.dist(x,q)))
    # Isolate enumeration on the SAME independent cloud on every underestimate.
    isolation=None
    if 'OURS_WRONG' in cats:
        pts=jo.source_points(ji(i)); truth=jo.brute(pts,q,eps,q==tuple(i['S']))
        same=score_point(ss,q,SourceSamples(tuple(map(tuple,pts)),2,(35,113)),cfg)
        isolation=dict(oracle=truth['lower_bound_m'],ours_same_cloud=same.J_hat,
                       passes=same.J_hat>=truth['lower_bound_m']-TOL)
    diagnostics=None
    if gt['branch'] in ('near','direction') and all(w['second_distance_m']<=1500 for w in worlds):
        fb=Feedback(gt['branch'],gt['bearing_deg'],eps)
        ds=clearance_summary(ss,q,fb,SourceSamples(tuple(map(tuple,pair)),2,(2,2)),POL)
        # Continuous conditional upper vs independently attainable pair radius.
        diagnostics=dict(summary=asdict(ds),pair_radius_lower=lower/2,
            upper_not_refuted=ds.r_U is None or ds.r_U>=lower/2-TOL,
            warning='conditional feedback only; not worst continuous radius')
    return dict(case_id=cid,input=i,oracle=gt,worlds=worlds,certificate=cert,closed_form_interval=closed,L=L,U=U,
        ours=dict(J_hat=a.J_hat,status=a.status,sample_count=a.sample_count,witness=asdict(a.witness) if a.witness else None,
                  refined_J_hat=refined.J_hat,refined_not_underestimated=refined.J_hat>=L-TOL,
                  in_band=L-TOL<=a.J_hat<=U+TOL),
        theirs=dict(diameter_upper=upper,reception=peer_cert,bound=b,continuous_upper_proven=upper_proven,
                    verdict='PROVEN_BY_ORACLE_U' if upper_proven else 'REFUTED_BY_L' if upper<L-TOL else 'NOT_REFUTED_NOT_CERTIFIED'),
        pair_oracle_isolation=isolation,diagnostics=diagnostics,categories=sorted(set(cats)),
        interpretation='physical posterior J only when q in C_sig; otherwise direction/near pair functional, no no_signal branch')

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--seed',type=int,default=20260911);ap.add_argument('--scenes',type=int,default=16)
    ap.add_argument('--cert-nodes',type=int,default=2000);ap.add_argument('--extra-cert-nodes',type=int,default=20000);args=ap.parse_args(); start=time.monotonic()
    before=adapter.protected_hashes(); candidates=[]; scores=[]
    regeneration={}
    for name,mod in [('candidate',co),('diameter',jo)]:
        original=mod.HERE
        with tempfile.TemporaryDirectory(prefix='q2-oracle-') as tmp:
            try:
                mod.HERE=Path(tmp); generated=mod.generate()
            finally:mod.HERE=original
        saved=[json.loads(x) for x in (original/'cases.jsonl').read_text().splitlines()]
        regeneration[name]=adapter.canonical(generated)==adapter.canonical(saved)
        assert regeneration[name], name+' fixture mismatch'
    fixtures=[json.loads(x) for x in (co.HERE/'cases.jsonl').read_text().splitlines()]
    for c in fixtures: candidates.append(candidate('fixture_'+c['case_id'],norm(c['input']),c['ground_truth']))
    rc=random_cases(args.seed,args.scenes)
    for cid,i,gt in rc:candidates.append(candidate(cid,i,gt))
    # Minimal two-coordinate adversarial family around the peer's same_position tolerance.
    for d in (0.,-1e-12,-5e-11,-9e-11,-1e-10,-1e-9,-1e-6):
        i=co.base([d,0.]);candidates.append(candidate('micro_'+str(d),i,oracle_candidate(i)))
    print('candidate completed',len(candidates),flush=True)
    worst=[json.loads(x) for x in (jo.HERE/'cases.jsonl').read_text().splitlines()]
    jobs=[]
    for c in worst:
        if c['kind']=='score':
            i=norm(c['input']);i['eps2']=c['input'].get('eps2',1.)
            if 'oracle_extra_points' in c['input']:i['oracle_extra_points']=c['input']['oracle_extra_points']
            jobs.append(('fixture_'+c['case_id'],i,c['ground_truth']))
    # Random physical J: eligible independent IN scenes, not chosen by either implementation.
    for cid,i,gt in rc:
        if (cid.endswith('_inside') or cid.endswith('_parallel') or cid.endswith('_same') or '_random_' in cid) and gt.get('signal_member'):
            ps=jo.source_points(ji(i)); g=jo.brute(ps,i['q'],1.,i['q']==i['S'])
            if cid.endswith('_same') and math.dist(i['S'],i['center'])+1500<=1800:
                e=math.radians(1);g['J_exact_m']=max(3000*math.sin(e),math.sqrt(1495**2+30000*math.sin(e)**2))
            jobs.append((cid,i,g))
    for n,(cid,i,gt) in enumerate(jobs):
        print('score',n+1,len(jobs),cid,flush=True)
        scores.append(score(cid,i,gt,args))
    for row in scores:row['candidate_oracle']=oracle_candidate(row['input'])
    after=adapter.protected_hashes()
    data=dict(seed=args.seed,options=vars(args),candidates=candidates,scores=scores,
              truth_regenerated_equal=regeneration,unchanged=before==after,protected_sha256_before=before,protected_sha256_after=after,
              counts={name:dict(Counter(t for r in rows for t in r['categories'])) for name,rows in [('candidate',candidates),('score',scores)]},
              elapsed_s=time.monotonic()-start)
    dcheck=validate(data);data['artifact_validation']=dcheck
    (HERE/'differential-q2.json').write_text(json.dumps(adapter.clean(data),ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    report(data)
    print(json.dumps(data['counts'],ensure_ascii=False),flush=True)

def validate(d):
    checks=dict(protected_sources_unchanged=d['unchanged'],truth_regeneration=all(d['truth_regenerated_equal'].values()),
                all_bands_consistent=all(r['L']<=r['U']+TOL for r in d['scores']),
                all_lower_pairs_legal=all(all(w['independent_source_legal'] for w in r['worlds']) for r in d['scores']),
                all_pair_distances_match=all(math.isclose(math.dist(*r['oracle']['pair']),r['oracle']['lower_bound_m'],abs_tol=TOL) for r in d['scores']))
    checks['all_OUT_have_independent_world']=True
    for r in d['candidates']:
        if r['oracle'].get('signal_status')!='OUT':continue
        w=r['oracle'].get('counterexample');i=r['input']
        ok=w is not None and co.legal([w['p']],i)[0] and math.dist(w['p'],i['q'])>w['rho'] and max(1000,math.dist(w['p'],i['S']))<=w['rho']+1e-8
        checks['all_OUT_have_independent_world'] &= bool(ok)
    assert all(checks.values()),checks
    return checks

def report(d):
    ca=d['candidates'];sc=d['scores'];member=[r for r in ca if r['oracle'].get('signal_member')]
    ours=sum(r['ours']['status']=='IN' for r in member);theirs=sum(bool(r['theirs'] and r['theirs']['guaranteed']) for r in member)
    severe=[r for r in ca if 'DANGEROUS_FALSE_POSITIVE' in r['categories']]
    under=[r for r in sc if 'UNDERESTIMATE' in r['categories']]
    direction_decisions=[r for r in ca if 'direction_member' in r['oracle'] and r['ours_dir']['status'] in ('IN','OUT')]
    direction_agree=sum((r['ours_dir']['status']=='IN')==r['oracle']['direction_member'] for r in direction_decisions)
    strict=[r for r in member if r['oracle']['signal_status']=='IN']
    strict_ours=sum(r['ours']['status']=='IN' for r in strict);strict_theirs=sum(bool(r['theirs'] and r['theirs']['guaranteed']) for r in strict)
    lines=['# Q2 三方对拍（独立 oracle）','',
        f"种子 `{d['seed']}`；候选 {len(ca)} 例，最坏直径 {len(sc)} 例；耗时 {d['elapsed_s']:.1f} 秒。双方实现及 oracle/fixture 的 SHA-256 前后相同：**{d['unchanged']}**。详见 `differential-q2.json`。",'',
        '## 判定口径','',
        '随机首测 ε₁=ε₂=1°、场地圆心原点/半径1800 m；S 含原点、场地圆周、域外及域内。q 含四圆盘边界±0.0001 m、随机内外、近源、短基线与近平行。另保留固定 benchmark 的零角宽线段、窄角扇区等闭式回归（这些补充例不全是1°）。',
        '候选 oracle 使用独立 sector_oracle（全扇区闭式）、sample（2049×129网格+12000随机世界），再加入33个角度的径向分段点 r=1000，防止均匀径向网格漏掉定义拐点。截断 F 的 IN 接受完整扇区超集证书或独立径向端点的一维角区间证书；C_sig OUT 必须有合法失收世界。采样未发现反例不能证明 IN；未知单列 ORACLE_UNRESOLVED。同学 P 使用原 adapter 的 disk_outer/bearing_clip/clip，不用真值点构造。',
        '我方仅 IN 视为声称保收；BOUNDARY 和 UNRESOLVED 不视为 IN。同学 False 是未获证书，不自动算错误。C_dir 独立核查我方，同学没有对应接口，逐例标 API_UNPROVIDED。',
        'J 是连续 sup。主配置为 sample_sources(level=2,q,ε₂)+score_point(SearchConfig 默认 refine_pairs=False)，另实测 refine_pairs=True。下界来自独立 atan2 全对枚举和闭式；[L,U] 合并 optional/certified 的区间带与闭式的40位区间运算外向舍入带（不把无理闭式的float近似当零宽精确区间）。certified 只接收 SimpleNamespace 原始参数，不读我方 F 边界/采样/谓词。1e-6 m 是比较浮点容差，绝不是连续误差保证。',
        'UNDERESTIMATE 表示违反独立下界（含认证 L/闭式）；不是把 J_hat 的 NUMERICAL_CANDIDATE 声明改写成上界承诺。BOTH_OK 仅表示本轮一致性检查没有反驳，不表示精确相等或认证正确。2·半径上界允许保守，不要求逼近 J。只有同学值 ≥ 独立 U 才标 PROVEN_BY_ORACLE_U；介于 L、U 之间只能标 NOT_REFUTED_NOT_CERTIFIED。',
        '对 C_sig 外点，分数只解释为 direction/near 点对泛函，不能当包含失收反馈的物理最坏后验 J；JSON 保存 reception 状态。', '',
        '## 分类计数（标签可重叠）','', '| 分类 | 候选 | 直径 |','|---|---:|---:|']
    for k in ['DANGEROUS_FALSE_POSITIVE','UNDERESTIMATE','CONSERVATIVE','OURS_WRONG','THEIRS_WRONG','BOTH_OK','API_UNPROVIDED','ORACLE_UNRESOLVED','DIRECTION_FALSE_POSITIVE']:
        lines.append(f"| {k} | {d['counts']['candidate'].get(k,0)} | {d['counts']['score'].get(k,0)} |")
    lines += ['',f'C_dir：同学 {len(ca)} 例均 API_UNPROVIDED（未重复加入上表 C_sig 计数）；方向 oracle 有成员真值 {sum("direction_member" in r["oracle"] for r in ca)} 例。', '', '## 保守性与召回','',
        f'我方 C_dir 有独立真值且给出 IN/OUT 的 {len(direction_decisions)} 例中，一致 {direction_agree} 例。全部 C_dir 返回状态：`{dict(Counter(r["ours_dir"]["status"] for r in ca))}`；非二元返回没有计作声称方向保收。',
        f'按 fixture 边界容差口径接受的 C_sig 点共 {len(member)} 个（包括数值边界带）：我方 IN {ours}/{len(member)}={ours/len(member):.2%}，同学 True {theirs}/{len(member)}={theirs/len(member):.2%}。这只是本测试集召回，不能外推分布。',
        f'排除 BOUNDARY 数值带后的 oracle IN 点 {len(strict)} 个：我方 {strict_ours}/{len(strict)}={strict_ours/len(strict):.2%}，同学 {strict_theirs}/{len(strict)}={strict_theirs/len(strict):.2%}。BOUNDARY 沿用生成器平方容差 1e-5 m²，不将其宣称为二进制输入的精确成员证明；微基线由精确世界覆盖此容差口径。',
        f"我方合法点状态：`{dict(Counter(r['ours']['status'] for r in member))}`。同学在这些点拒绝 {len(member)-theirs} 个，可能来自 P 外包、未去掉首测5m开圆盘或数值安全裕量；不能将全部差异归因于 P 外包。", '',
        '| 合法点举例 | q | 我方 | 同学 |','|---|---|---|---|']
    refuses=[r for r in member if r['ours']['status']=='IN' and r['theirs'] and not r['theirs']['guaranteed']]
    for r in refuses[:8]:lines.append(f"| {r['case_id']} | {r['input']['q']} | IN | False |")
    lines += ['', '## 危险假阳：最小结构反例与世界','',
        '“最小”指删去无关自由度的单场景、单 q、单世界，不声称实数坐标存在最小非零扰动。所有严重项的完整输入与世界均在 JSON；以下列出每个危险假阳。', '',
        '| case | S / θ / q | 声称保收者 | 世界 (p,ρ) |','|---|---|---|---|']
    for r in severe:
        lines.append(f"| {r['case_id']} | {r['input']['S']} / {r['input']['theta']} / {r['input']['q']} | {[s for s in ('OURS_WRONG','THEIRS_WRONG') if s in r['categories']]} | `{json.dumps(r['oracle'].get('counterexample'),ensure_ascii=False)}` |")
    if not severe:lines.append('| 未检出 | | | |')
    if severe:lines += ['', '这3个微扰（若计数变化，以表为准）属于同一个根因：同学 `signal_minimax.py:15` 用 `‖q−S‖<1e-10` 代替坐标完全相同，并无条件返回 True。令 q=(−δ,0)，p=(1500,0)，ρ=1500，则失收平方余量为 3000δ+δ²>0。这是严格定义下的假阳，物理失收距离仅为 δ；没有发现米级失收反例。我方同点特判使用坐标相等，这些非零微扰返回 BOUNDARY。']
    lines += ['', '## 低估：全部反例','', '| case | 我方 J_hat | refine=True | oracle L | oracle U | 同学 2U_R | 可达世界对 (p,ρ) / 反馈 |','|---|---:|---:|---:|---:|---:|---|']
    for r in under:
        worlds=[dict(p=w['p'],rho=w['rho']) for w in r['worlds']]
        lines.append(f"| {r['case_id']} | {r['ours']['J_hat']:.9f} | {r['ours']['refined_J_hat']:.9f} | {r['L']:.9f} | {r['U']:.9f} | {r['theirs']['diameter_upper']:.9f} | `{json.dumps(worlds)}` / {r['oracle']['branch']}, β={r['oracle']['bearing_deg']} |")
    if not under:lines.append('| 本轮未检出低估 | — | — | — | — | — | — |')
    lines += ['', '表中世界对对应 oracle 采样下界；若更强的 L 来自区间证书，精确反例采用 JSON certificate.witness.parameters 与 coordinate_enclosures（其源点可能为无理数），而非舍入后的世界坐标。若仅闭式极限超过估计，闭式为 sup，不能冒充已达到的点对。', '',
        f"同学连续上界判定：`{dict(Counter(r['theirs']['verdict'] for r in sc))}`。区间 oracle 收敛 {sum(r['certificate'].get('converged',False) for r in sc)}/{len(sc)}；预算耗尽仍保留有效宽带，不能将宽带内判为高精度通过。",
        f"我方落入带内 {sum(r['ours']['in_band'] for r in sc)}/{len(sc)}；refine=True 后仍违反 L 的 {sum(not r['ours']['refined_not_underestimated'] for r in sc)} 例。相同 oracle 点云隔离检查：{sum(bool(r['pair_oracle_isolation'] and r['pair_oracle_isolation']['passes']) for r in sc)}/{sum(r['pair_oracle_isolation'] is not None for r in sc)} 通过；用来区分采样不足与点对枚举问题。",'',
        '## diagnostics 与范围限制','',
        f"clearance_summary 在 {sum(r['diagnostics'] is not None for r in sc)} 个 oracle 可达反馈上检查条件半径 r_U≥可达点对距离/2；反驳 {sum(r['diagnostics'] is not None and not r['diagnostics']['upper_not_refuted'] for r in sc)} 个。这只检验条件后验的覆盖界，不能把 R_hat 或 worst_radius_scale(J_hat) 当作连续最坏覆盖保证。",'',
        '## 结论与复现','',
        f"本轮检出 {len(severe)} 个保收危险假阳和 {len(under)} 个最坏直径低估。错误归属见计数及逐例表；保守拒绝和上界偏松独立记录。未被下界反驳的同学上界，只有通过独立 U 的子集获得本轮连续上界证明，其余仍待更紧认证。",'',
        '```sh',f'cd {ROOT}',f'models/q1q2/.venv/bin/python -B models/q1q2/peer-audit/differential_q2.py --seed {d["seed"]} --scenes {d["options"]["scenes"]} --cert-nodes {d["options"]["cert_nodes"]} --extra-cert-nodes {d["options"].get("extra_cert_nodes",0)}','```','',
        f'两份真值生成器均在临时目录重新执行，和保存 fixtures 语义一致：{d["truth_regenerated_equal"]}。',
        f'产物一致性核验（OUT世界、点对合法性/距离、区间顺序、哈希、真值重生成）：`{d.get("artifact_validation", {})}`。',
        '脚本：`differential_q2.py`；逐例输入、双方返回值、反例世界、区间参数、哈希：`differential-q2.json`。增大 --cert-nodes 可收紧未收敛区间；节点数固定，另设30秒应急时限，因此时限触发时区间端点可随机器性能变化。']
    exact_rows=[r for r in sc if r['oracle'].get('J_exact_m',0)>0]
    extra=['', '## 上界保守幅度（闭式真值子集）', '', '| case | 真 J | 我方 J_hat−J | 同学 2U_R−J | 同学 2U_R/J |', '|---|---:|---:|---:|---:|']
    for r in sorted(exact_rows,key=lambda r:r['theirs']['diameter_upper']/r['oracle']['J_exact_m'],reverse=True)[:8]:
        j=r['oracle']['J_exact_m'];extra.append(f"| {r['case_id']} | {j:.9f} | {r['ours']['J_hat']-j:.9f} | {r['theirs']['diameter_upper']-j:.9f} | {r['theirs']['diameter_upper']/j:.6f} |")
    physical=sum(r.get('candidate_oracle',{}).get('signal_member') is True for r in sc)
    diagnostic=[r for r in sc if r.get('candidate_oracle',{}).get('signal_member') is False]
    extra += ['', f'直径场景中，独立 oracle 确认 C_sig 内 {physical} 例、C_sig 外 {len(diagnostic)} 例，其余 {len(sc)-physical-len(diagnostic)} 例候选真值未决。C_sig 外结果仅作点对泛函诊断，不计为物理保收动作验证。']
    for r in diagnostic:extra.append(f"`{r['case_id']}` 不保收世界：`{json.dumps(r['candidate_oracle']['counterexample'],ensure_ascii=False)}`。")
    extra += ['', '这里认证的是换算后的直径上界 2U_R≥J。仅此不能反向证明半径 U_R≥连续最坏 MEC 半径；一般平面集合满足 J/2≤J_R≤J/√3。diagnostics 的条件半径检查也不替代全反馈最坏半径认证。']
    extra += ['', '## 尚未认证的同学直径上界', '', '| case | oracle L | oracle U | 同学 2U_R | 我方 J_hat |', '|---|---:|---:|---:|---:|']
    for r in sc:
        if not r['theirs']['continuous_upper_proven']:extra.append(f"| {r['case_id']} | {r['L']:.9f} | {r['U']:.9f} | {r['theirs']['diameter_upper']:.9f} | {r['ours']['J_hat']:.9f} |")
    at=lines.index('## diagnostics 与范围限制');lines[at:at]=extra+['']
    (HERE/'differential-q2.md').write_text('\n'.join(lines)+'\n')

if __name__=='__main__':main()
