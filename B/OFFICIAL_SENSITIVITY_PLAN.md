# 当前官方参数实验配置

当前生产baseline来自第二次正式测试：Q3最近邻、65米、max_active=2；Q4最近邻、35米及默认参数。配置源为`bounded_candidates.py`，参数实验构造器`official_sensitivity_config.py`与之对应。

已完成的2026-09-13历史宽扫与联合扰动仍按各自冻结配置解释，未倒改原始日志。当前四表与统计口径见[论文素材](experiments/paper_materials/2026-09-13_formal2_baselines/论文素材.md)。旧批次冻结计划位于其原始档案，不应直接用当前源码覆盖重跑。
