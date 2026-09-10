"""Independent analytic and definition-level oracles; never imports production code."""
from pathlib import Path
import json
import math
import numpy as np

HERE = Path(__file__).resolve().parent
SEED = 20260911
LENGTH_TOL = 1e-7
SQUARED_TOL = 1e-5


def local(q, inp):
    t = math.radians(inp['theta'])
    x, y = np.asarray(q) - inp['S']
    return np.array([x*math.cos(t)+y*math.sin(t), -x*math.sin(t)+y*math.cos(t)])


def world(p, inp):
    t = math.radians(inp['theta'])
    x, y = p
    return [inp['S'][0]+x*math.cos(t)-y*math.sin(t), inp['S'][1]+x*math.sin(t)+y*math.cos(t)]


def legal(points, inp, closure=False):
    p = np.atleast_2d(points)
    d = p - inp['S']
    r = np.linalg.norm(d, axis=1)
    a = (np.degrees(np.arctan2(d[:,1], d[:,0]))-inp['theta']+180)%360-180
    # Only roundoff allowance on closed constraints; near exclusion stays strict.
    return ((r >= 5-1e-8 if closure else r > 5) & (r <= inp['rho_hi']+1e-8)
            & (np.abs(a) <= inp['eps']+1e-10)
            & (np.linalg.norm(p-inp['center'], axis=1) <= inp['arena_radius']+1e-8))


def radial(alpha, inp):
    t = np.radians(inp['theta']) + np.asarray(alpha)
    u = np.column_stack((np.cos(t), np.sin(t)))
    z = np.asarray(inp['S'])-inp['center']
    b = u@z
    disc = b*b + inp['arena_radius']**2-z@z
    root = np.sqrt(np.maximum(0, disc))
    lo = np.maximum(5., -b-root)
    hi = np.minimum(inp['rho_hi'], -b+root)
    valid = (disc >= 0) & (hi >= lo) & (hi > 5)
    return u, lo, hi, valid


def sample(inp):
    """2049 angular x 129 radial grid plus 12000 independently jittered worlds."""
    rng = np.random.default_rng(SEED)
    a = np.linspace(-math.radians(inp['eps']), math.radians(inp['eps']), 2049)
    u, lo, hi, valid = radial(a, inp)
    u, lo, hi = u[valid], lo[valid], hi[valid]
    if not len(u):
        return np.empty((0,2)), np.empty(0)
    lo = np.where(lo == 5, 5+1e-8, lo)
    rr = lo[:,None]+(hi-lo)[:,None]*np.linspace(0,1,129)
    grid = (np.asarray(inp['S'])+rr[:,:,None]*u[:,None,:]).reshape(-1,2)
    a = rng.uniform(-math.radians(inp['eps']),math.radians(inp['eps']),12000)
    u, lo, hi, valid = radial(a,inp)
    rr = lo+(hi-lo)*rng.random(len(lo))
    random = np.asarray(inp['S'])+rr[:,None]*u
    points = np.vstack((grid, random[valid]))
    points = points[legal(points,inp)]
    rmin = np.maximum(1000, np.linalg.norm(points-inp['S'],axis=1))
    # The minimum rho is decisive; also exercise independently chosen larger rho.
    rho = rmin+(inp['rho_hi']-rmin)*rng.random(len(points))
    return points, rho


