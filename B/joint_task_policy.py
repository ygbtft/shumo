"""Route scan stations and uncertain source-service tasks jointly.

MEC centers are only route predictions. They are never exposed as exact truth
or used to bypass certified clearance and finite optical completion.
"""
import math
import numpy as np
from joint_policy import JointPolicy
from bracket_policy import BracketMixin
from adaptive_routes import remaining_route


class JointTaskPolicy(BracketMixin,JointPolicy):
    def __init__(self,client,stations,mixed=False,task_order="two_opt",share=True,
                 share_limit=6,localization_weight=.08,trial_radius=80.,steps=10):
        super().__init__(client,stations,mode="immediate",order="fixed",
                         sensing="cov_mean",trial_radius=trial_radius,
                         time_weight=localization_weight)
        self.mixed=mixed
        self.task_order,self.share,self.share_limit=task_order,share,share_limit
        self.init_bracket(steps,trial_radius if mixed else 40.)
        self._sharing=False
        self._surveying=False
        self._attempted={ch:[] for ch in range(1,21)}
        self.stats.update(joint_route_solves=0,shared_known_measurements=0,
                          skipped_precise_measurements=0)

    def complete_source(self,ch):
        if self.mixed:
            BracketMixin.complete_source(self,ch)
        else:
            JointPolicy.complete_source(self,ch)

    def measure(self,p,ch):
        # Sharing can change client.channel before return; callers must read actual client state.
        # Attempt positions suppress near-duplicate (<1 m) sharing measurements.
        self._attempted[ch].append(np.asarray(p).copy())
        result=super().measure(p,ch)
        if self.share and not self._sharing and not self._surveying:
            self.share_at(np.asarray(p),ch)
        return result

    def clear(self,p,ch,certified=False):
        # A successful clear may trigger sharing RF and leave a different current channel.
        success=super().clear(p,ch,certified)
        if success and self.share and not self._sharing and not self._surveying:
            self.share_at(np.asarray(p),ch)
        return success

    def share_at(self,p,exclude):
        candidates=[]
        for ch in self.regions:
            if ch==exclude or ch in self.cleared:
                continue
            center,radius=self.circle(ch)
            if radius<=20.-1e-5 or (len(self.observations[ch])>=2 and radius<=40.):
                continue
            if any(np.linalg.norm(p-q)<1. for q in self._attempted[ch]):
                continue
            delta=center-p
            distance=np.linalg.norm(delta)
            if distance>1000.+radius:
                continue  # optional usefulness filter only
            angle=math.radians(self.observations[ch][0][1])
            u=np.array([math.cos(angle),math.sin(angle)])
            # Normalized transverse displacement relative to the first bearing. The 0.2
            # threshold and 1000+radius cutoff rank usefulness, not impossibility of reception.
            cross=abs(u[0]*delta[1]-u[1]*delta[0])/max(1.,distance)
            if cross<.2:
                continue
            candidates.append((radius*cross/max(20.,distance*math.radians(1.01)),ch))
        # Prevent recursive share calls; surveying separately forbids these extra RF actions.
        self._sharing=True
        try:
            for score,ch in sorted(candidates,reverse=True)[:self.share_limit]:
                if ch not in self.cleared:
                    self.stats["shared_known_measurements"]+=1
                    self.measure(p,ch)
        finally:
            self._sharing=False

    def next_task(self,unused):
        tasks=[("survey",i,self.stations[i]) for i in unused]
        tasks += [("source",ch,self.circle(ch)[0]) for ch in self.regions if ch not in self.cleared]
        if not tasks:
            return None
        points=np.array([task[2] for task in tasks])
        if self.task_order=="nearest":
            chosen=int(np.linalg.norm(points-self.client.position,axis=1).argmin())
        else:
            self.stats["joint_route_solves"]+=1
            chosen=int(remaining_route(points,self.client.position,True)[0])
        return tasks[chosen]

    def run(self):
        self.client.enter()
        unused=list(range(len(self.stations)))
        # 16 is the public upper bound, not the hidden source count. Otherwise require full coverage.
        while len(self.cleared)<16:
            task=self.next_task(unused)
            if task is None:
                break
            kind,key,p=task
            if kind=="source":
                self.complete_source(key)
                if key not in self.cleared:
                    raise RuntimeError("Source completion did not terminate")
                continue
            unused.remove(key)
            self.stats["stations_visited"]+=1
            self._surveying=True
            try:
                channels=[ch for ch in range(1,21) if ch not in self.cleared]
                if self.client.channel in channels:
                    channels.remove(self.client.channel)
                    channels.insert(0,self.client.channel)
                for ch in channels:
                    if ch in self.cleared:
                        continue
                    if ch in self.regions and self.circle(ch)[1]<=20.-1e-5:
                        self.stats["skipped_precise_measurements"]+=1
                        continue
                    self.measure(p,ch)
                    # Processed at this station includes certified skips; unknown channels get real RF.
                    self.surveyed[ch].add(key)
            finally:
                self._surveying=False
        if len(self.cleared)==16:
            self.stats["stop_reason"]="public_upper_bound_16"
        else:
            assert not unused and all(ch in self.cleared for ch in self.regions)
            assert all(ch in self.regions or ch in self.cleared or len(self.surveyed[ch])==len(self.stations)
                       for ch in range(1,21))
            self.stats["stop_reason"]="full_coverage_and_all_discovered_cleared"
        self.client.exit()
        return {**self.stats,"discovered_channels":len(set(self.regions)|self.cleared),
                "policy_cleared_channels":sorted(self.cleared)}
