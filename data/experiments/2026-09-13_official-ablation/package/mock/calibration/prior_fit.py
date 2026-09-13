"""Censored radius bounds and conservative source-type/position priors."""
from ..geometry import angle_delta, bearing, distance
from .observations import active_measurements, angular_uncertainty


def source_constraints(rows,source,problem=None):
    if source.get('invalid'): return source
    point=(source['x'],source['y']);u=source['uncertainty_m']
    measures=list(active_measurements(rows,source['channel']))
    kind='omni' if problem==3 else source.get('kind','unknown')
    inferred=[]
    # A known existing, uncleared source must be audible <=1000m if omni.
    for row in measures:
        p=row['request']['position'];d=distance(point,(p['x'],p['y']))
        if row['response']['measure_result']=='no_signal' and d+u<1000:
            if kind=='omni': inferred.append('conflict: no_signal inside guaranteed omni radius')
            else: kind='directional';inferred.append('no_signal inside guaranteed 1000m range before clearance')
    lo,hi=1000.,1500.
    upper_evidence=[];ambiguous=0
    for row in measures:
        p=row['request']['position'];p=(p['x'],p['y']);d=distance(point,p)
        result=row['response']['measure_result']
        if result!='no_signal': lo=max(lo,d-u)
        else:
            angle_known=kind=='omni'
            if kind=='directional' and source.get('direction_deg') is not None:
                margin=angular_uncertainty(source,p)+source.get('direction_uncertainty_deg',0)
                angle_known=abs(angle_delta(bearing(point,p),source['direction_deg']))+margin<90
            if angle_known:
                hi=min(hi,d+u);upper_evidence.append(row['request_id'])
            else: ambiguous+=1
    return dict(channel=source['channel'],kind=kind,kind_evidence=inferred,
                radius_interval_m=[lo,hi],radius_interval_consistent=lo<=hi,
                radius_upper_bound_is_strict=bool(upper_evidence),upper_bound_request_ids=upper_evidence,
                ambiguous_no_signal=ambiguous,x=source['x'],y=source['y'],uncertainty_m=u)


def aggregate_priors(runs):
    counts=[];fractions=[];positions=[];radii=[];angles=[];omni_runs=0;partial_runs=0
    for run in runs:
        total=run.get('total_sources')
        sources=[s for s in run['sources'] if not s.get('invalid')]
        if total is not None:
            if type(total) is not int or not 10<=total<=16: raise ValueError('practice total_sources must be 10..16')
            counts.append(total)
        complete=(total is not None and len(sources)==total and
                  all(s['uncertainty_m']<=20 and distance((s['x'],s['y']),(0,0))<=1800 for s in sources))
        if not complete: partial_runs+=1
        # Default exports position samples only from completely localized cases, reducing detection selection bias.
        if complete: positions.extend([[s['x'],s['y']] for s in sources])
        dc=run.get('directional_count')
        if dc is not None and total is not None:
            if type(dc) is not int or not 0<=dc<=total: raise ValueError('invalid directional_count')
            fractions.append(dc/total)
        elif complete and all(s['kind']!='unknown' for s in sources):
            fractions.append(sum(s['kind']=='directional' for s in sources)/total)
        for s in sources:
            interval=s.get('radius_interval_m')
            if s.get('radius_interval_consistent') and interval[1]-interval[0]<500:
                radii.append(interval)
    return dict(count_samples=counts,directional_fraction_samples=fractions,position_samples=positions,
                radius_intervals_m=radii,excluded_partial_position_runs=partial_runs,
                limitation='Unseen sources are never labeled absent or omni. Radius observations are censored intervals, not exact radii. Uniform sampling within an interval and bootstrapping positions are explicit residual assumptions.')
