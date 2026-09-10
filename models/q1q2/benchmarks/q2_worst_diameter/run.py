"""Read-only production runner; independent truth lives in generate.py."""
import hashlib
import inspect
import json
import math
import time
import traceback
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
from .generate import HERE, brute, source_points, mec, generate
from ...geometry import BearingMeasurement, NumericPolicy
from ...feasible import PhysicsConfig, Feedback, build_source_set
from ...q2 import SearchConfig, SourceSamples, score_point, sample_sources, select_second_point, movement_frontier
from ...diagnostics import clearance_summary

TOL={'reachable_pair_m':1e-6,'closed_form_absolute_m':.1,'closed_form_relative':.01,'invariant_m':1e-7,'radius_m':1e-6,'note':'Pair dominance is strict up to floating tolerance. Closed forms separately use max(0.1 m,1% J); this is an approximation acceptance threshold, never a certified error bound.'}

def build(inp):
    return build_source_set(BearingMeasurement(tuple(inp.get('S',[0.,0.])),inp.get('theta',0.),inp.get('eps1',1.)),PhysicsConfig(arena_center=tuple(inp.get('center',[0.,0.])),arena_radius=inp.get('radius',1800.),rho_hi=inp.get('rho_hi',1500.)),NumericPolicy())

def samples(points):return SourceSamples(tuple(map(tuple,points)),2,(35,113))

def production_samples(ss,level,q,eps2=1.):
    # New production API accepts epsilon2; older snapshots remain runnable.
    if 'second_half_width_deg' in inspect.signature(sample_sources).parameters:
        return sample_sources(ss,level,q,second_half_width_deg=eps2)
    return sample_sources(ss,level,q)

def compact(summary):return asdict(summary)

