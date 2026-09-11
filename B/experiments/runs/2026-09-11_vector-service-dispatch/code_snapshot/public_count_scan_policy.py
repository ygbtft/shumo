"""Delete stationary scans of empty channels after 16 public discoveries."""
import numpy as np
from faithful_skip_policy import FaithfulSkipMixin
from lean_scan_policy import LeanCompletionPolicy,LeanWidthPolicy,LeanFastWidthPolicy


class PublicCountScanMixin:
    def __init__(self,*args,public_empty_skip=True,**kwargs):
        super().__init__(*args,**kwargs)
        self.public_empty_skip=public_empty_skip
        self._scan_empty_unknown=0
        self.stats.update(public_empty_scan_skips=0,public_empty_scans=0,minimum_unknown_actions_per_station=20)

    def measure(self,p,ch):
        if (self.public_empty_skip and self._surveying and ch not in self.regions and ch not in self.cleared
                and len(set(self.regions)|self.cleared)==16
                and np.array_equal(np.asarray(p),np.asarray(self.client.position))):
            self._planned_channel=ch
            query=np.asarray(p)
            self._attempted[ch].append(query.copy())
            self.stats["faithful_attempt_memory_updates"]+=1
            if hasattr(self,"_last_negative"):
                self._last_negative[ch]=query.copy()
                self.stats["inferred_negative_memory_updates"]+=1
            self.stats["certified_scan_skips"]+=1
            self.stats["faithful_stationary_skips"]+=1
            self.stats["public_empty_scan_skips"]+=1
            self._scan_empty_unknown+=1
            self._last_skip_certificate=dict(kind="public_16_bound",discovered_channels=tuple(sorted(set(self.regions)|self.cleared)))
            self.remember_negative(p,ch)
            return "certified_no_reception"
        return super().measure(p,ch)

    def scan_station(self,p,key):
        unknown=[ch for ch in range(1,21) if ch not in self.regions and ch not in self.cleared]
        assert len(unknown)>=4
        self._scan_actual_unknown=0
        self._scan_empty_unknown=0
        # Replace DeferredScanMixin's every-unknown-channel-is-measured assertion
        # with actual measurement OR a public-16 stationary-empty certificate.
        FaithfulSkipMixin.scan_station(self,p,key)
        actions=self._scan_actual_unknown+self._scan_empty_unknown
        assert actions>=len(unknown)>=4
        self.stats["minimum_actual_unknown_per_station"]=min(self.stats["minimum_actual_unknown_per_station"],self._scan_actual_unknown)
        self.stats["minimum_unknown_actions_per_station"]=min(self.stats["minimum_unknown_actions_per_station"],actions)
        self.stats["public_empty_scans"]+=int(self._scan_empty_unknown>0)


class PublicCountCompletionPolicy(PublicCountScanMixin,LeanCompletionPolicy):
    pass


class PublicCountWidthPolicy(PublicCountScanMixin,LeanWidthPolicy):
    pass


class PublicCountFastWidthPolicy(PublicCountScanMixin,LeanFastWidthPolicy):
    pass
