"""Official practice-only serial recorder. UI activation is deliberately external.
Uses documented robot endpoints only; no simulator internal data access.
"""
import argparse, collections, http.client, json, math, pathlib, platform, statistics, sys, time, uuid

def dist(a,b): return math.hypot(a[0]-b[0],a[1]-b[1])
def distribution(v):
 s=sorted(v)
 def q(p):
  x=(len(s)-1)*p; i=int(x); return s[i]+(s[min(i+1,len(s)-1)]-s[i])*(x-i)
 return dict(count=len(s),p50_ms=q(.5),p95_ms=q(.95),max_ms=max(s),mean_ms=statistics.mean(s))

class Run:
 def __init__(self,args):
  self.out=pathlib.Path(args.output); self.out.mkdir(exist_ok=False,parents=True)
  self.log=(self.out/'requests.jsonl').open('w',encoding='utf8'); self.rows=[]; self.robot=args.robot_id
  self.prefix=uuid.uuid4().hex; self.pos=(0,0); self.channel=1; self.vt=0; self.deadline=float('inf'); self.conn=None
  self.start=time.monotonic(); self.findings=[]; self.observations=collections.defaultdict(list)
 def req(self,action,pos=None,ch=None,phase='rules',connection='keepalive'):
  if action!='/enter' and (time.monotonic()+15>=self.deadline or self.vt>340000): raise RuntimeError('Budget reserve reached')
  payload=dict(arena_id='default',robot_id=self.robot,request_id=f'{self.prefix}-{len(self.rows):06}')
  if pos is not None: payload.update(position=dict(x=round(pos[0],6),y=round(pos[1],6)),channel=ch); pos=tuple(payload['position'].values())
  body=json.dumps(payload,separators=(',',':'),allow_nan=False).encode()
  if connection=='new' and self.conn: self.conn.close(); self.conn=None
  if self.conn is None: self.conn=http.client.HTTPConnection('127.0.0.1',2026,timeout=10)
  row=dict(schema_version=1,session_mode='practice',sequence=len(self.rows),action=action,position=payload.get('position'),channel=ch,request_id=payload['request_id'],phase=phase,connection=connection,request=payload,local_start_timestamp_ms=time.time_ns()/1e6)
  t=time.perf_counter_ns(); data=None
  try:
   self.conn.request('POST',action,body,{'Content-Type':'application/json'})
   resp=self.conn.getresponse(); raw=resp.read(); row['rtt_ms']=(time.perf_counter_ns()-t)/1e6
   row.update(http_status=resp.status,response_raw_utf8=raw.decode('utf8')); data=json.loads(raw)
   row['response']=data
   for k in ['accepted','virtual_time_s','measure_result','svd_deg','clear_result','real_timestamp_ms']: row[k]=data.get(k)
   if resp.status!=200 or data.get('accepted') is not True: raise RuntimeError(f'Unaccepted HTTP {resp.status}')
   delta=0
   if pos is not None:
    delta=dist(self.pos,pos)/5 + ((5+int(ch!=self.channel)) if action=='/measure' else (5 if data['clear_result']=='success' else 3))
    self.pos=pos
    if action=='/measure': self.channel=ch
   row.update(expected_virtual_delta_s=delta,observed_virtual_delta_s=data['virtual_time_s']-self.vt,timing_error_s=data['virtual_time_s']-self.vt-delta)
   self.vt=data['virtual_time_s']
   if action=='/enter': self.deadline=time.monotonic()+data['remaining_real_duration_s']; self.enter=data
   if action=='/measure' and data['measure_result']=='direction': self.observations[ch].append((pos,data['svd_deg']))
   return data
  except Exception as e:
   row['error']=f'{type(e).__name__}: {e}'; row.setdefault('rtt_ms',(time.perf_counter_ns()-t)/1e6); raise
  finally:
   row['local_end_timestamp_ms']=time.time_ns()/1e6
   for k in ['accepted','virtual_time_s','measure_result','svd_deg','clear_result','real_timestamp_ms']: row.setdefault(k,None)
   self.rows.append(row); self.log.write(json.dumps(row,ensure_ascii=False,allow_nan=False)+'\n'); self.log.flush()
 def measure(self,p,c,phase='rules'): return self.req('/measure',p,c,phase)
 def fit(self,obs):
  aa=ab=bb=ac=bc=0
  for (x,y),deg in obs:
   rad=math.radians(deg); a=-math.sin(rad); b=math.cos(rad); c=a*x+b*y
   aa+=a*a; ab+=a*b; bb+=b*b; ac+=a*c; bc+=b*c
  det=aa*bb-ab*ab
  if det<.02: return None
  return ((ac*bb-bc*ab)/det,(bc*aa-ac*ab)/det)
 def run(self):
  self.req('/enter',phase='control')
  # Exact attachment example plus same-position control.
  self.measure((300,400),1,'timing_example'); self.measure((300,400),2,'timing_example')
  self.req('/clear',(300,0),3,'timing_example'); self.measure((300,0),2,'timing_example')
  self.measure((300,0),2,'timing_same_channel')
  for p in [(0,0),(-1200,-1200),(0,-1200),(1200,-1200),(1200,0),(1200,1200),(0,1200),(-1200,1200),(-1200,0)]:
   for c in range(1,21): self.measure(p,c,'survey')
  print('survey complete', {c:len(o) for c,o in self.observations.items()},flush=True)
  # Solve only from ordinary measured bearings; refine locally, then seek near.
  for c in sorted(self.observations):
   estimate=self.fit(self.observations[c]); near=None; shadow=None
   if estimate is None or dist(estimate,(0,0))>2100: continue
   for radius in [100,25]:
    local=[]
    for i in range(8):
     a=i*math.pi/4; p=(estimate[0]+radius*math.cos(a),estimate[1]+radius*math.sin(a)); r=self.measure(p,c,'localize')
     if r['measure_result']=='direction': local.append((p,r['svd_deg']))
     elif r['measure_result']=='near': near=p
    fitted=self.fit(local)
    if fitted is not None: estimate=fitted
   for dx,dy in [(0,0),(-3,0),(3,0),(0,-3),(0,3),(-3,-3),(-3,3),(3,-3),(3,3)]:
    p=(estimate[0]+dx,estimate[1]+dy); r=self.measure(p,c,'near_search')
    if r['measure_result']=='near': near=p; break
   if near:
    # Every ring point is <=15m from source by near<=5 plus ring radius10.
    for i in range(12):
     a=i*math.pi/6; p=(near[0]+10*math.cos(a),near[1]+10*math.sin(a)); r=self.measure(p,c,'coverage_ring')
     if r['measure_result']=='no_signal': shadow=p
    self.measure((4000,0),c,'out_of_range')
    self.measure(near,c,'near_before_clear')
    clearpos=shadow or near
   else: clearpos=estimate
   r=self.req('/clear',clearpos,c,'clear_target')
   finding=dict(channel=c,estimated_position=estimate,near_position=near,shadow_position=shadow,clear_position=clearpos,clear_result=r['clear_result'])
   self.findings.append(finding)
   if r['clear_result']=='success':
    self.measure(near or clearpos,c,'after_clear'); self.req('/clear',clearpos,c,'clear_repeat')
   print('target',finding,flush=True)
  # Two realistic client modes, fresh IDs and strictly serial. Keep bounded.
  for mode in ['keepalive','new']:
   for i in range(210):
    phase='warmup' if i<10 else 'benchmark'
    p=(4000,0); c=i%20+1
    self.req('/measure',p,c,phase,mode)
    self.req('/clear',p,c,phase,mode)
   print('benchmark completed',mode,flush=True)
  self.req('/exit',phase='control')
 def finish(self,error=None):
  self.log.close()
  if self.conn: self.conn.close()
  groups=collections.defaultdict(list)
  for row in self.rows:
   if row.get('accepted') and not row.get('error'):
    groups['all:'+row['action']].append(row['rtt_ms'])
    result=row.get('measure_result') or row.get('clear_result')
    if result: groups['result:'+result].append(row['rtt_ms'])
    if row['phase']=='benchmark': groups['benchmark:'+row['connection']+':'+row['action']].append(row['rtt_ms'])
  summary=dict(status='error' if error else 'complete',error=error,session_mode='practice',python=sys.version,executable=sys.executable,platform=platform.platform(),elapsed_real_s=time.monotonic()-self.start,enter_response=getattr(self,'enter',None),final_virtual_time_s=self.vt,requests=len(self.rows),latency={k:distribution(v) for k,v in groups.items()},max_abs_timing_error_s=max(abs(r.get('timing_error_s',0)) for r in self.rows),findings=self.findings,percentiles='linear interpolation (n-1)*q',rtt_scope='HTTP send including connect if needed through complete body read; excludes JSON coding and recorder file writes',prism_scope='Whole guest end-to-end RTT, no native x64 control; Prism overhead not isolated')
  (self.out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf8'); print(json.dumps(summary,ensure_ascii=False),flush=True)

if __name__=='__main__':
 p=argparse.ArgumentParser(); p.add_argument('--practice',action='store_true',required=True); p.add_argument('--robot-id',required=True); p.add_argument('--output',required=True); args=p.parse_args()
 r=Run(args); err=None
 try: r.run()
 except Exception as e: err=f'{type(e).__name__}: {e}'
 finally: r.finish(err)
 sys.exit(1 if err else 0)
