"""Run production functions against saved independent answers; never alter them."""
from __future__ import annotations
import argparse
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import platform
import sys
import time
import numpy as np
import scipy
from models.q1q2 import geometry as g
from .generate import HERE

TOL = dict(length_abs_m=1e-8, length_relative=1e-9,
           witness_abs_m=1e-8, witness_relative=1e-12,
           direction_abs=1e-10, angle_deg=1e-10,
           vertices='unordered geometric coverage plus separate bijection/normalization checks',
           classification='exact equality; NUMERICAL_UNRESOLVED counts as failure',
           length_rule='abs_error <= length_abs_m + length_relative * expected_length',
           vertex_rule='length_abs_m + length_relative * diameter + 32 ulp(max coordinate)',
           lp_primal_feasibility=1e-9, lp_dual_feasibility=1e-9)


def fl(x):
    return float(Fraction(x))


def points(v):
    return [tuple(map(fl,p)) for p in v]


def clean(x):
    if isinstance(x, float) and not math.isfinite(x):
        return None
    if isinstance(x, dict):
        return {k:clean(v) for k,v in x.items()}
    if isinstance(x, (tuple,list)):
        return [clean(v) for v in x]
    return x


def distance(a,b):
    return math.hypot(a[0]-b[0],a[1]-b[1])


def match_vertices(actual, expected, tol):
    if not actual or not expected:
        return len(actual)==len(expected), None
    hausdorff=max(max(min(distance(a,b) for b in expected) for a in actual),
                  max(min(distance(a,b) for a in actual) for b in expected))
    # Bipartite matching also detects multiple near-duplicates replacing one vertex.
    owner={}
    def visit(i,seen):
        for j,b in enumerate(expected):
            if j not in seen and distance(actual[i],b)<=tol:
                seen.add(j)
                if j not in owner or visit(owner[j],seen):
                    owner[j]=i
                    return True
        return False
    ok=len(actual)==len(expected) and all(visit(i,set()) for i in range(len(actual)))
    return ok,hausdorff


def recession_witness(direction, rows):
    """Accept any finite nonzero feasible direction, independently of oracle witness.

    Scale by largest component BEFORE normalizing: both subnormal and huge
    positive multiples represent exactly the same candidate direction.
    """
    if direction is None:
        return dict(valid=False, reason='missing_direction', residual=None)
    if len(direction)!=2 or not all(math.isfinite(x) for x in direction):
        return dict(valid=False, reason='nonfinite_or_invalid_direction', residual=None)
    scale=max(map(abs,direction))
    if scale==0:
        return dict(valid=False, reason='zero_direction', residual=None)
    w=[x/scale for x in direction]
    length=math.hypot(*w)
    unit=[x/length for x in w]
    # Fraction dot products avoid cancellation in the certificate check itself.
    u=list(map(Fraction.from_float,unit))
    residuals=[]
    exact=True
    for row in rows:
        a,b=map(Fraction,row[:2])
        dot=a*u[0]+b*u[1]
        exact &= dot<=0
        residuals.append(float(dot)/math.hypot(float(a),float(b)))
    residual=max(residuals,default=0.)
    valid=residual<=TOL['direction_abs']
    return dict(valid=valid, reason=('exactly_feasible' if exact else
                'within_direction_roundoff' if valid else 'violates_homogeneous_constraint'),
                unit_direction=unit,residual=residual,exactly_feasible=exact,
                compared_to_reference_direction=False)


