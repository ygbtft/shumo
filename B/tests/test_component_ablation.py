"""Contracts for experimental overrides; no network or official entry point."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import unittest
import numpy as np
import component_ablation as a


def client():
    # Construction needs no transport calls.
    return a.harness.Client(lambda *args: (_ for _ in ()).throw(AssertionError('Unexpected call')),
                            robot_id='mock-robot')


class AblationContracts(unittest.TestCase):
    def test_instances_do_not_change_production_globals_or_defaults(self):
        from completion_sensing_policy import completion_choice
        from geometry import clip, optical_cover
        for p in (3, 4):
            before = a.construct(p, client(), 'baseline')
            for setting in a.SETTINGS[p]:
                a.construct(p, client(), setting)
            after = a.construct(p, client(), 'baseline')
            self.assertEqual(before.trial_radius, after.trial_radius)
            self.assertEqual(after.trial_radius, {3:65., 4:35.}[p])
            self.assertTrue(after.share)
            self.assertEqual(after.dispatch_model, 'base')
        self.assertIs(a.CompletionClearancePolicy.complete_source.__globals__['completion_choice'], completion_choice)
        self.assertIs(a.InterleavedMixin.source_packet.__globals__['clip'], clip)
        self.assertIs(a.Policy.complete_source.__globals__['optical_cover'], optical_cover)

    def test_q3_negative_removal_keeps_bearing_and_only_removes_halfplane(self):
        reply = dict(accepted=True, measure_result='no_signal')
        direction = dict(accepted=True, measure_result='direction')
        regions = []
        for setting in ('baseline', 'no_negative'):
            policy = a.construct(3, client(), setting)
            policy.record_feedback((0.,0.), 1, reply)
            from geometry import update_region
            poly = update_region(None, np.array([1140.,0.]), 180.)
            policy.regions[1] = poly.copy()
            policy.observations[1] = [(np.array([1140.,0.]),180.)]
            policy.record_feedback((1140.,0.),1,direction)
            regions.append(policy.regions[1])
        self.assertGreater(regions[0][:,0].min(), 569.)
        self.assertLess(regions[1][:,0].min(), 0.)

    def test_q4_negative_pair_is_still_atomic(self):
        for setting in ('baseline','no_negative'):
            policy = a.construct(4,client(),setting)
            policy.regions[1] = np.array([[100.,-1.],[1000.,-1.],[1000.,1.],[100.,1.]])
            policy.observations[1] = [(np.zeros(2),0.)]
            policy.probes = lambda ch,step:(np.zeros(2),np.array([1.,0.]),500.,
                                           [np.array([500.,40.]),np.array([500.,-40.])])
            called=[]
            policy.primary_measure = lambda q,ch: (called.append(q), 'no_signal')[1]
            policy.source_packet(1)
            self.assertEqual(len(called),2)
            self.assertEqual(policy._rounds[1],1)
            self.assertAlmostEqual(policy.regions[1][:,0].max(),
                                   1000. if setting=='no_negative' else 500.000001, places=5)

    def test_real_baseline_matches_existing_harness_before_and_after_overrides(self):
        for p in (3,4):
            fixture=next(a.harness.cases(p,1,202649001))
            original=a.harness.execute((p,'baseline',{},fixture))
            first=a.execute((p,'baseline',fixture))
            for setting in ('no_negative','no_share','nearest_sensing' if p==3 else 'no_optical_grid'):
                a.execute((p,setting,fixture))
            last=a.execute((p,'baseline',fixture))
            for key in ('total_virtual_s','measurements','switches','misses','cleared','all_cleared'):
                self.assertEqual(original[key],first[key],key)
                self.assertEqual(first[key],last[key],key)


if __name__=='__main__':
    unittest.main()
