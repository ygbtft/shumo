import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import ablation_data_suite as s


def bare_client():
    return s.old.harness.Client(lambda *args: (_ for _ in ()).throw(AssertionError('network')), robot_id='mock-robot')


class DataSuiteContracts(unittest.TestCase):
    def test_matrix_and_independent_factor_crossing(self):
        self.assertEqual([len(s.variants(p)) for p in (3,4)], [16,15])
        all_ids = []
        for p in (3,4):
            f = s.fixtures(p,'validation')
            groups = {}
            for x in f:
                groups.setdefault(x['stratum'],0); groups[x['stratum']] += 1
            self.assertEqual(set(groups.values()), {10 if p==3 else 5})
            self.assertEqual(len(f),2100)
            all_ids.extend(x['scenario']['seed'] for x in f+s.fixtures(p,'pilot'))
            if p == 4:
                self.assertEqual({(x['factors']['radius'],x['factors']['direction']) for x in f},
                    {('uniform','uniform'),('uniform','outward'),('fixed','uniform'),('fixed','outward')})
        self.assertEqual(len(set(all_ids)),4620)

    def test_instrumented_full_matches_uninstrumented_trace(self):
        for p in (3,4):
            for f in s.fixtures(p,'pilot')[:2]:
                scenario=s.old.harness.Scenario.from_dict(f['scenario'])
                sim=s.old.harness.Simulator(scenario,
                    s.old.harness.ErrorField(scenario.seed,s.old.harness.ErrorConfig(**f['error'])),
                    s.old.harness.Limits(countdown_s=0))
                policy=s.old.construct(p,s.old.harness.Client(s.old.harness.Transport(s.old.harness.Protocol(sim)),
                                       robot_id='mock-robot'),'baseline')
                policy.run()
                row,detail=s.execute(p,s.variants(p)[0],f)
                self.assertEqual(s.normalized_trace(sim.trace),s.normalized_trace(detail['trace']))
                self.assertEqual(row['total_virtual_s'],sim.virtual_time_s)

    def test_phase_switch_preserves_service_selector(self):
        for p in (3,4):
            policy=s.construct(p,bare_client(),dict(component='full',gate=s.DEFAULT_GATE[p]))
            called=[]
            def selector(unused):
                called.append(unused.copy()); return ('source',7,np.array([2.,3.]))
            phased=s.phased_next(policy,selector)
            self.assertEqual(phased([0,1])[0],'survey')
            self.assertEqual(called,[])
            self.assertEqual(phased([])[1],7)
            self.assertEqual(called,[[]])

    def test_negative_pair_still_measured(self):
        for component in ('full','no_negative'):
            policy=s.construct(4,bare_client(),dict(component=component,gate=20.))
            policy.regions[1]=np.array([[100.,-1.],[1000.,-1.],[1000.,1.],[100.,1.]])
            policy.observations[1]=[(np.zeros(2),0.)]
            policy.probes=lambda ch,step:(np.zeros(2),np.array([1.,0.]),500.,[np.array([500.,40.]),np.array([500.,-40.])])
            calls=[]
            policy.primary_measure=lambda q,ch:(calls.append(q),'no_signal')[1]
            policy.source_packet(1)
            self.assertEqual(len(calls),2)
            self.assertAlmostEqual(policy.regions[1][:,0].max(),500.000001 if component=='full' else 1000.)

    def test_isolation_and_run_order(self):
        specs=s.canonical(s.old.harness.builders.SPECS)
        for p in (3,4):
            fixture=s.fixtures(p,'pilot')[7]
            first,_=s.execute(p,s.variants(p)[0],fixture)
            for v in reversed(s.variants(p)):
                row,_=s.execute(p,v,fixture)
                self.assertFalse(row['failure'] and not row['unavailable'])
            last,_=s.execute(p,s.variants(p)[0],fixture)
            self.assertEqual(first['trace_sha256'],last['trace_sha256'])
            self.assertEqual(first['total_virtual_s'],last['total_virtual_s'])
        self.assertEqual(specs,s.canonical(s.old.harness.builders.SPECS))


if __name__=='__main__': unittest.main()
