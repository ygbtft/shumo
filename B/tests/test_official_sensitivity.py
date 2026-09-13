"""Pure configuration/statistical contracts; never start a simulator or mock."""
import unittest
import numpy as np
import official_sensitivity_config as config
from official_sensitivity_analysis import block_bootstrap, robust_comparisons


class SensitivityContracts(unittest.TestCase):
    def test_frozen_balanced_schedule(self):
        settings, rows = config.assignments()
        self.assertEqual((len(settings),len(rows)),(50,742))
        self.assertEqual(rows,config.assignments()[1])
        for p in (3,4):
            pool=[r for r in rows if r['phase']=='robustness' and r['problem']==p]
            self.assertEqual(sum(r['setting']=='baseline' for r in pool),40)
            self.assertEqual(sum(r['setting']=='perturbed' for r in pool),80)
            for r in pool:
                if r['setting']=='perturbed':
                    self.assertNotEqual(r['parameters'],config.DEFAULT[p])
                    self.assertEqual(set(r['changes']),set(config.NEIGHBORHOOD[p]))

    def test_source_weighting_not_mean_of_ratios(self):
        a=np.array([[200.,10.],[100.,20.]])
        b=np.array([[100.,10.],[50.,20.]])
        delta,ratio=block_bootstrap(a,b,100,7)
        np.testing.assert_allclose(ratio,2.)
        self.assertGreater(len(set(np.round(delta,8))),1)

    def test_robustness_success_failure_and_incomplete(self):
        # Algebraic fixtures for the analysis function, never experiment records.
        rows=[]
        for block in range(1,41):
            for setting in ('baseline','perturbed','perturbed'):
                rows.append(dict(phase='robustness',problem=3,setting=setting,block=block,
                                 sources=10,total_s=100.,completed=1))
        good=robust_comparisons(rows)[0]
        self.assertTrue(good['overall_pass'])
        self.assertAlmostEqual(good['ratio_upper97_5'],1.)
        self.assertAlmostEqual(good['clear_probability_lower97_5'],.025**(1/80))
        slow=[dict(r,total_s=r['total_s']*(1.06 if r['setting']=='perturbed' else 1)) for r in rows]
        self.assertFalse(robust_comparisons(slow)[0]['overall_pass'])
        failed=[dict(r) for r in rows]
        failed[1]['completed']=0
        self.assertFalse(robust_comparisons(failed)[0]['overall_pass'])
        partial=robust_comparisons(rows[:-1])[0]
        self.assertFalse(partial['complete'])
        self.assertIsNone(partial['ratio_upper97_5'])


if __name__=='__main__':
    unittest.main()
