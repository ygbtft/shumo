# Windows guest cover21 部署就绪说明

## 2026-09-12 重新部署（当前有效，对应仓库 HEAD `aeb33000f`）

上一版部署（下方 2026-09-11 节）已**失效**：入口重构后 `run_bounded_robot.py` 依赖新增的 `bounded_candidates.py` 与 `layouts/`，旧 guest 缺这两项会直接崩；清除门也仍是旧的 80/40。

- **旧目录保留**：`C:\BRobot-old-20260912-004600`（含此前演练产出的 `robot_runs`）。官方模拟器自身的权威统计库在 `C:\Jammers`，未受影响。
- **新部署**：`C:\BRobot`，共 199 个文件（顶层全部 `.py` + `layouts/` + `reference/shumo-b/mock/` 代码 + `tests/`），1.7 MB。清单 `C:\BRobot\DEPLOY_MANIFEST.json`。
- **SHA 校验**：199/199 与宿主逐字节一致，零不符、零缺失。
- **不再部署 `experiments/` 冻结 JSON（约 60 MB）**：入口重构后已与实验树解耦，`tests/test_bounded_entry.py` 明确禁止 import `experiments/confirmation/final_checks` 且禁止读取含 `experiments` 的路径，四种执行组合仍通过。
- **环境**：`C:\Python314-arm64\python.exe`（3.14.7 ARM64）、NumPy 2.5.3、SciPy 1.18.1。
- **冒烟（仅进程内 mock，未连官方）**：Q3 `range_area7` 与 Q4 `range_grid21_29` 的 offline 均 `all_cleared=true`，`stop_reason=full_coverage_and_all_discovered_cleared`。

### guest 内测试的已知偏差（非缺陷，勿误判）

在 guest 跑 `python -m unittest discover -s tests` 会有 5 ERROR + 5 FAIL，均已定性：

- **5 ERROR 为测试专属依赖缺失**：guest 未装 `pytest`；未部署 `benchmarks_q34`；`mock` 包不在 `sys.path`；有意排除的 `experiments/*.json`。另 `test_q34_protocol` 的半包拆除用例在 Windows 上抛 `WinError 10053`，属平台 socket 行为差异，只涉及本地 mock 服务。均不在正式运行路径上。
- **5 FAIL 为跨平台浮点差异**：`test_bounded_entry` 比对的是**宿主录制的基线夹具**。Q3 站点 `stations(6,1140.)` 的三角函数在 guest 上差 1 ULP（`-987.2689603142599` vs `...97`，1.1e-13 m），经贪心/2-opt 平局翻转放大为整局时间差异。覆盖余量 7.3 m、清除判据余量 1e-5 m，对 1e-13 m 免疫，**无正确性风险**；guest 实跑仍全清，且本例中略快（Q3 3090.42 vs 宿主 3105.88；Q4 6176.68 vs 6328.58）。

**推论**：宿主数值不能逐位外推到 guest；应以 guest 自身的演练结果为准（历史演练成绩本就产自 guest）。正式测试前须在本部署上另跑演练验证。

---

## 2026-09-11 首次部署（已被上节取代，仅作历史记录）

2026-09-11：已部署，Q3/Q4 本地 offline 冒烟通过。**未连接官方模拟器，未发起正式测试，未执行或发起演练。** 本次仅使用进程内 mock，不访问 127.0.0.1:2026；未执行 mock-http，也未操作 GUI、登录或官方会话。

## 部署位置与环境

- Parallels VM：`Windows 11`；工作目录：`C:\BRobot`（裸 import 要求先切换到此目录）。
- 解释器：`C:\Python314-arm64\python.exe`，Python 3.14.7 ARM64；NumPy 2.5.3；SciPy 1.18.1。
- SciPy 是当前导入链的必要依赖（`visibility_certificate.py` 导入 `scipy.spatial`），已从宿主准备的 Windows ARM64 wheel 以 `pip install --no-index --no-deps` 离线安装。未改动策略源码。
- 宿主独立目录：`/Users/flower/Downloads/BRobot-cover21-20260911`。
- 纯运行包：`/Users/flower/Downloads/BRobot-cover21-20260911.zip`，不含宿主冒烟结果。
- 完整逐文件路径、字节数和 SHA-256：[DEPLOY_MANIFEST.json](guest_deploy_evidence/DEPLOY_MANIFEST.json)。guest 副本：`C:\BRobot\DEPLOY_MANIFEST.json`；180 个文件校验全部通过。

## 最小文件集

按任务要求保留 B 顶层全部 161 个 `.py`，再加实际导入的 14 个 mock 文件和实际读取的 5 个冻结 JSON，共 180 个运行文件。另附一个部署清单。未包含 `.venv`、`dist`、既有 `robot_runs`、其他同学结果、实验日志或代码快照。保留原有目录结构和字节内容。

依赖确认方法：在宿主对导入及 `cover21_confirmation.all_paths()` 记录 JSON 读取，并用审计钩子禁止 socket 连接、绑定和域名解析；随后只复制这些数据和依赖，在独立目录运行原始入口的 Q3/Q4 offline，两局均成功。入口选择 cover21 后不会调用默认 icra 的 `all_paths()`，也不会调用实验 `freeze()`；所以该运行路径**不读取任何 `run_config.json` 或 `routes.json`**，没有把这些非必要实验归档加入包。

