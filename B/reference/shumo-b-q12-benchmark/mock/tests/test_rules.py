from dataclasses import replace
import json
import math
import threading
from concurrent.futures import ThreadPoolExecutor
import pytest
from mock.error_field import ErrorConfig, ErrorField
from mock.geometry import angle_delta, bearing, covered
from mock.protocol import Protocol
from mock.scenario_gen import Scenario, ScenarioConfig, Source, generate
from mock.simulator import InterfaceClosed, Limits, Simulator

class Clock:
    def __init__(self): self.now = 1000.
    def __call__(self): return self.now

def build(sources=(), limits=None, error=None):
    clock = Clock()
    sim = Simulator(Scenario(1, tuple(sources)), error, limits or Limits(countdown_s=0), clock, clock)
    return sim, Protocol(sim), clock

def payload(key='x', **extra):
    return dict(arena_id='default', robot_id='mock-robot', request_id=key, **extra)

def send(p, path, key='x', point=None, channel=1, **extra):
    data = payload(key, **extra)
    if point is not None: data.update(position=dict(x=point[0],y=point[1]), channel=channel)
    return p.handle('POST', path, json.dumps(data).encode(), {'Content-Type':'application/json'})

def test_document_timing_example():
    s, p, _ = build()
    assert send(p,'/enter','e').body['virtual_time_s'] == 0
    expected = [('/measure',(300,400),1,105),('/measure',(300,400),2,111),('/clear',(300,0),3,194),('/measure',(300,0),2,199)]
    for i,(path,point,c,t) in enumerate(expected):
        assert send(p,path,str(i),point,c).body['virtual_time_s'] == t
    assert send(p,'/exit','exit').body['virtual_time_s'] == 199
    assert s.channel == 2

def test_success_repeat_clear_and_no_switch():
    s,p,_ = build([Source(7,20,0,1000,0)])
    send(p,'/enter')
    assert send(p,'/measure','m',(0,0),7).body['measure_result']=='no_signal'
    assert s.channel == 7
    assert send(p,'/clear','c',(0,0),7).body['clear_result']=='success'
    assert s.virtual_time_s == 11
    assert send(p,'/clear','c2',(0,0),1).body['clear_result']=='no_target_in_range'
    assert s.channel == 7 and s.virtual_time_s == 14
    assert send(p,'/clear','c3',(0,0),7).body['clear_result']=='no_target_in_range'
    assert send(p,'/measure','m2',(0,0),7).body['measure_result']=='no_signal'
    assert s.virtual_time_s == 22

@pytest.mark.parametrize('point,result', [((5,0),'near'),((5.000001,0),'direction'),((1000,0),'direction'),((1000.000001,0),'no_signal'),((-1,0),'no_signal'),((0,5),'near'),((0,0),'near')])
def test_near_and_radius_boundaries(point,result):
    s,p,_=build([Source(1,0,0,1000,0)])
    send(p,'/enter')
    body=send(p,'/measure','m',point).body
    assert body['measure_result']==result
    assert ('svd_deg' in body)==(result=='direction')

@pytest.mark.parametrize('heading', [0,1,90,179,270,359])
def test_sector_wraparound(heading):
    source=Source(1,0,0,1200,heading)
    for delta in (-90,90):
        t=math.radians(heading+delta)
        assert covered(source,(100*math.cos(t),100*math.sin(t)))
    t=math.radians(heading+90.00001)
    assert not covered(source,(100*math.cos(t),100*math.sin(t)))

def test_omni_and_angle_convention():
    for p,a in [((1,0),0),((0,1),90),((-1,0),180),((0,-1),270)]:
        assert bearing((0,0),p)==a
        assert covered(Source(1,0,0,1000),p)

@pytest.mark.parametrize('distance,success', [(20,True),(20.00001,False)])
def test_clear_boundary(distance,success):
    _,p,_=build([Source(1,distance,0,1000,0)])
    send(p,'/enter')
    r=send(p,'/clear','c',(0,0))
    assert (r.body['clear_result']=='success')==success
    assert r.body['virtual_time_s']==(5 if success else 3)

def test_microseconds_and_outside_arena():
    s,p,_=build();send(p,'/enter')
    assert send(p,'/measure','a',(.000003,0)).body['virtual_time_s']==5.000001
    send(p,'/measure','b',(3000,0))
    assert s.position==(3000,0)

@pytest.mark.parametrize('model', ['iid','smooth','adversarial'])
def test_fixed_bounded_error_field(model):
    config=ErrorConfig(model=model)
    f=ErrorField(99,config)
    values=[f.value((i*.73,i*2.13),1) for i in range(1000)]
    assert all(-1<=v<=1 for v in values)
    assert values==[ErrorField(99,config).value((i*.73,i*2.13),1) for i in range(1000)]
    if model=='iid':
        assert abs(sum(values)/len(values))<.06
        assert .28<sum(v*v for v in values)/len(values)<.38
    if model=='smooth':
        assert abs(f.value((1,2),1)-f.value((1.001,2),1))<.001