def sector_oracle(inp, low=5., high=None):
    """Exact 1-D polar extrema for a full sector / clipped zero-width ray.

    Low residual is convex in r, high residual affine in r; extrema use
    radial endpoints. Angular extrema are endpoints or alignment/opposition.
    This does not build or enumerate production boundary pieces.
    """
    high = inp['rho_hi'] if high is None else high
    q = local(inp['q'],inp)
    eps = math.radians(inp['eps'])
    phi = math.atan2(q[1],q[0])
    angles = [-eps,eps]
    for a in (phi,phi+math.pi,phi-math.pi):
        if -eps <= a <= eps:
            angles.append(a)
    rs = sorted(set([low, high]+([1000.] if low<=1000<=high else [])))
    candidates = [(r*np.array([math.cos(a),math.sin(a)]),r) for r in rs for a in angles]
    residuals = [(float(np.sum((q-p)**2)-max(1000,r)**2),p,r) for p,r in candidates]
    v,p,r = max(residuals,key=lambda x:x[0])
    gl = max((v for v,p,r in residuals if r<=1000),default=None)
    gh = max((v for v,p,r in residuals if r>=1000),default=None)
    nearest_angle = min(eps,max(-eps,phi))
    u = np.array([math.cos(nearest_angle),math.sin(nearest_angle)])
    nr = min(high,max(low,float(q@u)))
    near = nr*u
    dist = float(np.linalg.norm(q-near))
    attained = nr > 5+1e-8
    sig = 'OUT' if v>SQUARED_TOL else 'IN' if v < -SQUARED_TOL else 'BOUNDARY'
    if np.array_equal(q,np.zeros(2)):
        sig = 'IN'  # API explicitly represents the known S invariant as IN.
    direction_member = dist>5+LENGTH_TOL or (abs(dist-5)<=LENGTH_TOL and not attained)
    ds = sig
    if sig != 'OUT':
        ds = 'OUT' if dist<5-LENGTH_TOL or (abs(dist-5)<=LENGTH_TOL and attained) else sig
    witness = None
    if sig == 'OUT':
        # An excluded r=5 supremum must be moved into F before becoming a world.
        for delta in (0.,1e-9,1e-8,1e-7,1e-6,1e-5,.001):
            rp = r+delta
            pp = p*(rp/r)
            if rp>5 and rp<=high and np.linalg.norm(q-pp)>max(1000,rp):
                witness = {'p':world(pp,inp),'rho':max(1000,rp),'kind':'no_signal'}
                break
    elif ds == 'OUT':
        if nr <= 5+1e-8:
            nr = 5+1e-6
            near = nr*u
        witness = {'p':world(near,inp),'rho':max(1000,nr),'kind':'near'}
    return {'signal_status':sig,'direction_status':ds,'signal_member':sig!='OUT',
            'direction_member':sig!='OUT' and direction_member,'g_low':gl,'g_high':gh,
            'distance_to_closure':dist,'nearest_attained':attained,'counterexample':witness}


def base(q, **kw):
    inp = dict(S=[0.,0.],theta=0.,eps=1.,center=[0.,0.],arena_radius=1800.,rho_hi=1500.,q=list(q))
    inp.update(kw)
    return inp


