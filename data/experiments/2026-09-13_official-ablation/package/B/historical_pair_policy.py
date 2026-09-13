"""Reuse two genuine negative positions and a successful anchor safely."""
from collections import defaultdict
from itertools import combinations
import numpy as np

from coupled_dispatch_policy import CoupledCompletionPolicy,CoupledWidthPolicy
from fast_dispatch_policy import FastWidthPolicy
from geometry import clip,hull,polygon_area


def exclusion_planes(success,negative_a,negative_b):
    """Five normalized halfplanes whose intersection cannot contain a source.

    The first three mean [success,g] meets [negative_a,negative_b]. The last
    two guarantee both negative positions are no farther from g than success.
    """
    s=np.asarray(success)
    a,b=np.asarray(negative_a),np.asarray(negative_b)
    ra,rb=a-s,b-s
    la,lb=np.linalg.norm(ra),np.linalg.norm(rb)
    if min(la,lb)<1e-6:
        return None
    ua,ub=ra/la,rb/lb
    cross=ua[0]*ub[1]-ua[1]*ub[0]
    if abs(cross)<1e-4:
        return None
    if cross<0:
        a,b,ra,rb,la,lb,ua,ub=b,a,rb,ra,lb,la,ub,ua
    edge=b-a
    normal=np.array([-edge[1],edge[0]])/np.linalg.norm(edge)
    normals=np.array([[ua[1],-ua[0]],[-ub[1],ub[0]],normal,-ua,-ub])
    bounds=np.array([normals[0]@s,normals[1]@s,normal@a,
                     normals[3]@s-la/2,normals[4]@s-lb/2])
    return normals,bounds


def exclude_historical_pair(poly,planes):
    if planes is None:
        return poly
    normals,bounds=planes
    values=poly@normals.T-bounds
    # If every old vertex is retained by the union, its convex hull is exactly
    # the original polygon. Avoid expensive no-effect clipping/reordering.
    if not np.any(np.all(values < -1e-4,axis=1)):
        return poly
    pieces=[clip(poly,-normal,-bound+1e-4) for normal,bound in zip(normals,bounds)]
    pieces=[p for p in pieces if len(p)]
    if not pieces:
        return np.empty((0,2))
    candidate=hull(np.vstack(pieces))
    if len(poly)<3 or polygon_area(poly)<1e-8:
        if np.max(np.ptp(poly,axis=0)-np.ptp(candidate,axis=0))>1e-5:
            return candidate
    elif polygon_area(poly)-polygon_area(candidate)>1e-6*max(1.,polygon_area(poly)):
        return candidate
    return poly


class HistoricalPairsMixin:
    def __init__(self,*args,history_enabled=True,negative_history=8,anchor_mode="ends",**kwargs):
        if not 2<=negative_history<=16 or anchor_mode not in ("first","recent","ends"):
            raise ValueError("Invalid bounded historical inference rule")
        super().__init__(*args,**kwargs)
        self.history_enabled,self.negative_history,self.anchor_mode=history_enabled,negative_history,anchor_mode
        self._historical_negatives=defaultdict(list)
        self._historical_plane_cache={}
        self.stats.update(historical_pair_cuts=0,historical_pair_updates=0,historical_pair_checks=0,
                          historical_inconsistent_cuts=0,historical_cache_evictions=0,
                          historical_negative_limit=negative_history,historical_anchor_mode=anchor_mode)

    def measure(self,p,ch):
        result=super().measure(p,ch)
        if not self.history_enabled or ch in self.cleared:
            return result
        if result=="no_signal":
            q=np.asarray(p).copy()
            memory=self._historical_negatives[ch]
            if not any(np.linalg.norm(q-previous)<1e-8 for previous in memory):
                memory.append(q)
                del memory[:-self.negative_history]
        if result not in ("direction","no_signal") or ch not in self.regions or len(self._historical_negatives[ch])<2:
            return result
        observations=self.observations[ch]
        anchors=[observations[0][0]] if self.anchor_mode=="first" else [observations[-1][0]]
        if self.anchor_mode=="ends" and not np.array_equal(observations[0][0],observations[-1][0]):
            anchors.insert(0,observations[0][0])
        poly=self.regions[ch]
        cuts=0
        for s in anchors:
            for a,b in combinations(self._historical_negatives[ch],2):
                key=(tuple(s),tuple(a),tuple(b))
                if key not in self._historical_plane_cache:
                    if len(self._historical_plane_cache)>=4096:
                        self._historical_plane_cache.clear()
                        self.stats["historical_cache_evictions"]+=1
                    self._historical_plane_cache[key]=exclusion_planes(s,a,b)
                self.stats["historical_pair_checks"]+=1
                candidate=exclude_historical_pair(poly,self._historical_plane_cache[key])
                if not len(candidate):
                    self.stats["historical_inconsistent_cuts"]+=1
                    continue
                if candidate is not poly:
                    poly=candidate
                    cuts+=1
        if cuts:
            self.regions[ch]=poly
            self._circles.pop(ch,None)
            self.stats["historical_pair_cuts"]+=cuts
            self.stats["historical_pair_updates"]+=1
        return result


class HistoricalWidthPolicy(HistoricalPairsMixin,CoupledWidthPolicy):
    pass


class HistoricalFastWidthPolicy(HistoricalPairsMixin,FastWidthPolicy):
    pass


class HistoricalCompletionPolicy(HistoricalPairsMixin,CoupledCompletionPolicy):
    pass
