# 无线电干扰源定位与清除：最终交付仓库

仓库保留 Q1—Q4 算法、官方模拟器本地调试接口、实验源码与数据。Q3/Q4 唯一交付版本为各题**第二次正式测试**采用的策略；三次正式测试原始数据全部留档。

| 路径 | 内容 |
|---|---|
| `algorithms/q1q2/` | Q1/Q2 求解、几何、输入、绘图；`optional/` 为区间认证，`benchmarks/` 与 `reviews/sensitivity/` 保留数学实验和结果 |
| `algorithms/q34/` | Q3/Q4 第二次正式版本的策略依赖、HTTP 客户端和布局；`strategy.py` 是唯一配置源 |
| `interfaces/` | Windows 官方 HTTP 调试入口；macOS 到 Parallels VM 的部署工具 |
| `experiments/` | 官方消融/参数实验运行入口，以及从原始记录统计实验结果的源码 |
| `data/formal/` | `q3/`、`q4/` 各含 `attempt1`、`attempt2`、`attempt3`；[正式结果汇总](data/formal/README.md)和 `index.json` 索引六次记录 |
| `data/experiments/` | 官方消融、参数宽扫、联合扰动与配置复测的原始记录及实验源码 |
| `data/evidence/` | 官方消融逐局时间及请求哈希核验记录 |
| `docs/q1.md`—`q4.md` | 四题主要思路、代码入口与证据边界；`attachments/` 为官方附件 |
| `tools/` | 打包、数据审计、已保存官方响应回放、环境验证工具 |
| `HANDOFF.md` | 面向 agent 的环境部署、实验复现和操作约束 |
| `outputs/`、`dist/` | 新运行输出与新构建压缩包，均与原始数据分开 |

## 实验数据与结果表在哪里

| 内容 | 原始数据目录 | 整理后的结果 |
|---|---|---|
| Q3、Q4 官方消融实验 | [data/experiments/2026-09-13_official-ablation/](data/experiments/2026-09-13_official-ablation/)（160局实验＋2局接入） | [逐局结果](data/experiments/2026-09-13_official-ablation/runs.jsonl) |
| Q3、Q4 官方参数性实验 | [data/experiments/2026-09-13_official-sensitivity/](data/experiments/2026-09-13_official-sensitivity/)（500局宽扫＋240局联合扰动＋2局接入） | [逐局结果](data/experiments/2026-09-13_official-sensitivity/trials.csv) |
| Q3、Q4 各三次正式测试 | [data/formal/q3/](data/formal/q3/)、[data/formal/q4/](data/formal/q4/) | [六次正式成绩](data/formal/README.md) |

两个官方实验目录都同时包含Q3和Q4，内有原始记录、`config.json`实验配置，以及`package/`冻结源码。重新统计的源码是 [experiments/build_tables.py](experiments/build_tables.py)。追加复测也保存在 `data/experiments/` 的对应批次中，并已纳入统计。

## 安装与 Q1/Q2

以下命令在仓库根目录执行。Python 3.11 及以上；已验证环境为 Python 3.14。`requirements.txt` 含求解、绘图、认证和测试依赖。

```sh
python -m venv .venv
# macOS/Linux: source .venv/bin/activate
# Windows: .venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m algorithms.q1q2.run q1 algorithms/q1q2/data/standard.json --output outputs/q1
python -m algorithms.q1q2.run q2 algorithms/q1q2/data/standard.json --config algorithms/q1q2/data/default_config.json --output outputs/q2
```

输出目录需不存在。Q2 数值搜索有预算，返回数值候选与状态；不能把采样结果写成全域最优证明。认证入口见 [Q2说明](docs/q2.md)。

## Q3/Q4 baseline：第二次正式测试方案

下表是当前交付及结果比较唯一采用的baseline配置。实验表的baseline均值来自该配置的10局官方演练，正式测试单局成绩另行留档。

| 题目 | 排序 | 试清门限 | 其余参数 |
|---|---|---:|---|
| Q3 | 最近邻 | 65 米 | max_active=2、share_limit=6、localization_weight=0.08、remainder_weight=1.5 |
| Q4 | 最近邻 | 35 米 | fraction=0.15、share_limit=6、share_cooldown=150、transverse_m=40、steps=10、pause_limit=16 |

配置检查不联网，任何平台均可执行：

```sh
python interfaces/official.py --problem 3 --check-config
python interfaces/official.py --problem 4 --check-config
```

机器人在运行官方模拟器的同一台 Windows VM 内运行。先在官方界面手动打开对应**演练**案例，待倒计时结束、显示“等待机器狗进入”，再使用真实队号和当前案例码：

```powershell
python interfaces/official.py --problem 3 --mode practice --robot-id 实际队号 --case-code 当前案例码
```

入口直接连接 `http://127.0.0.1:2026`。题号、模式和案例由运行者在官方界面选择；`--mode`、`--case-code` 只记入日志，不会切换或核对官方会话。每局输出到独立目录。Q3/Q4 三次正式机会已全部使用，正式日志均已上传；现有数据可以离线复核。

## 消融和参数实验

各对照组按`config.json`记录的参数与对应`package/`源码运行。下面两类命令只做配置检查，不调用官方接口，也不运行 mock：

```sh
python experiments/official.py ablation --problem 3 --list
python experiments/official.py ablation --problem 3 --setting online_nearest__g50 --check-config
python experiments/official.py sensitivity --problem 4 --list
python experiments/official.py sensitivity --problem 4 --setting fraction=0.3 --check-config
```

新演练必须在官方服务仍开放、Windows 界面已打开对应案例时显式执行：

```powershell
python experiments/official.py sensitivity --problem 3 --setting trial_radius=65 --run --robot-id 实际队号 --case-code 当前案例码
```

每次命令只运行一局，输出在 `outputs/experiments/`，不会覆盖已保存样本。冻结源码在相应 `data/experiments/*/package/`，完整随机顺序在 `config.json`。案例由官方重新生成，无法重现原隐藏场景；已保存成绩的精确复核应使用下面的离线统计/回放。详见 [实验说明](experiments/README.md)。

## 数据统计和验证

```sh
python experiments/build_tables.py
python tools/audit_data.py
python -m pytest algorithms/q1q2/tests -q
# 在原 Windows ARM64 Python 环境回放：不连接模拟器
python tools/replay_official.py
python tools/package.py
```

统计脚本将结果写入 `outputs/tables/`，覆盖927局有效官方演练；4局接入校验及正式测试不混入演练均值。所有方案逐局等权，程序时间统一采用官方 `/exit` 与 `/enter` 的响应时间戳差；客户端计时另存。对照组的实际配置在各表中列明；相对baseline的偏移不等于单个参数的因果影响。

完整原始数据含大量 GUI 截图，体积较大；`tools/package.py` 默认只打包算法和接口，不打包实验记录。加 `--include-experiments` 才包含两类官方实验的冻结运行源码和配置，仍不包含成绩、请求日志或截图。

压缩包用于 VM 中运行算法；测试、证书复核、数据统计命令需要完整仓库。

交付要求与代码风格的检查结果见 [交付检查](docs/delivery-check.md)，验证记录见 [交付验证](docs/validation.md)。

需要在 VM 内精确回放时，打包增加 `--include-replay`，仅带上27局所需请求响应；在 VM 解压目录运行 `python tools/replay_official.py` 即可。