def evaluate(case):
    inp,gt=case['input'],case['ground_truth']
    checks=[];actual={}
    def check(name,passed,expected,value,semantics='correctness'):
        checks.append(dict(name=name,passed=bool(passed),expected=expected,actual=value,semantics=semantics))
    kind=case['kind']
    if kind=='finite_score':
        ss=build(inp);q=tuple(inp['q'])
        result=score_point(ss,q,samples(inp['points']),SearchConfig())
        actual=asdict(result)
        check('explicit_feedback_posterior_diameter',abs(result.J_hat-gt['lower_bound_m'])<=1e-6,gt['lower_bound_m'],result.J_hat,'exact finite-cloud maximum, not continuous J')
    elif kind=='score':
        ss=build(inp);q=tuple(inp['q']);cfg=SearchConfig(second_half_width_deg=inp.get('eps2',1.))
        prod=production_samples(ss,2,q,cfg.second_half_width_deg)
        score=score_point(ss,q,prod,cfg)
        actual=dict(J_hat=score.J_hat,sample_count=len(prod.points),status=score.status,witness=asdict(score.witness) if score.witness else None)
        lower=gt['lower_bound_m']
        check('independent_reachable_pair_dominance',score.J_hat>=lower-TOL['reachable_pair_m'],lower,score.J_hat,'independent lower-bound approximation; not exact J')
        actual['underestimate_m']=max(0.,lower-score.J_hat)
        cloud_truth=brute(prod.points,q,cfg.second_half_width_deg,q==ss.first.position)
        actual['production_cloud_independent_oracle']=cloud_truth
        check('production_cloud_pair_enumeration',score.J_hat>=cloud_truth['lower_bound_m']-1e-6,cloud_truth['lower_bound_m'],score.J_hat,'independent strict finite-cloud lower bound; equality is not required for threshold-band pairs')
        # Isolate pair implementation from production sampling on an identical independent cloud.
        independent=source_points(inp)
        own=score_point(ss,q,samples(independent),cfg)
        check('same_cloud_pair_enumeration',own.J_hat>=lower-1e-6,lower,own.J_hat,'independent strict finite-cloud lower-bound dominance')
        if 'J_exact_m' in gt:
            exact=gt['J_exact_m'];gap=score.J_hat-exact
            actual['closed_form_signed_gap_m']=gap
            refined=score_point(ss,q,prod,replace(cfg,refine_pairs=True))
            actual['refined_J_hat']=refined.J_hat
            actual['refined_closed_form_signed_gap_m']=refined.J_hat-exact
            check('refined_closed_form_approximation',abs(refined.J_hat-exact)<=max(.1,.01*exact),exact,refined.J_hat,'continuous J approximation after default pair refinement')
            check('refined_reachable_pair_dominance',refined.J_hat>=lower-1e-6,lower,refined.J_hat,'independent lower bound after default pair refinement')
            check('closed_form_approximation',abs(gap)<=max(.1,.01*exact),exact,score.J_hat,'continuous J approximation, not exact equality')
        levels=[production_samples(ss,k,q,cfg.second_half_width_deg) for k in range(3)]
        check('sample_sources_nested',all(set(a.points)<=set(b.points) for a,b in zip(levels,levels[1:])),True,[len(x.points) for x in levels])
        actual['missing_nested_samples']=[dict(from_level=k,to_level=k+1,count=len(set(a.points)-set(b.points)),examples=sorted(set(a.points)-set(b.points))[:4]) for k,(a,b) in enumerate(zip(levels,levels[1:]))]
        values=[score_point(ss,q,x,cfg).J_hat for x in levels]
        actual['nested_score_values_m']=values
        check('q_augmented_score_monotonicity',all(b>=a-1e-7 for a,b in zip(values,values[1:])),'nondecreasing',values)
        if score.witness:
            w=score.witness
            try:
                v=regression_target(inp,q,dict(pair=[w.x,w.y],branch=w.branch,bearing_deg=w.common_bearing_deg))
                check('reported_witness_reachable',abs(v['distance_m']-w.distance_m)<=1e-6,w.distance_m,v['distance_m'])
            except AssertionError:
                check('reported_witness_reachable',False,'independent common-feedback validation',asdict(w))
    elif kind=='monotone':
        mode=inp['mode'];q=tuple(inp['q']);cfg=SearchConfig();ss=build({})
        if mode=='epsilon':
            common=sample_sources(ss,2,q)
            values=[score_point(ss,q,common,replace(cfg,second_half_width_deg=e)).J_hat for e in [.25,.5,1.,2.,4.]]
        elif mode=='nested':
            values=[score_point(ss,q,sample_sources(ss,k,q),cfg).J_hat for k in range(3)]
        else:
            values=[];points=set()
            for width in [.25,.5,1.]:
                obj=build(dict(eps1=width))
                points.update(source_points(dict(eps1=width),13,47))
                values.append(score_point(obj,q,samples(sorted(points)),cfg).J_hat)
            # The wider standard sector is analytically guaranteed-signal at q.
            e=math.radians(1);x,y=q
            g_low=max((x-r*math.cos(a))**2+(y-r*math.sin(a))**2-1000**2 for r in [5,1000] for a in [-e,e])
            g_high=x*x+y*y-2000*(x*math.cos(e)-abs(y)*math.sin(e))
            check('expanded_F_q_guaranteed_signal',max(g_low,g_high)<0,'both <= 0',[g_low,g_high])
        actual['values_m']=values
        check('monotonicity',all(b>=a-1e-7 for a,b in zip(values,values[1:])),'nondecreasing',values)
    elif kind=='clearance':
        ss=build(inp);q=tuple(inp['q']);near=gt['H_m']<=5
        fb=Feedback('near') if near else Feedback('direction',0.,1.)
        summary=clearance_summary(ss,q,fb,samples(gt['K_support']),NumericPolicy())
        actual=compact(summary)
        r=gt['radius_m']
        check('conditional_radius',abs(summary.R_hat-r)<=1e-6,r,summary.R_hat)
        if r>20+1e-6:
            expected='NOT_YET_GUARANTEED'
            check('impossibility_evidence',bool(summary.impossibility_witness),True,summary.impossibility_witness)
        elif abs(r-20)<=1e-6:
            expected='NOT_YET_GUARANTEED' # conservative strict-margin policy, E20 still nonempty
        elif gt['H_m']<20-1e-6:expected='ON_SITE'
        else:expected='MOVE_TO_COVER_CENTER'
        check('clearance_three_state',summary.status==expected,expected,summary.status,'R=20 may remain unresolved under the documented margin policy')
        if summary.status!='NOT_YET_GUARANTEED':
            check('no_false_E20_guarantee',gt['E20_nonempty'],True,gt['E20_nonempty'])
    else:
        ss=build({})
        # Bounded regression profile, explicitly distinct from the production default resolution.
        cfg=SearchConfig(station_steps_m=(10.,5.),source_grids=((3,9),(5,17),(9,33)),starts=2,pair_starts=2,pair_rounds=2,station_initial_step_m=5.,station_min_step_m=2.5,boundary_step_deg=45.,time_budget_s=90.)
        results=([select_second_point(ss,replace(cfg,movement_budget_m=inp['budget']))] if kind=='select' else movement_frontier(ss,inp['budgets'],cfg))
        actual={'config':asdict(cfg),'results':[]}
        for result in results:
            budget=result.config.movement_budget_m
            row=dict(budget=budget,q_best=result.q_best,J_hat=result.diameter_estimate_m,status=result.status,stop_reason=result.stop_reason,completed_stages=result.completed_stages,tie_threshold_m=result.tie_threshold_m,clearance_diagnostics=[compact(c) for c in result.clearance_diagnostics])
            actual['results'].append(row)
            if budget==0:
                check('zero_budget_no_distinct_point',result.q_best is None,None,result.q_best)
                check('zero_budget_baseline_lower_bound',result.baseline is not None and result.baseline.J_hat>=1000-1e-6,1000,result.baseline.J_hat if result.baseline else None)
                continue
            check(f'B{budget}_distinct_recommendation',result.q_best is not None and result.q_best!=ss.first.position,'distinct point',result.q_best)
            if result.q_best is None:continue
            check(f'B{budget}_budget',math.dist(result.q_best,ss.first.position)<=budget+1e-6,budget,math.dist(result.q_best,ss.first.position))
            check(f'B{budget}_analytic_lower_bound',result.score.J_hat>=1000-1e-6,1000,result.score.J_hat)
            own=brute(source_points({}),result.q_best,1.)
            row['independent_oracle']=own
            check(f'B{budget}_oracle_dominance',result.score.J_hat>=own['lower_bound_m']-1e-6,own['lower_bound_m'],result.score.J_hat,'independent reachable lower bound')
            minimum=min((r.score.J_hat for r in result.alternatives),default=result.score.J_hat)
            tie=result.tie_threshold_m if result.tie_threshold_m is not None else cfg.tie_floor_m
            eligible=[r for r in result.alternatives if r.score.J_hat<=minimum+tie]
            if eligible:
                winner=min(eligible,key=lambda r:(r.movement_m,r.q))
                check(f'B{budget}_tie_movement_order',result.q_best==winner.q,winner.q,result.q_best,'ranking contract on returned candidates; not proof of global optimum')
            check(f'B{budget}_diagnostics_present',bool(result.clearance_diagnostics),True,bool(result.clearance_diagnostics))
            for j,summary in enumerate(result.clearance_diagnostics):
                if summary.support_points:
                    radius=mec(summary.support_points)['radius_m']
                    check(f'B{budget}_conditional_R_support_{j}',abs(summary.R_hat-radius)<=1e-6,radius,summary.R_hat,'support consistency; not exact full posterior radius')
                if summary.status!='NOT_YET_GUARANTEED':
                    # Independently screen a dense cloud for this particular feedback.
                    pts=source_points({});fb=summary.feedback;kept=[]
                    for p in pts:
                        d=math.dist(p,result.q_best)
                        a=math.degrees(math.atan2(p[1]-result.q_best[1],p[0]-result.q_best[0]))
                        if (d<=5 if fb.kind=='near' else d>5 and abs((a-fb.bearing_deg+180)%360-180)<=fb.half_width_deg):kept.append(p)
                    center=result.q_best if summary.status=='ON_SITE' else summary.cover_center
                    check(f'B{budget}_clearance_claim_{j}',all(math.dist(center,p)<=20+1e-6 for p in kept),'all independently sampled K covered',len(kept),'necessary sampled check only')
        if kind=='frontier':
            vals=[r.score.J_hat if r.score else r.baseline.J_hat for r in results]
            check('frontier_nonincreasing',all(b<=a+1e-7 for a,b in zip(vals,vals[1:])),'nonincreasing',vals,'numerical frontier invariant')
    return actual,checks