def vertex_diagnostics(actual, expected, tol, status='OK'):
    matched,err=match_vertices(actual,expected,tol)
    same_set=err is not None and err<=tol
    if not expected and not actual:
        same_set=True
    nearest_actual=[min((distance(p,q) for q in expected),default=math.inf) for p in actual]
    nearest_expected=[min((distance(q,p) for p in actual),default=math.inf) for q in expected]
    if matched:
        category='equivalent_unordered_vertices'
    elif same_set:
        category='same_geometry_normalization_defect'
    elif err is None:
        category='missing_vertex_set'
    elif err<=10*tol:
        category='outside_tolerance_needs_numerical_review'
    else:
        category='vertex_set_discrepancy'
    return dict(category=category if status=='OK' else 'upstream_numerical_unresolved',
                geometric_comparison=category, upstream_status=status,
                geometry_matches=same_set, bijection_matches=matched,
                actual_count=len(actual), expected_count=len(expected),
                hausdorff_m=err,tolerance_m=tol,
                error_over_tolerance=err/tol if err is not None else None,
                unmatched_actual_indices=[i for i,d in enumerate(nearest_actual) if d>tol],
                unmatched_expected_indices=[i for i,d in enumerate(nearest_expected) if d>tol],
                order_ignored=True, diagnostic_only_review_multiplier=10)


def comparator_self_checks():
    """Hand-constructed comparator regressions; no production geometry involved."""
    rows=[['-1','0','0'],['0','-1','0']]  # First-quadrant recession cone.
    tests={}
    for name,v in [('east',(1.,0.)),('north',(0.,1.)),('interior',(2.,3.)),
                   ('huge',(1.7e308,1.7e308)),('subnormal',(5e-324,5e-324))]:
        tests['accept_'+name]=recession_witness(v,rows)['valid']
    for name,v in [('zero',(0.,0.)),('outside',(-1.,1.)),('inf',(math.inf,1.)),
                   ('nan',(math.nan,1.)),('missing',None)]:
        tests['reject_'+name]=not recession_witness(v,rows)['valid']
    tests['whole_plane_arbitrary']=recession_witness((-2.,7.),[])['valid']
    line=[['1','-1','0'],['-1','1','0']]
    tests['line_both_signs']=all(recession_witness(v,line)['valid'] for v in [(3.,3.),(-7.,-7.)])
    square=[(0.,0.),(1.,0.),(1.,1.),(0.,1.)]
    tol=1e-8
    tests['vertex_order_ignored']=all(vertex_diagnostics(v,square,tol)['bijection_matches']
                                    for v in [square[2:]+square[:2],square[::-1]])
    diag=vertex_diagnostics(square+[square[0]],square,tol)
    tests['duplicate_is_normalization_only']=diag['geometry_matches'] and not diag['bijection_matches']
    tests['missing_corner_is_real_difference']=vertex_diagnostics(square[:3],square,tol)['category']=='vertex_set_discrepancy'
    tests['within_tolerance_accepted']=vertex_diagnostics([(x+tol/2,y) for x,y in square],square,tol)['bijection_matches']
    tests['outside_tolerance_not_silently_widened']=not vertex_diagnostics([(x+2*tol,y) for x,y in square],square,tol)['geometry_matches']
    assert all(tests.values()),tests
    return tests


def recheck_baseline(baseline, cases):
    """Counterfactual: new comparator on SAVED old outputs, no producer calls.

    Separates benchmark-induced pass changes from concurrent production fixes.
    """
    byid={c['case_id']:c for c in cases}
    results=[]
    attribution_changes=[]
    for old in baseline['results']:
        c=byid[old['case_id']]
        checks=old['checks'].copy()
        region=old['actual'].get('region',{})
        if 'recession_witness' in checks:
            checks['recession_witness']=recession_witness(region.get('recession_direction'),c['input']['oracle_halfplanes'])['valid']
        for key in ['vertices','hull_vertices']:
            if key in checks:
                vv=points(c['ground_truth']['vertices'])
                d=c['ground_truth'].get('diameter') or 0
                coord=max((abs(x) for p in vv for x in p),default=1)
                tol=TOL['length_abs_m']+TOL['length_relative']*d+32*math.ulp(coord)
                vd=vertex_diagnostics(region.get('vertices',[]),vv,tol,region.get('status','OK'))
                if not checks[key] and vd['geometry_matches'] and not vd['bijection_matches']:
                    attribution_changes.append(old['case_id'])
                checks[key]=vd['geometry_matches']
                checks['vertex_normalization']=vd['bijection_matches']
        results.append(dict(case_id=old['case_id'],old_pass=old['pass'],new_comparator_pass=all(checks.values())))
    return dict(note='Replays comparator changes against immutable saved production outputs; no current production calls.',
                n_cases=len(results),n_pass=sum(x['new_comparator_pass'] for x in results),
                n_fail=sum(not x['new_comparator_pass'] for x in results),
                vertex_attribution_corrected_cases=attribution_changes,
                changed_cases=[x for x in results if x['old_pass']!=x['new_comparator_pass']])


