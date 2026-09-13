from copy import deepcopy
from dataclasses import replace
import json
import math
from pathlib import Path
import threading
import pytest
from mock.backends import Backend, InProcMock, HttpMock, HttpOfficial, RecordingBackend, create_backend
from mock.client_or_inproc import run_strategy
from mock.calibration.error_fit import residual_samples, fit_error
from mock.calibration.observations import auto_localize, validate_source
from mock.calibration.prior_fit import source_constraints, aggregate_priors
from mock.differ import audit_timing, compare, microseconds
from mock.error_field import ErrorConfig, ErrorField
from mock.evaluator import mandatory_conditions
from mock.protocol import Protocol, Reply
from mock.replay import read_jsonl, replay
from mock.scenario_gen import Scenario, ScenarioConfig, Source, generate
from mock.server import MockHTTPServer
from mock.simulator import InterfaceClosed, Limits, Simulator
from mock.strategy import Action, Baseline


def test_all_backends_share_contract_and_config():
    assert isinstance(create_backend({'kind':'inproc_mock'}),Backend)
    assert isinstance(create_backend({'kind':'http_mock'}),Backend)
    official=create_backend({'kind':'http_official','robot_id':'team','session_mode':'practice'})
    assert isinstance(official,Backend)
    with pytest.raises(ValueError): create_backend({'kind':'http_official','robot_id':'team','session_mode':'disabled'})
    with pytest.raises(TypeError): HttpOfficial(robot_id='team')
    with pytest.raises(ValueError): official.exchange('/admin',{})
    with pytest.raises(ValueError): HttpOfficial('http://example.com',session_mode='practice')


def test_http_official_uses_only_public_robot_requests(monkeypatch):
    seen=[]
    def fake(self,path,payload):
        seen.append((path,payload));return Reply(200,{'accepted':True,'virtual_time_s':0,'real_timestamp_ms':0})
    monkeypatch.setattr(HttpMock,'exchange',fake)
    b=HttpOfficial(robot_id='team',session_mode='practice')
    b.send(Action('/enter'),'e')
    assert seen==[('/enter',{'arena_id':'default','robot_id':'team','request_id':'e'})]


def test_recording_retries_logs_every_attempt_without_double_execution(tmp_path):
    class LostOnce(Backend):
        kind='synthetic_loss'
        def __init__(self):
            super().__init__(retries=1);self.inner=InProcMock();self.first=True
        def exchange(self,path,payload):
            reply=self.inner.exchange(path,payload)
            if self.first:
                self.first=False;raise InterfaceClosed('synthetic response loss')
            return reply
    b=RecordingBackend(LostOnce(),tmp_path/'record.jsonl')
    reply=b.send(Action('/enter'),'e');b.close()
    rows=read_jsonl(tmp_path/'record.jsonl')
    assert len(rows)==2 and rows[0]['transport_error']
    assert rows[1]['response']==reply.body
    assert rows[0]['request']==rows[1]['request']
    assert not audit_timing(rows)
    with pytest.raises(FileExistsError): RecordingBackend(InProcMock(),tmp_path/'record.jsonl')


def test_http_record_inproc_replay_zero_diff(tmp_path):
    sim=Simulator(generate(42),limits=Limits(countdown_s=0))
    server=MockHTTPServer(('127.0.0.1',0),Protocol(sim))
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    recorder=RecordingBackend(HttpMock(f'http://127.0.0.1:{server.server_port}',retries=0),tmp_path/'http.jsonl')
    try: result=run_strategy(recorder,Baseline(),max_actions=30)
    finally: recorder.close();server.shutdown();server.server_close();thread.join(2)
    rows=read_jsonl(tmp_path/'http.jsonl')
    replayed=RecordingBackend(InProcMock(seed=42),tmp_path/'inproc.jsonl')
    try: assert replay(rows,replayed)==[]
    finally: replayed.close()
    diff=compare(rows,read_jsonl(tmp_path/'inproc.jsonl'),'known_mock_scene')
    assert diff['deterministic_zero_difference']
    assert len(rows)==32 and result.stop_reason=='action_limit'
    assert all(r['request_id'] for r in rows)


def fixture_rows(tmp_path):
    p=Protocol(Simulator(Scenario(0,(Source(1,0,0,1200),)),limits=Limits(countdown_s=0)))
    backend=RecordingBackend(InProcMock(p),tmp_path/'s.jsonl')
    for key,action in [('e',Action('/enter')),('m',Action('/measure',(100,0),1)),('c',Action('/clear',(0,0),1)),('x',Action('/exit'))]: backend.send(action,key)
    backend.close()
    return read_jsonl(tmp_path/'s.jsonl')


def test_differ_locates_microsecond_and_clear_timing_rule(tmp_path):
    rows=fixture_rows(tmp_path)
    assert not audit_timing(rows)
    modified=deepcopy(rows)
    modified[2]['response']['virtual_time_s']+=2
    issues=audit_timing(modified)
    assert issues[0]['sequence']==3 and issues[0]['hint']=='clear_success_5s_vs_failure_3s'
    diff=compare(rows,modified)
    assert not diff['deterministic_zero_difference']
    assert diff['differences'][0]['delta_us']==2_000_000
    modified=deepcopy(rows);modified[1]['response']['virtual_time_s']+=.000001
    assert compare(rows,modified)['differences'][0]['delta_us']==1
    assert microseconds(.123456)==123456
    with pytest.raises(ValueError): microseconds(.0000001)


