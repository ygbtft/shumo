"""Paired forward probes safely use two no-signal replies for Q3 AND Q4.

For a received bearing at s, put the x-axis along that bearing and let
|y| <= t*x contain all possible source directions. Probe (l,+t*l),(l,-t*l).
If a source has x >= l and t <= 1/sqrt(3), both probes are no farther from
it than s; the segment joining the probes intersects its ray toward s.
Any closed receiving halfplane containing s therefore contains at least one
probe. Two no-signal replies imply x <= l (retain equality for robustness).
One no-signal alone is never used as a location exclusion.
"""
import math
import numpy as np
from geometry import minimum_circle,clip
from policies import Policy
from adaptive_routes import AdaptiveOrder
from cooperative_policy import CooperativePolicy


class BracketMixin:
    def init_bracket(self,steps,trial):
        self.bracket_steps=steps;self.bracket_trial_radius=trial;self.bracket_tried=set()
        self.stats.update(bracket_pair_cuts=0,bracket_measurements=0,bracket_optical_trials=0,
                          bracket_optical_success=0,bracket_cut_inconsistencies=0)

    def complete_source(self,ch):
        if ch in self.cleared:return
        for step in range(self.bracket_steps):
            poly=self.regions[ch];center,radius=minimum_circle(poly)
            if radius<=20.-1e-5:
                if not self.clear(center,ch,certified=True):raise RuntimeError("Certified clear failed")
                return
            if radius<=self.bracket_trial_radius and ch not in self.bracket_tried:
                self.bracket_tried.add(ch);self.stats["bracket_optical_trials"]+=1
                if self.clear(center,ch):
                    self.stats["bracket_optical_success"]+=1;return
            # Every anchor is a point at which this channel actually returned
            # a bearing. No guessed target position or radius is used.
            anchor,angle=self.observations[ch][-1]
            theta=math.radians(angle);u=np.array([math.cos(theta),math.sin(theta)]);v=np.array([-u[1],u[0]])
            projection=(poly-anchor)@u
            length=float((projection.min()+projection.max())/2)
            if length<=1e-3:break
            # 1.02 degrees encloses the 1.01-degree engineering error wedge
            # with additional margin; it is far below the proof's 30-degree limit.
            width=length*math.tan(math.radians(1.02))
            probes=[anchor+length*u+width*v,anchor+length*u-width*v]
            probes.sort(key=lambda p:float(np.linalg.norm(p-self.client.position)))
            both_negative=True
            for q in probes:
                self.stats["bracket_measurements"]+=1;self.stats["active_measurements"]+=1
                result=self.measure(q,ch)
                self.stats["active_no_signal"]+=int(result=="no_signal")
                if ch in self.cleared:return
                if result!="no_signal":
                    both_negative=False;break
            if both_negative:
                restricted=clip(self.regions[ch],u,float(u@anchor)+length+1e-6)
                if not len(restricted):
                    self.stats["bracket_cut_inconsistencies"]+=1;break
                self.regions[ch]=restricted
                if hasattr(self,"_circles"):self._circles.pop(ch,None)
                self.stats["bracket_pair_cuts"]+=1
        # We do not assume each noisy update exactly halves the diameter.
        # A fixed iteration budget is followed by the proved finite optical cover.
        self.active=False
        try:Policy.complete_source(self,ch)
        finally:self.active=True


class BracketPolicy(BracketMixin,Policy):
    def __init__(self,client,stations,mixed=False,dynamic=False,steps=10,trial_radius=40.):
        super().__init__(client,stations,mixed=mixed,active=True,optimized=True)
        self.init_bracket(steps,trial_radius)
        if dynamic:self.stations=AdaptiveOrder(client,stations,True)


class CooperativeBracketPolicy(BracketMixin,CooperativePolicy):
    def __init__(self,client,stations,steps=10,bracket_trial_radius=40.,**kwargs):
        super().__init__(client,stations,**kwargs)
        self.init_bracket(steps,bracket_trial_radius)
