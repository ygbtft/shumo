# 本轮实际使用的主要命令

工作目录均为 `/Users/dingdingzai/Desktop/数学建模`，特别注明者除外。Python为用户指定路径，均加 `-B`；长矩阵通过后台启动器运行。源文件查找/阅读使用 rg、cat、sed 和只读Python；原始PDF/DOCX未改动。没有执行官方客户端、GUI、安装器或登录动作。

```bash
/Users/dingdingzai/anaconda3/bin/python -B B/extract_sources.py
/Users/dingdingzai/anaconda3/bin/python -B B/checks.py
/Users/dingdingzai/anaconda3/bin/python -B B/launch.py
git clone --depth 1 --single-branch --branch b https://github.com/ygbtft/shumo.git B/reference/shumo-b
/Users/dingdingzai/anaconda3/bin/python -B B/peer_audit.py
```

上游规则检查的工作目录为 `B/reference/shumo-b`：

```bash
PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /Users/dingdingzai/anaconda3/bin/python -B -m pytest -q -p no:cacheprovider mock/tests/test_rules.py
```

返回主工作目录后：

```bash
/Users/dingdingzai/anaconda3/bin/python -B B/launch.py --peer
git clone --depth 1 --single-branch --branch b https://github.com/ygbtft/shumo.git B/reference/shumo-b-macos-handoff
/Users/dingdingzai/anaconda3/bin/python -B B/analysis_experiments.py
/Users/dingdingzai/anaconda3/bin/python -B B/summarize.py
/Users/dingdingzai/anaconda3/bin/python -B B/run_robot.py --mode offline --problem 4 --strategy square_cropped_2opt
/Users/dingdingzai/anaconda3/bin/python -B B/package_robot.py
/Users/dingdingzai/anaconda3/bin/python -B B/final_checks.py
/Users/dingdingzai/anaconda3/bin/python -B B/write_report.py
```

后台启动器将 OPENBLAS_NUM_THREADS/OMP_NUM_THREADS 固定为1，并将 Matplotlib 配置写入 B/.mplconfig。矩阵分别输出到两个 `B/experiments/runs/` 目录的 log.txt，PID也保留；输出已完成，PID文件不代表仍在运行。

检查脚本初次48项通过；新增薄多边形用例后49项通过。补充Q2安全候选网格及该分类修正后重算了Q1/Q2分析文件；两套主矩阵未因成绩调参重跑。两轮主矩阵分别约72.90秒、106.27秒。打包后在B/dist/package-smoke解压执行Q3离线冒烟；该过程由 final_checks.py 记录。

首次沙箱内 git clone 因本机代理不可达失败，获得 git clone 联网权限后成功；没有改代理配置。首次Matplotlib字体发现报告默认字体缓存不可写，但图形成功生成；后续把XDG_CACHE_HOME也设置到B/.cache，未请求或写入外部缓存目录。

主矩阵脚本拒绝覆盖已有 trials.jsonl，以保留原结果。保存的run_config、源场景、逐次轨迹及code_snapshot可用于精确复核。最终检查中的旧探针 signed-zero 测试故意复现已有漏洞，其false不表示新策略失败。

后续完整复现可用以下新目录命令（本轮未重复执行）：

```bash
/Users/dingdingzai/anaconda3/bin/python -B B/run_experiments.py --output B/experiments/runs/reproduce-independent
/Users/dingdingzai/anaconda3/bin/python -B B/peer_benchmark.py --output B/experiments/runs/reproduce-peer
```

2026-09-10至09-11新增算法实验的完整命令见 [command.sh](experiments/runs/2026-09-10_metaheuristics/command.sh)。主比较后台PID、确认后台PID、消融后台PID均保存在该目录；`log.txt`、`confirmation.log`、`ablation.log` 分别记录实际运行。主矩阵先冻结路线，确认程序在主矩阵完成后按已保存规则选定路线再运行新种子，代码快照分启动时和最终两份。

新增入口只运行本地同学benchmark，不包含HTTP/正式模式：

```bash
/Users/dingdingzai/anaconda3/bin/python -B B/run_smart_robot.py --task q4_active --method fireworks
```

