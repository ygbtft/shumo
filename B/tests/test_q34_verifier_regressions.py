"""Audited P2 counterexamples, including optimized-interpreter checks."""
import ast
import copy
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import numpy as np
import pytest

import icra_final_checks as checks
from integer_visibility_certificate import certify_integer_stations, verify_integer_certificate
from visibility_certificate import directional_witness, rectangle_certificate, verify_cells


@pytest.fixture
def integer_fixture():
    points, cells = [], []
    for x in range(-1575, 1800, 450):
        for y in range(-1575, 1800, 450):
            ids = list(range(len(points), len(points)+4))
            points.extend([[x+dx*245,y+dy*245] for dx,dy in ((-1,-1),(1,-1),(1,1),(-1,1))])
            cells.append([x,y,225,ids])
    return points, dict(covered=True,scale=8,arena_radius=1800,receive_radius=1000,cells=cells)


def test_optimized_false_certificate_and_generator_rejected():
    code = '''
from integer_visibility_certificate import verify_integer_certificate, certify_integer_stations
calls = [lambda: verify_integer_certificate([[-1,-1],[1,-1],[0,1]],dict(
    scale=1,covered=True,arena_radius=1800,receive_radius=1000,cells=[[0,0,1800,[0,1,2]]])),
    lambda: certify_integer_stations([[0.5,0],[1,1],[0,1]]),
    lambda: certify_integer_stations([[1951,0],[1,1],[0,1]]),
    lambda: certify_integer_stations([[0,0],[1,1],[0,1]],max_depth=17)]
for call in calls:
    try: call()
    except ValueError: continue
    raise RuntimeError("invalid geometry was certified")
'''
    subprocess.run([sys.executable,'-B','-O','-c',code],check=True,timeout=30)


@pytest.mark.parametrize('field,value', [('scale',0),('scale',-2),('scale',3),('scale',1.5),
    ('scale',True),('scale',131072),('covered',False),('covered',1),
    ('arena_radius',1),('receive_radius',10),('cells',[]),('cells',None)])
def test_integer_metadata(integer_fixture,field,value):
    points,cert = integer_fixture
    cert[field] = value
    with pytest.raises(ValueError): verify_integer_certificate(points,cert)


@pytest.mark.parametrize('points', [[],[[0.5,0]],[[float('nan'),0]],[[float('inf'),0]],[[1951,0]],[0,1]])
def test_integer_station_contract(integer_fixture,points):
    with pytest.raises(ValueError): verify_integer_certificate(points,integer_fixture[1])
    with pytest.raises(ValueError): certify_integer_stations(points)


@pytest.mark.parametrize('ids', [[-1,1,2],[True,1,2],[0.,1,2],[0,1,99999],[0,1],None])
def test_integer_ids(integer_fixture,ids):
    points,cert = integer_fixture
    cert['cells'][0][3] = ids
    with pytest.raises(ValueError): verify_integer_certificate(points,cert)


@pytest.mark.parametrize('change', ['zero','negative','nan','inf','off_scale','outside','duplicate','missing','overlap','hull','range'])
def test_integer_leaf_and_geometry(integer_fixture,change):
    points,cert = integer_fixture
    if change in ('zero','negative','nan','inf'):
        cert['cells'][0][2] = dict(zero=0,negative=-1,nan=float('nan'),inf=float('inf'))[change]
    elif change == 'off_scale': cert['cells'][0][0] += .01
    elif change == 'outside': cert['cells'][0][0] = 1800
    elif change == 'duplicate': cert['cells'].append(copy.deepcopy(cert['cells'][0]))
    elif change == 'missing': cert['cells'].pop(27)
    elif change == 'overlap':
        x,y,h,ids = cert['cells'][27]
        cert['cells'].append([x+h/2,y+h/2,h/2,ids])
    elif change == 'hull':
        x,y,_,ids = cert['cells'][0]
        for i in ids: points[i] = [x,y]
    elif change == 'range': points[0] = [1950,1950]
    with pytest.raises(ValueError): verify_integer_certificate(points,cert)


def test_integer_closed_hull_and_strict_radius(integer_fixture):
    points,cert = integer_fixture
    x,y,h,ids = cert['cells'][0]
    for i,(dx,dy) in zip(ids,((-1,-1),(1,-1),(1,1),(-1,1))):
        points[i] = [x+dx*h,y+dy*h]
    assert verify_integer_certificate(points,cert)['verified_leaves'] == 64
    # Extra station exactly 1000 m from the opposite corner: strict radius fails.
    x,y,h,ids = cert['cells'][27]
    points.append([x-h+1000,y-h]); ids.append(len(points)-1)
    with pytest.raises(ValueError,match='receiving distance'): verify_integer_certificate(points,cert)