def regression_target(inp, q, truth):
    """Portable concrete worlds, verified without any production predicate."""
    pair=truth['pair'];s=inp.get('S',[0.,0.]);same=tuple(q)==tuple(s)
    branch=truth['branch']
    beta=inp.get('theta',0.) if same else truth.get('bearing_deg')
    kind='direction' if same or branch=='direction' else 'near'
    eps=inp.get('eps1',1.) if same else inp.get('eps2',1.)
    worlds=[]
    for p in pair:
        r1=math.dist(p,s);r2=math.dist(p,q)
        a1=math.degrees(math.atan2(p[1]-s[1],p[0]-s[0]))
        a2=math.degrees(math.atan2(p[1]-q[1],p[0]-q[0]))
        first_error=abs((a1-inp.get('theta',0.)+180)%360-180)
        second_error=None if beta is None else abs((a2-beta+180)%360-180)
        legal=(r1>5 and r1<=inp.get('rho_hi',1500.)+1e-9
               and math.dist(p,inp.get('center',[0.,0.]))<=inp.get('radius',1800.)+1e-9
               and first_error<=inp.get('eps1',1.)+1e-10
               and (r2<=5 if kind=='near' else r2>5 and second_error<=eps+1e-10))
        rho=max(1000.,r1,r2)
        legal=legal and rho<=inp.get('rho_hi',1500.)+1e-9
        if not legal:raise AssertionError('independent regression witness is not realizable')
        worlds.append(dict(source=p,rho_m=rho,first_range_m=r1,second_range_m=r2,
                           first_error_deg=first_error,second_error_deg=second_error))
    distance=math.dist(*pair)
    return dict(source_coordinates=pair,q=q,
                common_feedback=dict(kind=kind,bearing_deg=beta,half_width_deg=eps,
                                     same_station_reuses_first=same),
                distance_m=distance,tolerance_m=TOL['reachable_pair_m'],
                required_J_hat_min_m=distance-TOL['reachable_pair_m'],
                independent_validation='raw_distance_and_atan2; float boundary slack 1e-9 m / 1e-10 deg',
                worlds=worlds)

