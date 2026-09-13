"""Incremental full-domain cover certificates for replacing future surveys."""
import math
import numpy as np
from layout_certificates import critical_cover_radius


class ReplacementCover:
    def __init__(self,points,certificate=None):
        self.points=np.asarray(points,float).copy();self.active=np.ones(len(points),bool)
        self.certificate=certificate
        if certificate is not None:
            cells=certificate["cells"];self.centers=np.array([c[:2] for c in cells]);self.half=np.array([c[2] for c in cells])
            offsets=np.array([[-1.,-1.],[1.,-1.],[1.,1.],[-1.,1.]])
            self.corners=(self.centers[:,None,:]+self.half[:,None,None]*offsets[None,:,:]).reshape(-1,2)
            self.angles=self.columns(self.points)

    def columns(self,points):
        farthest=np.linalg.norm(np.abs(self.centers[:,None,:]-points[None,:,:])+self.half[:,None,None],axis=2)
        eligible=np.repeat(farthest<1000.-1e-5,4,axis=0)
        delta=points[None,:,:]-self.corners[:,None,:]
        return np.where(eligible,np.mod(np.arctan2(delta[:,:,1],delta[:,:,0]),2*math.pi),np.inf)

    def append(self,p):
        self.points=np.vstack([self.points,p]);self.active=np.r_[self.active,True]
        if self.certificate is not None:self.angles=np.column_stack([self.angles,self.columns(np.asarray(p).reshape(1,2))])

    def pop(self):
        self.points=self.points[:-1];self.active=self.active[:-1]
        if self.certificate is not None:self.angles=self.angles[:,:-1]

    def removable(self,unused):
        if not unused:return []
        if self.certificate is None:
            result=[]
            for i in unused:
                mask=self.active.copy();mask[i]=False
                if critical_cover_radius(self.points[mask])<999.99:result.append(i)
            return result
        # A point belongs to the convex hull iff eligible directions have no
        # angular gap > pi. We use strict margins for all four cell corners.
        angles=np.where(self.active[None,:],self.angles,np.inf)
        order=np.argsort(angles,axis=1);a=np.take_along_axis(angles,order,axis=1)
        count=np.isfinite(a).sum(axis=1);assert np.all(count>=3)
        rows=np.arange(len(a));last=a[rows,count-1];closing=a[:,0]+2*math.pi-last
        finite=np.arange(a.shape[1])[None,:]<count[:,None]
        safe=np.where(finite,a,0.)
        following=np.roll(safe,-1,axis=1)-safe
        following[rows,count-1]=closing;following=np.where(finite,following,0.)
        assert following.max()<math.pi-1e-10,"Current cell certificate lost"
        previous=np.roll(following,1,axis=1);previous[:,0]=closing
        # Deleting station i merges its two neighboring gaps. Other gaps do
        # not change. Any violating cell corner makes that station essential.
        essential=np.unique(order[((following+previous)>=math.pi-1e-10)&finite])
        essential=set(essential.tolist())
        return [i for i in unused if i not in essential]

    def proposal(self,p,unused):
        self.append(p)
        try:return self.removable(unused)
        finally:self.pop()

    def remove_greedily(self,unused,current):
        removed=[]
        while True:
            candidates=self.removable(unused)
            if not candidates:return removed
            i=max(candidates,key=lambda j:float(np.linalg.norm(self.points[j]-current)))
            self.active[i]=False;unused.remove(i);removed.append(i)

    def validate(self):
        if self.certificate is None:
            bound=critical_cover_radius(self.points[self.active])
            assert bound<999.999,bound
        else:self.removable([0])  # no mutation; checks all current angular gaps
