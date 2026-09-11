"""Local-only HTTP cross-validation; no changes to peer algorithms or production code."""
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, replace
import gzip
import hashlib
import json
import os
from pathlib import Path
import platform
import sys
import threading
import time
import traceback

ROOT = Path(__file__).resolve().parents[1]
PEER = ROOT / 'B'
sys.path.insert(0, str(ROOT))
# Resolve our package BEFORE peer_benchmark inserts its reference checkout into sys.path.
from mock import scenario_gen, error_field, simulator, protocol, server, evaluator
from mock.scenario_gen import Scenario, ScenarioConfig, generate
from mock.error_field import ErrorConfig, ErrorField
from mock.simulator import Simulator, Limits
from mock.protocol import Protocol
from mock.server import MockHTTPServer
from mock.evaluator import mandatory_conditions, metrics, summarize, write_json
import numpy as np

ALLOWED = set()
def network_guard(event, args):
    if event == 'socket.connect':
        address = args[1]
        if address not in ALLOWED:
            raise RuntimeError(f'Local audit blocks connection outside its owned server: {address!r}')
sys.addaudithook(network_guard)

METHODS = {3: 'range_area7', 4: 'range_grid21_29'}
ARCHIVE = PEER / 'experiments/runs/2026-09-11_cover21-confirmation'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def peer_factory():
    os.chdir(PEER)
    sys.path.insert(0, str(PEER))
    from client import Client, HttpTransport
    import cover21_confirmation as engine
    for mod in (scenario_gen, error_field, simulator, protocol, server, evaluator):
        assert Path(mod.__file__).resolve().parent == ROOT / 'mock', mod.__file__
    frozen = json.loads((ARCHIVE / 'run_config.json').read_text())
    for p, method in METHODS.items():
        assert engine.SPECS[p][method] == frozen['specs'][str(p)][method]
    paths = {k: np.array(v) for k, v in frozen['paths'].items()}
    return Client, HttpTransport, engine.build, frozen['specs'], paths


class Journal:
    def __init__(self): self.rows = []
    def append(self, row): self.rows.append(row)


class SerialSessionHTTPServer(MockHTTPServer):
    """Serialize handler lifetimes, including the protocol admission release.

    The stock threaded handler can expose a 409 race after response delivery but
    before complete_pending. This scheduling-only adapter leaves HTTP parsing,
    response bytes, physics, and the peer Client/HttpTransport unchanged.
    """
    def __init__(self, *args, **kwargs):
        self.session_lock = threading.Lock()
        super().__init__(*args, **kwargs)

    def process_request_thread(self, request, client_address):
        with self.session_lock:
            super().process_request_thread(request, client_address)


def run_case(job):
    started = time.perf_counter()
    Client, HttpTransport, build, specs, paths = peer_factory()
    p, profile, label, seed, scfg, ecfg, out, saved = job
    case = Scenario.from_dict(saved['scenario']) if saved else generate(seed, ScenarioConfig(**scfg))
    ec = ErrorConfig(**ecfg)
    sim = Simulator(case, ErrorField(seed, ec), Limits(countdown_s=0))
    http = SerialSessionHTTPServer(('127.0.0.1', 0), Protocol(sim, robot_id='mock-robot'))
    address = ('127.0.0.1', http.server_port)
    ALLOWED.add(address)
    thread = threading.Thread(target=http.serve_forever, kwargs={'poll_interval': .01}, daemon=True)
    thread.start()
    journal = Journal()
    cli = Client(HttpTransport(f'http://127.0.0.1:{http.server_port}'), robot_id='mock-robot', transcript=journal)
    stats, error, policy = {}, None, None
    try:
        policy = build(cli, specs[str(p)][METHODS[p]], p, paths)
        stats = policy.run()
        assert cli.virtual_s == sim.virtual_time_s
        assert set(policy.cleared) == sim.cleared
        assert sim.end_reason == 'user_exit'
        assert len(journal.rows) == len(sim.trace)
        assert all(r.get('http_status') == 200 and r.get('response', {}).get('accepted') is True for r in journal.rows)
    except Exception:
        error = traceback.format_exc()
    finally:
        http.shutdown()
        http.server_close()
        thread.join()
        ALLOWED.remove(address)
    row = dict(problem=p, method=METHODS[p], profile=profile, condition=label, seed=seed,
               **metrics(len(case.sources), len(sim.cleared), sim.virtual_time_s),
               actions=len(sim.trace), stop_reason=sim.end_reason, runtime_s=time.perf_counter()-started,
               error=error, missed_channels=sorted(set(sim.sources)-sim.cleared),
               failure=len(sim.cleared)!=len(case.sources) or error is not None or sim.end_reason!='user_exit',
               official_calls=0, http_attempts=len(journal.rows), policy=stats)
    result = dict(metrics=row, scenario=case.to_dict(), error=asdict(ec), trace=sim.trace,
                  http_journal=journal.rows, end_reason=sim.end_reason,
                  endpoint=f'http://127.0.0.1:{address[1]}', owned_mock=True,
                  policy_class=type(policy).__name__ if policy else None,
                  stations=policy.stations.tolist() if policy else None)
    folder = Path(out) / profile / f'q{p}' / label
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / f'seed-{seed}.json.gz'
    with gzip.open(dest, 'wt', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, allow_nan=False, separators=(',', ':'))
    if row['failure']:
        write_json(folder / 'failures' / f'seed-{seed}.json', result)
    return row


