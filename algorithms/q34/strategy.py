"""Q3/Q4 的固定参数和构造入口：只使用第二次正式测试的方案。"""
import json
from pathlib import Path

import numpy as np

from coupled_dispatch_policy import CoupledWidthPolicy
from omni_negative_policy import OmniNegativeCompletionPolicy
from ring_coverage import stations

ROOT = Path(__file__).resolve().parent

# 这是交付参数。历史消融和参数实验使用 data/ 内各自冻结的配置。
FORMAL_PARAMETERS = {
    3: {
        'task_order': 'nearest',
        'trial_radius': 65.0,
        'max_active': 2,
        'share_limit': 6,
        'localization_weight': 0.08,
        'remainder_weight': 1.5,
    },
    4: {
        'dispatch': 'nearest',
        'trial_radius': 35.0,
        'share_limit': 6,
        'share_cooldown': 150.0,
        'transverse_m': 40.0,
        'fraction': 0.15,
        'steps': 10,
        'pause_limit': 16,
    },
}


def construct(problem, client):
    parameters = FORMAL_PARAMETERS[problem]
    if problem == 3:
        # 中心站加六个环站，覆盖全向源。最近邻排序同时考虑扫描和定位任务。
        points = stations(6, 1140.0)
        policy = OmniNegativeCompletionPolicy(
            client, points,
            mixed=False,
            dispatch_model='base',
            range_skip=True,
            area_prior=True,
            task_order=parameters['task_order'],
            trial_radius=parameters['trial_radius'],
            share_limit=parameters['share_limit'],
            localization_weight=parameters['localization_weight'],
            remainder_weight=parameters['remainder_weight'],
        )
        # 两轮预算只限制主定位测量，不限制扫描和顺路共享测量。
        policy.max_active = parameters['max_active']
        return policy

    # Q4 必须读取原始二十一站坐标及顺序，不能重新取整或重新生成布局。
    layout = json.loads((ROOT / 'layouts/grid21_29.json').read_text(encoding='utf8'))
    points = np.asarray(layout['route'])
    return CoupledWidthPolicy(
        client, points,
        mixed=True,
        dispatch_model='base',
        range_skip=True,
        dispatch=parameters['dispatch'],
        trial_radius=parameters['trial_radius'],
        share_limit=parameters['share_limit'],
        share_cooldown=parameters['share_cooldown'],
        transverse_m=parameters['transverse_m'],
        fraction=parameters['fraction'],
        steps=parameters['steps'],
        pause_limit=parameters['pause_limit'],
    )


def actual_parameters(policy, problem):
    # 直接列出实例字段，方便逐项核对，不再通过 getattr 做动态名称映射。
    if problem == 3:
        return {
            'task_order': policy.task_order,
            'trial_radius': policy.trial_radius,
            'max_active': policy.max_active,
            'share_limit': policy.share_limit,
            'localization_weight': policy.time_weight,
            'remainder_weight': policy.remainder_weight,
        }
    return {
        'dispatch': policy.dispatch,
        'trial_radius': policy.trial_radius,
        'share_limit': policy.share_limit,
        'share_cooldown': policy.share_cooldown,
        'transverse_m': policy.transverse_m,
        'fraction': policy.fraction,
        'steps': policy.bracket_steps,
        'pause_limit': policy.pause_limit,
    }
