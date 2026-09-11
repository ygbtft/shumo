"""Local batch adapter; unchanged peer policy factory + B/simulator.py only."""
import os
THREADS = ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS','VECLIB_MAXIMUM_THREADS','NUMEXPR_NUM_THREADS','BLIS_NUM_THREADS')
for key in THREADS: os.environ[key] = '1'
os.environ['PYTHONDONTWRITEBYTECODE']='1'
os.environ['PYTHONHASHSEED']='0'
import sys, json, math, time, gzip, hashlib, platform, argparse, signal, traceback
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
import multiprocessing as mp
ROOT=Path('/Users/flower/math/2026/B题/B')
HERE=Path(__file__).resolve().parent

def no_network(event,args):
    if event in ('socket.connect','socket.connect_ex','socket.bind','socket.getaddrinfo'):
        raise RuntimeError('Network forbidden in local mock batch: '+event)
sys.addaudithook(no_network)

def initialize(config):
    global np, World, Source, Protocol, Client, engine, CFG, PATHS
    os.chdir(ROOT);sys.path.insert(0,str(ROOT))
    import numpy as np
    from simulator import World, Source, Protocol
    from client import Client
    import cover21_confirmation as engine
    assert Path(sys.modules['simulator'].__file__).resolve()==ROOT/'simulator.py'
    CFG=config;PATHS={k:np.array(v) for k,v in config['paths'].items()}

def generate(problem,seed):
    # Same random-case construction/order as run_experiments.make_scenarios;
    # independent, explicit SeedSequence namespace for this scale batch.
    seq=np.random.SeedSequence([20260911,problem,seed]);rng=np.random.default_rng(seq)
    n=int(rng.integers(10,17));channels=rng.choice(np.arange(1,21),n,replace=False)
    angles=rng.uniform(0,2*math.pi,n);radii=1800*np.sqrt(rng.random(n))
    points=radii[:,None]*np.column_stack([np.cos(angles),np.sin(angles)])
    reception=rng.uniform(1000,1500,n)
    directed=rng.random(n)<.5 if problem==4 else np.zeros(n,bool)
    facing=rng.uniform(0,2*math.pi,n)
    sources=[Source(int(ch),float(p[0]),float(p[1]),float(r),float(f) if d else None)
             for ch,p,r,d,f in zip(channels,points,reception,directed,facing)]
    return sources,int(seq.generate_state(1)[0])

def alarm(signum,frame): raise TimeoutError('Adapter 1200s policy watchdog expired')

