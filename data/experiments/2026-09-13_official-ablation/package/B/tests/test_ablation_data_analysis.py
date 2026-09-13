import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
import ablation_data_analysis as a


def row(case,n,t,complete=True):
    return dict(case_id=case,sources=n,total_virtual_s=t,all_cleared=complete,
                stratum=str(n),costs=dict(move_s=t,measure_s=0,switch_s=0,clear_success_s=0,clear_failure_s=0))


class AnalysisContracts(unittest.TestCase):
    def test_source_weighting_and_cost_identity(self):
        base=[row('a',10,100),row('b',16,160)]
        group=[row('a',10,110),row('b',16,192)]
        weights=a.bootstrap_weights(group)
        result=a.paired(group,base,weights)
        self.assertAlmostEqual(result['delta_s'],42/26)
        self.assertAlmostEqual(result['delta_move_s'],42/26)
        self.assertEqual(result['slower'],2)
        self.assertTrue(np.all(weights.sum(1)==2))

    def test_failure_is_not_a_speedup(self):
        base=[row('a',10,100),row('b',16,160)]
        group=[row('a',10,10,False),row('b',16,180)]
        result=a.paired(group,base,a.bootstrap_weights(group))
        self.assertIsNone(result['delta_s'])
        self.assertIsNone(result['p_bootstrap'])
        self.assertEqual(result['noncomparable'],1)
        self.assertEqual(result['faster'],0)
        self.assertEqual(result['completion_delta_pp'],-50.)

    def test_each_cell_count_is_preserved(self):
        group=[row(str(i),10 if i<4 else 16,100) for i in range(9)]
        weights=a.bootstrap_weights(group)
        self.assertTrue(np.all(weights[:,:4].sum(1)==4))
        self.assertTrue(np.all(weights[:,4:].sum(1)==5))


if __name__=='__main__': unittest.main()
