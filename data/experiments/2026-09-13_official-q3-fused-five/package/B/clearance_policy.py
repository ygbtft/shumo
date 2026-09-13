"""Stop at the nearest point that optically contains every feasible source."""
import math
import numpy as np
from geometry import minimum_circle
from efficient_joint_policy import EfficientJointPolicy,ProbeJointPolicy


def closest_clearance_point(poly,current,radius=20.-1e-6):
    """Project current onto intersection of equal-radius vertex disks.

    A closest point is current itself, a radial projection onto one active
    circle, or an intersection of two active circles. Include the independently
    certified MEC center as a robust fallback. No true source position is used.
    """
    p=np.asarray(poly);current=np.asarray(current);center,bound=minimum_circle(p)
    if bound>radius:return center
    if np.linalg.norm(p-current,axis=1).max()<=radius:return current.copy()
    candidates=[center]
    delta=current-p;distance=np.linalg.norm(delta,axis=1);mask=distance>1e-9
    candidates.extend(p[mask]+radius*delta[mask]/distance[mask,None])
    i,j=np.triu_indices(len(p),1)
    if len(i):
        difference=p[j]-p[i];d=np.linalg.norm(difference,axis=1);valid=(d>1e-8)&(d<2*radius)
        a,b=p[i[valid]],p[j[valid]];d=d[valid];difference=difference[valid]
        normal=np.column_stack([-difference[:,1],difference[:,0]])/d[:,None]
        middle=(a+b)/2;height=np.sqrt(np.maximum(0,radius**2-d**2/4))
        candidates.extend(middle+normal*height[:,None]);candidates.extend(middle-normal*height[:,None])
    candidates=np.array(candidates)
    feasible=np.linalg.norm(candidates[:,None,:]-p[None,:,:],axis=2).max(axis=1)<=radius+1e-9
    valid=candidates[feasible]
    if not len(valid):return center
    return valid[int(np.linalg.norm(valid-current,axis=1).argmin())]


class ClearanceMixin:
    def init_clearance(self):self.stats.update(optical_position_adjustments=0,optical_local_move_saved_m=0.)

    def clear(self,p,ch,certified=False):
        if certified and ch in self.regions and self.circle(ch)[1]<=20.-1e-5:
            q=closest_clearance_point(self.regions[ch],self.client.position)
            assert np.linalg.norm(self.regions[ch]-q,axis=1).max()<=20.-1e-5+2e-5
            saved=float(np.linalg.norm(np.asarray(p)-self.client.position)-np.linalg.norm(q-self.client.position))
            if saved>1e-7:
                self.stats["optical_position_adjustments"]+=1;self.stats["optical_local_move_saved_m"]+=saved;p=q
        return super().clear(p,ch,certified)


class ClearanceJointPolicy(ClearanceMixin,EfficientJointPolicy):
    def __init__(self,*args,**kwargs):super().__init__(*args,**kwargs);self.init_clearance()


class ClearanceProbePolicy(ClearanceMixin,ProbeJointPolicy):
    def __init__(self,*args,**kwargs):super().__init__(*args,**kwargs);self.init_clearance()
