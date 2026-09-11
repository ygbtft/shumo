# NTJ_B：B 题算法与实验工作区

这是 `ygbtft/shumo` 仓库 `NTJ_B` 分支中的独立研究快照。入口是 [REPORT.md](REPORT.md)，最新正确性复核见 [REPORT_Q12_UPDATE.md](REPORT_Q12_UPDATE.md)。持续算法优化目前按用户要求暂停；本次发布只归档已有工作。

## 当前状态

- 已实现覆盖扫描、路线优化、主动定位、接收保证和多种元启发式策略，并保存代码、配置、动作记录与数值结果。
- 最新 Q1/Q2 复核使用同学 b 分支提交 `253bf943a58d6f21de88f14fdc940da66b87ab96` 的独立夹具。我们的 Q1 仍有 11 个退化分类失败；不能称作全部边界情况通过。
- Q2 的候选域、连续最坏误差和移动代价仍需联合改进。固定检测点的误差认证不等于检测点全局最优。
- 合成清除结果、他人演练录制和本队官方测试必须区分。本工作区的实验没有消耗本队正式测试机会。
- 历史 `FINAL_MANIFEST.json` 对应封存阶段。后来 Q1/Q2 报告更新、service/vector 两轮暂停记录有各自范围；不要把所有目录中的执行次数直接累加成已审计成绩。

## 文件导航

| 路径 | 内容 |
|---|---|
| `REPORT.md`、`REPORT_*_UPDATE.md` | 综合报告与每轮更新 |
| `geometry.py`、`signal_minimax.py` | 区域、圆、接收证书和连续误差上界 |
| `*_policy.py`、`route_algorithms.py` | 搜索、定位、调度和路线策略 |
| `experiments/runs/` | 完整实验配置、结果、日志、代码快照及验证 |
| `reference/` | 冻结的同学仓库副本与文献；发布时移除嵌套 `.git` 元数据 |
| `别人的结果/` | 用户提供的比较材料，作为引用与复核输入 |
| `inputs_readonly_extract/` | 题面与附件的提取内容和原始哈希 |
| `SNAPSHOT_MANIFEST.json` | 本次 Git 发布文件与源快照哈希，由发布脚本生成 |

原仓库的 `models/`、`mock/`、题面及附件保留原状。为兼容本工作区的相对路径，发布分支还包含 `CUMCM2026Problems/B题/` 的三份原件拷贝，以及 `project/topic_probes/b_probe.py`、`common.py` 的只读依赖副本；不包含 A/C 工作区。

## 使用与复核

使用 Python 及 NumPy、SciPy、pandas、Matplotlib；Q1/Q2 测试还使用 pytest 和 mpmath。历史运行环境为 macOS ARM64、Python 3.13.5；新研究的基础随机种子为 42。已有上游固定夹具保留原始内容，不重生成来改变通过率。

先阅读目标实验目录的 `plan.md`、`precheck.md`、`command*.sh`、`summary.md` 和 `next_steps.md`。历史命令中的绝对路径是原机器记录，迁移时应改为自己的 checkout。多数收集器有防覆盖检查，复现应另选输出目录，保留历史结果。

本次发布排除编译缓存、macOS 元数据、pytest 临时目录、PID 文件和发布用的临时 checkout。所有研究代码、有效输入、完整数值结果和轨迹均保留。历史清单中对已排除临时文件的引用应结合本次发布清单解释。

官方接口仅在用户提供实际运行条件后另行验证；上传这个分支不启动模拟器、演练或正式测试。