ICRA启发后的新一轮归档（均已执行，计分矩阵拒绝覆盖）：

```bash
zsh B/experiments/runs/2026-09-11_asymmetric-probes/command.sh launch
zsh B/experiments/runs/2026-09-11_reception-layout/command.sh launch
zsh B/experiments/runs/2026-09-11_clearance-neighborhood/command.sh launch
zsh B/experiments/runs/2026-09-11_q2-minimax/command.sh run
zsh B/experiments/runs/2026-09-11_mission-confirmation/command.sh launch
zsh B/experiments/runs/2026-09-11_mission-confirmation/command.sh http
zsh B/experiments/runs/2026-09-11_mission-confirmation/command.sh smoke3
zsh B/experiments/runs/2026-09-11_mission-confirmation/command.sh smoke4
zsh B/experiments/runs/2026-09-11_mission-confirmation/command.sh audit
zsh B/experiments/runs/2026-09-11_mission-confirmation/command.sh diagnose
zsh B/experiments/runs/2026-09-11_mission-confirmation/command.sh summarize
zsh B/experiments/runs/2026-09-11_mission-confirmation/command.sh finalize
```

本轮基础seed42；普通确认87—96，压力SeedSequence([42,114,problem,layout_index,count])。HTTP步骤只连接脚本自己启动的127.0.0.1随机端口，未联系现有服务。audit核查已有记录，不生成新计分结果；finalize仅检查文档和更新归档清单。Q2短实验最初未单独保存stdout与precheck，其补录说明明确标注追溯来源，未伪称原始日志。

分包任务与发现排序（本轮已执行，完整矩阵拒绝覆盖旧结果）：

```bash
zsh B/experiments/runs/2026-09-11_interleaved-tasks/command.sh check
zsh B/experiments/runs/2026-09-11_interleaved-tasks/command.sh launch
zsh B/experiments/runs/2026-09-11_discovery-priority/command.sh check
zsh B/experiments/runs/2026-09-11_discovery-priority/command.sh launch
zsh B/experiments/runs/2026-09-11_task-confirmation/command.sh launch
zsh B/experiments/runs/2026-09-11_task-confirmation-v2/command.sh check
zsh B/experiments/runs/2026-09-11_task-confirmation-v2/command.sh launch
zsh B/experiments/runs/2026-09-11_task-confirmation-v2/command.sh http
zsh B/experiments/runs/2026-09-11_task-confirmation-v2/command.sh smoke3
zsh B/experiments/runs/2026-09-11_task-confirmation-v2/command.sh smoke4
zsh B/experiments/runs/2026-09-11_task-confirmation-v2/command.sh audit
zsh B/experiments/runs/2026-09-11_task-confirmation-v2/command.sh summarize
zsh B/experiments/runs/2026-09-11_task-confirmation-v2/command.sh finalize
```

首次task-confirmation在首条计分行前因初始化统计字段重名退出，旧目录保留；v2仅修采集，决策代码及参数哈希保持首次冻结。新确认普通97—106，压力SeedSequence([42,115,problem,layout_index,count])。累计4935个新计分执行，额外中断、反馈重放、HTTP、CLI不计入全清次数。

宽探测、横移限幅与完工评分（完整矩阵和检查拒绝覆盖旧记录）：

```bash
zsh B/experiments/runs/2026-09-11_wide-probes/command.sh check
zsh B/experiments/runs/2026-09-11_wide-probes/command.sh launch
zsh B/experiments/runs/2026-09-11_completion-width/command.sh check
zsh B/experiments/runs/2026-09-11_completion-width/command.sh launch
zsh B/experiments/runs/2026-09-11_wide-confirmation/command.sh launch
zsh B/experiments/runs/2026-09-11_wide-confirmation/command.sh protocol
zsh B/experiments/runs/2026-09-11_wide-confirmation/command.sh smoke3
zsh B/experiments/runs/2026-09-11_wide-confirmation/command.sh smoke4
zsh B/experiments/runs/2026-09-11_wide-confirmation/command.sh check
zsh B/experiments/runs/2026-09-11_wide-confirmation/command.sh diagnose
zsh B/experiments/runs/2026-09-11_wide-confirmation/command.sh summarize
/Users/dingdingzai/anaconda3/bin/python -B B/write_report.py
zsh B/experiments/runs/2026-09-11_wide-confirmation/command.sh finalize
```

