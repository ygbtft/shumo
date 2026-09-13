# 官方敏感性实验：742局已完成并归档

全部742局来自原官方模拟器演练，742/742局全清，共9571个源；mock运行0次，正式测试0次。

先阅读[结果报告](REPORT.md)，其中列出了两题预设5%非劣效判据的实际结果。不能仅凭全部清除或差异不显著推断耗时稳健。

- [预注册计划](PLAN.md)、[冻结配置](config.json)、[统计判据](analysis_plan.json)
- [逐局数据](trials.csv)、[组汇总](summary.csv)、[宽扫比较](comparisons.csv)
- [联合扰动结论](robustness.json)、[证据审计](audit.json)、[交付核验](delivery_audit.json)
- [机制计数说明](MECHANISMS.md)与[参数路径统计](mechanisms.csv)
- figures/：参数散点、差异区间、联合扰动和动作成本图。
- runs.jsonl与host/auto_practice_evidence/：原始官方成绩、HTTP动作、UI快照和截图。
- jlogs/：官方加密行为日志原件，校验和见jlog_manifest.json。

前序消融完成归档后，本批独占官方模拟器串行执行。实验参数与排程在结果出现前冻结；没有根据宽扫结果挑选联合扰动参数。operations/保留UI采集效率修订及未记录计数的口径修订：策略运行包、主指标和统计推断函数保持不变。

deliverable_manifest.json记录最终主要交付文件的SHA-256；runtime_manifest.json、host_manifest.json和jlog_manifest.json分别核对策略、宿主脚本和官方日志。
