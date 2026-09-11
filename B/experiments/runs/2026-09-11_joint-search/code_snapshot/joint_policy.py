"""Feedback-only joint scan/clear scheduling and covariance-ranked sensing.

Covariance is a candidate-ranking approximation, never a replacement for the
containing polygon, receiving certificate, or finite optical clearing cover.
"""
import math
import numpy as np
from geometry import minimum_circle
from intelligent import candidate_points, guaranteed_omni, hypotheses, choose_second
from adaptive_routes import remaining_route
from policies import Policy


def choose_covariance(poly, observations, current, robust=False, weight=.08):
    center,radius=minimum_circle(poly)
    centered=poly-poly.mean(axis=0)
    # A documented prior for ranking, not a claimed source distribution.
    covariance=centered.T@centered/max(1,len(poly))+np.eye(2)*.01
    samples=hypotheses(poly)
    choices=[]
    for q in candidate_points(poly,observations,current):
        if not guaranteed_omni(q,poly,observations[0][0]):continue
        delta=samples-q;dist=np.maximum(1.,np.linalg.norm(delta,axis=1))
        normal=np.column_stack((-delta[:,1],delta[:,0]))/dist[:,None]
        cn=normal@covariance
        # Linearized angular measurement variance at each hypothetical source.
        noise=(dist*math.radians(1.01))**2/3
        denominator=np.sum(cn*normal,axis=1)+noise
        post=covariance[None,:,:]-cn[:,:,None]*cn[:,None,:]/denominator[:,None,None]
        discriminant=np.maximum(0,(post[:,0,0]-post[:,1,1])**2+4*post[:,0,1]**2)
        eigen=(post[:,0,0]+post[:,1,1]+np.sqrt(discriminant))/2
        uncertainty=np.sqrt(np.maximum(0,eigen))*math.sqrt(3)
        residual=float(uncertainty.max() if robust else uncertainty.mean())
        cost=float(np.linalg.norm(q-current))/5+5
        choices.append((residual+weight*cost,q))
    if choices:return min(choices,key=lambda item:item[0])[1]
    # First-bearing containing sets have longitudinal extent <=1502m, so their
    # MEC centers should qualify; validate rather than silently relying on it.
    if guaranteed_omni(center,poly,observations[0][0]):return center
    return choose_second(poly,observations,current,False,weight)[0]


class JointPolicy(Policy):
    def __init__(self,client,stations,mode="immediate",order="fixed",sensing="sample",trial_radius=0.,detour_limit=200.,skip_precise=True,**kwargs):
        super().__init__(client,stations,mixed=False,active=True,optimized=True,**kwargs)
        if mode not in ("immediate","deferred","opportunistic"):raise ValueError(mode)
        if order not in ("fixed","greedy","two_opt"):raise ValueError(order)
        if sensing not in ("sample","cov_mean","cov_robust"):raise ValueError(sensing)
        self.mode,self.order,self.sensing=mode,order,sensing
        self.trial_radius,self.detour_limit,self.skip_precise=trial_radius,detour_limit,skip_precise
        self._circles={};self._trial_done=set()
        self.stats.update(skipped_precise_measurements=0,early_optical_trials=0,early_optical_success=0)

    def circle(self,ch):
        if ch not in self._circles:self._circles[ch]=minimum_circle(self.regions[ch])
        return self._circles[ch]

    def measure(self,p,ch):
        result=super().measure(p,ch)
        if result=="direction":self._circles.pop(ch,None)
        return result

    def complete_source(self,ch):
        if ch in self.cleared:return
        for step in range(self.max_active):
            poly=self.regions[ch];center,radius=self.circle(ch)
            if radius<=20.-1e-5:
                if not self.clear(center,ch,certified=True):raise RuntimeError("Certified optical clear failed")
                return
            # A cheap optical attempt is safe even if uncertified: a failure
            # leaves the containing set intact. At most one such trial/source.
            if radius<=self.trial_radius and ch not in self._trial_done:
                self._trial_done.add(ch);self.stats["early_optical_trials"]+=1
                if self.clear(center,ch):
                    self.stats["early_optical_success"]+=1;return
                q=center
            elif self.sensing=="sample":
                q=choose_second(poly,self.observations[ch],self.client.position,False,self.time_weight)[0]
            else:
                q=choose_covariance(poly,self.observations[ch],self.client.position,self.sensing=="cov_robust",self.time_weight)
            self.stats["active_measurements"]+=1
            result=self.measure(q,ch)
            self.stats["active_no_signal"]+=int(result=="no_signal")
            if ch in self.cleared:return
            if result=="no_signal":break
        # The existing finite optical cover provides termination independently
        # of the candidate ranking or future radio reception.
        self.active=False
        try:super().complete_source(ch)
        finally:self.active=True

    def scan_order(self,remaining):
        if self.order=="fixed":return remaining.copy()
        ids=remaining_route(self.stations[remaining],self.client.position,self.order=="two_opt")
        return [remaining[i] for i in ids]

    def run(self):
        self.client.enter();remaining=list(range(len(self.stations)))
        while remaining and len(self.cleared)<16:
            index=self.scan_order(remaining)[0];remaining.remove(index);p=self.stations[index]
            self.stats["stations_visited"]+=1
            channels=[ch for ch in range(1,21) if ch not in self.cleared]
            if self.client.channel in channels:
                channels.remove(self.client.channel);channels.insert(0,self.client.channel)
            for ch in channels:
                if self.skip_precise and ch in self.regions and self.circle(ch)[1]<=20.-1e-5:
                    self.stats["skipped_precise_measurements"]+=1
                    continue
                self.measure(p,ch);self.surveyed[ch].add(index)
            if self.mode=="deferred":continue
            while True:
                candidates=[ch for ch in self.regions if ch not in self.cleared]
                if self.mode=="opportunistic" and remaining:
                    next_point=self.stations[self.scan_order(remaining)[0]]
                    direct=math.dist(self.client.position,next_point)
                    candidates=[ch for ch in candidates if self.circle(ch)[1]<=max(20.,self.trial_radius) and
                                math.dist(self.client.position,self.circle(ch)[0])+math.dist(self.circle(ch)[0],next_point)-direct<=self.detour_limit]
                if not candidates:break
                ch=min(candidates,key=lambda c:math.dist(self.client.position,self.circle(c)[0]))
                self.complete_source(ch)
        # Resolve every discovered source, independently of the unknown count.
        while True:
            candidates=[ch for ch in self.regions if ch not in self.cleared]
            if not candidates:break
            ch=min(candidates,key=lambda c:math.dist(self.client.position,self.circle(c)[0]))
            self.complete_source(ch)
        if len(self.cleared)==16:
            self.stats["stop_reason"]="public_upper_bound_16"
        else:
            # Known precise channels were allowed to skip redundant scans but
            # are now all cleared. Unknown channels require the complete cover.
            assert not remaining
            assert all(ch in self.cleared or len(self.surveyed[ch])==len(self.stations) for ch in range(1,21))
            self.stats["stop_reason"]="full_coverage_and_all_discovered_cleared"
        self.client.exit()
        return {**self.stats,"discovered_channels":len(set(self.regions)|self.cleared),"policy_cleared_channels":sorted(self.cleared)}