def test_differ_rejected_clock_bearings_and_idempotence(tmp_path):
    rows=fixture_rows(tmp_path)
    modified=deepcopy(rows);modified[1]['response']['svd_deg']+=.2
    assert compare(rows,modified)['deterministic_zero_difference']
    duplicate=deepcopy(rows[1]);duplicate['response']['real_timestamp_ms']+=1
    assert any(i['rule']=='idempotent_retry_changed_complete_response' for i in audit_timing(rows[:2]+[duplicate]))
    modified=deepcopy(rows);modified[1]['response']['accepted']=False
    assert any(i['rule']=='rejected_request_clock' for i in audit_timing(modified))


def test_matrix_cannot_be_reduced_by_config():
    conditions=mandatory_conditions(ScenarioConfig(position_distribution='edge'),ErrorConfig(model='iid'))
    assert len(conditions)==15
    assert {s.position_distribution for _,s,e in conditions}=={'uniform','edge','clustered'}
    assert len({(e.model,e.adversarial_sign) for _,s,e in conditions if s.position_distribution=='uniform'})==5


def rows_for_measurements(points,errors=None,radius=1200,directional=None):
    sim=Simulator(Scenario(0,(Source(1,0,0,radius,directional),)),limits=Limits(countdown_s=0))
    backend=InProcMock(Protocol(sim));backend.send(Action('/enter'),'e')
    rows=[]
    for index,point in enumerate(points):
        reply=backend.send(Action('/measure',point,1),str(index))
        if errors is not None and reply.body.get('measure_result')=='direction':
            from mock.geometry import bearing
            reply.body['svd_deg']=(bearing(point,(0,0))+errors[index])%360
        rows.append(dict(run_id='r',request_id=str(index),http_status=200,action='/measure',request=backend.last_request,response=reply.body))
    return rows


def test_localization_uncertainty_and_holdout():
    points=[(100,0),(0,100),(-100,0),(0,-100),(80,80),(-80,80)]
    rows=rows_for_measurements(points,errors=[0]*len(points))
    s=auto_localize(rows,1);validate_source(s)
    assert math.hypot(s['x'],s['y'])<=s['uncertainty_m']
    assert s['uncertainty_m']<5
    samples,excluded=residual_samples(rows,[s],'r',max_angle_uncertainty_deg=3)
    assert excluded['localization_training_observation']==3
    assert len(samples)==3
    # A clear point with 20m uncertainty does not justify short-range angle residuals.
    uncertain=dict(channel=1,x=0,y=0,uncertainty_m=20,method='independent')
    samples,excluded=residual_samples(rows,[uncertain],'r')
    assert not samples and excluded['localization_too_uncertain']==6


def test_error_fit_known_synthetic_distribution():
    points=[(300+10*i,100) for i in range(50)]
    errors=[-.9+1.8*i/49 for i in range(50)]
    rows=rows_for_measurements(points,errors)
    source=dict(channel=1,x=0,y=0,uncertainty_m=0,method='independent')
    samples,excluded=residual_samples(rows,[source],'r')
    assert len(samples)==50 and not excluded
    fit=fit_error(samples)
    assert abs(fit['mean_deg'])<1e-10 and fit['n']==50
    assert sum(v['pairs'] for v in fit['semivariogram'])==1225
    assert all(-1<=s['error_interval_deg'][0]<=s['error_interval_deg'][1]<=1 for s in samples)


def test_radius_censoring_and_directional_inference():
    source=dict(channel=1,x=0,y=0,uncertainty_m=0,method='independent',kind='omni')
    rows=rows_for_measurements([(1100,0),(1300,0)])
    c=source_constraints(rows,source)
    assert c['radius_interval_m']==[1100,1300]
    rows=rows_for_measurements([(500,0),(-500,0)],directional=0)
    source['kind']='unknown'
    c=source_constraints(rows,source)
    assert c['kind']=='directional' and c['radius_interval_m']==[1000,1500]
    assert c['ambiguous_no_signal']==1
    # Positive signal alone can never certify omni.
    c=source_constraints(rows[:1],source)
    assert c['kind']=='unknown'


def test_empirical_priors_are_explicit_and_bounded():
    cfg=ScenarioConfig(position_distribution='empirical',empirical_positions=((20,30),(100,200)),
                       empirical_counts=(10,),radius_distribution='empirical',empirical_radius_intervals=((1100,1150),))
    case=generate(10,cfg)
    assert len(case.sources)==10 and all(1100<=s.radius<=1150 for s in case.sources)
    for base in ('iid','smooth'):
        f=ErrorField(2,ErrorConfig(model='empirical',empirical_base=base,empirical_samples_deg=(-.8,0,.9)))
        values=[f.value((i,2),1) for i in range(50)]
        assert all(-.8<=v<=.9 for v in values)
        assert values[0]==f.value((0,2),1)
    conditions=mandatory_conditions(cfg,ErrorConfig(model='empirical',empirical_samples_deg=(-1,1)))
    assert len(conditions)==24


def test_incomplete_cases_not_exported_as_position_population():
    source=dict(channel=1,x=2,y=3,uncertainty_m=1,kind='unknown',radius_interval_m=[1000,1500],radius_interval_consistent=True)
    result=aggregate_priors([{'total_sources':10,'sources':[source]}])
    assert result['count_samples']==[10] and not result['position_samples']
    assert not result['directional_fraction_samples']
    sources=[dict(source,channel=c) for c in range(1,11)]
    sources[-1]['uncertainty_m']=30
    result=aggregate_priors([{'total_sources':10,'sources':sources}])
    assert not result['position_samples']
