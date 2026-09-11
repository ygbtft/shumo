"""Run production APIs against saved independent ground truth."""
from pathlib import Path
from datetime import datetime, timezone
from dataclasses import asdict
from decimal import Decimal, localcontext
import hashlib
import json
import math
import time
import numpy as np
from .generate import HERE, legal, sample, radial, world, LENGTH_TOL, SQUARED_TOL, SEED
from ...feasible import PhysicsConfig, Feedback, build_source_set, check_candidate, posterior_contains
from ...geometry import BearingMeasurement, NumericPolicy


def witness_checks(ans, inp):
    """Validate any returned witness geometrically, never against an oracle point.

    PLAN 5.4(5): signal extrema can be unattained limits.
    PLAN 5.5: a near separator must belong to actual F; an excluded endpoint
    at distance exactly five does not disprove direction membership.
    """
    checks = {}
    p = ans.extremal_source
    if p is None:
        if ans.status == 'OUT':
            checks['separating_witness_present'] = False
        return checks
    p = np.asarray(p)
    r1 = float(np.linalg.norm(p-inp['S']))
    dq = float(np.linalg.norm(p-inp['q']))
    in_closure = bool(legal([p], inp, closure=True)[0])
    # Strict r>5 is not a 1e-8 clearance condition. Resolve near-contact
    # distances on the exact submitted binary64 coordinates using Decimal.
    with localcontext() as ctx:
        ctx.prec = 70
        radius_squared = sum((Decimal.from_float(float(x))-Decimal.from_float(float(y)))**2
                             for x,y in zip(p, inp['S']))
    in_actual = in_closure and radius_squared > Decimal(25)
    residual = dq*dq-max(1000, r1)**2
    checks['witness_closure'] = in_closure
    # A declared limit at the analytic inner circle tolerates representation
    # roundoff; a declared actual world must satisfy the strict inequality.
    checks['witness_attainment'] = bool(in_actual if ans.witness_attained else
                                      in_closure and abs(r1-5) <= 1e-8)
    if ans.status == 'OUT':
        # C_dir is a subset of C_sig, so either kind of separator suffices.
        signal_separator = in_closure and residual > SQUARED_TOL
        near_separator = in_actual and dq <= 5+LENGTH_TOL
        checks['separating_witness_valid'] = bool(
            signal_separator or (inp['checking_direction'] and near_separator))
        # A near separator need not maximize the SIGNAL residual. g_low/g_high
        # are tested separately; imposing that identity rejected valid repairs.
    else:
        checks['witness_residual'] = (ans.max_violation is not None and
                                      abs(residual-ans.max_violation) <= SQUARED_TOL)
    return checks


def check_group(name):
    if name in ('sig_status', 'dir_status'):
        return 'core_membership'
    if 'witness' in name:
        return 'witness_metadata'
    return 'auxiliary'


def summarize_groups(results, cases):
    groups = {}
    for group in ('core_membership', 'witness_metadata', 'auxiliary'):
        rows = []
        for result in results:
            subset = {k:v for k,v in result['checks'].items() if check_group(k)==group}
            result.setdefault('groups', {})[group] = {
                'applicable': bool(subset), 'passed': all(subset.values()) if subset else None,
                'failed_checks': [k for k,v in subset.items() if not v]}
            if subset: rows.append(subset)
        total = sum(len(row) for row in rows)
        passed = sum(sum(row.values()) for row in rows)
        good_cases = sum(all(row.values()) for row in rows)
        groups[group] = dict(n_cases=len(rows), n_pass=good_cases,
            n_fail=len(rows)-good_cases, case_pass_rate=good_cases/len(rows) if rows else None,
            n_checks=total, n_checks_pass=passed, n_checks_fail=total-passed,
            check_pass_rate=passed/total if total else None)
    # Accuracy only among explicit IN/OUT answers on nonempty F. BOUNDARY and
    # UNRESOLVED are visible separately and never quietly counted as correct IN.
    binary = {}
    for mode, member in (('sig','signal_member'), ('dir','direction_member')):
        row = dict(n_decisions=0, n_correct=0, n_incorrect=0,
                   n_boundary=0, n_unresolved=0, n_inconsistent=0)
        for case, result in zip(cases,results):
            gt=case['ground_truth']; status=result['actual'][mode]['status']
            if member not in gt: row['n_inconsistent']+=1
            elif status in ('IN','OUT'):
                row['n_decisions']+=1
                row['n_correct' if (status=='IN')==gt[member] else 'n_incorrect']+=1
            elif status=='BOUNDARY': row['n_boundary']+=1
            else: row['n_unresolved']+=1
        row['accuracy']=row['n_correct']/row['n_decisions'] if row['n_decisions'] else None
        binary[mode]=row
    groups['core_membership']['binary_decisions']=binary
    return groups


