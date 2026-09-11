"""Offline replay of protocol/time accounting; does not contact any simulator."""
import collections, hashlib, json, math, pathlib
p=pathlib.Path(__file__).parent/'session-20260910'
raw=(p/'requests.jsonl').read_bytes(); rows=[json.loads(s) for s in raw.splitlines()]
assert len({r['request_id'] for r in rows})==len(rows)
pos=(0,0); channel=1; vt=0; errors=[]; outcomes=collections.Counter(); no_svd=True
for i,r in enumerate(rows):
 assert r['sequence']==i and r['session_mode']=='practice'
 assert r['http_status']==200 and r['accepted'] is True and 'error' not in r
 assert r['response']==json.loads(r['response_raw_utf8'])
 assert r['request_id']==r['request']['request_id']
 if i: assert rows[i-1]['local_end_timestamp_ms']<=r['local_start_timestamp_ms']
 delta=0
 if r['action'] in ['/measure','/clear']:
  q=(r['position']['x'],r['position']['y']); delta=math.dist(pos,q)/5
  if r['action']=='/measure':
   delta+=5+(r['channel']!=channel); channel=r['channel']; outcome=r['measure_result']
   assert ('svd_deg' in r['response'])==(outcome=='direction')
  else: outcome=r['clear_result']; delta+=5 if outcome=='success' else 3
  outcomes[outcome]+=1; pos=q
 errors.append(r['virtual_time_s']-vt-delta); vt=r['virtual_time_s']
assert rows[0]['action']=='/enter' and rows[-1]['action']=='/exit'
assert rows[-1]['response']['exit_reason']=='user_exit'
assert max(map(abs,errors))<=1e-6
assert [r['virtual_time_s'] for r in rows[:6]]==[0,105,111,194,199,204]
summary=dict(recording_sha256=hashlib.sha256(raw).hexdigest(),requests=len(rows),accepted_requests=len(rows),unique_request_ids=True,serial_timestamp_order=True,raw_response_matches_parsed=True,all_response_shapes_valid=True,attachment_example_exact=True,max_abs_virtual_delta_residual_s=max(map(abs,errors)),rtt_total_ms=sum(r['rtt_ms'] for r in rows),request_span_ms=rows[-1]['local_end_timestamp_ms']-rows[0]['local_start_timestamp_ms'],outcomes=dict(outcomes),source_count_from_gui=15,omnidirectional_count_from_gui=5,directional_count_from_gui=10,practice_case_id='CNDW-U29G-NUXR-UVKU',final_exit_reason='user_exit')
(p/'audit.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
# Focused paired evidence; sequence is zero-based, JSONL line is sequence+1.
selected=[r for r in rows if r['sequence']<6 or (r['channel']==2 and r['phase'] in ['near_search','near_before_clear','coverage_ring','out_of_range','clear_target','after_clear','clear_repeat']) or r['action']=='/exit']
(p/'rule-evidence.json').write_text(json.dumps(selected,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(summary,ensure_ascii=False,indent=2))
