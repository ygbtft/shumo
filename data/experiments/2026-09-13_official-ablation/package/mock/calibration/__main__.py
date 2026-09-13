"""Fit calibration artifacts from practice journals plus localization evidence."""
import argparse
from collections import Counter
import json
from pathlib import Path
from ..replay import read_jsonl
from .observations import auto_localize, unique_accepted, validate_source
from .error_fit import residual_samples, fit_error
from .prior_fit import source_constraints, aggregate_priors


def calibrate(manifest_path,max_angle_uncertainty_deg=.1):
    path=Path(manifest_path)
    manifest=json.loads(path.read_text(encoding='utf-8'))
    if manifest.get('session_mode')!='practice': raise ValueError('Calibration supports practice records only')
    results=[];samples=[];excluded=Counter();seen_runs=set()
    for entry in manifest['runs']:
        rows=read_jsonl(path.parent/entry['recording'])
        if rows[0]['run_id'] in seen_runs: raise ValueError('duplicate recorded run would double-count calibration evidence')
        seen_runs.add(rows[0]['run_id'])
        sources=entry.get('sources',[])
        if entry.get('auto_localize'):
            channels=sorted({r['request']['channel'] for r in unique_accepted(rows) if r['action']=='/clear' and r['response'].get('clear_result')=='success'})
            supplied={s['channel'] for s in sources}
            sources=sources+[auto_localize(rows,c) for c in channels if c not in supplied]
        if len({s['channel'] for s in sources})!=len(sources): raise ValueError('duplicate localized source channel')
        for source in sources: validate_source(source)
        residuals,counts=residual_samples(rows,sources,rows[0]['run_id'],max_angle_uncertainty_deg)
        samples.extend(residuals);excluded.update(counts)
        results.append(dict(recording=entry['recording'],total_sources=entry.get('total_sources'),
                            recorded_backends=sorted({r.get('backend','unknown') for r in rows}),
                            directional_count=entry.get('directional_count'),
                            sources=[source_constraints(rows,s,entry.get('problem')) for s in sources],
                            localizations=sources))
    priors=aggregate_priors(results)
    fit=fit_error(samples)
    # Empirical exports are optional EXTRA conditions, never replacements for the mandatory stress matrix.
    scenario={}
    if priors['count_samples']: scenario['empirical_counts']=priors['count_samples']
    if priors['position_samples']: scenario.update(position_distribution='empirical',empirical_positions=priors['position_samples'])
    if priors['radius_intervals_m']: scenario.update(radius_distribution='empirical',empirical_radius_intervals=priors['radius_intervals_m'])
    if priors['directional_fraction_samples']:
        scenario['directional_fraction']=sum(priors['directional_fraction_samples'])/len(priors['directional_fraction_samples'])
    error={}
    if len(samples)>=20:
        error=dict(model='empirical',empirical_samples_deg=[max(-1,min(1,s['residual_deg'])) for s in samples],
                   empirical_base='smooth' if fit['suggested_length_scale_m'] else 'iid')
        if fit['suggested_length_scale_m']: error['length_scale_m']=max(1,fit['suggested_length_scale_m'])
    return dict(provenance=manifest.get('provenance','unspecified'),session_mode='practice',runs=results,
                samples=samples,excluded_samples=dict(excluded),error_fit=fit,priors=priors,
                export_config={'scenario':scenario,'error':error},
                assumptions=['Empirical residual point samples are approximations inside reported uncertainty intervals.',
                             'Empirical radii are sampled uniformly inside censored intervals; this is not a recovered true density.',
                             'Empirical positions bootstrap complete localized cases; limited cases and policy selection can still bias priors.',
                             'No automatic conclusion about cross-channel correlation or omnidirectionality from positive measurements alone.'])


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('manifest')
    p.add_argument('--max-angle-uncertainty',type=float,default=.1)
    p.add_argument('--output',default='mock/results/calibration')
    args=p.parse_args()
    result=calibrate(args.manifest,args.max_angle_uncertainty)
    out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
    (out/'calibration.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    (out/'empirical-config.json').write_text(json.dumps(result['export_config'],ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'samples':len(result['samples']),'excluded':result['excluded_samples'],'provenance':result['provenance'],'output':str(out)},ensure_ascii=False,indent=2))

if __name__=='__main__': main()
