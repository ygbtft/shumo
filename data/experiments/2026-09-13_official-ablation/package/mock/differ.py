"""Microsecond contract audit and aligned transcript diff; no oracle truth invented."""
import argparse
from decimal import Decimal, InvalidOperation
import json
import math
from pathlib import Path
from .geometry import angle_delta, distance
from .replay import read_jsonl

DETERMINISTIC=('accepted','virtual_time_s','measure_result','clear_result','exit_reason')


def microseconds(value):
    if type(value) not in (int,float): raise ValueError('timestamp must be a JSON number')
    try: scaled=Decimal(str(value))*1_000_000
    except InvalidOperation as exc: raise ValueError('invalid timestamp') from exc
    if not scaled.is_finite() or scaled!=scaled.to_integral_value():
        raise ValueError('virtual_time_s is not an exact microsecond value')
    return int(scaled)


def audit_timing(rows):
    position,channel,time_us=(0.,0.),1,0
    entered=False
    cache={}
    issues=[]
    unresolved=None
    for index,row in enumerate(rows,1):
        p,path,b=row['request'],row['action'],row.get('response')
        key=p.get('request_id')
        def issue(rule,**detail): issues.append(dict(sequence=index,request_id=key,rule=rule,**detail))
        if b is None:
            unresolved=key
            continue
        if unresolved is not None and unresolved!=key:
            issue('unresolved_transport_failure', explanation='Prior action may have executed; its ID was not retried before a new action.')
        unresolved=None
        try: actual=microseconds(b.get('virtual_time_s'))
        except ValueError as exc:
            issue('microsecond_precision',explanation=str(exc));continue
        if b.get('accepted') is not True:
            if actual!=0: issue('rejected_request_clock',expected_us=0,actual_us=actual)
            if set(b)!={'accepted','virtual_time_s','real_timestamp_ms'}: issue('rejected_response_fields')
            continue
        if row.get('http_status')!=200: issue('accepted_with_non_200_status')
        if key in cache:
            old_request,old_path,old_body=cache[key]
            if old_request!=p or old_path!=path: issue('id_reused_for_different_action')
            if old_body!=b: issue('idempotent_retry_changed_complete_response')
            continue
        components={}
        if path=='/enter':
            if entered: issue('duplicate_enter_accepted')
            entered=True
        elif not entered:
            issue('action_before_enter')
        elif path in ('/measure','/clear'):
            point=(p['position']['x'],p['position']['y'])
            movement=math.floor(distance(position,point)/5*1_000_000+.5)
            switching=1_000_000 if path=='/measure' and p['channel']!=channel else 0
            if path=='/measure':
                detection=5_000_000
                kind=b.get('measure_result')
                if kind not in ('near','direction','no_signal'): issue('measure_result_enum')
                if ('svd_deg' in b)!=(kind=='direction'): issue('near_direction_field_contract')
                if kind=='direction' and (type(b['svd_deg']) not in (float,int) or not 0<=b['svd_deg']<360): issue('bearing_range')
                channel=p['channel']
            else:
                kind=b.get('clear_result')
                if kind not in ('success','no_target_in_range'): issue('clear_result_enum')
                detection=5_000_000 if kind=='success' else 3_000_000
            components=dict(movement_us=movement,switch_us=switching,action_us=detection,previous_time_us=time_us)
            time_us+=movement+switching+detection
            position=point
        elif path=='/exit' and b.get('exit_reason')!='user_exit': issue('exit_reason')
        if actual!=time_us:
            delta=actual-time_us
            hint='movement_speed_or_rounding'
            if abs(delta)==1_000_000: hint='channel_switch_or_prior_clock_drift'
            if abs(delta)==2_000_000 and path=='/clear': hint='clear_success_5s_vs_failure_3s'
            if path in ('/enter','/exit'): hint='enter_exit_must_not_advance'
            issue('virtual_time_accumulation',expected_us=time_us,actual_us=actual,delta_us=delta,components=components,hint=hint)
        # Re-anchor to isolate the NEXT wrong transition instead of cascading drift.
        time_us=actual
        cache[key]=(p,path,b)
    if unresolved is not None:
        issues.append(dict(sequence=len(rows),request_id=unresolved,rule='unresolved_transport_failure',
                           explanation='Final connection failure has no response; whether that attempt executed is unknown.'))
    return issues