实际读取的冻结数据（相对 `C:\BRobot`）：

- `experiments/runs/2026-09-11_closed-cover21/certified_layouts.json`
- `experiments/runs/2026-09-11_convex-visibility/certified_layouts.json`
- `experiments/runs/2026-09-11_convex-visibility/polar25_rectangle_certificate.json`
- `experiments/runs/2026-09-11_layout-alternatives/certified_layouts.json`
- `experiments/runs/2026-09-11_rounded-cover21/certified_layouts.json`

mock 依赖（仅代码，不含参考项目结果和测试）：

- `reference/shumo-b/mock/__init__.py`
- `reference/shumo-b/mock/backends/__init__.py`
- `reference/shumo-b/mock/backends/base.py`
- `reference/shumo-b/mock/backends/http.py`
- `reference/shumo-b/mock/backends/inproc.py`
- `reference/shumo-b/mock/backends/recording.py`
- `reference/shumo-b/mock/client_or_inproc.py`
- `reference/shumo-b/mock/error_field.py`
- `reference/shumo-b/mock/evaluator.py`
- `reference/shumo-b/mock/geometry.py`
- `reference/shumo-b/mock/protocol.py`
- `reference/shumo-b/mock/scenario_gen.py`
- `reference/shumo-b/mock/simulator.py`
- `reference/shumo-b/mock/strategy.py`

顶层 Python 完整清单：

```text
adaptive_routes.py
analysis_experiments.py
asymmetric_probe_experiments.py
batched_history_experiments.py
batched_history_policy.py
bounded_http.py
bounded_width_policy.py
bracket_policy.py
cheap_prediction_experiments.py
cheap_prediction_policy.py
checks.py
clearance_experiments.py
clearance_policy.py
client.py
closed_cover21_search.py
completion_sensing_policy.py
completion_width_experiments.py
cooperative_policy.py
coupled_confirmation.py
coupled_dispatch_experiments.py
coupled_dispatch_policy.py
coupled_final_checks.py
coupled_postprocess.py
coupled_protocol_checks.py
coupled_trace_diagnosis.py
cover21_archive_verify.py
cover21_confirmation.py
cover21_experiments.py
cover21_figures.py
cover21_final_checks.py
cover21_geometry_audit.py
cover21_protocol_checks.py
cover21_report_support.py
cover21_trace_diagnosis.py
coverage.py
coverage_replacement.py
deferred_confirmation.py
deferred_final_checks.py
deferred_postprocess.py
deferred_protocol_checks.py
deferred_replay.py
deferred_report_support.py
deferred_skip_experiments.py
deferred_skip_policy.py
deferred_trace_diagnosis.py
deferred_tradeoff_figure.py
discovery_priority_experiments.py
discovery_priority_policy.py
efficient_joint_policy.py
extract_sources.py
faithful_skip_experiments.py
faithful_skip_policy.py
fast_dispatch_experiments.py
fast_dispatch_policy.py
final_checks.py
geometry.py
historical_pair_experiments.py
historical_pair_policy.py
history_confirmation.py
history_final_checks.py
history_postprocess.py
history_protocol_checks.py
history_report_support.py
history_trace_diagnosis.py
icra_artifact_finalize.py
icra_confirmation.py
icra_final_checks.py
integer_visibility_certificate.py
intelligent.py
interleaved_experiments.py
interleaved_policy.py
joint_experiments.py
joint_policy.py
joint_task_experiments.py
joint_task_policy.py
launch.py
layout_alternative_checks.py
layout_alternative_experiments.py
layout_certificates.py
lean_scan_experiments.py
lean_scan_policy.py
metaheuristic_experiments.py
mission_confirmation.py
mission_final_checks.py
mission_http_checks.py
mission_postprocess.py
mission_trace_diagnosis.py
multicore_cover_audit.py
multicore_cover_search.py
multicore_cover_smallcore.py
negative_hull_experiments.py
negative_hull_policy.py
odd_ring_cover_search.py
package_robot.py
peer_audit.py
peer_benchmark.py
peer_paper_checks.py
peer_review_final_checks.py
plot_icra_update.py
policies.py
probe_diagnostics.py
public_count_experiments.py
public_count_replay.py
public_count_scan_policy.py
publish_metaheuristic_report.py
q12_benchmark_archive.py
q12_benchmark_diagnostics.py
q12_certification_run.py
q12_our_benchmark.py
q12_peer_benchmark.py
q2_minimax_experiments.py
reception_layout_experiments.py
replacement_experiments.py
replacement_policy.py
ring_coverage.py
ring_experiments.py
rotating_layout_policy.py
rounded_cover21_search.py
route_ablation.py
route_algorithm_checks.py
route_algorithms.py
route_confirmation.py
route_final_checks.py
run_bounded_robot.py
run_experiments.py
run_robot.py
run_smart_robot.py
safe_sensing_policy.py
scan_experiment_support.py
scan_pair_analysis.py
service_aware_analysis.py
service_aware_audit.py
service_aware_experiments.py
service_aware_policy.py
signal_minimax.py
simulator.py
spatial_decision_experiments.py
summarize.py
summarize_icra_update.py
summarize_metaheuristics.py
summarize_ring_review.py
task_collector_checks.py
task_confirmation.py
task_confirmation_v2.py
task_final_checks.py
task_postprocess.py
task_protocol_checks.py
vector_service_experiments.py
vector_service_policy.py
verify_bounded_http.py
visibility_certificate.py
visibility_layout_search.py
wide_confirmation.py
wide_final_checks.py
wide_postprocess.py
wide_probe_experiments.py
wide_probe_policy.py
wide_protocol_checks.py
wide_trace_diagnosis.py
write_q12_report.py
write_report.py
```

