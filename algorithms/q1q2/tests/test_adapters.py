import json
import math
from dataclasses import replace
import pytest
from algorithms.q1q2.adapters import (ErrorMode, ObservationRecord, observations_to_bearings,
                                  observation_record, read_jsonl, read_measurements)
from algorithms.q1q2.run import jsonable, write_json
from algorithms.q1q2.geometry import NumericPolicy
from algorithms.q1q2.q1 import solve


def record(**kwargs):
    base = ObservationRecord('/measure',(0.,0.),1,{'accepted':True,'measure_result':'direction','svd_deg':0.},
                             request_id='r1',session_id='session',stability_id='stable')
    return replace(base,**kwargs)


@pytest.mark.parametrize('mode,width', [(ErrorMode.THEORETICAL_1_DEG,1),
                                       (ErrorMode.NEAREST_ROUNDING_OUTER_1_005_DEG,1.005)])
def test_explicit_error_modes_preserve_reading(mode,width):
    result = observations_to_bearings([record()],1,mode)
    assert result[0].half_width_deg == width
    assert result[0].raw_bearing_deg == 0
    assert result[0].error_mode == mode.value
    assert result[0].rounding_assumption_source == mode.assumption_source


def test_unknown_official_does_not_invent_a_guarantee():
    with pytest.raises(ValueError,match='OFFICIAL_UNKNOWN'):
        observations_to_bearings([record()],1,ErrorMode.OFFICIAL_UNKNOWN)


def test_transport_invalid_and_non_direction_not_bearings():
    rows = [record(response={'accepted':False,'measure_result':'direction','svd_deg':1}),
            record(http_status=500),record(transport_error={'message':'offline'}),
            record(request_id='near',response={'accepted':True,'measure_result':'near'}),
            record(request_id='no_signal',response={'accepted':True,'measure_result':'no_signal'})]
    assert observations_to_bearings(rows,1,ErrorMode.THEORETICAL_1_DEG) == ()


def test_request_dedup_and_conflicts():
    first = record()
    result = observations_to_bearings([first,first,record(request_id='r2')],1,ErrorMode.THEORETICAL_1_DEG)
    assert len(result) == 1
    with pytest.raises(ValueError,match='duplicate'):
        observations_to_bearings([first,record(response={'accepted':True,'measure_result':'direction','svd_deg':.1})],1,ErrorMode.THEORETICAL_1_DEG)


def test_clearance_stage_and_session_isolation():
    rows = [record(),record(action='/clear',request_id='r2',response={'accepted':True,'clear_result':'success'}),
            record(request_id='r3',position=(100,0))]
    result = observations_to_bearings(rows,1,ErrorMode.THEORETICAL_1_DEG)
    assert len(result) == 1
    with pytest.raises(ValueError,match='cross-session'):
        observations_to_bearings([record(),record(request_id='r2',session_id='other')],1,ErrorMode.THEORETICAL_1_DEG)


@pytest.mark.parametrize('value',[360,-.01,float('nan'),float('inf')])
def test_interface_rejects_invalid_angles(value):
    with pytest.raises(ValueError):
        observations_to_bearings([record(response={'accepted':True,'measure_result':'direction','svd_deg':value})],1,ErrorMode.THEORETICAL_1_DEG)



def test_jsonl_recording_contract(tmp_path):
    path = tmp_path/'record.jsonl'
    payload = {'action':'/measure','request':{'request_id':'r','position':{'x':0,'y':0},'channel':1},
               'run_id':'s','http_status':200,'response':{'accepted':True,'measure_result':'direction','svd_deg':359.99}}
    path.write_text(json.dumps(payload)+'\n',encoding='utf-8')
    converted = observations_to_bearings(read_jsonl(path),1,ErrorMode.NEAREST_ROUNDING_OUTER_1_005_DEG)
    assert converted[0].bearing_deg == 359.99
    assert converted[0].request_id == 'r'


def test_json_finite_and_status_preserved(tmp_path):
    result = solve([],NumericPolicy())
    path = tmp_path/'result.json'
    write_json(path,result)
    text = path.read_text()
    assert 'Infinity' not in text and 'NaN' not in text
    payload = json.loads(text)
    assert payload['diameter']['length'] is None
    assert payload['diameter']['status'] == 'UNBOUNDED'
    assert payload['region']['kind'] == 'UNBOUNDED'


def test_manual_unknown_fields_refused(tmp_path):
    path = tmp_path/'input.json'
    path.write_text(json.dumps({'measurements': [{'position':[0,0],'bearing_deg':0,'truth':[1,1]}]}))
    with pytest.raises(ValueError,match='unknown measurement fields'):
        read_measurements(path)
