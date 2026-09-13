"""Recompute key result invariants and replay a failure per factorial control."""
import argparse
import hashlib
import json
from pathlib import Path
import component_ablation as a
import component_ablation_supplement as s


def read_rows(path):
    return [json.loads(line) for line in path.open()]


def run_with_trace(p, setting, fixture):
    scenario=a.harness.Scenario.from_dict(fixture['scenario'])
    sim=a.harness.Simulator(scenario,a.harness.ErrorField(scenario.seed,a.harness.ErrorConfig(**fixture['error'])),
                            a.harness.Limits(countdown_s=0))
    policy=s.construct(p,a.harness.Client(a.harness.Transport(a.harness.Protocol(sim)),robot_id='mock-robot'),setting)
    failure=''
    try:policy.run()
    except a.ComponentUnavailable as exc:
        failure=str(exc);policy.client.exit()
    return sim,policy,failure


def normalized(trace):
    return [dict(path=e['path'],position=e['request'].get('position'),channel=e['request'].get('channel'),
                 response={k:v for k,v in e['response'].items() if k!='real_timestamp_ms'})
            for e in trace]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive',type=Path,required=True)
    args=parser.parse_args();out=args.archive.resolve()
    phases=['training','validation','supplement/stress','supplement/interaction_training','supplement/interaction_validation']
    all_rows={phase:read_rows(out/phase/'trials.jsonl') for phase in phases}
    audits=[];failures=[];total=0;max_error=0.
    for phase,rows in all_rows.items():
        total+=len(rows)
        summary=json.loads((out/phase/'summary.json').read_text())
        baseline={(r['problem'],r['case_id']):r for r in rows if r['setting']=='baseline'}
        for r in rows:
            assert r['certified_failures']==0
            assert not r['failure'] or r['unavailable'], (phase,r['case_id'],r['failure'])
            assert r['all_cleared']==(r['cleared']==r['sources'] and not r['failure'])
            max_error=max(max_error,abs(r['ledger_error_s']))
            if r['setting']=='no_share':assert r['stats']['shared_known_measurements']==0
            if r['setting'] in ('no_early_trial','certified_only'):
                assert r['stats'].get('early_optical_trials',0)==0
                assert r['stats'].get('bracket_optical_trials',0)==0
            if r['setting']=='certified_only':assert r['misses']==0
            if r['setting']=='no_negative':
                if r['problem']==3:assert r['stats']['omni_negative_cuts']==0
                else:assert r['stats']['bracket_pair_cuts']==r['stats']['ablation_disabled_negative_calls']
            if 'without_grid' in r['setting'] or r['setting']=='no_optical_grid':
                assert r['stats']['optical_fallback_calls']==0
            if r['failure']:
                assert r['stats']['ablation_missing_grid']==1
                assert r['failure_trace'][-1]['path']=='/exit'
                assert r['failure_trace'][-2]['response'].get('clear_result')=='no_target_in_range'
                failures.append(dict(phase=phase,problem=r['problem'],setting=r['setting'],case_id=r['case_id'],
                                     cleared=r['cleared'],sources=r['sources'],failure=r['failure']))
        for item in summary:
            group=[r for r in rows if r['problem']==item['problem'] and r['setting']==item['setting']]
            n=sum(r['sources'] for r in group)
            assert len({r['case_id'] for r in group})==len(group)
            assert n==item['sources'] and len(group)==item['runs']
            assert abs(sum(r['total_virtual_s'] for r in group)/n-item['seconds_per_source'])<1e-10
            assert item['all_cleared']==sum(r['all_cleared'] for r in group)
            d=sum(r['total_virtual_s']-baseline[r['problem'],r['case_id']]['total_virtual_s'] for r in group)/n
            assert abs(d-item['delta'])<1e-10
        audits.append(dict(phase=phase,runs=len(rows),failed=sum(bool(r['failure']) for r in rows),
                           unexpected_errors=0,summary_recomputed=True))
    # Repeated controls must agree across independent worker executions.
    for phase in ('training','validation'):
        original={(r['problem'],r['setting'],r['case_id']):r for r in all_rows[phase]}
        for r in all_rows['supplement/interaction_'+phase]:
            if 'without_grid' in r['setting']:continue
            old=original[r['problem'],r['setting'],r['case_id']]
            for key in ('total_virtual_s','distance_m','measurements','switches','misses','cleared','stats'):
                assert r[key]==old[key],(phase,key)
    train_ids={r['case_id'] for r in all_rows['training']}
    validation_ids={r['case_id'] for r in all_rows['validation']}
    assert train_ids.isdisjoint(validation_ids)
    # Replay the earliest failure in each problem, then prove the retained-grid
    # counterpart shares the entire accepted action prefix and completes.
    replay=[]
    fixtures={int(p):{r['case_id']:r for r in rows} for p,rows in
              json.loads((out/'validation/fixtures.json').read_text()).items()}
    rows=all_rows['supplement/interaction_validation']
    for p,combo,weak in ((3,'nearest_without_grid','nearest_sensing'),(4,'negative_without_grid','no_negative')):
        old=next(r for r in rows if r['problem']==p and r['setting']==combo and r['failure'])
        fixture=fixtures[p][old['case_id']]
        failed,policy,error=run_with_trace(p,combo,fixture)
        full,full_policy,noerror=run_with_trace(p,weak,fixture)
        assert error and not noerror
        assert normalized(failed.trace)==normalized(old['failure_trace'])
        assert normalized(full.trace[:len(failed.trace)-1])==normalized(failed.trace[:-1])
        assert len(full.cleared)==old['sources'] and full_policy.stats['optical_fallback_calls']>0
        evidence=dict(problem=p,case_id=old['case_id'],setting=combo,prefix_identical=True,
                      removed_grid_cleared=len(failed.cleared),retained_grid_cleared=len(full.cleared),
                      grid_calls=full_policy.stats['optical_fallback_calls'],failure_trace=failed.trace,
                      retained_grid_trace=full.trace)
        (out/f'failure_witness_q{p}.json').write_text(json.dumps(evidence,indent=2))
        replay.append({k:v for k,v in evidence.items() if not k.endswith('trace')})
    hashes=json.loads((out/'config.json').read_text())['sha256']
    integrity={f:hashlib.sha256(Path(f).read_bytes()).hexdigest()==h for f,h in hashes.items()}
    assert all(integrity.values())
    audit=dict(total_valid_executions=total,phases=audits,unexpected_errors=0,
               failed_completions=len(failures),max_abs_ledger_error_s=max_error,
               train_validation_disjoint=True,replicated_controls_identical=True,
               original_files_unchanged=all(integrity.values()),files=integrity,
               conditional_failure_replays=replay,official_calls=0)
    (out/'audit.json').write_text(json.dumps(audit,indent=2)+'\n')
    (out/'failure_index.json').write_text(json.dumps(failures,indent=2)+'\n')
    print(json.dumps({k:v for k,v in audit.items() if k not in ('files','conditional_failure_replays')},indent=2))

if __name__=='__main__':main()