## 冒烟结果

均使用默认 seed 42。宿主解释器为已有 `../models/q1q2/.venv/bin/python`（Python 3.14.6、NumPy 2.5.3、SciPy 1.18.1），虚拟环境没有进入运行包。

| 环境 | 问题 / 方法 | 全清 | 指令数 | official_calls |
|---|---|---|---:|---:|
| 宿主独立目录 | Q3 / `range_area7` | 15/15，True | 148 | 0 |
| 宿主独立目录 | Q4 / `range_grid21_29` | 15/15，True | 270 | 0 |
| Windows guest | Q3 / `range_area7` | 15/15，True | 144 | 0 |
| Windows guest | Q4 / `range_grid21_29` | 15/15，True | 263 | 0 |

guest 两局 `stop_reason=full_coverage_and_all_discovered_cleared`、`inconsistent_updates=0`。每局均生成 `summary.json`、`scoring_only.json`、`trace.jsonl.gz`：

- Q3：`C:\BRobot\robot_runs\20260911-155301-560537-bounded-offline`。
- Q4：`C:\BRobot\robot_runs\20260911-155302-605922-bounded-offline`。

宿主证据：[host-results.json](guest_deploy_evidence/host-results.json)、[guest-results.json](guest_deploy_evidence/guest-results.json)；回传的完整 guest 日志及轨迹在 [guest](guest_deploy_evidence/guest)。部署和冒烟脚本也归档在 `guest_deploy_evidence/`，其中无 practice 调用。

已执行的 guest 冒烟命令（Windows cmd）：

```bat
chcp 65001
cd /d C:\BRobot
C:\Python314-arm64\python.exe -B run_bounded_robot.py --series cover21 --problem 3 --method range_area7 --mode offline
C:\Python314-arm64\python.exe -B run_bounded_robot.py --series cover21 --problem 4 --method range_grid21_29 --mode offline
```

实际通过 PowerShell 在相同 cwd 执行这两个 Python 命令，设置 `PYTHONUTF8=1`，输出重定向至 `C:\BRobot\guest-q3-offline.log` 与 `guest-q4-offline.log`。

## 官方演练待执行命令——本任务未执行

**仅供用户手动登录并确认官方演练会话后，由主控手动执行。当前就绪状态只证明本地部署和 offline 冒烟成功，不代表官方连接或演练验证成功。** 以下为 Windows cmd 命令；Q3/Q4 应在各自对应演练会话中单独运行，不要把两局作为自动脚本连续启动。

Q3：

```bat
chcp 65001
cd /d C:\BRobot
C:\Python314-arm64\python.exe -B run_bounded_robot.py --series cover21 --problem 3 --method range_area7 --mode practice --base-url http://127.0.0.1:2026 --robot-id 202623001141 --confirm-practice
```

Q4：

```bat
chcp 65001
cd /d C:\BRobot
C:\Python314-arm64\python.exe -B run_bounded_robot.py --series cover21 --problem 4 --method range_grid21_29 --mode practice --base-url http://127.0.0.1:2026 --robot-id 202623001141 --confirm-practice
```

两条命令均依赖上述完整运行文件集和已安装的 NumPy/SciPy。将来手动执行时，结果写入 `C:\BRobot\robot_runs\<时间戳>-bounded-practice\`。本任务没有创建此类结果目录。

## 遇到的问题及处理

- 宿主默认 Python 缺 NumPy，另一个 mock 虚拟环境缺 SciPy；改用已有且依赖完整的 q1q2 虚拟环境，仅作为隔离目录的解释器。
- guest 原先只有 NumPy；补装 SciPy ARM64 wheel，离线安装成功。
- 冻结数据并非集中于 `cover21-*`；按实际读取保留 5 个布局/证书 JSON，避免遗漏上游布局。
- Session 0 仅运行命令行；通过 Downloads 共享目录传 ZIP、wheel 和脚本，不依赖桌面。裸 import 通过固定 cwd 解决。
- 相同 seed 的两端场景有少量约 1e-13 的坐标浮点差异，指令数也不完全一致；未将其原因完全归结于浮点误差。两端均全清；本次不声明逐指令复现或官方成绩。

运行 ZIP：3854740 bytes，SHA-256 `f1c23a3f3ba8dbe3ba0ac4ac067aba33617b95e3e86366ee1ffa0c0146e14444`。
