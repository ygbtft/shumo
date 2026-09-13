"""Residual intervals, marginal histogram and within-source spatial semivariogram."""
from collections import defaultdict
import math
import random
import numpy as np
from ..geometry import angle_delta, bearing, distance
from .observations import active_measurements, angular_uncertainty


def residual_samples(rows,sources,run_id,max_angle_uncertainty_deg=.1):
    samples=[];excluded=defaultdict(int)
    for source in sources:
        if source.get('invalid'): excluded['invalid_localization']+=1;continue
        support=set(source.get('support_request_ids',[]))
        seen=set()
        for row in active_measurements(rows,source['channel']):
            if row['response'].get('measure_result')!='direction': continue
            if row['request_id'] in support: excluded['localization_training_observation']+=1;continue
            p=row['request']['position'];point=(p['x'],p['y'])
            if point in seen: excluded['repeat_location']+=1;continue
            seen.add(point)
            uncertainty=angular_uncertainty(source,point)
            if uncertainty>max_angle_uncertainty_deg:
                excluded['localization_too_uncertain']+=1;continue
            true_estimate=bearing(point,(source['x'],source['y']))
            residual=angle_delta(row['response']['svd_deg'],true_estimate)
            # 0.005 degree report rounding is distinct from the physical error bound.
            if abs(residual)>1+uncertainty+.005+1e-9:
                excluded['inconsistent_error_bound']+=1;continue
            samples.append(dict(run_id=run_id,channel=source['channel'],request_id=row['request_id'],
                                x=point[0],y=point[1],residual_deg=residual,
                                angle_uncertainty_deg=uncertainty,
                                error_interval_deg=[max(-1,residual-uncertainty-.005),min(1,residual+uncertainty+.005)]))
    return samples,dict(excluded)


def fit_error(samples,max_pairs=100000):
    values=np.asarray([s['residual_deg'] for s in samples],dtype=float)
    if len(values)==0: return {'n':0,'histogram':None,'semivariogram':[],'suggested_length_scale_m':None}
    edges=np.linspace(-1.01,1.01,21)
    counts,_=np.histogram(values,edges)
    bins=np.asarray([0,1,5,20,50,100,200,500,1000,2000,4000,8000],float)
    pairs=[[] for _ in range(len(bins)-1)]
    groups=defaultdict(list)
    for s in samples: groups[(s['run_id'],s['channel'])].append(s)
    rng=random.Random(0)
    eligible=[g for g in groups.values() if len(g)>1]
    total=sum(len(g)*(len(g)-1)//2 for g in eligible)
    if total<=max_pairs:
        selected=((g[i],g[j]) for g in eligible for i in range(len(g)) for j in range(i+1,len(g)))
    else:
        weights=[len(g)*(len(g)-1)//2 for g in eligible]
        def random_pairs():
            for _ in range(max_pairs):
                g=rng.choices(eligible,weights=weights,k=1)[0]
                a,b=rng.sample(g,2);yield a,b
        selected=random_pairs()
    mean=float(values.mean());var=float(values.var())
    for a,b in selected:
        d=distance((a['x'],a['y']),(b['x'],b['y']))
        index=int(np.searchsorted(bins,d,side='right'))-1
        if 0<=index<len(pairs): pairs[index].append((.5*(a['residual_deg']-b['residual_deg'])**2,(a['residual_deg']-mean)*(b['residual_deg']-mean)))
    variogram=[]
    for i,items in enumerate(pairs):
        variogram.append(dict(distance_bin_m=[float(bins[i]),float(bins[i+1])],pairs=len(items),
                              semivariance_deg2=float(np.mean([v[0] for v in items])) if items else None,
                              correlation=float(np.mean([v[1] for v in items])/var) if items and var>0 else None))
    crossing=next((v for v in variogram if v['pairs']>=20 and v['correlation'] is not None and v['correlation']<=math.exp(-1)),None)
    scale=sum(crossing['distance_bin_m'])/2 if crossing else None
    return dict(n=len(values),mean_deg=mean,std_deg=float(values.std()),
                quantiles_deg={str(q):float(np.percentile(values,q)) for q in (0,5,25,50,75,95,100)},
                histogram={'edges_deg':edges.tolist(),'counts':counts.tolist()},
                semivariogram=variogram,suggested_length_scale_m=scale,
                limitation='Descriptive estimate from policy-selected, held-out points; intervals include location uncertainty. Pair estimates are not independent, and a correlation crossing is only a provisional scale suggestion.')