def classify_value(inp,q,value,truth,exact=None,profile='primary'):
    target=regression_target(inp,q,truth)
    lower=target['distance_m'];threshold=None if exact is None else max(.1,.01*exact)
    grade=('A' if value<lower-TOL['reachable_pair_m'] else
           'B' if exact is not None and abs(value-exact)>threshold else 'C')
    return dict(grade=grade,label={'A':'低估','B':'逼近不够','C':'通过'}[grade],
                profile=profile,J_hat=value,independent_reachable_lower_bound_m=lower,
                underestimate_m=max(0.,lower-value),closed_form_J_m=exact,
                closed_form_signed_gap_m=None if exact is None else value-exact,
                approximation_threshold_m=threshold,
                regression_target=target if grade=='A' else None)

def classify_case(case,actual):
    inp=case['input'];gt=case['ground_truth'];kind=case['kind']
    assessments=[];refined=[]
    if 'exception' in actual:return None,assessments,refined
    if kind in ('score','finite_score'):
        truth=gt
        cloud=actual.get('production_cloud_independent_oracle')
        if cloud and cloud['lower_bound_m']>truth['lower_bound_m']:truth=cloud
        assessments.append(classify_value(inp,inp['q'],actual['J_hat'],truth,gt.get('J_exact_m')))
        if 'refined_J_hat' in actual:
            refined.append(classify_value(inp,inp['q'],actual['refined_J_hat'],truth,gt.get('J_exact_m'),'refined'))
    elif kind in ('select','frontier'):
        for row in actual['results']:
            if row.get('independent_oracle'):
                assessment=classify_value({},row['q_best'],row['J_hat'],row['independent_oracle'])
                assessment['budget_m']=row['budget'];assessments.append(assessment)
    grade=min((x['grade'] for x in assessments),default=None)
    return grade,assessments,refined

