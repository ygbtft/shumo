# 采集异常：保留原尝试

首个q3/uniform/iid/97候选执行返回后，icra_confirmation构造结果行时发生TypeError：dict() got multiple values for keyword argument 'initialization_s'。新训练builder在policy.stats写了初始化耗时，而确认引擎本来已测量并显式写同名字段。

已检查PID 71402不存在，进程终止；trials.jsonl为0行，traces为空，仅有首个场景fixture。没有将这次无完整评分/轨迹的尝试计入计分执行，也未将其作为算法表现使用。log.txt、冻结快照和首个fixture原样保留，不删除/移动/覆盖。

修复在task_confirmation_v2：移除策略统计中的重复计时字段，保留确认外层的独立初始化计时；算法、参数及场景流与首个真值生成之前冻结的版本相同，并核验决策文件SHA。新目录重新运行完整2145次，不能称旧尝试已通过。97首个fixture已生成的事实在新配置明确记录；未依据它改动策略或选择候选。