def check_diameter(result, truth, vertices, tolerance, checks, prefix):
    expected=truth.get('diameter')
    if truth['kind']=='EMPTY':
        checks[prefix+'status']=result.status=='EMPTY' and result.length is None and result.endpoints is None
        return None
    if truth['kind']=='UNBOUNDED':
        checks[prefix+'status']=result.status=='UNBOUNDED' and result.length==math.inf and result.endpoints is None
        return None
    checks[prefix+'status']=result.status=='OK'
    error=abs(result.length-expected) if result.length is not None else None
    checks[prefix+'length']=error is not None and error<=tolerance
    sq=fl(truth['diameter_squared'])
    checks[prefix+'squared']=result.squared is not None and abs(result.squared-sq)<=tolerance*(2*expected+tolerance)
    ends=result.endpoints
    checks[prefix+'endpoints']=bool(ends) and all(any(distance(p,v)<=tolerance for v in vertices) for p in ends) and abs(distance(*ends)-expected)<=tolerance
    indices=result.indices
    checks[prefix+'indices']=indices is not None and len(indices)==2 and all(0<=i<len(vertices) for i in indices) and bool(ends) and all(distance(vertices[i],p)<=tolerance for i,p in zip(indices,ends))
    return error


def evaluate(c):
    truth, inp=c['ground_truth'],c['input']
    checks={}
    vv=points(truth['vertices'])
    d=truth.get('diameter') or 0
    tolerance=TOL['length_abs_m']+TOL['length_relative']*d
    coord=max((abs(x) for p in vv for x in p), default=1)
    vtol=tolerance+32*math.ulp(coord)
    actual={}
    errors={}
    diagnostics={}
    policy=g.NumericPolicy()
    if 'points' in inp:
        cloud=points(inp['points'])
        hv=g.convex_hull(cloud,policy)
        vd=vertex_diagnostics(hv,vv,vtol)
        diagnostics['vertices']=vd
        checks['hull_vertices']=vd['geometry_matches']
        checks['vertex_normalization']=vd['bijection_matches']
        errors['vertex_hausdorff_m']=vd['hausdorff_m']
        region=g.Region(g.RegionKind(truth['kind']),vertices=hv)
        actual['region']=asdict(region)
    else:
        if 'observations' in inp:
            hps=[h for o in inp['observations'] for h in g.wedge_halfplanes(g.BearingMeasurement(**o))]
            # Independently compare wedge normals/offsets in order, including front rays.
            rows=[[fl(x) for x in r] for r in inp['oracle_halfplanes']]
            checks['wedge_count']=len(hps)==len(rows)
            coefficient_error=0.
            wedge_ok=len(hps)==len(rows)
            for h,r in zip(hps,rows):
                size=math.hypot(*r[:2])
                rn=[x/size for x in r]
                ne=distance(h.normal,rn[:2])
                be=abs(h.offset-rn[2])
                coefficient_error=max(coefficient_error,ne)
                wedge_ok &= ne <= math.radians(TOL['angle_deg']) and be<=1e-8+1e-12*abs(rn[2])
            checks['wedge_coefficients']=bool(wedge_ok)
            errors['normal_l2']=coefficient_error
        else:
            hps=[g.HalfPlane(tuple(map(fl,r[:2])),fl(r[2])) for r in inp['halfplanes']]
        region=g.intersect_halfplanes(hps,policy)
        actual['region']=asdict(region)
        checks['region_status']=region.status=='OK'
        checks['classification']=region.kind==truth['kind']
        if truth['kind'] not in ('EMPTY','UNBOUNDED'):
            vd=vertex_diagnostics(region.vertices,vv,vtol,region.status)
            diagnostics['vertices']=vd
            checks['vertices']=vd['geometry_matches']
            checks['vertex_normalization']=vd['bijection_matches']
            errors['vertex_hausdorff_m']=vd['hausdorff_m']
        rows=[[fl(x) for x in r] for r in inp['oracle_halfplanes']]
        def residual(p, homogeneous=False):
            return max(((r[0]*p[0]+r[1]*p[1]-(0 if homogeneous else r[2]))/math.hypot(*r[:2]) for r in rows),default=0.)
        if truth['kind']!='EMPTY':
            p=region.feasible_point
            bound=1e-8+1e-12*max([1]+[abs(x) for x in (p or [])])
            res=residual(p) if p is not None else None
            checks['feasible_witness']=res is not None and res<=bound
            errors['feasible_residual_m']=res
        if truth['kind']=='UNBOUNDED':
            rd=recession_witness(region.recession_direction,inp['oracle_halfplanes'])
            diagnostics['recession_witness']=rd
            checks['recession_witness']=rd['valid']
            errors['recession_residual']=rd['residual']
        if region.vertices:
            res=max(residual(p) for p in region.vertices)
            checks['vertices_feasible']=res<=vtol
            errors['vertex_constraint_residual_m']=res
    dr=g.diameter(region)
    if len(region.vertices)>=3:
        # Exact orientation on returned binary64 coordinates; no producer predicates.
        pv=[tuple(Fraction.from_float(x) for x in p) for p in region.vertices]
        turns=[]
        for i,p in enumerate(pv):
            q,s=pv[(i+1)%len(pv)],pv[(i+2)%len(pv)]
            turns.append((q[0]-p[0])*(s[1]-q[1])-(q[1]-p[1])*(s[0]-q[0]))
        checks['strictly_convex_ccw']=all(z>0 for z in turns)
    actual['diameter']=asdict(dr)
    errors['diameter_abs_m']=check_diameter(dr,truth,region.vertices,tolerance,checks,'pipeline_diameter_')
    if errors['diameter_abs_m'] is not None:
        errors['diameter_relative']=errors['diameter_abs_m']/max(d,1e-300)
    # Feed exact oracle vertices directly, isolating calipers from intersection/hull.
    if vv:
        isolated=g.diameter(g.Region(g.RegionKind(truth['kind']),vertices=tuple(vv)))
        actual['isolated_diameter']=asdict(isolated)
        errors['isolated_diameter_abs_m']=check_diameter(isolated,truth,vv,tolerance,checks,'isolated_diameter_')
        # Exact ties on float-representable vertices exercise documented lexicographic rule.
        exactly_representable=all(Fraction.from_float(x)==Fraction(q) for p,ep in zip(vv,truth['vertices']) for x,q in zip(p,ep))
        if exactly_representable:
            checks['isolated_tie_rule']=list(isolated.indices or [])==list(min(truth['farthest_pairs']))
    return dict(case_id=c['case_id'], category=c['category'], tags=c['tags'], input=inp,
                expected=truth, actual=clean(actual), errors=clean(errors),
                error=errors.get('diameter_abs_m'), checks=checks, diagnostics=diagnostics, truth_method=c['truth_method'],
                tolerances=dict(length_m=tolerance,vertex_m=vtol), invariant=c.get('invariant'))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--regenerate',action='store_true')
    args=parser.parse_args()
    self_checks=comparator_self_checks()
    source=Path(g.__file__)
    source_hash=hashlib.sha256(source.read_bytes()).hexdigest()
    baseline=json.loads((HERE/'regression_baseline.json').read_text())
    previous={r['case_id']:r for r in baseline['results']}
    if args.regenerate or not (HERE/'cases.jsonl').exists():
        from .generate import main as generate
        generate()
    start=time.monotonic()
    cases=[json.loads(s) for s in (HERE/'cases.jsonl').read_text().splitlines() if s.strip()]
    baseline_recheck=recheck_baseline(baseline,cases)
    results=[]
    for c in cases:
        try:
            r=evaluate(c)
        except Exception as e:
            import traceback
            r=dict(case_id=c['case_id'],category=c['category'],input=c['input'],expected=c['ground_truth'],actual=dict(exception=repr(e),traceback=traceback.format_exc()),error=None,errors={},checks={'no_exception':False},truth_method=c['truth_method'],invariant=c.get('invariant'))
        results.append(r)
    byid={r['case_id']:r for r in results}
    for r in results:
        rel=r.get('invariant')
        if rel:
            base=byid[rel['base']]
            a=r['actual'].get('diameter',{}).get('length')
            b=base['actual'].get('diameter',{}).get('length')
            k=r['actual'].get('region',{}).get('kind')
            bk=base['actual'].get('region',{}).get('kind')
            if rel['kind']!='nonincrease':
                r['checks']['invariant_classification']=k==bk and k is not None
            if a is not None and b is not None:
                delta=a-b*rel['scale']
                tol=1e-8+1e-9*abs(b*rel['scale'])
                r['checks']['invariant_diameter']=delta<=tol if rel['kind']=='nonincrease' else abs(delta)<=tol
            elif r['expected']['kind'] not in ('EMPTY','UNBOUNDED'):
                r['checks']['invariant_diameter']=False
        r['pass']=all(r['checks'].values())
        r['note']='; '.join(k for k,v in r['checks'].items() if not v) or 'all checks passed'
        prior=previous.get(r['case_id'],{})
        single=len(r['input'].get('observations',[]))==1
        known_bug=(single and r['expected']['kind']=='UNBOUNDED' and
                   prior.get('actual',{}).get('region',{}).get('status')=='NUMERICAL_UNRESOLVED')
        vd=r.get('diagnostics',{}).get('vertices',{})
        r['assessment']=dict(
            baseline_pass=prior.get('pass'),current_pass=r['pass'],
            vertex_finding=vd.get('category'),
            confirmed_production_regression=known_bug,
            production_bug_state=('resolved_regression_pass' if r['pass'] else 'confirmed_bug_waiting_for_production_fix') if known_bug else None,
            benchmark_correction=('vertex_failure_attribution_split' if r['case_id'] in baseline_recheck['vertex_attribution_corrected_cases'] else None),
            failure_class=('confirmed_production_bug' if known_bug and not r['pass'] else
                           'production_output_normalization' if not r['pass'] and vd.get('category')=='same_geometry_normalization_defect' else
                           'numerical_tolerance_review' if not r['pass'] and vd.get('category')=='outside_tolerance_needs_numerical_review' else
                           'other_production_or_numerical_failure' if not r['pass'] else None))
    failures=[r for r in results if not r['pass']]
    categories={}
    for category in sorted({r['category'] for r in results}):
        rr=[r for r in results if r['category']==category]
        categories[category]=dict(n_cases=len(rr),n_pass=sum(r['pass'] for r in rr),n_fail=sum(not r['pass'] for r in rr))
    maxima={}
    for key in sorted({k for r in results for k in r['errors']}):
        valid=[(r['errors'].get(key),r['case_id']) for r in results if r['errors'].get(key) is not None]
        if valid:
            value,case_id=max(valid)
            maxima[key]=dict(value=value,case_id=case_id)
    source_unchanged=source_hash==hashlib.sha256(source.read_bytes()).hexdigest()
    assert source_unchanged, 'Production source changed during run; rerun on stable source'
    report=dict(area='q1_geometry',generated_utc=datetime.now(timezone.utc).isoformat(),
                n_cases=len(results),n_pass=len(results)-len(failures),n_fail=len(failures),
                categories=categories,tolerances=TOL,failures=failures,results=results,
                weak_comparisons_excluded=0,max_errors=maxima,
                comparator_self_checks=dict(n_checks=len(self_checks),n_pass=sum(self_checks.values()),checks=self_checks),
                baseline_comparator_recheck=baseline_recheck,
                confirmed_production_bugs=[dict(case_id=r['case_id'],state=r['assessment']['production_bug_state'],
                    historical_status=previous[r['case_id']]['actual']['region']['status'],
                    current_status=r['actual'].get('region',{}).get('status'),
                    current_kind=r['actual'].get('region',{}).get('kind'),
                    note='Single closed forward wedge is nonempty and unbounded; retained without xfail or tolerance exemption.')
                    for r in results if r['assessment']['confirmed_production_regression']],
                benchmark_corrections=[
                    dict(id='recession_certificate_hardening',kind='comparator_hardening',
                         note='Previous comparator already checked homogeneous feasibility, not equality to the saved witness. Explicit finite/nonzero checks and scale-safe normalization now prevent overflow/subnormal mischecks; Fraction dot products independently verify any direction.'),
                    dict(id='vertex_failure_attribution_split',kind='reporting_correction',
                         note='Order was already ignored. Geometric coverage and bijective output normalization are now separate checks. Numeric tolerances unchanged; near duplicates remain normalization failures, not claims of different geometry.',
                         affected_cases=[r['case_id'] for r in results if r['assessment']['benchmark_correction']]),
                    dict(id='vertex_tolerance_review',kind='diagnostic_improvement',
                         note='Records error/tolerance, unmatched vertices, missing upstream output and 1-to-10 tolerance numerical-review band. Review band never changes pass/fail.')],
                baseline_comparison=dict(n_pass=baseline['n_pass'],n_fail=baseline['n_fail'],
                    production_changed=baseline['provenance']['production_sha256']!=source_hash,
                    cases_unchanged=baseline['provenance']['cases_sha256']==hashlib.sha256((HERE/'cases.jsonl').read_bytes()).hexdigest(),
                    fail_to_pass=[r['case_id'] for r in results if previous.get(r['case_id'],{}).get('pass') is False and r['pass']],
                    pass_to_fail=[r['case_id'] for r in results if previous.get(r['case_id'],{}).get('pass') is True and not r['pass']]),
                vertex_findings=dict(Counter(r.get('diagnostics',{}).get('vertices',{}).get('category') for r in results if 'vertices' in r.get('diagnostics',{}))),
                lp_disagreements=[c['case_id'] for c in cases if c['ground_truth'].get('lp',{}).get('agrees_with_exact') is False],
                failure_checks=dict(Counter(k for r in failures for k,v in r['checks'].items() if not v)),
                outcome_breakdown=dict(
                    numerical_unresolved=sum(r['actual'].get('region',{}).get('status')=='NUMERICAL_UNRESOLVED' for r in results),
                    definite_wrong_classification=sum(r['actual'].get('region',{}).get('kind') is not None and r['actual']['region']['kind']!=r['expected']['kind'] for r in results),
                    isolated_diameter_cases=sum('isolated_diameter' in r['actual'] for r in results),
                    isolated_diameter_failures=sum(any(not v for k,v in r['checks'].items() if k.startswith('isolated_')) for r in results)),
                elapsed_seconds=time.monotonic()-start,
                provenance=dict(python=sys.version,platform=platform.platform(),numpy=np.__version__,scipy=scipy.__version__,
                                production_sha256=source_hash,production_stable_during_run=source_unchanged,
                                cases_sha256=hashlib.sha256((HERE/'cases.jsonl').read_bytes()).hexdigest(),seed=20260911))
    (HERE/'report.json').write_text(json.dumps(clean(report),ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    print(json.dumps({k:report[k] for k in ['n_cases','n_pass','n_fail','categories','max_errors','lp_disagreements','failure_checks']},ensure_ascii=False,indent=2))
    return 1 if failures else 0

if __name__=='__main__':
    raise SystemExit(main())