def run():
    started=time.perf_counter()
    production_path = HERE.parents[1]/'feasible.py'
    production_sha256_start = hashlib.sha256(production_path.read_bytes()).hexdigest()
    cases=[json.loads(s) for s in (HERE/'cases.jsonl').read_text().splitlines()]
    failures=[]; results=[]; categories={}; cache={}; status_counts={}; witness_counts={}
    def tally(d,k): d[k]=d.get(k,0)+1
    for c in cases:
        inp=c['input']; gt=c['ground_truth']; notes=[]; checks={}; actual={}
        first=BearingMeasurement(inp['S'],inp['theta'],inp['eps'])
        physics=PhysicsConfig(rho_hi=inp['rho_hi'],arena_center=inp['center'],arena_radius=inp['arena_radius'])
        policy=NumericPolicy()
        ss=build_source_set(first,physics,policy)
        actual['source_status']=ss.status
        if 'source_status' in gt:
            checks['inconsistent_state']=ss.status==gt['source_status']
        else: checks['source_nonempty']=ss.status=='OK'
        key=json.dumps({k:v for k,v in inp.items() if k not in ('q','require_direction_modes')},sort_keys=True)
        if key not in cache: cache[key]=sample(inp)
        points,rhos=cache[key]
        # Definition-level source membership probes include exact/near boundaries.
        probes=np.array([world([r,0],inp) for r in (0,4.999999,5,5.000001,1000,inp['rho_hi'],inp['rho_hi']+1e-5)])
        probes=np.vstack((probes,points[::max(1,len(points)//100)]))
        expected=legal(probes,inp,boundary_slack=False)
        relaxed_expected=legal(probes,inp)
        actual['source_probe_boundary_reclassifications']=np.flatnonzero(expected!=relaxed_expected).tolist()
        checks['source_contains']=bool(np.array_equal(ss.contains(probes),expected))
        actual['source_probe_mismatches']=np.flatnonzero(ss.contains(probes)!=expected).tolist()
        # Independent polar interval roots, including angular endpoints.
        aa=np.linspace(-math.radians(inp['eps']),math.radians(inp['eps']),41)
        _,lo,hi,valid=radial(aa,inp)
        radial_ok=True
        for j,a in enumerate(aa):
            rr=ss.radial_interval(float(a))
            if (rr is not None)!=bool(valid[j]): radial_ok=False
            elif rr is not None and (abs(rr.low-lo[j])>1e-7 or abs(rr.high-hi[j])>1e-7 or rr.low_open!=(lo[j]==5)): radial_ok=False
        checks['radial_intervals']=radial_ok
        sample_info={'n_sources':len(points),'n_worlds':2*len(points),'weak_for_IN':True}
        if len(points):
            d=np.linalg.norm(points-inp['q'],axis=1)
            rmin=np.maximum(1000,np.linalg.norm(points-inp['S'],axis=1))
            sample_info.update(max_minimum_rho_violation_m=float(np.max(d-rmin)),max_random_rho_violation_m=float(np.max(d-rhos)),minimum_distance_m=float(np.min(d)))
            checks['sample_no_contradiction']=not (gt.get('signal_member') and np.max(d-rmin)>LENGTH_TOL)
            if gt.get('direction_member'): checks['sample_direction_no_contradiction']=bool(np.min(d)>5-LENGTH_TOL)
        if gt.get('counterexample'):
            w=gt['counterexample']; p=np.array(w['p']); r1=float(np.linalg.norm(p-inp['S'])); dq=float(np.linalg.norm(p-inp['q']))
            checks['truth_counterexample_valid']=bool(legal([p],inp)[0] and max(1000,r1)<=w['rho']+1e-8 and w['rho']<=inp['rho_hi']+1e-8 and (dq>w['rho'] if w['kind']=='no_signal' else dq<=5+1e-8))
        elif gt.get('signal_status')=='OUT' or gt.get('direction_status')=='OUT':
            checks['truth_counterexample_present']=False
        if 'four_disk_status' in gt: checks['two_analytic_oracles_agree']=gt['four_disk_status']==gt['signal_status']
        for direction in (False,True):
            mode='dir' if direction else 'sig'
            ans=check_candidate(ss,inp['q'],direction,policy)
            actual[mode]=asdict(ans); tally(status_counts,mode+':'+ans.status)
            want=gt['direction_status' if direction else 'signal_status']
            acceptable=[want]
            # PLAN explicitly permits numerical uncertainty at 5m contact.
            # Keep exact membership separately; do not count unresolved as IN.
            if direction and 'distance_to_closure' in gt and abs(gt['distance_to_closure']-5)<=LENGTH_TOL and gt['signal_status']!='OUT' and inp['q']!=inp['S']:
                acceptable.append('UNRESOLVED')
            checks[mode+'_status']=ans.status in acceptable
            if gt.get('source_status'):
                checks[mode+'_inconsistency_reason']=ans.reason==gt['source_status']
            if 'g_low' in gt and inp['q']!=inp['S']:
                for field,prod in [('g_low',ans.g_low),('g_high',ans.g_high)]:
                    val=gt[field]
                    checks[mode+'_'+field]=(prod is None if val is None else prod is not None and abs(prod-val)<=SQUARED_TOL)
            for name, valid_witness in witness_checks(ans, dict(inp, checking_direction=direction)).items():
                checks[mode+'_'+name] = valid_witness
            if ans.extremal_source is not None:
                tally(witness_counts, 'attained' if ans.witness_attained else 'limit')
            # Posterior definition check on modest independent probes, not an oracle call.
            for fb in (Feedback('near'),Feedback('direction',33.,1.)):
                delta=probes-inp['q']; rr=np.linalg.norm(delta,axis=1)
                angular=(np.degrees(np.arctan2(delta[:,1],delta[:,0]))-33+180)%360-180
                mask=expected & ((rr<=5) if fb.kind=='near' else ((rr>5)&(np.abs(angular)<=1)))
                if inp['q']==inp['S']:
                    mask=expected & (fb.kind=='direction' and (33-inp['theta']+180)%360-180==0)
                checks['posterior_'+fb.kind]=bool(np.array_equal(posterior_contains(ss,inp['q'],fb,probes,policy),mask))
        bad=[k for k,v in checks.items() if not v]
        ok=not bad
        result={'case_id':c['case_id'],'passed':ok,'checks':checks,'actual':actual,'sampling':sample_info}
        results.append(result)
        for tag in c['categories']:
            row=categories.setdefault(tag,dict(n_cases=0,n_pass=0,n_fail=0)); row['n_cases']+=1; row['n_pass' if ok else 'n_fail']+=1
        if not ok:
            failures.append(dict(case_id=c['case_id'],input=inp,expected=gt,actual=actual,error=None,truth_method=c['truth_method'],note=', '.join(bad)))
        # Limit cache RAM while preserving paired standard scenes.
        if len(cache)>8:
            del cache[next(iter(cache))]
    byid={r['case_id']:r for r in results}
    invariants=[]
    for c in cases:
        pair=c['ground_truth'].get('paired_case')
        if c['case_id'].startswith('four_disk_') and c['case_id'].endswith('_1500'): pair=c['case_id'][:-4]+'1000'
        if pair:
            a=byid[c['case_id']]['actual']; b=byid[pair]['actual']
            invariants.append({'case_id':c['case_id'],'paired_case':pair,'signal_status_equal':a['sig']['status']==b['sig']['status'],'direction_status_equal':a['dir']['status']==b['dir']['status']})
    for inv in invariants:
        byid[inv['case_id']]['checks']['paired_invariant'] = inv['signal_status_equal'] and inv['direction_status_equal']
        if not inv['signal_status_equal'] or not inv['direction_status_equal']:
            row=byid[inv['case_id']]
            if row['passed']:
                row['passed']=False
                c=next(c for c in cases if c['case_id']==inv['case_id'])
                for tag in c['categories']:
                    categories[tag]['n_pass']-=1; categories[tag]['n_fail']+=1
                failures.append(dict(case_id=c['case_id'],input=c['input'],expected=c['ground_truth'],actual=row['actual'],error=None,truth_method=c['truth_method'],note='paired_invariant'))
    breakdown={}
    for f in failures:
        for k in f['note'].split(', '): tally(breakdown,k)
    groups = summarize_groups(results, cases)
    report=dict(groups=groups,area='q2_candidate',generated_utc=datetime.now(timezone.utc).isoformat(),seed=SEED,n_cases=len(cases),n_pass=len(cases)-len(failures),n_fail=len(failures),categories=categories,
        tolerances={'length_m':LENGTH_TOL,'squared_m2':SQUARED_TOL,'world_closed_constraints_m':1e-8,'world_angle_deg':1e-10,'source_and_posterior_probe_closed_slack':0.,'production_policy':asdict(NumericPolicy()),'direction_contact':'UNRESOLVED allowed only at analytically established 5m equality; mathematical membership preserved in cases'},
        failures=failures,weak_comparisons_excluded=len([r for r in results if r['sampling']['n_sources']]),status_counts=status_counts,witness_counts=witness_counts,failure_check_counts=breakdown,
        invariants=invariants,results=results,elapsed_seconds=time.perf_counter()-started,
        source_sha256=hashlib.sha256(production_path.read_bytes()).hexdigest(),
        source_sha256_start=production_sha256_start,
        production_unchanged_during_run=production_sha256_start==hashlib.sha256(production_path.read_bytes()).hexdigest(),cases_sha256=hashlib.sha256((HERE/'cases.jsonl').read_bytes()).hexdigest(),
        notes=['Sampling is corroboration only, excluded as an IN proof; every OUT expectation requires an actual world.','Empty F tested as explicit API error state and UNRESOLVED reason, not mandatory Python exception.','Returned extremal source tested separately for validity, attainment and separation, including direction OUT.'])
    (HERE/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    print(json.dumps({k:report[k] for k in ('n_cases','n_pass','n_fail','failure_check_counts','groups','elapsed_seconds')},indent=2))
    return report

if __name__=='__main__': run()
