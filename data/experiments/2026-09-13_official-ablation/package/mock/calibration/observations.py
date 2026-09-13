"""Conservative localization evidence, including holdout-aware bearing intersection."""
import math
from ..geometry import angle_delta, bearing, distance


def unique_accepted(rows):
    seen=set()
    for row in rows:
        if not (row.get('response') or {}).get('accepted') or row.get('http_status')!=200: continue
        key=row['request'].get('request_id')
        if key in seen: continue
        seen.add(key)
        yield row


def active_measurements(rows,channel):
    for row in unique_accepted(rows):
        if row['request'].get('channel')!=channel: continue
        if row['action']=='/clear' and row['response'].get('clear_result')=='success': break
        if row['action']=='/measure': yield row


def clip(poly,a,b,c):
    """Intersection with a*x+b*y<=c, preserving a conservative outer polygon."""
    if not poly: return []
    result=[]
    previous=poly[-1]; pv=a*previous[0]+b*previous[1]-c
    for current in poly:
        cv=a*current[0]+b*current[1]-c
        if (pv<=0)!=(cv<=0):
            t=pv/(pv-cv)
            result.append((previous[0]+t*(current[0]-previous[0]),previous[1]+t*(current[1]-previous[1])))
        if cv<=0: result.append(current)
        previous,pv=current,cv
    return result


def auto_localize(rows,channel):
    """Use alternate bearings for fit, reserve the others for residual analysis.

    Intersect +/-1.005 degree wedges and OUTER squares for known distance disks.
    The bounding radius includes polygon vertices, so it does not understate uncertainty.
    """
    measures=list(active_measurements(rows,channel))
    directions=[r for r in measures if r['response'].get('measure_result')=='direction']
    support=directions[::2]
    poly=[(-1800.,-1800.),(1800.,-1800.),(1800.,1800.),(-1800.,1800.)]
    constraints=[]
    for row in support:
        p=row['request']['position']; angle=row['response']['svd_deg']
        for offset,sign in ((-1.005,-1),(1.005,1)):
            theta=math.radians(angle+offset)
            # lower: cross(u, G-P)>=0; upper: cross(u, G-P)<=0
            a,b=sign*(-math.sin(theta)),sign*math.cos(theta)
            constraints.append((a,b,a*p['x']+b*p['y']))
    for row in unique_accepted(rows):
        if row['request'].get('channel')!=channel: continue
        b=row['response']; radius=None
        if row['action']=='/measure' and b.get('measure_result') in ('direction','near'):
            radius=5 if b['measure_result']=='near' else 1500
        elif row['action']=='/clear' and b.get('clear_result')=='success': radius=20
        if radius is not None:
            p=row['request']['position']
            constraints.extend(((1,0,p['x']+radius),(-1,0,-p['x']+radius),(0,1,p['y']+radius),(0,-1,-p['y']+radius)))
    for a,b,c in constraints: poly=clip(poly,a,b,c+1e-9)
    if not poly: return {'channel':channel,'invalid':'inconsistent localization constraints'}
    x=sum(p[0] for p in poly)/len(poly);y=sum(p[1] for p in poly)/len(poly)
    return dict(channel=channel,x=x,y=y,uncertainty_m=max(distance((x,y),p) for p in poly),
                method='bearing_holdout',support_request_ids=[r['request']['request_id'] for r in support],
                kind='unknown',polygon=poly)


def angular_uncertainty(source,point):
    d=distance((source['x'],source['y']),point)
    u=source['uncertainty_m']
    return 180. if d<=u else math.degrees(math.asin(min(1,u/d)))


def validate_source(source):
    if source.get('invalid'): return
    for key in ('x','y','uncertainty_m'):
        if key not in source or not math.isfinite(source[key]): raise ValueError(f'missing/invalid localization {key}')
    if source['uncertainty_m']<0: raise ValueError('negative localization uncertainty')
    if source.get('kind','unknown') not in ('omni','directional','unknown'): raise ValueError('invalid source kind')
    if source.get('method') not in ('independent','bearing_holdout'):
        raise ValueError('localization method must be independent or bearing_holdout')
    if source['method']=='bearing_holdout' and 'support_request_ids' not in source:
        raise ValueError('bearing-derived locations must declare support_request_ids to avoid fitting their own residuals')
