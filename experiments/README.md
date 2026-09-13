# 官方消融、参数实验与结果复现

`official.py`选择一个实验配置，在虚拟机内的官方模拟器中运行一局；`build_tables.py`读取保存的官方数据，生成Q3、Q4的四张结果表，输出到已忽略的 `outputs/tables/`。

## 数据和源码

以下路径相对仓库根目录；每个官方实验目录同时包含Q3和Q4。

| 实验 | 数据目录 | 内容 |
|---|---|---|
| 消融实验 | [2026-09-13_official-ablation](../data/experiments/2026-09-13_official-ablation/) | 160局实验、2局接入校验、配置及`package/`实验源码 |
| 参数性实验 | [2026-09-13_official-sensitivity](../data/experiments/2026-09-13_official-sensitivity/) | 500局参数宽扫、240局联合扰动、2局接入校验、配置及`package/`实验源码 |
| Q3两轮各5局 | [第一轮](../data/experiments/2026-09-13_official-q3-fused-five/)、[第二轮](../data/experiments/2026-09-13_official-q3-fused-five-repeat/) | 最近邻、trial_radius=65、max_active=2；合计10局作为Q3 baseline样本 |
| Q3参数组合比较 | [official-q3-refinement](../data/experiments/2026-09-13_official-q3-refinement/) | two_opt排序；50米/3轮配置3局、65米/2轮配置4局，按实际局数统计 |
| Q4参数组合比较 | [official-q4-fused-five](../data/experiments/2026-09-13_official-q4-fused-five/) | 最近邻、35米、fraction=0.30、share_limit=2，共5局 |
| Q4 baseline复测 | [official-q4-nearest-five](../data/experiments/2026-09-13_official-q4-nearest-five/) | 最近邻、35米、fraction=0.15、share_limit=6，共5局；单列报告 |

正式测试另存于[data/formal](../data/formal/README.md)，Q3、Q4各三次，不计入演练均值。请求响应、官方日志、成绩和截图用于复核实验数据；`package/`与`runtime_manifest.json`标识产生数据的源码。

## Baseline定义

- Q3：第二次正式方案，最近邻、trial_radius=65、max_active=2、share_limit=6、localization_weight=0.08、remainder_weight=1.5。
- Q4：第二次正式方案，最近邻、trial_radius=35、fraction=0.15、share_limit=6、share_cooldown=150、transverse_m=40、steps=10、pause_limit=16；baseline统计取消融实验中同配置的10局。

每个对照组按`config.json`中的实际配置运行。two_opt组的消融与参数宽扫以各表注列出的配置为实验起点；与交付baseline比较不表示这些组仅相对baseline改变了一个参数。

## 使用方法

从仓库根目录执行：

```sh
python experiments/official.py ablation --problem 3 --list
python experiments/official.py ablation --problem 3 --setting online_nearest__g50 --check-config
python experiments/official.py sensitivity --problem 4 --setting fraction=0.3 --check-config
python experiments/official.py sensitivity --problem 3 --schedule-row 503 --check-config
```

`--schedule-row N`选择配置中`schedule`的第N行，从1开始；`--problem`必须与该行题号一致。上述检查不发送HTTP请求。

在Windows官方界面打开对应演练，等待“等待机器狗进入”，再执行：

```powershell
python experiments/official.py sensitivity --problem 3 --setting trial_radius=65 --run --robot-id 实际队号 --case-code 当前案例码
```

每次只运行一局，输出在`outputs/experiments/`。官方新建案例的隐藏场景不同；精确复核已保存成绩用下面的离线命令：

```sh
python experiments/build_tables.py
python tools/audit_data.py
python tools/check_configs.py
# 在Windows ARM64环境执行已保存响应回放：
python tools/replay_official.py
```

## 统计口径

统计覆盖927局有效官方演练，4局接入和6局正式记录另存。核验和回放使用 `data/provenance/practice_audit.json` 中的逐局索引。

- 清除数：各局实际清除数之和除以该组局数。
- 平均定位清除时间：先算每局虚拟总时间/清除数，再对各局取算术平均。
- 程序运行时间：每局官方退出与进入响应的实时时间戳差，换算为秒后取平均。
- 时间偏移：方案均值/baseline均值减1，再乘100%。
