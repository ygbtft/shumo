import http.client
import json
import socket
import threading
import pytest
from mock.client_or_inproc import HTTPClient, InProcessClient, run_strategy
from mock.evaluator import distribution, evaluate_case, metrics, summarize
from mock.error_field import ErrorConfig
from mock.protocol import Protocol
from mock.scenario_gen import Scenario, ScenarioConfig, generate
from mock.server import MockHTTPServer
from mock.simulator import Limits, Simulator
from mock.strategy import Action, Baseline

@pytest.fixture
def server():
    sim=Simulator(Scenario(0,()),limits=Limits(countdown_s=0))
    srv=MockHTTPServer(('127.0.0.1',0),Protocol(sim),max_connections=1)
    thread=threading.Thread(target=srv.serve_forever,daemon=True);thread.start()
    yield srv
    srv.shutdown();srv.server_close();thread.join(2)

def request(srv,path='/enter',raw=None,method='POST',headers=None):
    conn=http.client.HTTPConnection('127.0.0.1',srv.server_port,timeout=2)
    raw=raw if raw is not None else json.dumps(dict(arena_id='default',robot_id='mock-robot',request_id='e'))
    try:
        conn.request(method,path,raw,headers or {'Content-Type':'application/json'})
        res=conn.getresponse();return res.status,json.loads(res.read())
    finally: conn.close()

def test_wire_errors(server):
    for path in ('/wrong','/enter/','/enter?x=1'):
        status,body=request(server,path)
        assert status==404 and set(body)=={'accepted','real_timestamp_ms','virtual_time_s'}
    assert request(server,method='PATCH')[0]==405
    assert request(server,raw='{')[0]==400
    assert request(server,raw=' '*65537)[0]==413
    assert request(server,headers={'Content-Type':'text/plain'})[0]==415
    server.protocol.fail_next=True
    assert request(server)[0]==500
    assert request(server)[1]['accepted']

def test_wire_lifecycle_and_replay(server):
    client=HTTPClient(f'http://127.0.0.1:{server.server_port}',retries=0)
    assert client.send(Action('/enter'),'e').body['accepted']
    result=client.send(Action('/measure',(300,400),1),'m')
    assert result.body['virtual_time_s']==105
    assert client.send(Action('/measure',(300,400),1),'m')==result
    assert client.send(Action('/measure',(300,400),2),'m').status==409
    assert client.send(Action('/exit'),'x').body['exit_reason']=='user_exit'
    with pytest.raises(ConnectionError): client.send(Action('/exit'),'x')

def test_wire_closed_has_no_bytes(server):
    server.protocol.sim.enabled=False
    with socket.create_connection(('127.0.0.1',server.server_port),timeout=2) as s:
        s.sendall(b'POST /enter HTTP/1.1\r\nHost: localhost\r\nContent-Length: 2\r\n\r\n{}')
        try: assert s.recv(4096)==b''
        except ConnectionResetError: pass

def test_wire_connection_protection(server):
    assert server.slots.acquire(timeout=2)
    try: assert request(server)[0]==429
    finally: server.slots.release()

def test_wire_capacity(server):
    object.__setattr__(server.protocol.sim.limits,'max_records',1)
    request(server)
    assert request(server,raw=json.dumps(dict(arena_id='default',robot_id='mock-robot',request_id='e2')))[0]==429

def test_metrics_zero_and_summary():
    assert metrics(10,0,15)['average_clear_time_s'] is None
    assert metrics(10,2,100)['average_clear_time_s']==50
    stats=distribution([None,1,2,3])
    assert stats['undefined']==1 and stats['mean']==2 and stats['quantiles']['p50']==2

def test_runner_exposes_only_observations_and_honors_action_limit():
    class Custom:
        def next_action(self,obs):
            assert not hasattr(obs,'scenario') and not hasattr(obs,'sources')
            return Action('/measure',(0,0),1)
    sim=Simulator(generate(1),limits=Limits(countdown_s=0))
    result=run_strategy(InProcessClient(Protocol(sim)),Custom(),max_actions=2)
    assert result.stop_reason=='action_limit' and result.virtual_time_s==10
    assert len(result.trace)==4

def test_full_chain_and_reproducibility():
    args=(17,ScenarioConfig(),ErrorConfig(),'mock.strategy:Baseline')
    a,b=evaluate_case(*args),evaluate_case(*args)
    assert a['metrics']['cleared']>=10
    assert a['metrics']['cleared_fraction']==b['metrics']['cleared_fraction']
    assert a['metrics']['total_time_s']==b['metrics']['total_time_s']
    assert a['metrics']['average_clear_time_s']==a['metrics']['total_time_s']/a['metrics']['cleared']
    assert a['metrics']['stop_reason']=='user_exit'

def test_plugin_load_failure_is_saved():
    a=evaluate_case(1,ScenarioConfig(),ErrorConfig(),'mock.strategy:Missing')
    assert a['metrics']['failure'] and a['metrics']['stop_reason']=='strategy_load_error'
    assert a['metrics']['average_clear_time_s'] is None
