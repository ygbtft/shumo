# Q1/Q2 精简敏感性实验

权威口径：`../../PLAN.md` §11.6、§12.2 T6。本目录只运行离线数学模型，不访问官方模拟器或正式测试；不修改 `models/paper-full.md`，不改变 P1/P2 修复或生产求解器的数学口径。

- [T6 执行记录](T6.md)：S1—S9 完成范围、样本/网格/评分次数、公共补点、扫描比例、细化、排序、时间与停止原因。
- [论文表格与结论段落草稿](paper-draft.md)：供父 agent 并入正文。
- [逐运行 CSV](T6_detail.csv)：旧点可行性优先，失效/未评估保留空值。
- `results/`：逐场景完整模型、搜索记录、统一终评、S2/S7/F11/F9 和复现 manifest。
- [本地测试日志](tests.log)、[四块 benchmark 汇总](verification.json)：1315 项测试通过（原1311项加4个敏感性合同测试）；四块为285/285、330/330、531/531、48/48。

## 实验范围与限制

四个代表首读数：标准 `(0,0), 0°`（角锥跨0°），普通 `(0,0), 35°`，近切边 `(1900,0), 180°−asin(1800/1900)+0.2°`，边缘 `(1850,0), 180°`。后两者首站合法地在目标域外。S3 另有只检查信息不一致的 `(2900,0), 180°` 控制，不另做优化。

S1/S2/S3/S4/S7 和复用 F11/F9 的 S8/S9 执行；S5/S6 为选做未执行。1.01°压力和精确量化未执行。已有旧输出不含可直接复用的本轮Q2数值终选，本轮默认场景只计算一次供各项复用，没有另生成重复图件；F11/F9 保存为可绘制数值数据。

搜索仍调用原 `select_second_point`，站点50/25 m，局部最小步长1.5625 m。精简源三级为 `(5,13)/(9,25)/(17,49)`，保留2个分散起点并保留对称侧/边界起点；边界射线15°，点对4起点/4轮。每次搜索30 s。该配置不是默认配置文件的完整分辨率。每模型的旧点、搜索推荐点、原搜索最小评分点与镜像点，先判可行，再在同一第三级源池、错位源及各点接触/合法见证的公共并集上终评。统一tie阈值0.1 m。

这是有限搜索与有限候选重选。搜索器到时退回的粗评分只作为搜索日志，论文用单独统一终评值；统一终评没有把未完成的全域/终选审计变成稳定解。S7的源/容差/偏移比较使用各自同精度池内的旧点重评与候选重选，站点阶段再用公共终选精度比较。变化量不是连续最坏值误差保证，不要求对称解坐标唯一。

S8只裁剪同一合法反馈的集合，不改变问题一对象或另优化半径目标，因此固定点和重新选择点复用同一个Q2终选点；重复首站反馈仅用于“无界→有限”信息控制，不列为合法的第二次不同站点选择。圆盘以64边切线外包处理，排除5 m圆后的非凸K另列样本估计与保守r_U，不能将二者差值当作排除圆的精确效应。

S9预算单位为米，实际移动秒数为距离/5，测量另加5 s；清除后的行动时间在条件诊断字段另存。预算间累计候选、统一公共池重评；近切边场景补充B=200/400/500 m，标准B=10池加入轴向候选(10,0)供S2的near对照（该点未获选）。B=10的解析下界只标在标准场景。S2条件半径不叫最坏半径J_R。

## 复现

在仓库根目录运行，始终使用指定 venv。`--output` 必须是新目录。下面以 `results-replay` 为例：

```sh
models/q1q2/.venv/bin/python -m models.q1q2.sensitivity --output models/q1q2/reviews/sensitivity/results-replay --search-seconds 30
models/q1q2/.venv/bin/python -m models.q1q2.reviews.sensitivity.supplement models/q1q2/reviews/sensitivity/results-replay
models/q1q2/.venv/bin/python -m models.q1q2.reviews.sensitivity.budget_threshold models/q1q2/reviews/sensitivity/results-replay
models/q1q2/.venv/bin/python -m models.q1q2.reviews.sensitivity.report models/q1q2/reviews/sensitivity/results-replay
models/q1q2/.venv/bin/python -m pytest models/q1q2/tests -q --import-mode=importlib
models/q1q2/.venv/bin/python models/q1q2/reviews/sensitivity/verify.py
```

报告脚本把T6/CSV/论文草稿写到传入结果目录的父目录，复现时会更新这些派生文件。`verify.py` 仅调用四块本地数学benchmark，复制报告到本目录后恢复原benchmark报告的原始字节，不触发正式测试。运行命令、Python路径、依赖版本及核心源码SHA256在 `results/manifest.json`；补充脚本是本目录可审阅源码。

时间上限会使不同机器/负载的搜索候选和调用次数略异，原始候选与全部评分证据均留存；确定的同一候选、配置、源池才是逐点数值复现的比较对象。`elapsed_seconds` 均为本机墙钟时间，不是虚拟移动时间。S2复用诊断耗时计入各场景，裁剪几何未单独计时处明确为未记录，不填0冒充测量。

## 保存与复核

为避免重复保存数千候选的完整点对见证，逐运行 `.json` 中的搜索候选评分只保留摘要；同名 `.full.json.gz` 无损保存完整原始JSON，摘要中的 `raw_search_archive.sha256_uncompressed` 可核对。网格记录、最终候选全部评分与条件证据仍在可读JSON中。

```sh
models/q1q2/.venv/bin/python -m models.q1q2.reviews.sensitivity.pack models/q1q2/reviews/sensitivity/results-replay
models/q1q2/.venv/bin/python -m models.q1q2.reviews.sensitivity.check_artifacts models/q1q2/reviews/sensitivity/results-replay
```

[产物一致性检查](artifact-check.log) 核验20次运行、不可行点不评分、三种条件清除状态、已知半径同步重建、无界控制、预算累计候选单调性容差、源码与无损归档哈希。T6中全部搜索仍为 `NEEDS_REFINEMENT`：即使流程 `COMPLETED`，也不改写稳定性判断。
