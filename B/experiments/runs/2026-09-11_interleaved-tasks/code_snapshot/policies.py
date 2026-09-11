"""Policies use only Client feedback and public problem constants.

No World/source import, no source counts, radii, orientations, seeds or score reads.
"""
import math
import numpy as np
from geometry import update_region, minimum_circle, optical_cover
from intelligent import choose_second


class Policy:
    def __init__(self,client,stations,mixed=False,active=False,optimized=True,max_active=3,time_weight=.08):
        self.client,self.stations=client,np.asarray(stations)
        self.mixed,self.active,self.optimized=mixed,active,optimized
        self.max_active,self.time_weight=max_active,time_weight
        self.regions,self.observations={},{}
        self.cleared=set()
        self.surveyed={ch:set() for ch in range(1,21)}
        self.stats={"certified_clears":0,"optical_fallback_calls":0,"active_measurements":0,
                    "active_no_signal":0,"inconsistent_updates":0,"optical_max_cover_radius":0.,
                    "stations_visited":0,"stop_reason":None}

    def measure(self,p,ch):
        reply=self.client.measure(p,ch)
        result=reply["measure_result"]
        if result=="near":
            if not self.clear(p,ch,certified=True):
                raise RuntimeError("A valid near response must permit optical clear")
        elif result=="direction":
            angle=reply["svd_deg"]
            self.observations.setdefault(ch,[]).append((np.asarray(p).copy(),angle))
            try:
                self.regions[ch]=update_region(self.regions.get(ch),np.asarray(p),angle)
            except ValueError:
                # Never erase the last containing set. First-bearing optical fallback remains valid.
                self.stats["inconsistent_updates"]+=1
                if ch not in self.regions:
                    raise
        return result

    def clear(self,p,ch,certified=False):
        success=self.client.clear(p,ch)["clear_result"]=="success"
        if success:
            self.cleared.add(ch)
            self.stats["certified_clears"]+=int(certified)
        return success

    def complete_source(self,ch):
        if ch in self.cleared:
            return
        if self.active:
            for _ in range(self.max_active):
                poly=self.regions[ch]
                center,radius=minimum_circle(poly)
                if radius<=20.-1e-5:
                    if not self.clear(center,ch,certified=True):
                        raise RuntimeError("Certified optical containment failed")
                    return
                q,_=choose_second(poly,self.observations[ch],self.client.position,self.mixed,self.time_weight)
                self.stats["active_measurements"]+=1
                result=self.measure(q,ch)
                self.stats["active_no_signal"]+=int(result=="no_signal")
                if ch in self.cleared:
                    return
                if result=="no_signal":
                    # Unknown direction/range: keep the posterior and go to finite optical cover.
                    break
        poly=self.regions[ch]
        center,radius=minimum_circle(poly)
        if self.clear(center,ch,certified=radius<=20.-1e-5):
            return
        cover,r=optical_cover(poly,self.observations[ch][0][1])
        self.stats["optical_max_cover_radius"]=max(self.stats["optical_max_cover_radius"],r)
        if math.dist(self.client.position,cover[-1])<math.dist(self.client.position,cover[0]):
            cover=cover[::-1]
        for q in cover:
            self.stats["optical_fallback_calls"]+=1
            if self.clear(q,ch):
                return
        raise RuntimeError("Finite optical cover exhausted: feedback/model/numerical inconsistency")

    def run(self):
        self.client.enter()
        for index,p in enumerate(self.stations):
            # 16 is the public upper bound, never the hidden actual count.
            if len(self.cleared)==16:
                self.stats["stop_reason"]="public_upper_bound_16"
                break
            channels=[ch for ch in range(1,21) if ch not in self.cleared]
            if self.optimized and self.client.channel in channels:
                channels.remove(self.client.channel)
                channels.insert(0,self.client.channel)
            self.stats["stations_visited"]+=1
            for ch in channels:
                self.measure(p,ch)
                self.surveyed[ch].add(index)
            candidates=[ch for ch in self.regions if ch not in self.cleared]
            if not self.active:
                candidates=[ch for ch in candidates if minimum_circle(self.regions[ch])[1]<=20.-1e-5]
            while candidates:
                ch=min(candidates,key=lambda c:math.dist(self.client.position,minimum_circle(self.regions[c])[0]))
                self.complete_source(ch)
                candidates.remove(ch)
        for ch in sorted(self.regions):
            if ch not in self.cleared:
                self.complete_source(ch)
        if self.stats["stop_reason"] is None:
            assert all(ch in self.cleared or len(self.surveyed[ch])==len(self.stations) for ch in range(1,21))
            self.stats["stop_reason"]="full_coverage_and_all_discovered_cleared"
        self.client.exit()
        return {**self.stats,"discovered_channels":len(set(self.regions)|self.cleared),
                "policy_cleared_channels":sorted(self.cleared)}
