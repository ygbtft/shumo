# D1 / F3 修复与验证（2026-09-11）

本次仅修改 `B/discovery_priority_policy.py`、`B/discovery_priority_experiments.py`、`B/tests/test_discovery_priority_policy.py` 并新增本报告。保留工作区已有及其他并发修改，不改覆盖、定位、清除判据与主候选参数。

## D1：废弃参数残留为路线开关

根因：上一轮已移除重复计算的清源奖励，但构造参数、负值校验、实例字段及 `discovery_weight or clear_weight` 条件仍存在。即使没有已知源，非零 clear_weight 也会启动前若干任务提升重排。

修复：从构造、校验、字段及条件彻底删除 clear_weight；零 discovery_weight 直接采用基础 route。保留已精准定位频道跳过 RF 的原口径，注释说明清源不再产生额外 RF 节省，不给 source 任务重复奖励。没有忽略旧参数的适配，旧参数（含 0）由正常构造链抛出 TypeError。

复现前：审计 D 的 seed99、第八组12点、discovery_weight=0，clear_weight=0 得到 `('survey', 3)`，改为1得到 `('survey', 4)`。

复现后：不传废弃参数时首任务为 `('survey', 3)`；所有四类 discovery 策略及已有 mixed 组合、choice_count=1/4/8 均通过；显式传 clear_weight=0/1/-1 均被拒绝。原精准源排序及 RF 跳扫边界回归保留。

## F3：失实消融候选与历史对应

根因：实验仍把已失去清源奖励的配置标为 clear_reward/clear。正 discovery 权重的 clear 变体重复已有候选，零 discovery 权重的 clear_reward 则意外只控制额外路线重排。

修复：删除下表四项，当前 Q3 6项、Q4 7项，共13项。同步删除冻结说明中的“清源省后续扫描奖励”，计数按候选数计算（每候选93场，当前1209场；这是配置数量，不声称本次运行了训练）。

| 历史问题/名称 | 原配置因素 | 当前处理 |
|---|---|---|
| Q3 discover300_clear7 | discovery=300, clear=1 | 删除；移除旧因素后对应 discover300_7 |
| Q3 clear_reward7 | discovery=0, clear=1 | 删除；不提供替代名称或重排开关 |
| Q4 discover900_clear22 | discovery=900, clear=1 | 删除；移除旧因素后对应 discover900_22 |
| Q4 clear_reward22 | discovery=0, clear=1 | 删除；不提供替代名称或重排开关 |

原始17候选配置与结果继续对应 [历史 run_config.json](../B/experiments/runs/2026-09-11_discovery-priority/run_config.json)、[历史实验源码](../B/experiments/runs/2026-09-11_discovery-priority/code_snapshot/discovery_priority_experiments.py) 和同目录的策略源码快照。所有历史 code_snapshot、结果、名称原样保留；上表是参数删除关系，不代表历史含清源奖励运行与当前无奖励策略的结果等价。旧快照应按其冻结源码解释，不把旧参数传入当前工厂。

复现后：13项现存 SPECS 均不含废弃参数，并全部通过构造回归；四个旧名称均不在注册表中。

## 测试与主候选证据

全部使用 `/Users/flower/math/2026/B题/mock/.venv/bin/python -B`，在 B/ 下执行：

- `-m unittest discover -s tests -p test_discovery_priority_policy.py -v`：6/6通过，含3项新增回归（参数拒绝、审计D、候选注册/构造）。
- `-m unittest discover -s tests -v`：37/37通过，耗时4.922秒。首次运行恰逢其他修改使 icra_final_checks.py 出现暂时语法错误，2项导入失败；该外部修改恢复可解析后重跑全套得到上述结果，本次未修改该文件。
- `run_bounded_robot.py --series cover21 --problem 3 --method range_area7 --mode mock-http`，Q4换为 `--problem 4 --method range_grid21_29`：修复前后各运行一次，默认seed42，均10/10全清、inconsistent_updates=0、official_calls=0。
- `verify_bounded_http.py` 核验下列四个目录全部通过（逐条虚拟时间、客户端与后端日志、全清、动作数量），5项无网络入口守卫通过。
- 前后完整 requests.jsonl 仅去掉 request_id、real_timestamp_ms、remaining_real_duration_s 后逐条完全相同，包含位置、频道、返回值及虚拟时间；Q3为140条、Q4为293条。

| 候选 | 前后虚拟秒 | 前后RF数 | 前后动作数 | 前后距离跳扫 |
|---|---:|---:|---:|---:|
| Q3 range_area7 | 3304.341074 | 127 | 140 | 4 |
| Q4 range_grid21_29 | 5847.482087 | 281 | 293 | 21 |

日志目录（均位于 `B/robot_runs/`）：

- Q3前：`20260911-182159-251525-bounded-mock-http`
- Q3后：`20260911-182233-057532-bounded-mock-http`
- Q4前：`20260911-182159-802758-bounded-mock-http`
- Q4后：`20260911-182233-044282-bounded-mock-http`

以本次修复前的实际工作区作配对基线；Q3值与原审计报告不同，不将其他已存在的改动归因于本次修复。以上仅为本地 mock-http seed42 的闭环及轨迹一致证据，未重跑历史大规模训练。