def profiles(p):
    base = ScenarioConfig(directional_fraction=0 if p == 3 else .5)
    # Fixed BEFORE evaluation; intentionally shifted from the shared default family.
    shifted = replace(base, edge_power=32, clusters=1, cluster_sigma_m=60,
                      radius_distribution='fixed', radius_fixed=1000,
                      directional_fraction=0 if p == 3 else .85,
                      direction_distribution='outward')
    return [('default', base, ErrorConfig()),
            ('shifted', shifted, ErrorConfig(length_scale_m=800, cross_channel='shared'))]


def manifest():
    files = list(PEER.glob('*.py')) + list((ROOT / 'mock').glob('*.py'))
    files += [ARCHIVE / 'run_config.json']
    return {str(f.relative_to(ROOT)): sha(f) for f in sorted(files)}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--runs', type=int, default=50)
    ap.add_argument('--shifted-runs', type=int, default=30)
    ap.add_argument('--seed', type=int, default=2026091100)
    ap.add_argument('--workers', type=int, default=4)
    ap.add_argument('--output', required=True)
    ap.add_argument('--case', help='Replay a saved .json or .json.gz from THIS runner')
    args = ap.parse_args()
    out = Path(args.output).resolve()
    out.mkdir(parents=True, exist_ok=False)
    before = manifest()
    jobs, configs = [], {}
    if args.case:
        path = Path(args.case)
        with (gzip.open(path, 'rt') if path.suffix == '.gz' else path.open()) as f: saved = json.load(f)
        r = saved['metrics']
        jobs.append((r['problem'], r['profile'], r['condition'], r['seed'], saved['scenario']['config'], saved['error'], str(out), saved))
    else:
        for p in METHODS:
            for profile, cfg, ec in profiles(p):
                n = args.runs if profile == 'default' else args.shifted_runs
                first = args.seed + (0 if profile == 'default' else 1000)
                for label, sc, err in mandatory_conditions(cfg, ec):
                    configs[f'{profile}/q{p}/{label}'] = dict(scenario=asdict(sc), error=asdict(err), runs=n, seed_start=first)
                    for seed in range(first, first+n):
                        jobs.append((p, profile, label, seed, asdict(sc), asdict(err), str(out), None))
    # Immutable design recorded before any truth generation or strategy execution.
    write_json(out/'design.json', dict(args=vars(args), configs=configs, code_sha256=before,
        backend_modules={m.__name__:m.__file__ for m in (scenario_gen,error_field,simulator,protocol,server,evaluator)},
        methods=METHODS, python=sys.version, numpy=np.__version__, platform=platform.platform(),
        official_calls=0, network_guard='socket.connect permitted only to the server bound by this worker',
        env={k:os.environ.get(k) for k in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','VECLIB_MAXIMUM_THREADS')},
        archive=str(ARCHIVE)))
    started = time.perf_counter()
    rows = []
    with (out/'rows.jsonl').open('x', encoding='utf-8') as stream:
        with ProcessPoolExecutor(args.workers) as pool:
            futures = [pool.submit(run_case, job) for job in jobs]
            for future in as_completed(futures):
                row = future.result()
                rows.append(row)
                stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False)+'\n'); stream.flush()
                if len(rows)%50==0 or row['failure']:
                    print(f'{len(rows)}/{len(jobs)} failures={sum(r["failure"] for r in rows)} elapsed={time.perf_counter()-started:.1f}s', flush=True)
    groups = {}
    for row in rows:
        key=f'{row["profile"]}/q{row["problem"]}/{row["condition"]}'
        groups.setdefault(key, []).append(row)
    summaries = {}
    for key, group in groups.items():
        group.sort(key=lambda r:r['seed'])
        summaries[key] = summarize(group)
        write_json(out/key/'rows.json', group)
        write_json(out/key/'summary.json', summaries[key])
    after = manifest()
    changes = [k for k in set(before)|set(after) if before.get(k)!=after.get(k)]
    write_json(out/'summary.json', dict(conditions=summaries, runs=len(rows), failures=sum(r['failure'] for r in rows),
        elapsed_s=time.perf_counter()-started, official_calls=0, changed_source_files=changes,
        mandatory_matrix_complete=all(sum(k.startswith(f'{prof}/q{p}/') for k in summaries)==15 for p in METHODS for prof in ('default','shifted')) if not args.case else False))
    print(json.dumps(dict(runs=len(rows), failures=sum(r['failure'] for r in rows), changed_source_files=changes)))

if __name__ == '__main__': main()
