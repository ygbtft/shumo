"""Independent clearance truth: exhaustive rational circle supports and Jung bands.
Kept independent of BOTH production and the localization oracle.
"""
from fractions import Fraction as F
from itertools import combinations
import math

def truth(points):
    ps=[tuple(map(F,p)) for p in points]
    def d2(a,b): return sum((x-y)**2 for x,y in zip(a,b))
    supports=[(p,F(0)) for p in ps]
    for a,b in combinations(ps,2):
        c=tuple((x+y)/2 for x,y in zip(a,b)); supports.append((c,d2(c,a)))
    for a,b,c in combinations(ps,3):
        rows=[(2*(p[0]-a[0]),2*(p[1]-a[1]),d2(p,(0,0))-d2(a,(0,0))) for p in (b,c)]
        x,y=rows; det=x[0]*y[1]-x[1]*y[0]
        if det:
            o=((x[2]*y[1]-x[1]*y[2])/det,(x[0]*y[2]-x[2]*y[0])/det)
            supports.append((o,d2(o,a)))
    o,r2=min(((c,r) for c,r in supports if all(d2(c,p)<=r for p in ps)),key=lambda cr:cr[1])
    D2=max(d2(a,b) for a in ps for b in ps)
    band='guaranteed' if D2<=1200 else ('impossible' if D2>1600 else 'mec_required')
    return dict(center=list(map(float,o)),radius=math.sqrt(r2),radius2=str(r2),diameter2=str(D2),band=band,
                possible=r2<=400,certified=r2<=(F(20)-F(1,100000))**2)
