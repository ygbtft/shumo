import hashlib,json
DEFAULT={3:{'task_order': 'nearest', 'trial_radius': 65.0, 'max_active': 2, 'share_limit': 6, 'localization_weight': 0.08, 'remainder_weight': 1.5}}
METHOD={3:'range_area7_nearest65_a2'}
def canonical_hash(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def actual_parameters(policy,problem):
    assert problem==3
    return {key:getattr(policy,'time_weight' if key=='localization_weight' else key) for key in DEFAULT[3]}
def construct(problem,client,changes):
    import bounded_candidates as builders
    assert problem==3 and not changes
    policy=builders.build(client,builders.SPECS[3][METHOD[3]],3,builders.load_paths(3))
    assert actual_parameters(policy,3)==DEFAULT[3]
    return policy