初次diagnose和summarize直接用Python执行对应脚本，再补入上面的统一命令；diagnose仅重放已完成记录、不读真值、拒绝覆盖，summarize可重建派生表和文档。普通确认107—116、压力SeedSequence([42,116,problem,layout_index,count])，计分5400；夹具修正日志保留。HTTP只连接自建随机端口。新CLI系列wide只运行本地后端；例如`--series wide --problem 4 --method width40_f015_22 --seed 42`。CPU单线程、基础seed42、所有输出B/。最后清单为新计分JSONL、完整轨迹和评分专用真值另存SHA256索引；之前27489次的清单保留。

任务联动、负反馈和加速（已完成计分矩阵拒绝覆盖）：

```bash
zsh B/experiments/runs/2026-09-11_coupled-dispatch/command.sh check
zsh B/experiments/runs/2026-09-11_coupled-dispatch/command.sh launch
zsh B/experiments/runs/2026-09-11_negative-hull/command.sh check
zsh B/experiments/runs/2026-09-11_negative-hull/command.sh launch
zsh B/experiments/runs/2026-09-11_fast-dispatch/command.sh check
zsh B/experiments/runs/2026-09-11_fast-dispatch/command.sh launch
zsh B/experiments/runs/2026-09-11_coupled-confirmation/command.sh launch
zsh B/experiments/runs/2026-09-11_coupled-confirmation/command.sh protocol
zsh B/experiments/runs/2026-09-11_coupled-confirmation/command.sh smoke3
zsh B/experiments/runs/2026-09-11_coupled-confirmation/command.sh smoke4
zsh B/experiments/runs/2026-09-11_coupled-confirmation/command.sh summarize
zsh B/experiments/runs/2026-09-11_coupled-confirmation/command.sh diagnose
zsh B/experiments/runs/2026-09-11_coupled-confirmation/command.sh check
/Users/dingdingzai/anaconda3/bin/python -B B/write_report.py
zsh B/experiments/runs/2026-09-11_coupled-confirmation/command.sh finalize
```

所有检查/计分用-B、禁止pyc、CPU单线程及B/内缓存。普通新确认117—126，压力SeedSequence([42,117,problem,layout_index,count])，本阶段5484计分；HTTP仅自建本地随机端口。负反馈测试夹具和审计包装器第一次失败后仅修检查并追加重跑，日志保留。finalize不再由shell重定向到被索引的同名日志：脚本自行写入并关闭finalize_log.txt后再采集哈希，末尾逐项复核清单；上一32889清单及单项日志哈希瑕疵保留。新CLI系列coupled仍只运行本地后端，不提供正式模式。

历史成对负反馈、保持原计划的检测删除及多内核布局（已完成；计分/检查拒绝覆盖）：

```bash
zsh B/experiments/runs/2026-09-11_multicore-cover-search/command.sh
zsh B/experiments/runs/2026-09-11_multicore-cover-smallcore/command.sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 /Users/dingdingzai/anaconda3/bin/python -B B/multicore_cover_audit.py >> B/experiments/runs/2026-09-11_multicore-cover-search/audit_log.txt 2>&1
zsh B/experiments/runs/2026-09-11_historical-negatives/command.sh check
zsh B/experiments/runs/2026-09-11_historical-negatives/command.sh launch
zsh B/experiments/runs/2026-09-11_faithful-skips/command.sh check
zsh B/experiments/runs/2026-09-11_faithful-skips/command.sh launch
zsh B/experiments/runs/2026-09-11_history-confirmation/command.sh launch
zsh B/experiments/runs/2026-09-11_history-confirmation/command.sh postprocess
zsh B/experiments/runs/2026-09-11_history-confirmation/command.sh protocol
zsh B/experiments/runs/2026-09-11_history-confirmation/command.sh smoke3
zsh B/experiments/runs/2026-09-11_history-confirmation/command.sh smoke4
zsh B/experiments/runs/2026-09-11_history-confirmation/command.sh audit
zsh B/experiments/runs/2026-09-11_history-confirmation/command.sh diagnose
zsh B/experiments/runs/2026-09-11_history-confirmation/command.sh report-support
/Users/dingdingzai/anaconda3/bin/python -B B/write_report.py
zsh B/experiments/runs/2026-09-11_history-confirmation/command.sh finalize
```