def trial(task):
    problem,seed,repeat,out=task;start=time.perf_counter();cpu0=time.process_time()
    method={3:'range_area7',4:'range_grid21_29'}[problem]
    dest=Path(out)/f'q{problem}_seed{seed}_r{repeat}';dest.mkdir()
    sources,noise_seed=generate(problem,seed)
    from dataclasses import asdict
    fixture=dict(problem=problem,seed=seed,seed_sequence=[20260911,problem,seed],noise_seed=noise_seed,
                 noise='hash',rounding='nearest',sources=[asdict(s) for s in sources])
    (dest/'scenario.json').write_text(json.dumps(fixture,indent=2))
    world=World(sources,noise_seed,'hash','nearest');trace=[]
    cli=Client(Protocol(world).dispatch,transcript=trace)
    t=time.perf_counter();policy=engine.build(cli,CFG['specs'][str(problem)],problem,PATHS)
    initialization=time.perf_counter()-t;began=time.perf_counter();cpu=time.process_time()
    failure='';stats={};signal.signal(signal.SIGALRM,alarm);signal.alarm(1200)
    try: stats=policy.run()
    except Exception as exc:
        failure=repr(exc);stats=policy.stats.copy()
        (dest/'error.txt').write_text(traceback.format_exc())
    finally: signal.alarm(0)
    wall=time.perf_counter()-began;policy_cpu=time.process_time()-cpu
    score=world.score()
    if not score['cleared']: score['per_source_s']=None
    # Timestamp/UUID-independent exact feedback and request fingerprint.
    canonical=[]
    for entry in trace:
        request={k:v for k,v in entry['request'].items() if k!='request_id'}
        response={k:v for k,v in entry['response'].items() if k!='real_timestamp_ms'}
        canonical.append(dict(path=entry['path'],request=request,response=response,http_status=entry['http_status']))
    digest=hashlib.sha256(json.dumps(canonical,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    with gzip.open(dest/'trace.jsonl.gz','wt') as f:
        for entry in trace:f.write(json.dumps(entry,separators=(',',':'))+'\n')
    row=dict(problem=problem,method=method,seed=seed,noise_seed=noise_seed,repeat=repeat,**score,
             failure=failure,timeout='Timeout' in failure or 'deadline' in failure,
             wall_s=wall,cpu_s=policy_cpu,initialization_s=initialization,
             task_wall_s=time.perf_counter()-start,task_cpu_s=time.process_time()-cpu0,
             directional_sources=sum(s.facing is not None for s in sources),stats=stats,
             trace_sha256=digest,official_calls=0,artifact=str(dest.relative_to(Path(out).parent)))
    (dest/'summary.json').write_text(json.dumps(row,indent=2));return row

def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--count',type=int,default=1000)
    p.add_argument('--start-seed',type=int,default=100000);p.add_argument('--workers',type=int,default=4)
    p.add_argument('--repeat-count',type=int,default=20);a=p.parse_args()
    began=time.perf_counter();out=a.out.resolve();out.mkdir();(out/'trials').mkdir();(out/'code_snapshot').mkdir()
    os.chdir(ROOT);sys.path.insert(0,str(ROOT))
    import simulator, numpy as np, scipy
    import cover21_confirmation as engine
    paths=engine.all_paths()
    hashes={}
    for path in ROOT.glob('*.py'):
        raw=path.read_bytes();hashes[path.name]=hashlib.sha256(raw).hexdigest()
        (out/'code_snapshot'/path.name).write_bytes(raw)
    config=dict(python=sys.executable,python_version=sys.version,numpy=np.__version__,scipy=scipy.__version__,
        platform=platform.platform(),threads={k:os.environ[k] for k in THREADS},workers=a.workers,
        count_per_problem=a.count,start_seed=a.start_seed,seed_namespace=20260911,
        backend=str(Path(simulator.__file__).resolve()),official_calls=0,network='socket audit hook blocks network',
        specs={str(q):engine.SPECS[q][m] for q,m in [(3,'range_area7'),(4,'range_grid21_29')]},
        paths={k:v.tolist() for k,v in paths.items()},code_sha256=hashes,
        policy_wall_timeout_s=1200,virtual_deadline_s=360000,command=list(sys.argv))
    try:
        from threadpoolctl import threadpool_info
        config['threadpool_info']=threadpool_info()
    except ImportError:config['threadpool_info']='threadpoolctl unavailable'
    (out/'config.json').write_text(json.dumps(config,indent=2));rows=[]
    tasks=[(q,s,0,str(out/'trials')) for s in range(a.start_seed,a.start_seed+a.count) for q in (3,4)]
    with ProcessPoolExecutor(max_workers=a.workers,mp_context=mp.get_context('spawn'),initializer=initialize,initargs=(config,)) as pool:
        futures={pool.submit(trial,t):t for t in tasks}
        with (out/'trials.jsonl').open('w') as f:
            for future in as_completed(futures):
                row=future.result();rows.append(row);f.write(json.dumps(row)+'\n');f.flush()
                if len(rows)%100==0:print(f'Completed {len(rows)}/{len(tasks)}, elapsed {time.perf_counter()-began:.1f}s, failures {sum(bool(r["failure"]) or not r["all_cleared"] for r in rows)}',flush=True)
    batch_wall=time.perf_counter()-began
    # Serial, fresh interpreter worker: compare early seeds and all tail/failure cases.
    selected=set()
    for q in (3,4):
        group=[r for r in rows if r['problem']==q]
        selected.update((q,r['seed']) for r in sorted(group,key=lambda r:r['seed'])[:a.repeat_count])
        for key in ('wall_s','per_source_s'):
            selected.update((q,r['seed']) for r in sorted(group,key=lambda r:r[key] or 0,reverse=True)[:5])
        selected.update((q,r['seed']) for r in group if r['failure'] or not r['all_cleared'])
    repeats=[]
    with ProcessPoolExecutor(max_workers=1,mp_context=mp.get_context('spawn'),initializer=initialize,initargs=(config,)) as pool:
        with (out/'repeats.jsonl').open('w') as f:
            for row in pool.map(trial,[(q,s,1,str(out/'trials')) for q,s in sorted(selected)]):
                repeats.append(row);f.write(json.dumps(row)+'\n');f.flush()
    after={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in ROOT.glob('*.py')}
    completion=dict(main_runs=len(rows),repeat_runs=len(repeats),batch_wall_s=batch_wall,
        total_wall_s=time.perf_counter()-began,source_files_unchanged=after==hashes,
        changed_files=[k for k in hashes if hashes[k]!=after.get(k)],official_calls=0)
    (out/'completion.json').write_text(json.dumps(completion,indent=2));print(json.dumps(completion),flush=True)

if __name__=='__main__': main()