def test_shared_field_and_adversarial_signs():
    f=ErrorField(2,ErrorConfig(cross_channel='shared'))
    assert f.value((0.,-0.),1)==f.value((-0.,0.),20)
    for sign,expected in [('positive',1),('negative',-1)]:
        assert ErrorField(2,ErrorConfig(model='adversarial',adversarial_sign=sign)).value((2,3),1)==expected
    assert set(ErrorField(2,ErrorConfig(model='adversarial',adversarial_sign='spatial')).value((i,3),1) for i in range(50))=={-1,1}

def test_bearing_rounding_and_wrap():
    angle=358.999
    source=Source(1,100*math.cos(math.radians(angle)),100*math.sin(math.radians(angle)),1000)
    s,p,_=build([source],error=ErrorField(1,ErrorConfig(model='adversarial')))
    send(p,'/enter')
    a=send(p,'/measure','a',(0,0)).body['svd_deg']
    assert a==0
    b=send(p,'/measure','b',(0,0)).body['svd_deg']
    assert a==b
    assert abs(angle_delta(a,angle))<=1.005

def test_reject_has_zero_clock_and_does_not_reserve_id():
    s,p,_=build();send(p,'/enter','e');send(p,'/measure','m',(1,0))
    old=s.time_us
    assert send(p,'/clear','fix',(5,0),5,typo=2).body == {'accepted':False,'real_timestamp_ms':1000000,'virtual_time_s':0}
    assert s.time_us==old and s.position==(1,0) and s.channel==1
    assert send(p,'/clear','fix',(5,0),5).body['accepted']

@pytest.mark.parametrize('mutation,status', [
    ({'robot_id':'wrong'},200),({'arena_id':'other'},200),({'unknown':1},200),
    ({'robot_id':''},400),({'request_id':''},400),({'request_id':'a\u200bb'},400),
    ({'robot_id':'a\nb'},400),({'request_id':'x'*129},400),({'robot_id':'中'*22},400),
    ({'arena_id':3},400),({'channel':True},400),({'channel':1.5},400),({'channel':0},400),({'channel':21},400),
    ({'position':{'x':True,'y':0}},400),({'position':{'x':2000001,'y':0}},400),
    ({'position':{'x':float('nan'),'y':0}},400),({'position':{'x':float('inf'),'y':0}},400),
    ({'position':{'x':0}},400),({'position':{'x':0,'y':0,'z':0}},200)])
def test_validation(mutation,status):
    s,p,_=build();send(p,'/enter','e')
    data=payload(position={'x':0,'y':0},channel=1);data.update(mutation)
    r=p.handle('POST','/measure',json.dumps(data).encode(),{'Content-Type':'application/json'})
    assert r.status==status and r.body['accepted'] is False
    assert s.time_us==0 and len(p.cache)==1

def test_integer_valued_float_and_coordinate_limit():
    _,p,_=build();send(p,'/enter','e')
    assert send(p,'/measure','m',(2_000_000,0),1.0).body['accepted']

@pytest.mark.parametrize('raw', [b'[]',b'null',b'{',b'{}',b'\xff',b'\xef\xbb\xbf{}',b'{"x":1,"x":2}',b'{"x":NaN}',b'{"x":'+b'['*16+b'0'+b']'*16+b'}',b'{"arena_id":"default","robot_id":"\\ud800","request_id":"x"}'])
def test_bad_json(raw):
    _,p,_=build()
    assert p.handle('POST','/enter',raw,{'Content-Type':'application/json'}).status==400

def test_http_status_codes_and_header_contract():
    _,p,_=build()
    valid=json.dumps(payload()).encode()
    for path in ('/missing','/enter/','/enter?x=1'):
        assert p.handle('POST',path,valid,{}).status==404
    assert p.handle('GET','/enter',valid,{}).status==405
    for headers in ({},{'Content-Type':'text/plain'},{'Content-Type':'application/json; foo=x'}, {'Content-Type':'application/json; charset=ascii'}, {'Content-Type':'application/json','Content-Encoding':'gzip'}):
        assert p.handle('POST','/enter',valid,headers).status==415
    assert p.handle('POST','/enter',b' '*65537,{'Content-Type':'application/json'}).status==413
    padded=valid+b' '*(65536-len(valid))
    assert p.handle('POST','/enter',padded,{'Content-Type':'application/json; charset=utf-8','Content-Encoding':'identity'}).body['accepted']

def test_idempotency_and_semantic_comparison():
    s,p,clock=build();send(p,'/enter','e')
    r=send(p,'/measure','m',(1,2),1)
    clock.now+=3
    assert send(p,'/measure','m',(1.,2.),1.0)==r
    assert s.virtual_time_s==r.body['virtual_time_s']
    assert send(p,'/clear','m',(1,2),1).status==409
    assert send(p,'/measure','m',(1,3),1).status==409
    assert send(p,'/measure','m',(1,2),2).status==409
    assert send(p,'/enter','e').body['accepted']
    assert not send(p,'/enter','e2').body['accepted']