def compare(oracle,candidate,scene_alignment='unverified'):
    differences=[];bearings=[]
    for index,(a,b) in enumerate(zip(oracle,candidate),1):
        prefix=dict(sequence=index,request_id=a['request'].get('request_id'),action=a['action'])
        if a['action']!=b['action'] or a['request']!=b['request']:
            differences.append(dict(**prefix,field='request_alignment',oracle=a['request'],candidate=b['request'],hint='Different actions/IDs; subsequent comparisons require alignment.'))
            continue
        aa,bb=a.get('response'),b.get('response')
        if (aa is None)!=(bb is None):
            differences.append(dict(**prefix,field='connection_lifecycle',oracle=aa,candidate=bb,hint='Check countdown, real deadlines, end-of-session and retry-after-exit policy.'))
            continue
        if a.get('http_status')!=b.get('http_status'):
            differences.append(dict(**prefix,field='http_status',oracle=a.get('http_status'),candidate=b.get('http_status'),hint='Validation, request IDs, capacity or lifecycle.'))
        if aa is None: continue
        for field in DETERMINISTIC:
            av,bv=aa.get(field),bb.get(field)
            if av==bv: continue
            hint='business_state'
            detail={}
            if field=='virtual_time_s':
                try: detail['delta_us']=microseconds(bv)-microseconds(av)
                except ValueError: pass
                hint='See per-transcript timing audit; movement d/5, measure-only switching, detection 5s, clear 5/3s.'
            elif field=='measure_result': hint='Source existence/cleared state, receive radius, 180-degree sector or 5m near boundary; requires aligned scene evidence.'
            elif field=='clear_result': hint='20m optical radius or cleared state; independent of sector. A result change adds/subtracts 2s.'
            differences.append(dict(**prefix,field=field,oracle=av,candidate=bv,hint=hint,**detail))
        if aa.get('measure_result')==bb.get('measure_result')=='direction':
            bearings.append(dict(**prefix,delta_deg=angle_delta(bb['svd_deg'],aa['svd_deg'])))
    if len(oracle)!=len(candidate): differences.append(dict(field='record_count',oracle=len(oracle),candidate=len(candidate)))
    audits={'oracle':audit_timing(oracle),'candidate':audit_timing(candidate)}
    return dict(scene_alignment=scene_alignment,
                deterministic_zero_difference=not differences and not audits['oracle'] and not audits['candidate'],
                differences=differences,timing_audit=audits,bearing_differences=bearings,
                compared_records=min(len(oracle),len(candidate)),
                coverage=dict(accepted_records=sum(bool((r.get('response') or {}).get('accepted')) for r in oracle),
                              actions=sorted({r['action'] for r in oracle}),
                              measure_results=sorted({r['response']['measure_result'] for r in oracle if r.get('response') and 'measure_result' in r['response']}),
                              clear_results=sorted({r['response']['clear_result'] for r in oracle if r.get('response') and 'clear_result' in r['response']})),
                provenance=dict(oracle_backends=sorted({r.get('backend','unknown') for r in oracle}),candidate_backends=sorted({r.get('backend','unknown') for r in candidate})),
                limitation='Measurement/clear equality requires the same scene. Official source coordinates, radii and directions are not disclosed by the API. Unknown truth cannot be replaced with mock truth. Bearings and real timestamps are not required to match across environments.')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('oracle')
    p.add_argument('candidate',nargs='?',help='omit for timing contract audit of a single recording')
    p.add_argument('--scene-alignment',choices=('unverified','reconstructed','known_mock_scene'),default='unverified')
    p.add_argument('--output',default='mock/results/diff.json')
    args=p.parse_args()
    oracle=read_jsonl(args.oracle)
    result=compare(oracle,read_jsonl(args.candidate),args.scene_alignment) if args.candidate else {'timing_audit':audit_timing(oracle)}
    out=Path(args.output);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in ('bearing_differences','differences')},ensure_ascii=False,indent=2))
    print(out)

if __name__=='__main__': main()
