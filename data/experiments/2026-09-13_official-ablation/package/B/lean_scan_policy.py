"""Identical certified decisions with position conversions only when needed."""
from itertools import combinations
import numpy as np

from faithful_skip_policy import FaithfulSkipMixin
from deferred_skip_policy import (DeferredCompletionPolicy, DeferredWidthPolicy,
                                  DeferredFastWidthPolicy, pair_nonreception_certificate)
from cheap_prediction_policy import cheap_pair_nonreception_certificate


class LeanScanMixin:
    def __init__(self,*args,cheap_prediction=False,**kwargs):
        super().__init__(*args,**kwargs)
        self._pair_certificate = cheap_pair_nonreception_certificate if cheap_prediction else pair_nonreception_certificate

    def measure(self,p,ch):
        self._planned_channel=ch
        certificate=None
        stationary=None
        if self.faithful_skip and self._surveying and ch in self.regions and ch not in self.cleared:
            center,radius=self.circle(ch)
            if not self.defer_scan:
                stationary=np.array_equal(np.asarray(p),np.asarray(self.client.position))
            if self.defer_scan or stationary:
                if np.linalg.norm(p-center)>1500.+radius+1e-5:
                    certificate=dict(kind="range",center=center.copy(),radius=radius)
                elif self.predict_negatives:
                    query=np.asarray(p)
                    certify=self._pair_certificate
                    for a,b in combinations(reversed(self._logical_negatives[ch]),2):
                        self.stats["pair_prediction_checks"]+=1
                        planes=certify(self.regions[ch],query,a,b)
                        if planes is not None:
                            certificate=dict(kind="two_negatives",a=a.copy(),b=b.copy())
                            break
            elif np.linalg.norm(p-center)>1500.+radius+1e-5:
                self.stats["faithful_nonstationary_retained"]+=1
        if certificate is not None:
            query=np.asarray(p)
            if stationary is None:
                stationary=np.array_equal(query,np.asarray(self.client.position))
            self._attempted[ch].append(query.copy())
            self.stats["faithful_attempt_memory_updates"]+=1
            if hasattr(self,"_last_negative"):
                self._last_negative[ch]=query.copy()
                self.stats["inferred_negative_memory_updates"]+=1
            self.stats["certified_scan_skips"]+=1
            self.stats["faithful_stationary_skips"]+=int(stationary)
            self.stats["deferred_nonstationary_skips"]+=int(not stationary)
            self.stats["certified_range_scan_skips"]+=int(certificate["kind"]=="range")
            self.stats["predicted_pair_skips"]+=int(certificate["kind"]=="two_negatives")
            self._last_skip_certificate=certificate
            self.remember_negative(p,ch)
            return "certified_no_reception"
        if self._surveying and ch not in self.regions and ch not in self.cleared:
            self._scan_actual_unknown+=1
        result=super(FaithfulSkipMixin,self).measure(p,ch)
        if result=="no_signal" and ch not in self.cleared:
            self.remember_negative(p,ch)
        return result


class LeanCompletionPolicy(LeanScanMixin,DeferredCompletionPolicy):
    pass


class LeanWidthPolicy(LeanScanMixin,DeferredWidthPolicy):
    pass


class LeanFastWidthPolicy(LeanScanMixin,DeferredFastWidthPolicy):
    pass