def test_capacity_invalid_protection_and_500():
    s,p,_=build(limits=Limits(countdown_s=0,max_records=1))
    send(p,'/enter','e')
    assert send(p,'/measure','m',(0,0)).status==429
    assert send(p,'/enter','e').body['accepted']
    s,p,_=build();p.invalid_limit=1
    assert send(p,'/enter','a',foo=1).status==200
    assert send(p,'/enter','a',foo=1).status==429
    assert send(p,'/enter','a').body['accepted']
    p.fail_next=True
    assert send(p,'/measure','m',(0,0)).status==500
    assert s.time_us==0
    assert send(p,'/measure','m',(0,0)).body['accepted']

def test_state_and_closed_interface():
    s,p,clock=build(limits=Limits(countdown_s=5))
    with pytest.raises(InterfaceClosed): send(p,'/enter')
    clock.now+=5
    assert not send(p,'/measure','m',(0,0)).body['accepted']
    assert not send(p,'/exit','x').body['accepted']
    assert send(p,'/enter','e').body['remaining_real_duration_s']==1200
    assert send(p,'/exit','x').body['exit_reason']=='user_exit'
    with pytest.raises(InterfaceClosed): send(p,'/exit','x')

def test_optional_exit_replay():
    _,p,_=build(limits=Limits(countdown_s=0,replay_after_end=True))
    send(p,'/enter','e'); r=send(p,'/exit','x')
    assert send(p,'/exit','x')==r
    with pytest.raises(InterfaceClosed): send(p,'/exit','new')

@pytest.mark.parametrize('late,remaining',[(0,1200),(300,1200),(300.5,1199),(1000,500)])
def test_remaining_real_window(late,remaining):
    s,p,c=build();c.now+=late
    assert send(p,'/enter','e').body['remaining_real_duration_s']==remaining
    c.now=s.open_at+min(1500,late+1200)
    with pytest.raises(InterfaceClosed): send(p,'/measure','m',(0,0))

def test_window_without_enter_and_disabled():
    s,p,c=build();s.enabled=False
    with pytest.raises(InterfaceClosed): send(p,'/enter')
    s.enabled=True;c.now+=1500
    with pytest.raises(InterfaceClosed): send(p,'/enter')
    assert s.end_reason=='window_timeout'

def test_virtual_overrun_completes_registered_action():
    s,p,_=build(limits=Limits(countdown_s=0,virtual_s=6));send(p,'/enter','e')
    assert send(p,'/measure','m',(100,0)).body['virtual_time_s']==25
    assert s.end_reason=='virtual_timeout'
    with pytest.raises(InterfaceClosed): send(p,'/exit','x')

def test_action_registered_before_real_deadline_finishes(monkeypatch):
    s,p,c=build();send(p,'/enter','e');c.now+=1199
    original=s.execute
    def slow(*a):
        c.now+=2
        return original(*a)
    monkeypatch.setattr(s,'execute',slow)
    assert send(p,'/measure','m',(0,0)).body['accepted']
    assert s.end_reason=='real_timeout'

def test_concurrent_duplicate_waits_different_action_conflicts(monkeypatch):
    s,p,_=build();send(p,'/enter','e')
    entered,release=threading.Event(),threading.Event()
    original=s.execute
    def slow(*a):
        entered.set(); assert release.wait(3)
        return original(*a)
    monkeypatch.setattr(s,'execute',slow)
    with ThreadPoolExecutor(3) as pool:
        first=pool.submit(send,p,'/measure','m',(0,0))
        assert entered.wait(3)
        second=pool.submit(send,p,'/measure','m',(0,0))
        assert send(p,'/measure','n',(0,0)).status==409
        release.set()
        assert first.result()==second.result()
    assert s.virtual_time_s==5 and len(s.trace)==2

@pytest.mark.parametrize('position', ['uniform','edge','clustered'])
@pytest.mark.parametrize('radius', ['uniform','fixed','beta'])
@pytest.mark.parametrize('direction', ['uniform','fixed','inward','outward','vonmises'])
def test_scenario_distributions(position,radius,direction):
    cfg=ScenarioConfig(position_distribution=position,radius_distribution=radius,direction_distribution=direction)
    a=generate(12,cfg)
    assert a==generate(12,cfg)
    assert 10<=len(a.sources)<=16
    assert len({s.channel for s in a.sources})==len(a.sources)
    assert any(s.direction_deg is None for s in a.sources)
    assert any(s.direction_deg is not None for s in a.sources)
    assert all(math.hypot(s.x,s.y)<=1800 and 1000<=s.radius<=1500 for s in a.sources)
