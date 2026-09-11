"""Run production APIs against independent serialized truth; nonzero on failure."""
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sys
import traceback
from .generate import ROOT, generate, exact_mec, candidate, root, F
from models.q1q2.circle import (minimum_circle, diameter_circle_cover, forced_circle,
                              ordinary_three_point_circle, clearance_diameter_regime, ForcedSupportError)
from models.q1q2.q1 import solve
from models.q1q2.geometry import BearingMeasurement, NumericPolicy, Region, RegionKind, DiameterResult

TOLERANCES = dict(length_abs_m=2e-9,length_relative=2e-10,coordinate_ulps=8,
                  ratio_abs=2e-8,thales_abs_m2=2e-9,thales_relative=2e-12,
                  oracle='exact Fraction predicates on binary64 input; sqrt Decimal precision 80',
                  coverage_status='Exact YES allows YES/UNRESOLVED in zero band; positive T <= policy tolerance requires UNRESOLVED; larger T requires NO',
                  support='1..3 distinct valid indices, boundary contact and independent support MEC matches full MEC')


def main():
    if '--regenerate' in sys.argv or not (ROOT/'cases.jsonl').exists():
        generate()
    cases=[json.loads(x) for x in (ROOT/'cases.jsonl').read_text().splitlines()]
    policy=NumericPolicy(); scale_limits=[]; anchors=[]; failures=[]; categories={}; outputs={}; check_count=0
    for case in cases:
        inp,gt=case['input'],case['ground_truth']; actual={}; errors=[]
        def check(ok,field,expected,observed):
            nonlocal check_count
            check_count+=1
            if not ok:
                errors.append(dict(field=field,expected=expected,actual=observed))
        def near(field,a,b,tol):
            check(a is not None and b is not None and math.isfinite(a) and abs(a-b)<=tol,field,b,a)
        try:
            if 'diameter_m' in inp:
                try:
                    result=clearance_diameter_regime(inp['diameter_m'])
                except ValueError:
                    result='ValueError'
                actual['regime']=result
                check(result==gt['regime'],'regime',gt['regime'],result)
            elif 'special' in inp:
                kind=inp['special']; region=Region(RegionKind(kind) if kind in ('EMPTY','UNBOUNDED') else RegionKind.SEGMENT,
                    ((0.,0.),(1.,0.)),status='NUMERICAL_UNRESOLVED' if kind=='region_unresolved' else 'OK')
                d=DiameterResult(None,None) if kind=='missing_endpoints' else DiameterResult(1.,1.,((0.,0.),(1.,0.)),(0,1))
                result=diameter_circle_cover(region, d, policy, minimum_circle(region.vertices, seed=0)); actual['cover']=asdict(result)
                check(result.status==gt['status'],'cover.status',gt['status'],result.status)
                check(result.kappa is None and result.eta is None,'inapplicable_ratios',None,[result.kappa,result.eta])
                check(not result.finite_cover,'finite_cover',False,result.finite_cover)
                if kind=='EMPTY':
                    empty=minimum_circle([], 0); actual['empty_circle']=asdict(empty)
                    check(empty.status=='EMPTY' and empty.center is None and empty.radius is None,'empty_circle','EMPTY/null',asdict(empty))
            else:
                pts=[tuple(p) for p in inp['points']]; d=gt['diameter']
                ulp=max(math.ulp(x) for p in pts for x in p)
                tol=2e-9+2e-10*d+8*ulp
                scale_limit=inp['scale_assessment']['scale_limit']
                unresolved=[]
                def accepted_unresolved(c,prefix):
                    if scale_limit and c.status=='NUMERICAL_UNRESOLVED':
                        unresolved.append(prefix)
                        return True
                    return False
                def circle_check(c,prefix,expected=gt):
                    if accepted_unresolved(c,prefix):
                        return
                    check(c.status=='OK',prefix+'.status','OK',c.status)
                    near(prefix+'.radius',c.radius,expected['radius'],tol)
                    if c.center is None:
                        check(False,prefix+'.center',expected['center'],None)
                    else:
                        for k in range(2): near(prefix+'.center.'+str(k),c.center[k],expected['center'][k],tol)
                actual['minimum_circle']=[]
                for seed in inp['seeds']:
                    c=minimum_circle(pts, seed); actual['minimum_circle'].append(asdict(c)); circle_check(c,'minimum.'+str(seed))
                    if scale_limit and c.status=='NUMERICAL_UNRESOLVED':
                        continue
                    ids=c.support_vertex_indices
                    check(ids==tuple(sorted(ids)), 'support.canonical_order', sorted(ids), ids)
                    valid=1<=len(ids)<=3 and len(set(ids))==len(ids) and all(0<=i<len(pts) for i in ids)
                    check(valid,'support.indices','1..3 distinct in-range',ids)
                    if valid and c.center is not None:
                        for i in ids: near('support.contact',math.dist(c.center,pts[i]),c.radius,tol)
                        sc,_=exact_mec([pts[i] for i in ids])
                        near('support.radius',root(sc[1]),gt['radius'],tol)
                        for k in range(2): near('support.center',float(sc[0][k]),gt['center'][k],tol)
                    if c.center is not None and c.radius is not None:
                        residual=max(math.dist(v,c.center)-c.radius for v in pts)
                        check(residual<=tol,'containment',f'<= {tol}',residual)
                        near('containment_residual',c.containment_residual,residual,tol)
                if len(pts)<=3:
                    ordinary=ordinary_three_point_circle(pts); actual['ordinary']=asdict(ordinary); circle_check(ordinary,'ordinary')
                    p=[tuple(F(x) for x in v) for v in pts]; fc=candidate(p)
                    det=abs((p[1][0]-p[0][0])*(p[2][1]-p[0][1])-(p[1][1]-p[0][1])*(p[2][0]-p[0][0])) if len(p)==3 else None
                    # forced_circle rejects exact collinearity only. Near-collinear
                    # circles still undergo the independent center/radius checks below.
                    force_reject = det == 0 if det is not None else False
                    try:
                        forced=forced_circle(pts); actual['forced']=asdict(forced)
                        check(not force_reject,'forced.exception','ForcedSupportError' if force_reject else 'circle','circle')
                        if fc:
                            circle_check(forced,'forced',dict(center=list(map(float,fc[0])),radius=root(fc[1])))
                    except ForcedSupportError:
                        actual['forced']='ForcedSupportError'; check(force_reject,'forced.exception','circle','ForcedSupportError')
                if 'ideal_side' in inp:
                    regime=clearance_diameter_regime(inp['ideal_side']); actual['clearance_regime']=regime
                    check(regime==inp['clearance_expected'],'wedge.clearance_regime',inp['clearance_expected'],regime)
                    near('wedge.Jung_equality',gt['radius'],inp['ideal_side']/math.sqrt(3),tol)
                i,j=gt['pair']; dia=DiameterResult(d,gt['diameter_squared'],(pts[i],pts[j]),(i,j))
                region=Region(RegionKind.POINT if d==0 else RegionKind.SEGMENT if len(pts)<=2 else RegionKind.POLYGON,tuple(pts))
                cover=diameter_circle_cover(region, dia, policy, minimum_circle(region.vertices, seed=0)); actual['cover']=asdict(cover)
                check(cover.status in gt['allowed_cover_status'],'cover.status',gt['allowed_cover_status'],cover.status)
                check(cover.finite_cover,'cover.finite_cover',True,cover.finite_cover)
                for k in range(2): near('forced_center',None if cover.forced_center is None else cover.forced_center[k],gt['forced_center'][k],tol)
                near('thales_max',cover.thales_max,gt['thales_max'],2e-9+2e-12*d*d)
                near('midpoint_radius',cover.midpoint_radius,gt['midpoint_radius'],tol)
                kappa_unavailable=scale_limit and actual['minimum_circle'][0]['status']=='NUMERICAL_UNRESOLVED'
                for field in ('kappa','eta'):
                    if field=='kappa' and kappa_unavailable:
                        check(cover.kappa is None,'unresolved.kappa',None,cover.kappa)
                        continue
                    val=getattr(cover,field)
                    if d: near(field,val,gt[field],2e-8)
                    else: check(val is None,field,None,val)
                if d:
                    near('tolerance_m2',cover.tolerance_m2,gt['tolerance_m2'],1e-20+1e-14*gt['tolerance_m2'])
                    if not kappa_unavailable:
                        check(cover.kappa is not None and 1-2e-8<=cover.kappa<=2/math.sqrt(3)+2e-8,'Jung_bound',[1,2/math.sqrt(3)],cover.kappa)
                    if not kappa_unavailable:
                        check(cover.kappa is not None and cover.eta is not None and cover.kappa<=cover.eta+2e-8 and cover.eta<=math.sqrt(3)+2e-8,'inflation_bounds','kappa <= eta <= sqrt(3)',[cover.kappa,cover.eta])
                if cover.status=='NO':
                    idx=cover.counterexample_index
                    check(idx is not None and 0<=idx<len(pts),'counterexample.index','valid',idx)
                    if idx is not None and 0<=idx<len(pts):
                        check(cover.counterexample_vertex==pts[idx],'counterexample.vertex',pts[idx],cover.counterexample_vertex)
                        t=sum((F(pts[idx][k])-F(pts[i][k]))*(F(pts[idx][k])-F(pts[j][k])) for k in range(2))
                        check(t>0,'counterexample.positive', '>0',float(t))
                if 'transform' in inp:
                    tr=inp['transform']; base=outputs[tr['base']]; old=base['minimum_circle'][0]; new=actual['minimum_circle'][0]
                    if new['status']=='OK' and old['status']=='OK':
                        near('invariant.radius',new['radius'],old['radius']*tr['scale'],tol)
                    bg=next(c['ground_truth'] for c in cases if c['case_id']==tr['base'])
                    near('invariant.diameter',d,bg['diameter']*tr['scale'],tol)
                    for field in ('kappa','eta'):
                        if field=='kappa' and (kappa_unavailable or base['cover'][field] is None):
                            continue
                        if d: near('invariant.'+field,actual['cover'][field],base['cover'][field],max(2e-8,16*ulp/d))
                    check(gt['mathematical_cover']==bg['mathematical_cover'] or gt['thales_max']<=gt['tolerance_m2'] or bg['thales_max']<=bg['tolerance_m2'], 'invariant.exact_cover','same outside rounding band',[bg['mathematical_cover'],gt['mathematical_cover']])
                    if gt['thales_max']>gt['tolerance_m2'] and bg['thales_max']>bg['tolerance_m2']:
                        check(cover.status==base['cover']['status'],'invariant.cover',base['cover']['status'],cover.status)
                if 'anchor_expected' in inp:
                    expected=inp['anchor_expected']
                    solved=solve([BearingMeasurement(**station) for station in inp['stations']],policy)
                    actual['anchor_pipeline']=asdict(solved)
                    check(solved.region.status=='OK','anchor.region.status','OK',solved.region.status)
                    circle_check(solved.minimum_circle,'anchor.pipeline_circle')
                    c=asdict(solved.minimum_circle)
                    anchor=dict(case_id=case['case_id'],name=inp['display_name'],diameter=solved.diameter.length,radius=c['radius'],
                                radius_diameter_ratio=c['radius']/solved.diameter.length,cover=solved.coverage.status,
                                regime=clearance_diameter_regime(solved.diameter.length),stations=inp['stations'])
                    for field in ('diameter','radius','radius_diameter_ratio'):
                        near('anchor.'+field,anchor[field],expected[field],tol)
                    for field in ('cover','regime'):
                        check(anchor[field]==expected[field],'anchor.'+field,expected[field],anchor[field])
                    anchor['passed']=not errors
                    anchors.append(anchor)
                if scale_limit:
                    scale_limits.append(dict(case_id=case['case_id'],assessment=inp['scale_assessment'],
                        accepted_unresolved=unresolved,actual=actual,passed=not errors))
                outputs[case['case_id']]=actual
        except Exception as exc:
            errors.append(dict(field='exception',expected='successful evaluation',actual=repr(exc),traceback=traceback.format_exc()))
        outputs[case['case_id']]=actual
        for cat in case['categories']:
            stats=categories.setdefault(cat,dict(n_cases=0,n_pass=0,n_fail=0)); stats['n_cases']+=1; stats['n_fail' if errors else 'n_pass']+=1
        if errors:
            failures.append(dict(case_id=case['case_id'],input=inp,expected=gt,actual=actual,error=errors,
                                 truth_method=case['truth_method'],note='All failed checks retained; no expected-failure suppression.'))
    report=dict(area='q1_circle_cover',generated_utc=datetime.now(timezone.utc).isoformat(),n_cases=len(cases),n_pass=len(cases)-len(failures),n_fail=len(failures),categories=categories,tolerances=TOLERANCES,failures=failures,weak_comparisons_excluded=0,n_checks=check_count,
                scale_limit_policy=dict(max_coordinate_m=1e6,min_nonzero_feature_m=1e-3,feature_definition="minimum nonzero pair distance and (three-point inputs only) triangle altitude",unresolved_accepted_only_outside=True,ok_results_still_checked=True),
                scale_limits=scale_limits,anchors=anchors,production_policy=asdict(policy),cases_sha256=hashlib.sha256((ROOT/'cases.jsonl').read_bytes()).hexdigest(),
                production_circle_sha256=hashlib.sha256((ROOT.parents[1]/'circle.py').read_bytes()).hexdigest(),python=sys.version,
                observed_cover_statuses={s:sum(a.get('cover',{}).get('status')==s for a in outputs.values()) for s in ['YES','NO','UNRESOLVED','NOT_APPLICABLE']})
    (ROOT/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    print(json.dumps({k:report[k] for k in ['area','n_cases','n_pass','n_fail','n_checks']},ensure_ascii=False))
    return int(bool(failures))

if __name__=='__main__':
    sys.exit(main())