首次smoke3/smoke4/report-support直接执行上述command分支内同一Python命令后补统一入口，不重复计数。原始cross_batch_reference先用只读两个trials.jsonl的短Python汇总，之后由history_report_support.py同口径重建，属于派生统计。独立见证ImportError及json计数错误的原记录/说明保留，修复未改策略或几何数据。

历史665、保序848前置检查不计成绩；408个覆盖候选全被实际见证拒绝，非计分执行。计分5343包括已用训练场景，不等于独立场景数。新确认127—136，压力SeedSequence([42,118,problem,layout_index,count])、误差42+2600+100*problem+index，未来137—146未生成。HTTP仅自建127.0.0.1随机端口，正式请求0。新history CLI仍仅本地后端。归档先关闭finalize日志再哈希，旧38373清单及191项入口核验保留。

延后扫描移动、负反馈预测及相同决策的计算加速（已完成；计分矩阵拒绝覆盖）：

```bash
zsh B/experiments/runs/2026-09-11_deferred-scans/command.sh check
zsh B/experiments/runs/2026-09-11_deferred-scans/command.sh launch
zsh B/experiments/runs/2026-09-11_batched-history/command.sh check
zsh B/experiments/runs/2026-09-11_batched-history/command.sh launch
zsh B/experiments/runs/2026-09-11_cheap-prediction/command.sh check
zsh B/experiments/runs/2026-09-11_cheap-prediction/command.sh launch
zsh B/experiments/runs/2026-09-11_deferred-confirmation/command.sh launch
zsh B/experiments/runs/2026-09-11_deferred-confirmation/command.sh postprocess
zsh B/experiments/runs/2026-09-11_deferred-confirmation/command.sh protocol
zsh B/experiments/runs/2026-09-11_deferred-confirmation/command.sh smoke3
zsh B/experiments/runs/2026-09-11_deferred-confirmation/command.sh smoke4
zsh B/experiments/runs/2026-09-11_deferred-confirmation/command.sh audit
zsh B/experiments/runs/2026-09-11_deferred-confirmation/command.sh diagnose
zsh B/experiments/runs/2026-09-11_deferred-confirmation/command.sh report-support
zsh B/experiments/runs/2026-09-11_deferred-confirmation/command.sh figure
/Users/dingdingzai/anaconda3/bin/python -B B/write_report.py
zsh B/experiments/runs/2026-09-11_deferred-confirmation/command.sh finalize
```

图首次执行的是figure分支内同一命令，之后补入统一入口；未重复计分。report-support补充训练CPU等价汇总后重建派生文件，不改变计分或轨迹。报告通过apply_patch编辑，完整数值表由full_metric_table.md插入REPORT_DEFERRED_UPDATE.md，再由write_report.py拼入REPORT.md。所有检查/执行均使用本地Python、-B、单线程，Matplotlib/缓存限定B/。

本轮新增2232+930+1116+3900=8178计分，全清，累计51894；前置检查、1057项运行审计、3987条展开/1413对等价/15条诊断重放、自建HTTP/CLI/绘图均不增加成绩。普通137—146、压力SeedSequence([42,119,problem,layout_index,count])，误差42+2900+100*problem+index；147—156仍未生成。所有旧失败和未通过候选保留，本阶段计分与数学/运行检查无失败。

归档先关闭finalize_log再哈希；上一43716清单219项入口核验保留。finalize后用独立只读Python逐项重算FINAL_MANIFEST.json里的sha256并核对累计数51894、1057运行检查、0正式请求，不重定向到已经索引的日志。附带的git status --short -- B因工作区不是git仓库退出128，仅记录环境状态，未初始化仓库，见本轮environment_review.md。

21站整数布局、相切证书与公开源数删除（计分及运行审计已完成，拒绝覆盖）：