def main():
    if not (HERE/'cases.jsonl').exists():generate()
    cases=[json.loads(x) for x in (HERE/'cases.jsonl').read_text().splitlines()]
    production_paths=[HERE.parents[1]/name for name in ['q2.py','diagnostics.py','feasible.py','geometry.py']]
    hashes_before={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in production_paths}
    rows=[];started=time.monotonic()
    for c in cases:
        start=time.monotonic()
        try:
            actual,checks=evaluate(c)
            grade,assessments,refined=classify_case(c,actual)
        except Exception as e:
            grade,assessments,refined=None,[],[]
            actual={'exception':repr(e),'traceback':traceback.format_exc()};checks=[dict(name='execution',passed=False,expected='successful execution',actual=repr(e),semantics='execution')]
        passed=all(x['passed'] for x in checks)
        rows.append(dict(case_id=c['case_id'],grade=grade,grade_label={'A':'低估','B':'逼近不够','C':'通过',None:'不适用或执行异常'}[grade],J_assessments=assessments,refined_J_assessments=refined,regression_targets=[a['regression_target'] for a in assessments if a['grade']=='A'],passed=passed,input=c['input'],expected=c['ground_truth'],actual=actual,checks=checks,truth_method=c['truth_method'],tags=c['tags'],elapsed_seconds=time.monotonic()-start))
        print(c['case_id'],grade or 'N/A','PASS' if passed else 'FAIL',','.join(x['name'] for x in checks if not x['passed']),flush=True)
    categories={}
    for row in rows:
        for tag in row['tags']:
            entry=categories.setdefault(tag,dict(n_cases=0,n_pass=0,n_fail=0))
            entry['n_cases']+=1;entry['n_pass' if row['passed'] else 'n_fail']+=1
    report=dict(area='q2_worst_diameter',generated_utc=datetime.now(timezone.utc).isoformat(),n_cases=len(rows),n_pass=sum(r['passed'] for r in rows),n_fail=sum(not r['passed'] for r in rows),categories=categories,tolerances=TOL,failures=[r for r in rows if not r['passed']],results=rows,weak_comparisons_excluded=0,elapsed_seconds=time.monotonic()-started,production_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [HERE.parents[1]/'q2.py',HERE.parents[1]/'diagnostics.py',HERE.parents[1]/'feasible.py']},scope_notes=['J_hat is NUMERICAL_CANDIDATE, not a certified upper bound. Strict oracle dominance is the user-requested adequacy criterion; a failure can expose insufficient sampling rather than incorrect pair algebra.','Selection tie order is checked on returned candidates; no global continuous optimum certificate is claimed. Conditional R support checks do not certify full K.','Known exact segment K checks independently decide E20. At equality R=20, conservative NOT_YET_GUARANTEED is valid, not mathematical impossibility.'])
    hashes_after={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in production_paths}
    report.update(schema_version=2,grade_scope='Primary J assessments only; refined profiles and non-J contracts are separate. C does not certify the continuous supremum or waive auxiliary failures.',
                  grade_definitions={'A':'低估: J_hat < independently realizable pair distance - 1e-6 m; correctness regression',
                                     'B':'逼近不够: no A, but closed-form absolute gap exceeds max(0.1 m, 1% exact J); numerical accuracy',
                                     'C':'通过: applicable reachable-pair and closed-form criteria pass'},
                  grade_counts={g:sum(row['grade']==g for row in rows) for g in ['A','B','C']},
                  n_grade_not_applicable=sum(row['grade'] is None for row in rows),
                  grade_case_ids={g:[row['case_id'] for row in rows if row['grade']==g] for g in ['A','B','C']},
                  refined_grade_counts={g:sum(a['grade']==g for row in rows for a in row['refined_J_assessments']) for g in ['A','B','C']},
                  regression_targets=[dict(case_id=row['case_id'],input=row['input'],**t) for row in rows for t in row['regression_targets']],
                  non_J_contract_cases=[dict(case_id=row['case_id'],passed=row['passed']) for row in rows if row['grade'] is None],
                  J_passing_cases_with_other_check_failures=[row['case_id'] for row in rows if row['grade']=='C' and not row['passed']],
                  legacy_pass_fail_note='n_pass/n_fail and failures retain all-check compatibility; use grade_counts for mutually exclusive A/B/C J results.',
                  production_sha256=hashes_before,production_sha256_after=hashes_after,
                  production_unchanged_during_run=hashes_before==hashes_after)
    (HERE/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    print(json.dumps({k:report[k] for k in ['n_cases','grade_counts','n_grade_not_applicable','refined_grade_counts','n_pass','n_fail','elapsed_seconds']}),flush=True)
    return 1 if report['n_fail'] else 0

if __name__=='__main__':raise SystemExit(main())
