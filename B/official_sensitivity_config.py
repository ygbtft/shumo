"""Parameter assignments around current formal-test-2 policies; historical runs are frozen separately."""
import hashlib
import json
import random

METHOD = {3: 'range_area7', 4: 'range_grid21_29'}
DEFAULT = {
    3: dict(trial_radius=65., share_limit=6, max_active=2,
            localization_weight=.08, remainder_weight=1.5, task_order='nearest'),
    4: dict(trial_radius=35., share_limit=6, share_cooldown=150.,
            transverse_m=40., fraction=.15, steps=10, pause_limit=16, dispatch='nearest'),
}
GRID = {
    3: dict(trial_radius=[20,35,50,65,80], share_limit=[0,2,6,12,20],
            max_active=[1,2,3,4,5], localization_weight=[0,.02,.08,.32,1.28],
            remainder_weight=[0,.5,1,1.5,2]),
    4: dict(trial_radius=[20,35,50,65,80], share_limit=[0,2,6,12,20],
            share_cooldown=[0,50,150,400,800], transverse_m=[10,20,40,70,100],
            fraction=[.05,.10,.15,.30,.50], steps=[1,2,3,4,10],
            pause_limit=[0,4,8,16,24]),
}
NEIGHBORHOOD = {
    3: dict(trial_radius=[35,50,65], share_limit=[4,6,8], max_active=[2,3,4],
            localization_weight=[.04,.08,.16], remainder_weight=[1,1.5,2]),
    4: dict(trial_radius=[25,35,45], share_limit=[4,6,8],
            share_cooldown=[75,150,300], transverse_m=[20,40,60],
            fraction=[.10,.15,.25], steps=[3,4,10], pause_limit=[8,16,24]),
}
LABELS = dict(trial_radius='Trial clearance gate (m)', share_limit='Sharing limit',
    max_active='Primary localization budget', localization_weight='Localization weight',
    remainder_weight='Remainder weight', share_cooldown='Negative cooldown (m)',
    transverse_m='Transverse distance (m)', fraction='Forward fraction',
    steps='Probe round budget', pause_limit='Interruption budget')


def assignments(seed=216091303):
    rng = random.Random(seed)
    settings = []
    for p in (3,4):
        settings.append(dict(problem=p, setting='baseline', changes={}))
        for key, values in GRID[p].items():
            for value in values:
                if value != DEFAULT[p][key]:
                    settings.append(dict(problem=p, setting=f'{key}={value:g}', changes={key:value}))
    assert len(settings) == 50
    schedule = [dict(problem=p, setting='baseline', changes={}, phase='calibration', block=0)
                for p in (3,4)]
    for block in range(1,11):
        group = [dict(s, phase='screen', block=block) for s in settings]
        rng.shuffle(group)
        schedule.extend(group)
    for block in range(1,41):
        group = []
        for p in (3,4):
            group.append(dict(problem=p, setting='baseline', changes={}, phase='robustness', block=block))
            for _ in range(2):
                while True:
                    changes = {key:rng.choice(values) for key,values in NEIGHBORHOOD[p].items()}
                    if DEFAULT[p] | changes != DEFAULT[p]:
                        break
                group.append(dict(problem=p, setting='perturbed', changes=changes, phase='robustness', block=block))
        rng.shuffle(group)
        schedule.extend(group)
    for i, row in enumerate(schedule,1):
        row['order'] = i
        row['method'] = METHOD[row['problem']]
        row['parameters'] = DEFAULT[row['problem']] | row['changes']
    assert len(schedule) == 742
    return settings, schedule


def actual_parameters(policy, problem):
    mapping = dict(localization_weight='time_weight', steps='bracket_steps')
    out = {key:getattr(policy,mapping.get(key,key)) for key in DEFAULT[problem]}
    if problem == 4:
        assert policy.bracket_trial_radius == policy.trial_radius
    return out


def construct(problem, client, changes):
    import bounded_candidates as builders
    assert problem in DEFAULT and set(changes) <= set(DEFAULT[problem])
    spec = builders.SPECS[problem][METHOD[problem]].copy()
    spec.update({k:v for k,v in changes.items() if k != 'max_active'})
    policy = builders.build(client, spec, problem, builders.load_paths(problem))
    if 'max_active' in changes:
        policy.max_active = changes['max_active']
    assert actual_parameters(policy, problem) == DEFAULT[problem] | changes
    return policy


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()
