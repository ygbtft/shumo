# 九项交付要求核对

| 要求 | 当前文件 | 核对结果 |
|---|---|---|
| 1. Q1—Q4 算法 | `algorithms/q1q2/`、`algorithms/q34/` | 保留；Q3/Q4 从 `strategy.py` 读取第二次正式参数 |
| 2. 官方模拟器本地调试接口 | `interfaces/official.py`、`vm.py`、`recording.py` | 直接通过 VM 内 HTTP 运行和记录；直接访问官方机器人接口 |
| 3. 正式三次、消融、参数数据 | `data/formal/`、`data/experiments/` | 两题各三次；927 局有效官方演练及接入记录完整保留 |
| 4. 论文素材 | `paper/` | 保留模型正文、图、四表及统计源码对应的素材 |
| 5. 仓库布局说明 | `README.md` | 已更新目录说明及当前命令 |
| 6. 四题主要思路 | `docs/q1.md`—`q4.md` | 四篇均保留 |
| 7. Agent 环境交接 | `HANDOFF.md` | 保留环境、部署、单局调试和离线复现命令 |
| 8. 消融/参数实验可运行源码 | `experiments/official.py`、`build_tables.py`，对应数据包的 `package/` | 保留；按实验设置和对应源码运行 |
| 9. 第二次正式版本 | `data/formal/q3/attempt2/package/`、`q4/attempt2/package/` | 当前核心算法和布局共21个文件与两题第二次冻结包逐字节一致 |

## 验证入口

`tools/audit_data.py`核验六次正式记录、927局演练和21个核心文件；`tools/check_configs.py`检查306个实验配置；`tools/replay_official.py`在Windows ARM64环境逐条回放27局官方响应。数值结果见[验证说明](validation.md)，回放记录见[replay.json](../data/provenance/replay.json)。
