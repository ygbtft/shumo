import hashlib,json
import original_sensitivity_config as original
DEFAULT={4:{'trial_radius': 35.0, 'share_limit': 6, 'share_cooldown': 150.0, 'transverse_m': 40.0, 'fraction': 0.15, 'steps': 10, 'pause_limit': 16, 'dispatch': 'nearest'}}
METHOD={4:'range_grid21_29'}
def canonical_hash(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def actual_parameters(policy,problem):
    assert problem==4
    return original.actual_parameters(policy,4)|{'dispatch':policy.dispatch}
def construct(problem,client,changes):
    assert problem==4 and not changes
    policy=original.construct(4,client,{})
    policy.dispatch='nearest'
    assert actual_parameters(policy,4)==DEFAULT[4]
    assert policy.bracket_trial_radius==35. and policy.bracket_steps==10
    assert policy.dispatch_model=='base' and policy.range_skip and len(policy.stations)==21
    return policy
