"""Standalone rational predicates; no production imports, no numpy/scipy."""
from fractions import Fraction as F


def point(p): return tuple(F(x) for x in p)
def cross(a,b,c): return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
def hull(points):
    points=sorted(set(map(point,points)))
    if len(points)<2: return points
    chains=[]
    for seq in (points,points[::-1]):
        out=[]
        for p in seq:
            while len(out)>1 and cross(out[-2],out[-1],p)<=0: out.pop()
            out.append(p)
        chains.append(out)
    return chains[0][:-1]+chains[1][:-1]


def partition(cells):
    # Prefix trie: a leaf may neither prefix nor be prefixed by another leaf.
    tree={}
    for row in cells:
        x,y,h=map(F,row[:3]); cx=cy=F(0); ch=F(1800); node=tree
        if h<=0: return False
        for _ in range(1100):
            if 'leaf' in node: return False
            if (cx,cy,ch)==(x,y,h):
                if node: return False
                node['leaf']=True; break
            if ch<=h: return False
            dx=1 if x>cx else -1; dy=1 if y>cy else -1
            ch/=2; cx+=dx*ch; cy+=dy*ch
            node=node.setdefault((dx,dy),{})
        else: return False
    def complete(node,x,y,h):
        if 'leaf' in node: return True
        if max(abs(x)-h,0)**2+max(abs(y)-h,0)**2>1800**2: return not node
        if not node: return False
        return all(complete(node.get((a,b),{}),x+a*h/2,y+b*h/2,h/2)
                   for a in (-1,1) for b in (-1,1))
    return bool(cells) and complete(tree,F(0),F(0),F(1800))


def leaf(points,cell,mode='closed'):
    x,y,h=map(F,cell[:3]); ids=cell[3]
    if h<=0 or len(ids)<3 or any(type(i)!=int or i<0 or i>=len(points) for i in ids): return False
    ps=[point(points[i]) for i in ids]; H=hull(ps)
    if len(H)<3: return False
    rr=(F(1000)-F(1,100000))**2 if mode=='strict' else F(1000)**2
    for q in ((x-h,y-h),(x+h,y-h),(x+h,y+h),(x-h,y+h)):
        for p in ps:
            d=sum((a-b)**2 for a,b in zip(p,q))
            if (d>rr if mode=='strict' else d>=rr): return False
        for a,b in zip(H,H[1:]+H[:1]):
            v=cross(a,b,q)
            if mode=='strict':
                if v<=0 or v*v <= F(1,10**10)*sum((u-w)**2 for u,w in zip(a,b)): return False
            elif v<0: return False
    return True


def certificate(points,cert,mode):
    return (cert.get('covered') is True and cert.get('arena_radius')==1800
            and cert.get('receive_radius')==1000 and partition(cert['cells'])
            and all(leaf(points,c,mode) for c in cert['cells']))


def omni_cells(points):
    """Independent finite square cover: one uniform station suffices for Q3."""
    ps=list(map(point,points)); stack=[(F(0),F(0),F(1800),0)]; cells=[]
    while stack:
        x,y,h,d=stack.pop()
        if max(abs(x)-h,0)**2+max(abs(y)-h,0)**2>1800**2: continue
        ids=[i for i,(a,b) in enumerate(ps) if (abs(x-a)+h)**2+(abs(y-b)+h)**2 < 1000**2]
        if ids: cells.append([float(x),float(y),float(h),ids[:1]]); continue
        if d==14: raise ValueError('Q3 certificate unresolved')
        stack.extend((x+a*h/2,y+b*h/2,h/2,d+1) for a in (-1,1) for b in (-1,1))
    assert partition(cells)
    return cells
