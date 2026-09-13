# B题 Q3、Q4 策略与官方实验

当前运行版本统一为各题第二次正式测试采用的方案：Q3最近邻、65米、主定位预算2轮；Q4最近邻、35米，其余参数默认。

- [当前代码与使用说明](Q34_CURRENT.md)：唯一策略配置、官方入口和打包方法。
- [四张实验表](experiments/paper_materials/2026-09-13_formal2_baselines/四表汇总.md)：Q3/Q4消融、参数宽扫及追加复測。
- [论文素材](../writing-kit/kit-q34.md)：统计口径、四表、正文分析与证据边界。
- [数学模型](../models/q34/modeling-q34.md)：覆盖、定位、清除、最近邻任务排序和停止准则。
- [整理后的官方记录回放](cleanup_formal2/replay.json)：27个已保存官方案例，5746条指令逐条一致；零新模拟、零官方请求。
- [Q1/Q2复核](REPORT_Q12_UPDATE.md)：该部分独立保留。

`bounded_candidates.py`只注册两个当前方案，`run_q34_official.py`为统一官方入口。`run_bounded_robot.py`的两题默认也指向相同配置。策略核心与第二次正式冻结包一致，未改变覆盖布局或定位算法。

`experiments/runs/`及`guest_deploy_evidence/`中的原始成绩、请求日志和冻结取证材料供复核；历史研究的参数与测试成绩不作为当前默认。第一轮正式运行的旧入口、部署脚本和运行包已清理。旧论文派生表格统一由当前四表取代。
