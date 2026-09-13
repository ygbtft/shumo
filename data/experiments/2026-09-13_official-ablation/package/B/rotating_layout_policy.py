"""Rotate a certified circular-domain backbone once using initial feedback."""
import math
import numpy as np
from adaptive_routes import remaining_route
from safe_sensing_policy import SafeSensingPolicy
from efficient_joint_policy import ProbeJointPolicy,EfficientJointPolicy


class RotatingMixin:
    def init_rotation(self,symmetry,phases):
        self.symmetry,self.phases=symmetry,phases;self.rotation_done=False
        self.stats.update(layout_rotation_deg=0.,rotation_route_candidates=0)

    def next_task(self,unused):
        if not self.rotation_done and not any(np.linalg.norm(self.stations[i])<1. for i in unused):
            self.rotation_done=True
            sources=[self.circle(ch)[0] for ch in self.regions if ch not in self.cleared]
            if sources and unused and len(set(self.regions)|self.cleared)<16:
                best=None;original=self.stations.copy();current=np.asarray(self.client.position)
                for phase in range(self.phases):
                    angle=2*math.pi/self.symmetry*phase/self.phases
                    matrix=np.array([[math.cos(angle),-math.sin(angle)],[math.sin(angle),math.cos(angle)]])
                    rotated=original@matrix.T;tasks=np.vstack([rotated[unused],sources])
                    order=remaining_route(tasks,current,True);ordered=tasks[order]
                    length=float(np.linalg.norm(ordered[0]-current)+np.linalg.norm(np.diff(ordered,axis=0),axis=1).sum())
                    self.stats["rotation_route_candidates"]+=1
                    if best is None or length<best[0]-1e-5:best=(length,angle,rotated)
                self.stations=best[2];self.stats["layout_rotation_deg"]=math.degrees(best[1])
        return super().next_task(unused)


class RotatingSafePolicy(RotatingMixin,SafeSensingPolicy):
    def __init__(self,*args,symmetry=6,phases=8,**kwargs):
        super().__init__(*args,**kwargs);self.init_rotation(symmetry,phases)


class RotatingEfficientPolicy(RotatingMixin,EfficientJointPolicy):
    def __init__(self,*args,symmetry=6,phases=8,**kwargs):
        super().__init__(*args,**kwargs);self.init_rotation(symmetry,phases)


class RotatingProbePolicy(RotatingMixin,ProbeJointPolicy):
    def __init__(self,*args,symmetry=7,phases=8,**kwargs):
        super().__init__(*args,**kwargs);self.init_rotation(symmetry,phases)
