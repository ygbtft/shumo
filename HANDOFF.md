# Agent 环境部署与实验复现

## 交付口径

Q1/Q2 在 `algorithms/q1q2/`；Q3/Q4 在 `algorithms/q34/`。Q3/Q4 **只以第二次正式测试代码为准**，直接配置源为 `strategy.py`。

- Q3：最近邻、trial_radius=65、max_active=2、share_limit=6、localization_weight=0.08、remainder_weight=1.5。
- Q4：最近邻、trial_radius=35、fraction=0.15、share_limit=6、share_cooldown=150、transverse_m=40、steps=10、pause_limit=16。fraction=0.30/share_limit=2 是参数组合对照，不属于交付baseline。
- **每题三次正式数据都保留**：`data/formal/q{3,4}/attempt{1,2,3}/`；`data/formal/index.json` 标出第二次主记录及全部六份日志哈希。
- 实验按记录的配置与对应源码复现；统计比较统一使用第二次正式方案作为baseline。

## 宿主环境

仓库根目录为所有命令的工作目录。Python 3.11+，本次 macOS 验证环境为 Python 3.14；统一虚拟环境 `.venv`。

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m algorithms.q1q2.run q1 algorithms/q1q2/data/standard.json --output outputs/q1
.venv/bin/python -m pytest algorithms/q1q2/tests -q --import-mode=importlib
.venv/bin/python interfaces/official.py --problem 3 --check-config
.venv/bin/python interfaces/official.py --problem 4 --check-config
```

Q1/Q2 求解输出目录须不存在；Q2 完整数值搜索按配置预算运行。现有环境已安装 numpy、scipy、matplotlib、mpmath、pytest，实际版本写入验证记录；认证环境需要安装 mpmath。

## 官方 Windows 虚拟机

当前已知配置（复现前只读确认）：

| 项目 | 路径/值 |
|---|---|
| Parallels CLI | `/Applications/Parallels Desktop.app/Contents/MacOS/prlctl` |
| VM 名 | `Windows 11` |
| Windows Python | `C:\Python314-arm64\python.exe` |
| 模拟器目录 | `C:\Jammers` |
| 官方机器人 HTTP | `http://127.0.0.1:2026`，只能在 VM 内访问 |
| 官方行为日志 | `C:\Jammers\JammersSimulatorData\behavior-logs` |
| 共享传输 | macOS `~/Downloads` 对应 `\\Mac\Home\Downloads` |

不要假设整个宿主工作区都被共享。部署时指定一个尚不存在的目录：

```sh
.venv/bin/python tools/package.py --include-experiments
.venv/bin/python interfaces/vm.py status
.venv/bin/python interfaces/vm.py deploy --destination 'C:\BDelivery-NEW'
.venv/bin/python interfaces/vm.py check-config --destination 'C:\BDelivery-NEW' --problem 3
.venv/bin/python interfaces/vm.py check-config --destination 'C:\BDelivery-NEW' --problem 4
```

`deploy` 从共享 Downloads 解压并验证包内 SHA-256 清单，请指定新目录。传输目录名称由程序生成，使用后可删除该次传输文件。打包默认不含实验；`--include-experiments` 增加冻结源码和配置，不含实验成绩、请求日志、截图及论文原始数据。

Parallels `exec` 运行在 SYSTEM/session 0。当前机器人入口只访问 HTTP，不依赖桌面 UI 自动化；官方案例仍需先在已登录界面中打开。下面给出在 VM 终端直接运行的命令。

## 单局本地调试

先在官方界面打开正确题目的演练案例，等待倒计时结束并显示“等待机器狗进入”。在同一桌面终端执行：

```powershell
Set-Location C:\BDelivery-NEW
& C:\Python314-arm64\python.exe -B interfaces/official.py --problem 3 --mode practice --robot-id 实际队号 --case-code 当前案例码
```

入口直接构造算法并运行官方 HTTP 策略，日志写入 `outputs/official/`。`--mode` 和 `--case-code` 仅用于日志记录，实际会话由官方界面决定。异常由 Python 直接报告，已收到的请求记录仍保留；异常局是否已进入或结束，查看官方界面和请求日志。

本次整理不新开官方测试，也不执行 mock 性能测试。截至 2026-09-13 留档，Q3/Q4 各三次正式机会均已使用，上传记录在对应档案内；不能把这份交付说明视为新的正式测试授权。官方服务是否仍开放以当前界面为准。

## 消融与参数实验

```sh
python experiments/official.py ablation --problem 3 --list
python experiments/official.py ablation --problem 3 --setting online_nearest__g50 --check-config
python experiments/official.py sensitivity --problem 4 --setting fraction=0.3 --check-config
```

在 Windows 已打开演练后，增加 `--run --robot-id ... --case-code ...` 执行一局。每局一个进程，顺序使用同一个官方模拟器；不并发争用会话。联合扰动用 `--schedule-row N` 选择原始 `config.json` 的 schedule 第 N 行（1起始），题号必须匹配。只有显式 `--run` 才发送请求，list/check-config 不联网。结束后保留官方成绩界面/导出与请求日志，以官方虚拟时间、清除结果为准。

`data/experiments/*/package`保存官方实验使用的源码。运行入口按题号和实验设置构造策略，通过官方HTTP运行。`python tools/audit_data.py`核验源码、正式记录与演练数据的对应关系。

## 纯离线复现与证据

```sh
python experiments/build_tables.py
python tools/audit_data.py
python -m algorithms.q1q2.benchmarks.q2_outer.exclusion_run verify
# 以下在原 Windows ARM64 Python 中执行，并带上所选原始轨迹：
python tools/replay_official.py
```

表格重建覆盖927局有效官方演练，4局接入校验及正式数据不混入均值。按每局等权计算清除数、每源定位清除时间、程序运行时间。程序时间为官方 exit 与 enter 的 `real_timestamp_ms` 差值除1000；客户端墙钟单独保存，不能与该指标混用。统计输出在 `outputs/tables/`；核验和回放使用的逐局索引在 `data/provenance/practice_audit.json`。

回放读取25局与第二次正式方案同配置的演练和2局第二次正式记录，逐条核对命令路径、频道、位置与虚拟时间；网络审计钩子禁止连接。必须用原 Windows ARM64 数值环境核验精确轨迹，跨平台浮点计算可能改变对称候选的选择顺序。回放不生成场景、不是 mock 实验，也不能算新增性能样本。

`data/formal/index.json`和`data/experiment_index.json`使用仓库相对路径定位记录。原始日志保持原样；新运行与统计输出写入`outputs/`。实验数据见`data/experiments/`，正式结果见`data/formal/README.md`。

交付核对见 [交付检查](docs/delivery-check.md)，验证范围见 [交付验证](docs/validation.md)。

## 快速部署离线回放

```sh
python tools/package.py --include-experiments --include-replay --output dist/replay.zip
python interfaces/vm.py deploy --archive dist/replay.zip --destination 'C:\BReplay-NEW'
```

在 Windows 的该目录执行 `python tools/replay_official.py`。此包只加入27局需要的原始请求响应，不复制界面截图，也不会创建案例。部署和回放均可通过 Parallels exec 执行，无需模拟器处于运行状态。

维护时优先使用普通函数、显式参数与中文注释；数学或协议实现调整后，用已保存的官方响应检查轨迹差异。
