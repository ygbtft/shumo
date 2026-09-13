"""Q4 fusion candidates; --check-config only constructs policies without HTTP."""
import argparse
import json
import sys
from pathlib import Path

FROZEN = Path(__file__).resolve().parent / 'runtime' / 'B'
sys.path.insert(0, str(FROZEN))
import official_sensitivity_config as original
from client import Client

PROFILES = {
    'nearest35': {},
    'nearest35_fraction30': {'fraction': .30},
    'nearest35_fraction30_share2': {'fraction': .30, 'share_limit': 2},
}


def construct(client, profile):
    changes = PROFILES[profile]
    policy = original.construct(4, client, changes)
    # Same Q4 dispatcher change as component_ablation.construct('online_nearest').
    policy.dispatch = 'nearest'
    expected = original.DEFAULT[4] | changes | {'dispatch': 'nearest'}
    actual = original.actual_parameters(policy, 4) | {'dispatch': policy.dispatch}
    assert actual == expected
    assert policy.dispatch_model == 'base' and policy.range_skip
    assert policy.bracket_trial_radius == policy.trial_radius == 35.
    assert policy.bracket_steps == 10 and policy.share
    assert len(policy.stations) == 21
    return policy


def check():
    def no_requests(*args, **kwargs):
        raise AssertionError('Configuration check must never send a request')
    def deny_network(event, args):
        if event in ('socket.connect', 'socket.bind', 'socket.getaddrinfo'):
            raise AssertionError('No network during configuration verification')
    sys.addaudithook(deny_network)
    settings = {}
    for profile in PROFILES:
        policy = construct(Client(no_requests), profile)
        settings[profile] = original.actual_parameters(policy, 4) | {
            'dispatch': policy.dispatch, 'dispatch_model': policy.dispatch_model,
            'stations': len(policy.stations), 'range_skip': policy.range_skip,
            'sharing_enabled': policy.share,
        }
    assert not any(k == 'mock' or k.startswith('mock.') for k in sys.modules)
    return dict(profiles=settings, configuration_checks_passed=True,
                official_requests_sent=0, new_test_cases=0, mock_executions=0)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check-config', action='store_true', required=True)
    parser.parse_args()
    print(json.dumps(check(), ensure_ascii=False, indent=2))