```bash
zsh B/experiments/runs/2026-09-11_odd-ring-cover/command.sh
zsh B/experiments/runs/2026-09-11_rounded-cover21/command.sh
zsh B/experiments/runs/2026-09-11_closed-cover21/command.sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 /Users/dingdingzai/anaconda3/bin/python -B B/cover21_geometry_audit.py > B/experiments/runs/2026-09-11_odd-ring-cover/audit_log.txt 2>&1
zsh B/experiments/runs/2026-09-11_lean-scan/command.sh check
zsh B/experiments/runs/2026-09-11_lean-scan/command.sh launch
zsh B/experiments/runs/2026-09-11_public-count-scan/command.sh check
zsh B/experiments/runs/2026-09-11_public-count-scan/command.sh launch
zsh B/experiments/runs/2026-09-11_cover21-training/command.sh check
zsh B/experiments/runs/2026-09-11_cover21-training/command.sh launch
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 /Users/dingdingzai/anaconda3/bin/python -B B/scan_pair_analysis.py --training > B/experiments/runs/2026-09-11_cover21-training/postprocess_log.txt 2>&1
zsh B/experiments/runs/2026-09-11_cover21-confirmation/command.sh launch
zsh B/experiments/runs/2026-09-11_cover21-confirmation/command.sh postprocess
zsh B/experiments/runs/2026-09-11_cover21-confirmation/command.sh protocol
zsh B/experiments/runs/2026-09-11_cover21-confirmation/command.sh smoke3
zsh B/experiments/runs/2026-09-11_cover21-confirmation/command.sh smoke4
zsh B/experiments/runs/2026-09-11_cover21-confirmation/command.sh audit
zsh B/experiments/runs/2026-09-11_cover21-confirmation/command.sh diagnose
zsh B/experiments/runs/2026-09-11_cover21-confirmation/command.sh report-support
zsh B/experiments/runs/2026-09-11_cover21-confirmation/command.sh figure
```

完整计分1116+744+1860+3900=7620全部清除，累计59514。新确认普通147—156，压力SeedSequence([42,120,problem,layout_index,count])，误差42+3200+100*problem+index；157—166尚未生成。240个布局枚举、72个舍入与4个未决重检、316项独立几何、570/780/560前置检查、180条轴向协议、99项运行审计及HTTP/CLI/诊断/绘图均不计入成绩。HTTP仅连接自己创建的127.0.0.1随机端口，正式请求0。

smoke3/smoke4首次以分支内同一Python命令执行后补入统一入口；没有重复计分。report-support修正三个训练标题，并生成跨批描述统计、完整指标表、坐标CSV及阶段账目。报告和七个next_steps通过apply_patch补齐；FULL_METRIC_TABLE由已保存表原文替换，不重算或挑选计分行。图表已查看，并核验所依赖summary.csv与selected_layouts.json的SHA256。

audit的Python完整通过99项后，外层zsh退出1并报告第19行附近解析错误。推断原因是在子进程运行中编辑同一启动脚本，导致外层继续读取位置异常；原错误和解释分别保留在launcher_error.txt及launcher_correction.md。所有任务结束后才将Python分支改为exec，语法检查通过。没有为了外层错误重跑/覆盖数学审计或成绩；今后不在运行中修改启动器。

本阶段归档与独立核验入口：

```bash
/Users/dingdingzai/anaconda3/bin/python -B B/write_report.py
zsh -n B/experiments/runs/2026-09-11_cover21-confirmation/command.sh
zsh B/experiments/runs/2026-09-11_cover21-confirmation/command.sh finalize
/Users/dingdingzai/anaconda3/bin/python -B B/cover21_archive_verify.py
```

finalize仅检查文档、源图、代码语法与已完成数据，写完并关闭finalize_log.txt后再采集哈希，不外层重定向到该日志。独立核验脚本不导入策略/模拟器，逐项检查当前清单与四个计分数据索引、累计数、原始计分行、检查结果及启动脚本语法；仅在B/写post_finalize_integrity.json，该记录不纳入它正在核验的清单，避免自引用。前一51894清单和237项入口核验保留。全部仅B/写入、CPU单线程、基础seed42；完整goal继续active。
