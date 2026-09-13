"""Current formal-test-2 entry contracts; no simulator or official requests."""
import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import bounded_candidates as candidates
from client import Client
import run_q34_official as entry

ROOT = Path(__file__).resolve().parents[1]

class BoundedEntryTests(unittest.TestCase):
    def test_only_second_formal_configurations(self):
        self.assertEqual({p: list(s) for p,s in candidates.SPECS.items()},
                         {3:['range_area7'],4:['range_grid21_29']})
        for p in (3,4):
            policy=candidates.construct(p,Client(lambda *a: self.fail('Unexpected request')))
            self.assertEqual(candidates.actual_parameters(policy,p),candidates.FORMAL_PARAMETERS[p])
            self.assertEqual(len(policy.stations),7 if p==3 else 21)
            self.assertTrue(policy.range_skip)
            self.assertEqual(policy.dispatch_model,'base')
        q3=candidates.construct(3,Client(lambda *a: self.fail('Unexpected request')))
        self.assertEqual((q3.task_order,q3.trial_radius,q3.max_active),('nearest',65.,2))
        q4=candidates.construct(4,Client(lambda *a: self.fail('Unexpected request')))
        self.assertEqual((q4.dispatch,q4.bracket_trial_radius,q4.fraction,q4.share_limit),('nearest',35.,.15,6))

    def test_layouts_exactly_match_formal_archives(self):
        folders={3:'q3-fused-formal-20260913',4:'q4-nearest-formal-20260913'}
        for p,folder in folders.items():
            source=next((ROOT/'guest_deploy_evidence'/folder/'results').rglob('policy.json'))
            expected=json.loads(source.read_text())['stations']
            policy=candidates.construct(p,Client(lambda *a: self.fail('Unexpected request')))
            if p == 3:
                # The same trigonometric layout differs by <1e-12 m across libm platforms.
                np.testing.assert_allclose(policy.stations,expected,rtol=0,atol=1e-12)
            else:
                np.testing.assert_array_equal(policy.stations,expected)

    def test_both_dispatchers_choose_nearest_task(self):
        for p in (3,4):
            cli=Client(lambda *a: self.fail('Unexpected request'))
            policy=candidates.construct(p,cli)
            cli.position=policy.stations[3].copy()
            kind,index,point=policy.next_task([1,3,5])
            self.assertEqual((kind,index),('survey',3))
            np.testing.assert_array_equal(point,policy.stations[3])

    def test_official_guards_before_io(self):
        cases=[['--problem','3'],
               ['--problem','4','--mode','formal'],
               ['--problem','3','--mode','practice','--robot-id','1','--case-code','AAAA-BBBB-CCCC-DDDD','--confirm-formal'],
               ['--problem','4','--mode','formal','--robot-id','1','--case-code','AAAA-BBBB-CCCC-DDDD','--confirm-practice','--confirm-formal'],
               ['--problem','3','--mode','formal','--robot-id','text','--case-code','AAAA-BBBB-CCCC-DDDD','--confirm-formal'],
               ['--problem','4','--mode','formal','--robot-id','1','--case-code','bad','--confirm-formal']]
        with patch.object(entry,'HttpTransport',side_effect=AssertionError('No transport')) as transport, \
             patch.object(Path,'mkdir',side_effect=AssertionError('No file writes')):
            for args in cases:
                with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                    entry.main(args)
                self.assertEqual(error.exception.code,2)
            self.assertEqual(transport.call_count,0)
        from verify_bounded_http import verify_guards
        self.assertEqual(verify_guards()['network_calls'],0)

    def test_configuration_check_has_no_experiment_or_network_dependency(self):
        script = r"""
import importlib.abc,json,socket,sys
from pathlib import Path
class NoExperiments(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if any(w in fullname for w in ('experiments','sensitivity','simulator','mock')):
            raise AssertionError('Historical/runtime-backend import: '+fullname)
sys.meta_path.insert(0,NoExperiments())
def deny(event,args):
    if event in ('socket.connect','socket.bind','socket.getaddrinfo'): raise AssertionError(event)
sys.addaudithook(deny)
original=Path.read_text
def read(self,*a,**kw):
    if 'experiments' in self.parts: raise AssertionError(str(self))
    return original(self,*a,**kw)
Path.read_text=read
import run_q34_official
run_q34_official.main(['--problem',sys.argv[1],'--check-config'])
"""
        for p in (3,4):
            result=subprocess.run([sys.executable,'-B','-c',script,str(p)],cwd=ROOT,
                                  check=True,capture_output=True,text=True,timeout=30)
            result=json.loads(result.stdout)
            self.assertEqual(result['parameters'],candidates.FORMAL_PARAMETERS[p])
            self.assertEqual(result['official_requests'],0)

    def test_duplicate_case_rejected_before_transport(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'ATTEMPT-q3-formal-AAAA-BBBB-CCCC-DDDD.json'
            path.write_text('{}')
            with patch.object(entry,'HttpTransport',side_effect=AssertionError('No transport')):
                with self.assertRaises(FileExistsError):
                    entry.main(['--problem','3','--mode','formal','--robot-id','1','--case-code','AAAA-BBBB-CCCC-DDDD',
                                '--confirm-formal','--output-dir',tmp])

if __name__ == '__main__': unittest.main()
