"""Batch no-effect predicates while retaining the exact history-cut sequence."""
from itertools import combinations
import numpy as np
from historical_pair_policy import (HistoricalPairsMixin, HistoricalWidthPolicy, HistoricalFastWidthPolicy,
                                    exclusion_planes, exclude_historical_pair)


def apply_pair_sequence(poly, records, batched=True, batch_min=4):
    cuts = inconsistent = calls = screens = 0
    offset = 0
    while offset < len(records):
        valid = [(j,records[j]) for j in range(offset,len(records)) if records[j] is not None]
        if batched and len(valid) >= batch_min:
            normals = np.concatenate([planes[0] for j,planes in valid],axis=0)
            bounds = np.concatenate([planes[1] for j,planes in valid])
            values = (poly @ normals.T-bounds).reshape(len(poly),len(valid),5)
            # Old clipping can only change the hull when a vertex is strictly
            # in all five exclusion planes. Keep a 1e-8 m ambiguity band for
            # exact original evaluation when matrix grouping changes rounding.
            possible = np.any(np.max(values,axis=2) < -1e-4+1e-8,axis=0)
            screens += len(valid)
            candidates = [j for (j,planes),maybe in zip(valid,possible) if maybe]
        else:
            candidates = [j for j,planes in valid]
        changed = False
        for j in candidates:
            calls += 1
            candidate = exclude_historical_pair(poly,records[j])
            if not len(candidate):
                inconsistent += 1
                continue
            if candidate is not poly:
                poly = candidate
                cuts += 1
                # A new vertex can activate a previously idle later plane.
                # Re-screen the entire suffix after every actual region change.
                offset = j+1
                changed = True
                break
        if not changed:
            break
    return poly,dict(cuts=cuts,inconsistent=inconsistent,calls=calls,screens=screens)


class BatchedHistoricalMixin:
    def __init__(self,*args,history_batch=True,batch_min=4,**kwargs):
        if not 2 <= batch_min <= 32:
            raise ValueError("Batch threshold outside 2..32")
        super().__init__(*args,**kwargs)
        self.history_batch,self.batch_min = history_batch,batch_min
        self.stats.update(historical_exact_clip_calls=0,historical_batch_screens=0)

    def measure(self,p,ch):
        # Reuse the same physical/control policy below HistoricalPairsMixin.
        result = super(HistoricalPairsMixin,self).measure(p,ch)
        if not self.history_enabled or ch in self.cleared:
            return result
        if result == "no_signal":
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
        records=[]
        for s in anchors:
            for a,b in combinations(self._historical_negatives[ch],2):
                key=(tuple(s),tuple(a),tuple(b))
                if key not in self._historical_plane_cache:
                    if len(self._historical_plane_cache)>=4096:
                        self._historical_plane_cache.clear()
                        self.stats["historical_cache_evictions"]+=1
                    self._historical_plane_cache[key]=exclusion_planes(s,a,b)
                records.append(self._historical_plane_cache[key])
        self.stats["historical_pair_checks"]+=len(records)
        poly,info=apply_pair_sequence(self.regions[ch],records,self.history_batch,self.batch_min)
        self.stats["historical_exact_clip_calls"]+=info["calls"]
        self.stats["historical_batch_screens"]+=info["screens"]
        self.stats["historical_inconsistent_cuts"]+=info["inconsistent"]
        if info["cuts"]:
            self.regions[ch]=poly
            self._circles.pop(ch,None)
            self.stats["historical_pair_cuts"]+=info["cuts"]
            self.stats["historical_pair_updates"]+=1
        return result


class BatchedHistoricalWidthPolicy(BatchedHistoricalMixin,HistoricalWidthPolicy):
    pass


class BatchedHistoricalFastWidthPolicy(BatchedHistoricalMixin,HistoricalFastWidthPolicy):
    pass
