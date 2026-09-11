# C1 / C2 / H1 修复记录

2026-09-11。实现改动仅涉及 B/client.py、B/bounded_http.py；新增 tests/test_q34_protocol.py，既有客户端/发送故障测试改为在新的连接边界注入故障。未修改策略、数学计算、候选参数或布局。工作区包含其他并行修改，下面的前后对照固定使用同一份当前候选工厂，仅替换本任务开始时保存的两个实现文件。

| Finding | 根因与改法 | 原复现前后 |
|---|---|---|
| C1 | socket 单次阻塞超时不能约束持续到达的响应头。固定 HTTPConnection transport 在连接前持有 socket，单次定时器覆盖连接、发送、响应头和正文；到时 shutdown/close，结束时取消并 join 定时器。每次尝试预算取 timeout_s 和同一绝对 deadline 剩余量的较小值；重试沿用不可变请求体及同一 request_id。保留正文片段、截断检测、非 200 正文解析。 | A 的 .12 秒预算，修前 .3575 秒才抛 TimeoutError，修后 .1244 秒；慢正文和重试也有回归。 |
| C2 | 解析/日志写入位于锁停范围外，且先写 virtual_s 后读其他字段。现在完整核验 accepted、必需时间字段、结果枚举与方向值；拒绝非有限数和布尔值。先解析局部变量并成功写日志，再统一提交确认状态。解析/持久化失败永久锁停此实例，catch 后不能发新动作或 enter/exit。明确拒绝的正常响应仍保留既有 Rejected 语义。 | B 修前发送 /enter,/measure,/measure；修后仅 /enter,/measure，后续调用 RuntimeError。回归还覆盖无半提交、NaN/Inf、缺字段、错误枚举和磁盘写入失败。 |
| H1 | 单线程服务在请求头/正文阻塞时，shutdown 等待该线程，造成退出死锁。接受连接时记绝对读取截止，默认 5 秒，并主动 shutdown/close 超期连接；退出先禁止新连接进入、关闭当前连接，再 shutdown/join。完整包在读取超期或退出后不派发动作。 | C 修前 1.5 秒被父进程超时终止，仅打印 leaving context；修后正常打印 closed。新增测试同时覆盖半头、半正文、持续慢发、后续请求恢复服务；退出测试把读取预算设为 30 秒，仍要求退出耗时 < .5 秒。 |

B 的 enter 夹具补齐了固定协议本来必需的 real_timestamp_ms、max_real_duration_s，以便复现目标仍是后续 measure 的畸形成功响应。

测试使用 `/Users/flower/math/2026/B题/mock/.venv/bin/python -B -m unittest discover -s tests -v`，最终 **45 tests，7.589 秒，全部通过**。新增文件包含 5 个测试方法及参数化子场景；既有真实 connect/sendall 故障、执行后断连、同 ID 恢复、碎片日志与失败摘要测试均通过。最初全套发现的范围外 core 回归失败，在工作区其他模块更新后消失；本任务没有修改那些模块。`git diff --check` 在本任务改动文件上通过。

主候选验证使用最终客户端源码、mock-http、seed=42、各 10 个源：

| 候选 | 全清 | 动作数 | RF | 虚拟秒 | 距离跳扫 |
|---|---:|---:|---:|---:|---:|
| Q3 range_area7 | 10/10 | 140 | 127 | 3304.341074 | 4 |
| Q4 range_grid21_29 | 10/10 | 293 | 281 | 5847.482087 | 21 |

两项均正常 enter/exit，transport_failures=0，inconsistent_updates=0，official_calls=0。将修前两个文件配合同一当前工厂重跑 mock-http，去掉随机 request_id 和 real_timestamp_ms 后，**全部请求/响应逐条完全相等**，包含位置、频道、结果与虚拟时间。Q3 数字与原审计表不同，因此没有拿历史审计分数充当前后基线。该对照证明本次协议修复未改变这两个 seed=42 闭环的行为，不外推全部场景。

证据：

- [完整测试输出](q34-protocol-fix-evidence/tests.log)
- [A/B/C 修前修后复现](q34-protocol-fix-evidence/reproductions.json)
- [同工厂前后逐条轨迹对照](q34-protocol-fix-evidence/before-after.json)
- [最终 Q3 运行及日志路径](q34-protocol-fix-evidence/q3.log)
- [最终 Q4 运行及日志路径](q34-protocol-fix-evidence/q4.log)
- [请求账本、全清核验与 5 项 CLI guard](q34-protocol-fix-evidence/verify.json)