def test_tuple_ids_and_generated_integer_certificate(integer_fixture):
    points,cert = integer_fixture
    for cell in cert['cells']: cell[3] = tuple(cell[3])
    assert verify_cells(points,cert)['verified_leaves'] == 64
    assert verify_integer_certificate(points,cert)['verified_leaves'] == 64
    generated = certify_integer_stations(points,max_depth=8)
    assert generated['covered']
    assert verify_integer_certificate(points,generated)['verified_leaves'] == generated['leaf_count']


@pytest.mark.parametrize('radius',[500.,2000.])
def test_witness_uses_requested_radius(radius):
    points = [[1200,0],[1300,0],[1200,100]]
    cert = rectangle_certificate(points,arena_radius=500,receive_radius=radius,max_depth=0)
    assert not cert['covered']
    assert cert['witness'] == directional_witness(points,np.zeros(2),radius)
    assert (cert['witness'].get('reason') == 'no_station_in_range') == (radius == 500)


@pytest.mark.parametrize('poly,point,inside', [
    ([[0,0]],[100,100],False), ([[0,0]],[0,0],True),
    ([[0,0],[1,0]],[2,0],False), ([[0,0],[1,0]],[-1,0],False),
    ([[0,0],[1,0]],[.5,1],False), ([[0,0],[1,0]],[.5,0],True),
    ([[0,0],[1,0]],[1,0],True), ([[0,0],[0,0]],[1,0],False),
    ([[0,0],[.5,0],[1,0]],[2,0],False),
    ([[0,0],[1,0],[1,1],[0,1]],[.5,.5],True),
    ([[0,0],[1,0],[1,1],[0,1]],[2,.5],False)])
def test_truth_containment(poly,point,inside):
    assert (checks.truth_margin(poly,point) >= -1e-5) == inside


def test_empty_truth_region():
    with pytest.raises(ValueError): checks.truth_margin([], [0,0])


def test_partition_invalid_inputs_terminate():
    code = '''
from icra_final_checks import partition_check
cases = [dict(arena_radius=0,cells=[[1,0,0,[]]]),
         dict(arena_radius=1800,cells=[])]
for h in (0,-1,float('nan'),float('inf'),5e-324):
    cases.append(dict(arena_radius=1800,cells=[[1,0,h,[]]]))
for case in cases:
    try: partition_check(case)
    except ValueError: continue
    raise RuntimeError("invalid partition passed")
'''
    subprocess.run([sys.executable,'-B','-O','-c',code],check=True,timeout=10)


def test_no_removable_success_assertions():
    for module in (checks,sys.modules['integer_visibility_certificate']):
        tree = ast.parse(Path(module.__file__).read_text())
        assert not any(isinstance(node,ast.Assert) for node in ast.walk(tree))


@pytest.fixture
def audit_archive(tmp_path,monkeypatch):
    root = tmp_path/'B'; root.mkdir()
    out = root/'out'; out.mkdir()
    def write(path,value):
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(value))
    digest = hashlib.sha256(b'ok').hexdigest()
    write(out/'run_config.json',{})
    write(out/'previous_final_manifest_6741.json',{'total_offline_executions':6741})
    for name in ('summary.md','trials.csv'): (out/name).write_text('ok')
    write(root/'experiments/runs/2026-09-11_convex-visibility/certified_layouts.json',{})
    folder = root/'experiments/runs/2026-09-11_test'
    write(folder/'completion.json',{'executions':1})
    row = dict(all_cleared=True,failure=None,inconsistent_updates=0,bracket_cut_inconsistencies=0,
               cleared=16,stop_reason='public_upper_bound_16',total_virtual_s=1,commands=1)
    write(folder/'trials.jsonl',row)
    write(folder/'run_config.json',{'code_sha256':{'code.py':digest}})
    (folder/'code_snapshot').mkdir(); (folder/'code_snapshot/code.py').write_text('ok')
    write(root/'inputs_readonly_extract/input_sha256.json',{'input':digest})
    (tmp_path/'input').write_text('ok')
    public = tmp_path/'project/topic_probes/b_probe.py'; public.parent.mkdir(parents=True); public.write_text('ok')
    write(root/'experiments/runs/2026-09-10_independent/run_config.json',{'input_sha256':{'project/topic_probes/b_probe.py':digest}})
    write(root/'experiments/runs/2026-09-11_peer-paper-review/paper_sha256.json',[{'name':'paper','sha256':digest}])
    peer = root/'别人的结果/同学一/paper'; peer.parent.mkdir(parents=True); peer.write_text('ok')
    for name in ('REPORT.md','ICRA_CONNECTION.md','ROBUST_GUARANTEES_UPDATE.md','REPORT_ICRA_UPDATE.md','GOAL.md'):
        (root/name).write_text('ok')
    monkeypatch.setattr(checks,'ROOT',root); monkeypatch.setattr(checks,'OUT',out)
    monkeypatch.setattr(checks,'RUNS',{'test':1}); monkeypatch.setattr(checks,'SPECS',{})
    monkeypatch.setattr(checks,'all_paths',lambda: {})
    monkeypatch.setattr(checks.subprocess,'run',lambda *a,**k: SimpleNamespace(stdout=''))
    return root,out,folder,row,write


