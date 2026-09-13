"""Add no-detour discovery surveys only when they replace required future sites."""
import numpy as np
from joint_task_policy import JointTaskPolicy
from coverage_replacement import ReplacementCover


class ReplacementPolicy(JointTaskPolicy):
    def __init__(self,client,stations,certificate=None,replace=True,**kwargs):
        super().__init__(client,stations,**kwargs)
        if self.mixed and certificate is None:raise ValueError("Q4 requires a full-domain direction certificate")
        self.cover=ReplacementCover(stations,certificate)
        self.replace=replace;self.unused=[];self.full_survey_points=[]
        self._replacing=False
        self.stats.update(replaced_stations=0,replacement_surveys=0,replacement_measurements=0,
                          replacement_proposals=0,known_upper_bound_skips=0)

    def clear(self,p,ch,certified=False):
        success=super().clear(p,ch,certified)
        if success and self.replace and not self._surveying and not self._sharing and not self._replacing:
            self.try_replacement(np.asarray(p))
        return success

    def try_replacement(self,p):
        if len(set(self.regions)|self.cleared)==16 or not self.unused:return
        if any(np.linalg.norm(p-q)<1. for q in self.full_survey_points):return
        self.stats["replacement_proposals"]+=1
        candidates=self.cover.proposal(p,self.unused)
        if not candidates:return
        unknown=[ch for ch in range(1,21) if ch not in self.regions and ch not in self.cleared]
        self._replacing=True;self._sharing=True
        try:
            for ch in unknown:
                self.stats["replacement_measurements"]+=1;self.measure(p,ch)
        finally:self._replacing=False;self._sharing=False
        self.cover.append(p);self.full_survey_points.append(p.copy())
        removed=self.cover.remove_greedily(self.unused,p)
        self.stats["replaced_stations"]+=len(removed);self.stats["replacement_surveys"]+=1

    def run(self):
        self.client.enter();self.unused=list(range(len(self.stations)))
        while len(self.cleared)<16:
            if len(set(self.regions)|self.cleared)==16:
                self.stats["known_upper_bound_skips"]+=len(self.unused);self.unused.clear()
            task=self.next_task(self.unused)
            if task is None:break
            kind,key,p=task
            if kind=="source":
                self.complete_source(key)
                if key not in self.cleared:raise RuntimeError("Completion did not terminate")
                continue
            self.unused.remove(key);self.stats["stations_visited"]+=1;self._surveying=True
            try:
                channels=[ch for ch in range(1,21) if ch not in self.cleared]
                if self.client.channel in channels:
                    channels.remove(self.client.channel);channels.insert(0,self.client.channel)
                for ch in channels:
                    if ch in self.cleared:continue
                    if ch in self.regions and self.circle(ch)[1]<=20.-1e-5:
                        self.stats["skipped_precise_measurements"]+=1;continue
                    self.measure(p,ch);self.surveyed[ch].add(key)
            finally:self._surveying=False
            self.full_survey_points.append(np.asarray(p).copy())
        if len(self.cleared)==16:self.stats["stop_reason"]="public_upper_bound_16"
        else:
            assert not self.unused and all(ch in self.cleared for ch in self.regions)
            # Every active original site was visited; appended sites are
            # activated only after a full survey of all then-unknown channels.
            assert all(any(np.linalg.norm(p-q)<1e-5 for q in self.full_survey_points)
                       for p in self.cover.points[self.cover.active])
            self.cover.validate()
            self.stats["stop_reason"]="continuous_replacement_coverage_and_all_discovered_cleared"
        self.client.exit()
        return {**self.stats,"discovered_channels":len(set(self.regions)|self.cleared),
                "policy_cleared_channels":sorted(self.cleared),"coverage_full_survey_points":len(self.full_survey_points)}
