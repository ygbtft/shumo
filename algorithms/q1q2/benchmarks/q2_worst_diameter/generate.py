"""Independent fixtures/oracles. Deliberately imports no production modules."""
import json
import math
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
SEED = 20260911

def source_points(inp, na=35, nr=113):
    s = np.array(inp.get('S', [0., 0.]))
    c = np.array(inp.get('center', [0., 0.]))
    radius = inp.get('radius', 1800.)
    out = []
    for alpha in np.linspace(-inp.get('eps1', 1.), inp.get('eps1', 1.), na):
        # Slightly inward angular endpoints avoid float boundary ambiguity.
        a = math.radians(inp.get('theta', 0.) + alpha*(1-(1e-8 if 0<inp.get('eps1',1.)<.01 else 1e-12)))
        u = np.array([math.cos(a), math.sin(a)])
        v = s-c
        proj = float(v@u)
        disc = proj*proj-float(v@v)+radius*radius
        if disc < 0:
            continue
        lo, hi = max(5.+1e-7, -proj-math.sqrt(disc)), min(inp.get('rho_hi', 1500.), -proj+math.sqrt(disc))
        if hi < lo:
            continue
        for r in np.linspace(lo+1e-9, hi-1e-9, nr):
            p = s+r*u
            if np.linalg.norm(p-c) <= radius and r > 5:
                out.append(tuple(p))
    out.extend(tuple(p) for p in inp.get("oracle_extra_points", []))
    return sorted(set(out))

def brute(points, q, eps2, same=False):
    """All unordered pairs; each legal pair supplies a realizable feedback.

    Exchanging the finite maxima over feedback and pairs is exact (§6.2).
    No dot/cross angular test, hull, rotating calipers or production helper.
    """
    p = np.asarray(points)
    d = p-np.asarray(q)
    r = np.hypot(d[:,0], d[:,1])
    angles = np.arctan2(d[:,1], d[:,0])
    best, witness, branch, beta = 0., [points[0], points[0]], 'near' if r[0]<=5 else 'direction', None
    for i in range(len(p)):
        delta = np.arctan2(np.sin(angles[i:]-angles[i]), np.cos(angles[i:]-angles[i]))
        near = (r[i]<=5) & (r[i:]<=5)
        direction = (r[i]>5) & (r[i:]>5) & (np.abs(delta)<=math.radians(2*eps2)-1e-14)
        ok = np.ones(len(delta), dtype=bool) if same else near|direction
        ds = np.hypot(p[i:,0]-p[i,0], p[i:,1]-p[i,1])
        ds[~ok] = -1
        j = int(np.argmax(ds))
        if ds[j] > best:
            best = float(ds[j]); witness = [points[i], points[i+j]]
            branch = 'same_station' if same else 'near' if near[j] else 'direction'
            beta = None if branch != 'direction' else math.degrees(angles[i]+delta[j]/2)%360
    return {'lower_bound_m':best, 'pair':witness, 'branch':branch, 'bearing_deg':beta, 'sample_count':len(points)}

def feedback_oracle(points, q, eps2):
    """Enumerate every finite-cloud feedback window, then naive pairs in each K.

    Slide an occupied arc left to its first source bearing. These N windows
    include a superset of every realizable finite-cloud direction posterior.
    """
    from itertools import combinations
    angles=[math.atan2(p[1]-q[1],p[0]-q[0])%(2*math.pi) for p in points]
    radii=[math.dist(p,q) for p in points]
    groups=[('near',None,[p for p,r in zip(points,radii) if r<=5])]
    width=math.radians(2*eps2)
    for angle,r in zip(angles,radii):
        if r<=5:continue
        members=[p for p,a,d in zip(points,angles,radii) if d>5 and (a-angle)%(2*math.pi)<=width]
        groups.append(('direction',math.degrees(angle+width/2)%360,members))
    best=0.;witness=[points[0],points[0]]
    branch='near' if radii[0]<=5 else 'direction'
    beta=None if branch=='near' else math.degrees(angles[0])
    for kind,bearing,members in groups:
        for x,y in combinations(members,2):
            d=math.dist(x,y)
            if d>best:best=d;witness=[x,y];branch=kind;beta=bearing
    return dict(lower_bound_m=best,pair=witness,branch=branch,bearing_deg=beta,feedback_windows=len(groups),sample_count=len(points))