def test_valid_audit_archive(audit_archive):
    root,out,_,_,_ = audit_archive
    checks.main()
    assert json.loads((out/'final_checks.json').read_text())['failed'] == 0
    assert (root/'FINAL_MANIFEST.json').exists()


@pytest.mark.parametrize('fault',['count','rows','all_cleared','failure','inconsistent_updates',
    'bracket_cut_inconsistencies','cleared','total_virtual_s','commands','snapshot',
    'input','public','peer','git','links','prior'])
def test_audit_success_checks_fail_closed(audit_archive,monkeypatch,fault):
    root,out,folder,row,write = audit_archive
    if fault == 'count': write(folder/'completion.json',{'executions':2})
    elif fault == 'rows': (folder/'trials.jsonl').write_text('')
    elif fault in row:
        row[fault] = dict(all_cleared=False,failure='error',inconsistent_updates=1,
            bracket_cut_inconsistencies=1,cleared=15,total_virtual_s=360000,commands=9767)[fault]
        write(folder/'trials.jsonl',row)
    elif fault == 'snapshot': (folder/'code_snapshot/code.py').write_text('changed')
    elif fault == 'input': (root.parent/'input').write_text('changed')
    elif fault == 'public': (root.parent/'project/topic_probes/b_probe.py').write_text('changed')
    elif fault == 'peer': (root/'别人的结果/同学一/paper').write_text('changed')
    elif fault == 'git': monkeypatch.setattr(checks.subprocess,'run',lambda *a,**k: SimpleNamespace(stdout=' M code.py'))
    elif fault == 'links': (root/'REPORT.md').write_text('[missing](missing.md)')
    elif fault == 'prior': write(out/'previous_final_manifest_6741.json',{'total_offline_executions':0})
    with pytest.raises(ValueError): checks.main()
    assert not (root/'FINAL_MANIFEST.json').exists()


@pytest.mark.parametrize('fault',['endpoint','request','unconsumed','point','segment','empty'])
def test_replay_checks_fail_closed(audit_archive,monkeypatch,fault):
    root,out,_,_,write = audit_archive
    monkeypatch.setattr(checks,'SPECS',{3:{'test':{}}})
    case = 'q3__uniform__iid__77'
    (out/'traces').mkdir()
    with gzip.open(out/'traces'/f'{case}__test.jsonl.gz','wt') as stream:
        stream.write(json.dumps(dict(path='/enter',request={},response={}))+'\n')
    write(out/'scenarios_scoring_only'/f'{case}.json',{'scenario':{'sources':[{'channel':1,'x':2,'y':0}]}})
    class Policy:
        def run(self):
            if fault == 'unconsumed': return {}
            replay('/wrong' if fault == 'endpoint' else '/enter',b'{"wrong":1}' if fault == 'request' else b'{}')
            self.regions[1] = {'point':[[0,0]],'segment':[[0,0],[1,0]],'empty':[]}[fault]
            return {}
    replay = None
    def client(transport,**kwargs):
        nonlocal replay
        replay = transport
    monkeypatch.setattr(checks,'Client',client)
    monkeypatch.setattr(checks,'build',lambda *a: Policy())
    with pytest.raises(ValueError): checks.main()
    assert not (out/'final_checks.json').exists()


@pytest.mark.parametrize('kwargs',[{'max_depth':-1},{'max_depth':17},{'max_depth':True},
    {'max_depth':1.5},{'arena_radius':1},{'receive_radius':10}])
def test_generator_fixed_bounds(integer_fixture,kwargs):
    with pytest.raises(ValueError): certify_integer_stations(integer_fixture[0],**kwargs)


def test_generator_python_integer_arithmetic(integer_fixture):
    points,_ = integer_fixture
    ordinary = certify_integer_stations(points,max_depth=8)
    # Accepted NumPy integers and integral radii must still use Python scalar
    # arithmetic for the rational squared threshold, which exceeds int64.
    assert certify_integer_stations(points,max_depth=np.int64(8),
        arena_radius=1800.,receive_radius=1000.) == ordinary


@pytest.mark.parametrize('name',['grid21_29','closed21_3'])
def test_frozen_main_integer_layouts(name):
    from cover21_experiments import certificates
    item = certificates()[name]
    generated = certify_integer_stations(item['points'])
    assert generated['covered']
    expected = {'grid21_29':6976,'closed21_3':8348}[name]
    assert verify_integer_certificate(item['points'],generated)['verified_leaves'] == expected
    if item['certificate'].get('exact_integer_predicates'):
        verify_integer_certificate(item['points'],item['certificate'])
    else:
        verify_cells(item['points'],item['certificate'])
