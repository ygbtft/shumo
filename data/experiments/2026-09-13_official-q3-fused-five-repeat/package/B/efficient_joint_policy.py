"""Public source-count stopping and bounded asymmetric paired probes."""
import math
import numpy as np
from geometry import minimum_circle,clip
from policies import Policy
from joint_task_policy import JointTaskPolicy
from adaptive_routes import remaining_route


class EfficientJointPolicy(JointTaskPolicy):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.stats.update(known_upper_bound_skips=0)

    def next_task(self,unused):
        if len(set(self.regions)|self.cleared)==16:
            self.stats["known_upper_bound_skips"]+=len(unused);unused.clear()
        return super().next_task(unused)


class ProbeJointPolicy(EfficientJointPolicy):
    def __init__(self,*args,fraction=.5,first_only=False,march=0.,share_cooldown=0.,
                 task_prediction="center",scan_stage="all",**kwargs):
        super().__init__(*args,**kwargs)
        if not self.mixed:raise ValueError("New probe tuning currently applies only to Q4")
        if not 0.<fraction<1.:raise ValueError("fraction outside open unit interval")
        self.fraction,self.first_only,self.march=fraction,first_only,march
        self.share_cooldown,self.task_prediction,self.scan_stage=share_cooldown,task_prediction,scan_stage
        self._last_negative={};self._outer_priority=None
        self.stats.update(shared_negative_cooldown_skips=0,outer_priority_used=False)

    def measure(self,p,ch):
        # Record before opportunistic sharing; only replies from this policy's
        # own public queries are retained. No source position/radius is read.
        old_share=self.share;self.share=False
        try:result=super().measure(p,ch)
        finally:self.share=old_share
        if result=="no_signal":self._last_negative[ch]=np.asarray(p).copy()
        else:self._last_negative.pop(ch,None)
        if self.share and not self._sharing and not self._surveying:self.share_at(np.asarray(p),ch)
        return result

    def share_at(self,p,exclude):
        # Suppress repeat no-signal sharing while moving only a short distance.
        # This is an efficiency choice, never a source-location exclusion.
        blocked=[ch for ch,q in self._last_negative.items() if ch!=exclude and ch in self.regions and ch not in self.cleared and np.linalg.norm(p-q)<self.share_cooldown]
        if not blocked:return super().share_at(p,exclude)
        # Base sharing only sees eligible pending regions; do not mutate the
        # retained feasible sets or drop their channels. A local implementation
        # avoids pretending these channels are already cleared.
        candidates=[]
        for ch in self.regions:
            if ch==exclude or ch in self.cleared:continue
            if ch in blocked:self.stats["shared_negative_cooldown_skips"]+=1;continue
            center,radius=self.circle(ch)
            if radius<=20.-1e-5 or (len(self.observations[ch])>=2 and radius<=40.):continue
            if any(np.linalg.norm(p-q)<1. for q in self._attempted[ch]):continue
            delta=center-p;distance=np.linalg.norm(delta)
            if distance>1000.+radius:continue
            theta=math.radians(self.observations[ch][0][1]);u=np.array([math.cos(theta),math.sin(theta)])
            cross=abs(u[0]*delta[1]-u[1]*delta[0])/max(1.,distance)
            if cross<.2:continue
            candidates.append((radius*cross/max(20.,distance*math.radians(1.01)),ch))
        self._sharing=True
        try:
            for score,ch in sorted(candidates,reverse=True)[:self.share_limit]:
                if ch not in self.cleared:
                    self.stats["shared_known_measurements"]+=1;self.measure(p,ch)
        finally:self._sharing=False

    def probes(self,ch,step):
        poly=self.regions[ch];anchor,angle=self.observations[ch][-1]
        theta=math.radians(angle);u=np.array([math.cos(theta),math.sin(theta)]);v=np.array([-u[1],u[0]])
        projection=(poly-anchor)@u;low,high=float(projection.min()),float(projection.max())
        fraction=.5 if self.first_only and step>0 else self.fraction
        length=low+fraction*(high-low)
        if self.march>0:length=min(low+self.march*1.5**step,low+.5*(high-low))
        width=length*math.tan(math.radians(1.02))
        points=[anchor+length*u+width*v,anchor+length*u-width*v]
        points.sort(key=lambda p:float(np.linalg.norm(p-self.client.position)))
        return anchor,u,length,points

    def complete_source(self,ch):
        if ch in self.cleared:return
        for step in range(self.bracket_steps):
            center,radius=self.circle(ch)
            if radius<=20.-1e-5:
                if not self.clear(center,ch,True):raise RuntimeError("Certified clear failed")
                return
            if radius<=self.bracket_trial_radius and ch not in self.bracket_tried:
                self.bracket_tried.add(ch);self.stats["bracket_optical_trials"]+=1
                if self.clear(center,ch):self.stats["bracket_optical_success"]+=1;return
            anchor,u,length,probes=self.probes(ch,step)
            if length<=1e-3:break
            both_negative=True
            for q in probes:
                self.stats["bracket_measurements"]+=1;self.stats["active_measurements"]+=1
                result=self.measure(q,ch);self.stats["active_no_signal"]+=int(result=="no_signal")
                if ch in self.cleared:return
                if result!="no_signal":both_negative=False;break
            if both_negative:
                restricted=clip(self.regions[ch],u,float(u@anchor)+length+1e-6)
                if not len(restricted):self.stats["bracket_cut_inconsistencies"]+=1;break
                self.regions[ch]=restricted;self._circles.pop(ch,None);self.stats["bracket_pair_cuts"]+=1
        self.active=False
        try:Policy.complete_source(self,ch)
        finally:self.active=True

    def next_task(self,unused):
        if len(set(self.regions)|self.cleared)==16:
            self.stats["known_upper_bound_skips"]+=len(unused);unused.clear()
        if self._outer_priority is None:
            origin_pending=any(np.linalg.norm(self.stations[i])<1. for i in unused)
            if not origin_pending:
                self._outer_priority=self.scan_stage=="outer" or (self.scan_stage=="outer_if_sparse" and len(set(self.regions)|self.cleared)<=2)
                self.stats["outer_priority_used"]=self._outer_priority
        candidates=unused
        if self._outer_priority:
            outer=[i for i in unused if np.linalg.norm(self.stations[i])>=1700.]
            if outer:candidates=outer
        tasks=[("survey",i,self.stations[i]) for i in candidates]
        for ch in self.regions:
            if ch in self.cleared:continue
            center,radius=self.circle(ch);p=center
            if self.task_prediction=="probe" and radius>max(20.,self.bracket_trial_radius):p=self.probes(ch,0)[3][0]
            tasks.append(("source",ch,p))
        if not tasks:return None
        points=np.array([t[2] for t in tasks]);self.stats["joint_route_solves"]+=1
        return tasks[int(remaining_route(points,self.client.position,True)[0])]
