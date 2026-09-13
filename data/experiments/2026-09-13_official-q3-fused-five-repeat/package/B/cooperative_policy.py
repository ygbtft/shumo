"""Share useful observations at visited points; certify dynamic Q3 coverage.

Motivated by the distinction between sensor placement and sensor selection.
Every choice depends only on public feedback and retained feasible polygons.
"""
import math
import numpy as np
from joint_policy import JointPolicy
from intelligent import guaranteed_omni
from adaptive_routes import remaining_route
from layout_certificates import critical_cover_radius


class CooperativePolicy(JointPolicy):
    def __init__(self,client,stations,share_known=True,discover_gain=None,prune=False,source_order="greedy",**kwargs):
        super().__init__(client,stations,mode="immediate",order="two_opt",**kwargs)
        self.share_known,self.discover_gain,self.prune=share_known,discover_gain,prune
        self.source_order=source_order;self._in_share=False;self._in_survey=False
        self.full_survey_points=[];self.unused=list(range(len(self.stations)))
        r=1800*np.sqrt((np.arange(16)+.5)/16);a=np.arange(96)*2*math.pi/96
        self.discovery_grid=(r[:,None,None]*np.column_stack((np.cos(a),np.sin(a)))[None,:,:]).reshape(-1,2)
        self.grid_covered=np.zeros(len(self.discovery_grid),bool)
        self.stats.update(shared_known_measurements=0,extra_discovery_measurements=0,extra_discovery_sites=0,
                          pruned_stations=0,dynamic_cover_checks=0,discovery_cover_radius=None)

    def measure(self,p,ch):
        result=super().measure(p,ch)
        if self.share_known and not self._in_share and not self._in_survey:self.collect_known(np.asarray(p),exclude=ch)
        return result

    def clear(self,p,ch,certified=False):
        success=super().clear(p,ch,certified)
        if success and not self._in_share and not self._in_survey:
            if self.share_known:self.collect_known(np.asarray(p),exclude=ch)
            if self.discover_gain is not None:self.collect_unknown(np.asarray(p))
        return success

    def collect_known(self,p,exclude):
        self._in_share=True
        try:
            for ch in list(self.regions):
                if ch==exclude or ch in self.cleared:continue
                center,radius=self.circle(ch)
                if radius<=20 or (len(self.observations[ch])>=2 and radius<=40):continue
                if any(np.linalg.norm(p-q)<1. for q,t in self.observations[ch]):continue
                if not guaranteed_omni(p,self.regions[ch],self.observations[ch][0][0]):continue
                delta=center-p;norm=np.linalg.norm(delta)
                t=math.radians(self.observations[ch][0][1]);u=np.array([math.cos(t),math.sin(t)])
                cross=abs(u[0]*delta[1]-u[1]*delta[0])/max(1.,norm)
                if cross<.2:continue  # ranking heuristic, never a correctness test
                self.stats["shared_known_measurements"]+=1;self.measure(p,ch)
        finally:self._in_share=False

    def remember_full_survey(self,p):
        self.full_survey_points.append(np.asarray(p).copy())
        self.grid_covered|=np.linalg.norm(self.discovery_grid-p,axis=1)<=1000

    def collect_unknown(self,p):
        if len(self.cleared)==16:return
        if any(np.linalg.norm(p-q)<1. for q in self.full_survey_points):return
        covered=np.linalg.norm(self.discovery_grid-p,axis=1)<=1000
        gain=float(np.mean(covered & ~self.grid_covered))
        if gain<self.discover_gain:return
        # Sampling controls whether a detour-free survey is worth its command
        # cost; only continuous coverage certificates can remove future stations.
        unknown=[ch for ch in range(1,21) if ch not in self.regions and ch not in self.cleared]
        self._in_share=True
        try:
            for ch in unknown:
                self.stats["extra_discovery_measurements"]+=1;self.measure(p,ch)
        finally:self._in_share=False
        self.stats["extra_discovery_sites"]+=1;self.remember_full_survey(p)

    def coverage_bound(self,points):
        self.stats["dynamic_cover_checks"]+=1
        return critical_cover_radius(points)

    def prune_future(self):
        if not self.prune or not self.full_survey_points:return
        # Each accepted removal retains a full-domain receiving cover composed
        # of completed all-unknown surveys plus the remaining required sites.
        order=sorted(self.unused,key=lambda i:np.linalg.norm(self.stations[i]-self.client.position),reverse=True)
        for i in order:
            proposal=[self.stations[j] for j in self.unused if j!=i]
            bound=self.coverage_bound(self.full_survey_points+proposal)
            if bound<999.99:
                self.unused.remove(i);self.stats["pruned_stations"]+=1

    def next_source(self,candidates):
        if self.source_order=="two_opt":
            points=np.array([self.circle(ch)[0] for ch in candidates])
            order=remaining_route(points,self.client.position,True)
            return candidates[int(order[0])]
        if self.source_order=="uncertainty":
            return min(candidates,key=lambda c:math.dist(self.client.position,self.circle(c)[0])+self.circle(c)[1])
        return min(candidates,key=lambda c:math.dist(self.client.position,self.circle(c)[0]))

    def run(self):
        self.client.enter()
        while self.unused and len(self.cleared)<16:
            self.prune_future()
            if not self.unused:break
            index=self.scan_order(self.unused)[0];self.unused.remove(index);p=self.stations[index]
            self.stats["stations_visited"]+=1;self._in_survey=True
            try:
                channels=[ch for ch in range(1,21) if ch not in self.cleared]
                if self.client.channel in channels:
                    channels.remove(self.client.channel);channels.insert(0,self.client.channel)
                for ch in channels:
                    if ch in self.cleared:continue
                    if ch in self.regions and self.circle(ch)[1]<=20.-1e-5:continue
                    self.measure(p,ch);self.surveyed[ch].add(index)
            finally:self._in_survey=False
            self.remember_full_survey(p)
            while True:
                candidates=[ch for ch in self.regions if ch not in self.cleared]
                if not candidates:break
                self.complete_source(self.next_source(candidates))
        # Pruning is done only after resolving known sources, nevertheless this
        # final loop keeps termination valid if a future scheduler changes that.
        while True:
            candidates=[ch for ch in self.regions if ch not in self.cleared]
            if not candidates:break
            self.complete_source(self.next_source(candidates))
        if len(self.cleared)==16:self.stats["stop_reason"]="public_upper_bound_16"
        else:
            assert not self.unused
            bound=self.coverage_bound(self.full_survey_points)
            assert bound<1000.-1e-3,bound
            self.stats["discovery_cover_radius"]=bound
            self.stats["stop_reason"]="continuous_dynamic_coverage_and_all_discovered_cleared"
        self.client.exit()
        return {**self.stats,"discovered_channels":len(set(self.regions)|self.cleared),"policy_cleared_channels":sorted(self.cleared)}
