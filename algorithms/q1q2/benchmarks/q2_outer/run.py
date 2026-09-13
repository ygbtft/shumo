"""Standard Q2 outer recommendation; production geometry and objective unchanged."""
from pathlib import Path
from dataclasses import asdict, replace
import argparse, hashlib, json, math, time
import numpy as np
from ...geometry import BearingMeasurement, NumericPolicy
from ...feasible import PhysicsConfig, build_source_set, Feedback, check_candidate
from ...q2 import SearchConfig, select_second_point, sample_sources, score_point, boundary_point
from ...run import jsonable
from ...optional.certified import certify
from ...diagnostics import clearance_summary
HERE=Path(__file__).resolve().parent
CFG=SearchConfig(time_budget_s=14400., tie_floor_m=0., tie_multiplier=0.)
SS=build_source_set(BearingMeasurement((0.,0.),0.),PhysicsConfig(),CFG.policy)
def save(name,obj):
    (HERE/name).write_text(json.dumps(jsonable(obj),ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def main():
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['search','refine','certify']);a=p.parse_args()
    if a.stage=='search':
        t=time.monotonic();r=select_second_point(SS,CFG,extra_points=[(750.,400.)]);save('search.json',r)
        print(r.q_best,r.score.J_hat,r.stop_reason,r.completed_stages,time.monotonic()-t,flush=True)
    elif a.stage=='refine':
        refine()
    elif a.stage=='certify':
        certify_final()
def refine():
    # Independent complete standard four-disk bounding rectangle, both signs.
    # x >= 0 and the disks centred at 5*u imply x <= 1005, |y| <= 1000.
    started=time.monotonic();cache={};rows=[];history=[]
    def value(q,level=0):
        q=tuple(float(x) for x in q);key=(q,level)
        if check_candidate(SS,q,False,CFG.policy).status!='IN' or q==(0.,0.):return math.inf
        if key not in cache:
            sm=sample_sources(SS,level,CFG.source_grids,q,inward=CFG.near_offset_m,second_half_width_deg=1.)
            cache[key]=score_point(SS,q,sm,CFG).J_hat
        return cache[key]
    for step in (50.,25.):
        n=0
        for x in np.arange(0,1005.00001,step):
            for y in np.arange(-1000,1000.00001,step):
                q=(float(x),float(y));v=value(q)
                if math.isfinite(v):rows.append(dict(q=q,J_hat=v,step_m=step));n+=1
        history.append(dict(stage='augmented_grid',step_m=step,admissible=n,best=min(rows,key=lambda r:r['J_hat'])))
        print(history[-1],flush=True)
    for deg in np.arange(0,360,1.):
        q=boundary_point(SS,math.radians(float(deg)),replace(CFG,boundary_precision_m=1e-7))
        if q:
            for f in (1.,.999):
                z=tuple(f*x for x in q);v=value(z)
                if math.isfinite(v):rows.append(dict(q=z,J_hat=v,boundary_deg=float(deg),fraction=f))
    save('augmented-grid.json',dict(config=CFG,rows=rows,history=history))
    starts=[]
    for r in sorted(rows,key=lambda r:r['J_hat']):
        if all(math.dist(r['q'],q)>=25 for q in starts):starts.append(tuple(r['q']))
        if len(starts)==12:break
    finals=[]
    for q in starts:
        initial=q;step=25.;trace=[]
        while step>=.1953125:
            opts=[(value((q[0]+dx,q[1]+dy)),(q[0]+dx,q[1]+dy)) for dx in (-step,0,step) for dy in (-step,0,step)]
            v,z=min(opts)
            if v<value(q)-1e-10:q=z
            else:trace.append(dict(step_m=step,q=q,J_hat=value(q)));step/=2
        finals.append(q);history.append(dict(stage='augmented_local',initial=initial,q=q,J_hat=value(q),trace=trace))
        print(history[-1],flush=True)
    # Golden-section boundary refinement around the best positive-y 1-degree sample.
    br=min((r for r in rows if r.get('fraction')==1. and r['q'][1]>0),key=lambda r:r['J_hat'])
    def bq(deg):return boundary_point(SS,math.radians(deg),replace(CFG,boundary_precision_m=1e-7))
    lo,hi=br['boundary_deg']-1.,br['boundary_deg']+1.;ratio=(math.sqrt(5)-1)/2
    aa,bb=hi-ratio*(hi-lo),lo+ratio*(hi-lo);fa,fb=value(bq(aa),2),value(bq(bb),2)
    for _ in range(32):
        if fa<fb:
            hi,bb,fb=bb,aa,fa;aa=hi-ratio*(hi-lo);fa=value(bq(aa),2)
        else:
            lo,aa,fa=aa,bb,fb;bb=lo+ratio*(hi-lo);fb=value(bq(bb),2)
    q=bq(aa if fa<fb else bb)
    # Report a reproducible decimal command coordinate, moved 1e-5 m inward.
    norm=math.hypot(*q);q=tuple(round(x*(1-1e-5/norm),6) for x in q)
    finals.extend([q,(q[0],-q[1]),(750.,400.)])
    final_values=[dict(q=q,J_hat=value(q,2)) for q in dict.fromkeys(finals)]
    best=min(final_values,key=lambda r:r['J_hat']);bestq=tuple(best['q'])
    # Reflect symmetry to publish the north-side representative, then re-evaluate exactly.
    bestq=(bestq[0],abs(bestq[1]));best=dict(q=bestq,J_hat=value(bestq,2))
    sensitivity=[]
    for origin in (bestq,(750.,400.)):
        for step in (1.,5.,25.):
            for dx,dy in ((step,0),(-step,0),(0,step),(0,-step)):
                z=(origin[0]+dx,origin[1]+dy);v=value(z,2)
                sensitivity.append(dict(origin=origin,q=z,offset_m=step,J_hat=v if math.isfinite(v) else None,status='IN' if math.isfinite(v) else 'OUT'))
    save('refined.json',dict(config=CFG,history=history,final_values=final_values,best=best,
        boundary_angle_interval_deg=[lo,hi],boundary_precision_m=1e-7,coordinate_inward_m=1e-5,
        local_min_step_m=.1953125,sensitivity=sensitivity,evaluations=len(cache),elapsed_seconds=time.monotonic()-started,
        status='NUMERICAL_CANDIDATE',scope='Complete augmented 50/25 m grids; 1 degree boundary; 12 local starts; no global outer certificate'))
    print('BEST',best,flush=True)

def certify_final():
    from ...geometry import convex_hull, diameter, Region, RegionKind
    from importlib.metadata import version
    data=json.loads((HERE/'refined.json').read_text());qs=[tuple(data['best']['q']),(750.,400.)]
    finer=((17,49),(33,97),(65,193));fcfg=replace(CFG,source_grids=finer,refine_pairs=True)
    union=set();own={};audits={}
    for q in qs:
        records=[]
        for level in range(3):
            sm=sample_sources(SS,level,CFG.source_grids,q,inward=CFG.near_offset_m,second_half_width_deg=1.)
            score=score_point(SS,q,sm,replace(CFG,refine_pairs=True))
            records.append(dict(kind='source_augmented',grid=CFG.source_grids[level],score=score))
        for factor in (.1,10.):
            pol=replace(CFG.policy,length_abs=CFG.policy.length_abs*factor,angle_abs=CFG.policy.angle_abs*factor,relative=CFG.policy.relative*factor)
            sm=sample_sources(SS,2,CFG.source_grids,q,inward=CFG.near_offset_m*factor,second_half_width_deg=1.)
            records.append(dict(kind='tolerance',factor=factor,score=score_point(SS,q,sm,replace(CFG,policy=pol,refine_pairs=True))))
        sm=sample_sources(SS,2,finer,q,inward=CFG.near_offset_m,second_half_width_deg=1.)
        own[q]=sm;union.update(sm.points)
        shifted=sample_sources(SS,2,finer,q,inward=CFG.near_offset_m,second_half_width_deg=1.,shifted=True)
        shscore=score_point(SS,q,shifted,fcfg)
        records.append(dict(kind='shifted_fine',grid=finer[-1],score=shscore))
        for w in shscore.top_pairs:union.update((w.x,w.y))
        audits[q]=records
        print('audited',q,flush=True)
    common=replace(own[qs[0]],points=tuple(sorted(union)),augmentation_q=None)
    # First fair pass collects locally refined witnesses; second freezes the union.
    for q in qs:
        score=score_point(SS,q,common,fcfg)
        for w in score.top_pairs:union.update((w.x,w.y))
    common=replace(common,points=tuple(sorted(union)))
    rows=[]
    for q in qs:
        score=score_point(SS,q,common,fcfg)
        cert=certify(SS,q,tol=.001,max_nodes=2000000,time_limit_s=1800.,dps=30)
        assert cert.converged and cert.lower_m<=score.J_hat+.001 and score.J_hat<=cert.upper_m
        fb=Feedback(score.witness.branch,score.witness.common_bearing_deg,1.)
        ds=replace(common,points=tuple(sorted(set(common.points)|{score.witness.x,score.witness.y})))
        clear=clearance_summary(SS,q,fb,ds,CFG.policy)
        verts=clear.outer_vertices
        outer_d=diameter(Region(kind=RegionKind.POLYGON,vertices=convex_hull(verts,CFG.policy))).length
        centers=[(r*math.cos(a),r*math.sin(a)) for r in (5.,1000.) for a in (-math.pi/180,math.pi/180)]
        margins=[1000.-math.dist(q,c) for c in centers]
        from mpmath.ctx_iv import MPIntervalContext
        iv=MPIntervalContext();iv.dps=30;ivq=tuple(iv.mpf(x) for x in q)
        residual_intervals=[]
        for r in (5,1000):
            for sign in (-1,1):
                a=sign*iv.pi/180
                residual=(ivq[0]-r*iv.cos(a))**2+(ivq[1]-r*iv.sin(a))**2-1000**2
                assert residual.b<0
                residual_intervals.append([math.nextafter(float(residual.a),-math.inf),math.nextafter(float(residual.b),math.inf)])
        movement=math.hypot(*q)
        row=dict(q=q,score=score,certificate=cert,clearance=clear,outer_diameter_m=outer_d,
            all_feedback_radius_upper_Jung_m=cert.upper_m/math.sqrt(3),
            movement_m=movement,movement_seconds=movement/5,movement_and_detection_seconds=movement/5+5,
            four_disk_distance_margins_m=margins,four_disk_squared_residual_intervals_m2=residual_intervals,check=check_candidate(SS,q,False,CFG.policy),audits=audits[q])
        rows.append(row);print('CERTIFIED',q,cert.lower_m,cert.upper_m,'r_U',clear.r_U,'H_U',clear.H_U,flush=True)
    hashes={n:hashlib.sha256((HERE.parents[1]/n).read_bytes()).hexdigest() for n in ('q2.py','feasible.py','geometry.py','diagnostics.py','optional/certified.py')}
    save('report.json',dict(first=SS.first,physics=SS.physics,config=fcfg,common_samples=len(common.points),
        rows=rows,production_sha256=hashes,versions={n:version(n) for n in ('numpy','mpmath')},
        interval_options=dict(tol=.001,max_nodes=2000000,time_limit_s=1800.,dps=30),
        status='NUMERICAL_CANDIDATE_WITH_CERTIFIED_FIXED_Q_DIAMETER',
        radius_scope='r_U, H_U and outer diameter conditional on each row common feedback; not worst over all feedbacks',
        outer_scope='float64 checked circumscribed polygon, not interval certification',
        lower_improvement_m=rows[1]['certificate'].lower_m-rows[0]['certificate'].upper_m))


if __name__=='__main__':main()