def generate():
    rng = np.random.default_rng(SEED)
    cases=[]
    def add(name,inp,tags,oracle='sector',bounds=None,extra=None):
        if oracle=='empty':
            truth={'source_status':'INCONSISTENT_FIRST_OBSERVATION','signal_status':'UNRESOLVED','direction_status':'UNRESOLVED'}
        else:
            truth=sector_oracle(inp,*(bounds or (5.,None)))
        if extra: truth.update(extra)
        cases.append(dict(case_id=name,input=inp,ground_truth=truth,truth_method=oracle,categories=tags))
    e=math.radians(1)
    edge=5*math.cos(e)+math.sqrt(1000**2-25*math.sin(e)**2)
    fixed=[[0,0],[750,400],[500,0],[5,0],[10,0],[-1,0],[2000,0],[0,1000]]
    fixed += [[edge+d,0] for d in (-1e-5,0,1e-5)]
    fixed += [[1e-6,0],[-1e-6,0]]
    # Boundary points along 40 rays: solve each disk quadratic for exit radius.
    centers=[r*np.array([math.cos(e),s*math.sin(e)]) for r in (5,1000) for s in (-1,1)]
    for a in np.linspace(-1.5,1.5,40):
        u=np.array([math.cos(a),math.sin(a)])
        limit=min(float(u@c)+math.sqrt(float(u@c)**2+1000**2-float(c@c)) for c in centers)
        fixed.extend([(limit+d)*u for d in (-1e-5,0,1e-5)])
    fixed += list(rng.uniform([-200,-1200],[1600,1200],size=(100,2)))
    for i,q in enumerate(fixed):
        for hi in (1000.,1500.):
            inp=base(q,rho_hi=hi)
            margins=[float(np.linalg.norm(np.asarray(q)-c)-1000) for c in centers]
            disk_status='OUT' if max(margins)>1e-8 else 'IN' if max(margins)<-1e-8 else 'BOUNDARY'
            if np.linalg.norm(q)==0: disk_status='IN'
            add(f'four_disk_{i}_{int(hi)}',inp,['closed_form','four_disks','outer_radius_invariance']+(['random'] if i>=133 else ['adversarial']),
                extra={'four_disk_status':disk_status,'four_disk_margins_m':margins})
    # Whole scene transforms include target center, first station and q.
    for i in range(24):
        angle=float(rng.uniform(-180,180)); shift=rng.uniform(-2000,2000,2).tolist()
        inp=base([0,0],S=shift,center=shift,theta=angle)
        inp['q']=world(fixed[i],inp)
        add(f'rigid_{i}',inp,['rigid_transform','closed_form'],extra={'paired_case':f'four_disk_{i}_1500'})
    # Exact zero-width sectors include excluded vs attained 5m equality.
    for i,q in enumerate([[0,0],[5,5],[5,5+1e-6],[5,5-1e-6],[10,0],[100,5],[100,5+1e-6],[100,5-1e-6],[0,0.0001]]):
        add(f'ray_{i}',base(q,eps=0),['degenerate','direction_equality','closed_form'])
    # Outside arena: S=(2000,0), inward ray F is exactly [200,1500].
    for i,q in enumerate([[2000,0],[1805,0],[1805+1e-6,0],[1805-1e-6,0],[1700,5],[1500,300],[3000,0]]):
        add(f'outside_ray_{i}',base(q,S=[2000.,0.],theta=180.,eps=0),['outside_arena','degenerate','closed_form'],'clipped_ray',(200.,1500.))
    for i,q in enumerate([[0,0],[200,5],[1200,0]]):
        add(f'tangent_point_{i}',base(q,center=[200.,10.],arena_radius=10.,eps=0),['degenerate','tangent_point','closed_form'],'clipped_ray',(200.,200.))
    # Nonzero-width clipped arenas: rigorous IN from a larger full sector,
    # rigorous OUT only from an actual sampled violating world.
    for j in range(6):
        inp=base([0,0],S=[1900.+j*100,0.],theta=180.+j,eps=1.+j)
        points,rhos=sample(inp)
        for k,q in enumerate([inp['S'],[inp['S'][0]-200,300],[inp['S'][0]+200,600],[1000.,-500.]]):
            inp2=dict(inp,q=list(q)); gt=sector_oracle(inp2)
            if gt['signal_status']=='OUT':
                dist=np.linalg.norm(points-q,axis=1); rmin=np.maximum(1000,np.linalg.norm(points-inp['S'],axis=1))
                ix=int(np.argmax(dist-rmin))
                if dist[ix]-rmin[ix] <= 1e-6: continue
                w={'p':points[ix].tolist(),'rho':float(rmin[ix]),'kind':'no_signal'}
                gt={'signal_status':'OUT','direction_status':'OUT','signal_member':False,'direction_member':False,'counterexample':w}
            else:
                # Superset proves IN, but extrema need not equal clipped extrema.
                if gt['direction_status']=='OUT': continue
                gt={k:v for k,v in gt.items() if k not in ('g_low','g_high','distance_to_closure','nearest_attained')}
            cases.append(dict(case_id=f'clipped_{j}_{k}',input=inp2,ground_truth=gt,truth_method='superset_certificate_or_actual_world',categories=['outside_arena','clipped','definition']))
    for i,inp in enumerate([base([4000,0],S=[4000.,0.],theta=0),base([3301,0],S=[3301.,0.],theta=180),base([1805,0],S=[1805.,0.],theta=0)]):
        add(f'empty_{i}',inp,['empty','inconsistent','degenerate'],'empty')
    # Exact 5m-only contact: small target disk tangent at excluded inner endpoint.
    add('empty_only_near_contact',base([0,0],center=[-5.,0.],arena_radius=10.,eps=0),['empty','excluded_boundary','degenerate'],'empty')
    # Additional membership/posterior probes are defined directly by distances and angles.
    for c in cases:
        c['input']['require_direction_modes']=[False,True]
        if c['case_id'] in ('four_disk_1_1000','four_disk_1_1500'):
            c['ground_truth']['hand_example'] = {
                'distance_r1000_m': math.sqrt(1722500-2000*(750*math.cos(e)-400*math.sin(e))),
                'distance_r5_limit_m': math.sqrt(750**2+400**2+25-10*(750*math.cos(e)-400*math.sin(e))),
                'g_high_m2':750**2+400**2-2000*(750*math.cos(e)-400*math.sin(e)),
                'wedge_distance_m':400*math.cos(e)-750*math.sin(e)}
    with (HERE/'cases.jsonl').open('w') as f:
        for c in cases: f.write(json.dumps(c,ensure_ascii=False,allow_nan=False)+'\n')
    return cases

if __name__=='__main__':
    print(f'Generated {len(generate())} cases with seed {SEED}')
