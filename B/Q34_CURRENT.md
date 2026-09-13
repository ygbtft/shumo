# Q3、Q4 当前运行版本

两题仅保留第二次正式测试采用的策略。历史方法名继续作为入口标识，其对应参数已统一更新。

| 题目 | 方法名 | 任务排序 | 试清门限 | 其他参数 |
|---|---|---|---:|---|
| Q3 | `range_area7` | 最近邻 | 65米 | max_active=2，share_limit=6，localization_weight=0.08，remainder_weight=1.5 |
| Q4 | `range_grid21_29` | 最近邻 | 35米 | fraction=0.15，share_limit=6，share_cooldown=150，transverse_m=40，steps=10，pause_limit=16 |

Q3保留七站全向覆盖与负反馈支配裁剪；Q4保留二十一站布局和有界成对探测。`bounded_candidates.py`是当前配置的唯一来源。策略使用公开反馈，清除距离仍为20米，65/35米为尝试清除的策略门限。

## 查看配置

安装NumPy、SciPy的Python环境中执行，以下命令不联网、不进入任何案例：

```sh
python run_q34_official.py --problem 3 --check-config
python run_q34_official.py --problem 4 --check-config
```

项目已有环境为`../mock/.venv/bin/python`；这只是Python依赖环境，使用它检查配置或回放记录不会运行mock。Windows实际测试环境为`C:\Python314-arm64\python.exe`。

## 官方入口

机器人与官方模拟器运行在同一台Windows机器，接口固定为`http://127.0.0.1:2026`。界面需已打开对应题目的案例；入口本身不创建案例。把下列队号和案例码替换为当前实际值：

```sh
python run_q34_official.py --problem 3 --mode practice --robot-id 实际队号 --case-code 实际案例码 --confirm-practice
python run_q34_official.py --problem 4 --mode practice --robot-id 实际队号 --case-code 实际案例码 --confirm-practice
```

正式会话使用`--mode formal --confirm-formal`，并须有该次正式运行的明确授权。专用入口`run_q3_fused_formal.py`、`run_q4_nearest_formal.py`固定题号和formal模式，也支持`--check-config`。本次代码清理不启动任何正式或演练案例。

每个案例写独立尝试标记和日志目录，重复启动同一案例会被拒绝。日志包括实际参数、所有请求及响应、清除数、官方虚拟总时间、平均定位清除时间与程序运行时间。程序运行时间取官方退出与进入响应时间戳之差；`client_policy_wall_s`另存客户端计时，不能混作同一指标。

## 代码与证据

`package_robot.py`只打包当前两套策略所需的24个Python文件及一份布局，不带mock、历史候选、官方日志或队号。输出为`dist/q34-formal2.zip`。

项目中的`run_bounded_robot.py`保留本地调试后端，但两题同样只注册上述当前配置；`--method`可省略。历史实验依靠各实验档案中的冻结包复现，不能用当前配置重跑后仍标成旧版本。

第二次正式测试的原始记录分别位于`guest_deploy_evidence/q3-fused-formal-20260913`和`guest_deploy_evidence/q4-nearest-formal-20260913`。代码整理后的指令一致性检查见`cleanup_formal2/replay.json`，由原Windows环境回放保存的官方响应获得；回放不发送官方请求、不产生新成绩。

当前四张实验表和论文分析统一见`experiments/paper_materials/2026-09-13_formal2_baselines/`，项目论文入口为`../writing-kit/kit-q34.md`。Q3基准取融合方案两轮共10局；Q4取原最近邻35米消融组10局，后续同配置5局另列。单局正式成绩不混入演练均值。
