"""Independent half-plane geometry, rational intersections and support enumeration."""
from fractions import Fraction as F
from decimal import Decimal, localcontext
from itertools import combinations
import math

PI=Decimal('3.1415926535897932384626433832795028841971693993751058209749445923')
def trig(deg):
    with localcontext() as ctx:
        ctx.prec=60
        x=Decimal(str(deg))%360*PI/180
        if x>PI: x-=2*PI
        s=t=x; c=u=Decimal(1)
        for k in range(1,100):
            t*=-x*x/((2*k)*(2*k+1)); u*=-x*x/((2*k-1)*(2*k))
            s+=t; c+=u
        # Rational coefficients at 35 decimal places; angular error < 1e-33 deg.
        return F(s.quantize(Decimal('1e-35'))),F(c.quantize(Decimal('1e-35')))

def clip(poly,n,b):
    result=[]
    for a,z in zip(poly,poly[1:]+poly[:1]):
        va=sum(u*v for u,v in zip(n,a))-b; vz=sum(u*v for u,v in zip(n,z))-b
        if va<=0: result.append(a)
        if (va<0 and vz>0) or (va>0 and vz<0):
            result.append(tuple((a[k]*vz-z[k]*va)/(vz-va) for k in (0,1)))
    return list(dict.fromkeys(result))

def region(initial,observations):
    p=[tuple(map(F,q)) for q in initial] if initial is not None else [(F(-2000),F(-2000)),(F(2000),F(-2000)),(F(2000),F(2000)),(F(-2000),F(2000))]
    planes=[]
    if initial is None:
        for k in range(64):
            s,c=trig(k*360/64); planes.append(((c,s),F(1800)))
    for o in observations:
        x,y=map(F,o['position']); a=F(str(o['angle'])); e=F(str(o.get('error',1.01)))
        sl,cl=trig(float(a-e)); su,cu=trig(float(a+e)); sm,cm=trig(float(a))
        ns=[(sl,-cl),(-su,cu)]+([(-cm,-sm)] if e==0 else [])
        for nx,ny in ns: planes.append(((nx,ny),nx*x+ny*y))
        for k in range(64):
            s,c=trig(k*360/64); planes.append(((c,s),c*x+s*y+1500))
    for n,b in planes:
        p=clip(p,n,b)
        if not p: break
    return p


def mec(points):
    p=list(dict.fromkeys(tuple(map(F,q)) for q in points))
    if not p: return None
    candidates=list(p)
    candidates.extend(tuple((a[k]+b[k])/2 for k in (0,1)) for a,b in combinations(p,2))
    for a,b,c in combinations(p,3):
        ux,uy=b[0]-a[0],b[1]-a[1]; vx,vy=c[0]-a[0],c[1]-a[1]
        d=2*(ux*vy-uy*vx)
        if d:
            u=ux*ux+uy*uy; v=vx*vx+vy*vy
            candidates.append((a[0]+(vy*u-uy*v)/d,a[1]+(ux*v-vx*u)/d))
    center=min(candidates,key=lambda c:max(sum((a-b)**2 for a,b in zip(q,c)) for q in p))
    r2=max(sum((a-b)**2 for a,b in zip(q,center)) for q in p)
    d2=max(sum((a-b)**2 for a,b in zip(q,z)) for q in p for z in p)
    return {'center':list(map(float,center)),'radius':math.sqrt(r2),'radius2':str(r2),'diameter2':str(d2)}


def negative_membership(source,position,problem):
    # A single negative observation in Q4 may be due to facing away, even at 6 m.
    if problem==4: return True
    return sum((F(a)-F(b))**2 for a,b in zip(source,position))>1000**2


def contains(poly,q):
    """Exact containment, including finite segments (not their infinite lines)."""
    ps=list(dict.fromkeys(tuple(map(F,p)) for p in poly)); q=tuple(map(F,q))
    if not ps: return False
    if len(ps)==1: return ps[0]==q
    a=ps[0]; b=next((p for p in ps if p!=a),a)
    def det(a,b,q): return (b[0]-a[0])*(q[1]-a[1])-(b[1]-a[1])*(q[0]-a[0])
    if all(det(a,b,p)==0 for p in ps):
        axis=0 if b[0]!=a[0] else 1
        return det(a,b,q)==0 and min(p[axis] for p in ps)<=q[axis]<=max(p[axis] for p in ps)
    signs=[det(a,b,q) for a,b in zip(ps,ps[1:]+ps[:1])]
    return min(signs)>=0 or max(signs)<=0
