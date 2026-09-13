# 官方模拟器消融实验（已完成）

本批次仅调用 Windows 内官方模拟器 v1.1 的演练测试，共 16 组 × 10 局，另有 2 局接入校验。不是本地 mock 数据，也不使用正式测试额度。

- 固定策略来源：`../2026-09-13_ablation-data/frozen`，独立部署在 Windows `C:\BAblation-20260913\B`。
- 主成绩：官方 `practice_statistics_tasks.virtual_time_us`；秒/源按组内总虚拟秒数 / 总源数计算。
- 每局排除完成率、排除失败次数单列。未完成局的短时退出不能证明效率更高。
- 官方每次分配新案例。本实验是随机分组比较，`block` 只是运行顺序区组，不代表同场景配对。
- 每个区组随机排列全部 16 组，共 10 个区组。排程已冻结在 `config.json`，不按成绩补跑、换案例或挑选结果。
- 问题三：完整策略 50 米、去顺路补测、扫描服务分阶段、去负反馈、任务最近邻、测向最近邻，以及完整策略 20/80 米。
- 问题四：完整策略 35 米、去顺路补测、扫描服务分阶段、去负反馈、任务最近邻，以及完整策略 20/40/80 米。

**已完成 160 局批次和 2 局接入校验；批次共 2060 个源全部排除。完整结果与证据限制见 [REPORT.md](REPORT.md)。**

核心证据已集中保存在 `evidence/`，官方加密日志在 `jlogs/`。`bundle_audit.json` 记录全部 162 局归档副本的独立核验；`finalization.json` 记录最终完成情况。

`runs.jsonl` 是逐局官方成绩记录，`batch.log` 是执行进度。每局的 `evidence` 指向截图、UI 文本、独立官方数据库副本和完整 HTTP 请求响应。`trials.csv`、`summary.csv` 和 `audit.json` 已汇总完整批次，并经逐局审计。

`analysis_plan.json` 记录统计方法及其确定时已完成的局数。主比较使用独立案例 bootstrap 区间，并报告源数量、全向/定向比例。随机化检验在运行顺序区组内交换标签，不能表述为相同场景配对消融。源数量调整仅作敏感性分析，不替代原始官方成绩。

在 B 目录运行：

```sh
../mock/.venv/bin/python -B official_ablation.py --output experiments/runs/2026-09-13_official-ablation --execute
../mock/.venv/bin/python -B official_ablation_analysis.py experiments/runs/2026-09-13_official-ablation
```

解释器位于 `mock/.venv` 只是复用已有 Python 环境；机器狗执行在 Windows，向官方端口 `127.0.0.1:2026` 发送 HTTP 请求。评分不调用本地模拟器。

如需中止，创建 `~/Downloads/AutoPractice/STOP`。如存在 `interruption.json`，须核查已开始案例及官方成绩后才能恢复，避免误重跑。不要并行运行另一套官方界面自动化。