def mec(points):
    """Exhaustive support circles (1/2/3 points), independent of Welzl."""
    from itertools import combinations
    p = np.asarray(points, dtype=float)
    candidates = [(x,0.) for x in p]
    for a,b in combinations(p,2):
        candidates.append(((a+b)/2, float(np.linalg.norm(a-b)/2)))
    for a,b,c in combinations(p,3):
        mat = 2*np.array([b-a,c-a])
        if abs(np.linalg.det(mat)) < 1e-12:
            continue
        center = np.linalg.solve(mat,np.array([b@b-a@a,c@c-a@a]))
        candidates.append((center,float(np.linalg.norm(center-a))))
    valid = [(r,c) for c,r in candidates if np.max(np.linalg.norm(p-c,axis=1))<=r+1e-8]
    r,c = min(valid,key=lambda x:x[0])
    return {'radius_m':r,'center':c.tolist(),'E20_nonempty':r<=20}

def segment(a,b,q,eps2=1.):
    return dict(S=[0.,0.],theta=0.,eps1=0.,center=[(a+b)/2,0.],radius=(b-a)/2,q=q,eps2=eps2,a=a,b=b)

def generate():
    cases=[]
    def add(cid,kind,inp,truth,tags,method):
        cases.append(dict(case_id=cid,kind=kind,input=inp,ground_truth=truth,tags=tags,truth_method=method))
    for a,b,h,e in [(10,100,20,1),(10,100,20,.5),(10,100,20,2),(20,80,40,1),(10,100,200,1)]:
        inp=segment(a,b,[0.,h],e)
        exact=b-max(a,h*math.tan(math.atan(b/h)-math.radians(2*e)))
        add(f'segment_{a}_{b}_{h}_{e}','score',inp,dict(J_exact_m=exact,**brute(source_points(inp),inp['q'],e)),['closed_form','degenerate'],'segment_tangent_closed_form + independent_all_pairs')
    # Boundary-optimal endpoints are constructed analytically, independently of
    # all production grids; move to the legal side of the common-angle limit.
    for i,(a,b,h,e) in enumerate([(10,100,17,.03),(10,100,23,.1),
                                (50,900,41,.25),(500,1400,20,.01),
                                (10,100,200,.07),(10,100,31,3.)]):
        inp=segment(a,b,[0.,h],e)
        inner=max(a,h*math.tan(math.atan(b/h)-math.radians(2*e)))
        inp['oracle_extra_points']=[[min(b,inner+1e-7),0.],[b,0.]]
        gt=dict(J_exact_m=b-inner,analytic_inner_endpoint_m=inner,
                **brute(source_points(inp),inp['q'],e))
        add(f'tangent_segment_{i}','score',inp,gt,
            ['closed_form','adversarial','tangent_optimum','narrow_angle'],
            'segment_closed_form + legal_inward_tangent_pair + independent_all_pairs')
    for i,(width,e,q,side) in enumerate([
        (.001,.03,[400.,150.],1),(.01,.1,[600.,37.],-1),
        (.05,.2,[500.,100.],1),(.0001,.01,[300.,23.],-1),
        (.2,.5,[750.,400.],1),(.01,.03,[400.,-150.],-1)]):
        inp=dict(S=[0.,0.],eps1=width,eps2=e,q=q)
        alpha=math.radians(side*width*(1-1e-9))
        u=[math.cos(alpha),math.sin(alpha)]
        longitudinal=sum(x*y for x,y in zip(q,u))
        h=abs(q[0]*u[1]-q[1]*u[0])
        outer=1500.-1e-7
        inner=longitudinal+h*math.tan(math.atan((outer-longitudinal)/h)-math.radians(2*e)*(1-1e-8))
        inp['oracle_extra_points']=[[r*u[0],r*u[1]] for r in [inner,outer]]
        add(f'tangent_polar_{i}','score',inp,brute(source_points(inp),q,e),
            ['adversarial','narrow_angle','tangent_optimum'],
            'independent_near_angular_boundary_tangent_pair + dense_polar_atan2_all_pairs')
    for i,width in enumerate([.001,.01,.2]):
        inp=dict(S=[0.,0.],q=[0.,0.],eps1=width)
        # Annular-sector diameter: maximum of outer chord and opposite-angle
        # inner/outer corners, with inner radius 5 attained only as a limit.
        e=math.radians(width)
        exact=max(3000*math.sin(e),math.sqrt(1495**2+4*5*1500*math.sin(e)**2))
        add(f'polar_same_station_closed_{i}','score',inp,
            dict(J_exact_m=exact,**brute(source_points(inp),inp['q'],1.,True)),
            ['closed_form','narrow_angle','supremum'],
            'annular_sector_diameter_closed_form + independent_actual_inward_pairs')
    for a,b,q in [(10,18,[14.,0.]),(10,100,[0.,0.])]:
        inp=segment(a,b,q)
        add(f'segment_special_{b}','score',inp,dict(J_exact_m=b-a,**brute(source_points(inp),q,1,q==[0.,0.])),['closed_form','degenerate'],'near_disk_or_same_station_diameter')
    configs=[dict(q=[750.,400.]),dict(q=[500.,0.]),dict(q=[.001,0.]),dict(q=[10.,0.]),dict(q=[0.,0.]),dict(q=[700.,-300.],theta=359.,eps1=1.),dict(q=[500.,2.])]
    rng=np.random.default_rng(SEED)
    configs += [dict(q=[float(rng.uniform(200,700)),float(rng.uniform(-250,250))],eps1=float(rng.uniform(.3,1.))) for _ in range(6)]
    for i,inp in enumerate(configs):
        inp=dict(S=[0.,0.],**inp)
        gt=brute(source_points(inp),inp['q'],1,inp['q']==inp['S'])
        add(f'polar_{i}','score',inp,gt,['adversarial' if i<7 else 'random'],'independent_polar_sampling + atan2_all_pairs_lower_bound')
    for mode in ['epsilon','expansion','nested']:
        add('monotone_'+mode,'monotone',dict(q=[750.,400.],mode=mode),dict(nondecreasing=True),['invariant'],'set_inclusion')
    for a,b,q in [(10,18,[14.,0.]),(10,30,[0.,0.]),(50,86,[0.,0.]),(50,90,[0.,0.]),(50,92,[0.,0.])]:
        inp=segment(a,b,q)
        pts=[[a,0.],[b,0.]]
        gt=mec(pts);gt.update(K_support=pts,H_m=max(math.dist(q,x) for x in pts))
        add(f'clearance_{a}_{b}','clearance',inp,gt,['closed_form','threshold'],'independent_exhaustive_support_circle_on_exact_segment_K')
    for name,inp,pts in [
        ('near_boundary',segment(10,30,[15.,0.]),[[x,0.] for x in [10.,10.0000001,14.,15.,19.9999999,20.,20.0000001,30.]]),
        ('wrap_zero',dict(S=[-100.,0.],q=[0.,0.],eps1=1.),[[r*math.cos(math.radians(a)),r*math.sin(math.radians(a))] for r in [20.,60.,100.] for a in [-1.01,-.99,0.,.99,1.01]]),
        ('singleton',segment(10,30,[0.,20.]),[[20.,0.]])]:
        inp['points']=pts
        add('feedback_'+name,'finite_score',inp,feedback_oracle(pts,inp['q'],1.),['adversarial','degenerate'],'explicit_feedback_window_enumeration_then_naive_all_pairs; exact finite-cloud target only')
    add('short_baseline_select','select',dict(budget=10.),dict(lower_bound_m=1000.,pair=[[500.,0.],[1500.,0.]],angle_bound_deg=math.degrees(math.asin(10/500)+math.asin(10/1500))),['closed_form','adversarial'],'arcsin_short_baseline_bound')
    add('short_baseline_frontier','frontier',dict(budgets=[0.,5.,10.]),dict(lower_bound_m=1000.),['closed_form','invariant'],'arcsin_short_baseline_bound')
    HERE.mkdir(exist_ok=True)
    with (HERE/'cases.jsonl').open('w') as f:
        for c in cases:f.write(json.dumps(c,ensure_ascii=False,allow_nan=False)+'\n')
    print(f'generated {len(cases)} cases',flush=True)
    return cases

if __name__=='__main__':generate()
