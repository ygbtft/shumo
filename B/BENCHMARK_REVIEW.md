# 同学 benchmark 与 macOS handoff 审核

用户提供 https://github.com/ygbtft/shumo.git 的 b 分支。

已冻结并核对 `c477d3660368f27c7131a0591426b4c4f107ea5d` 和新增 handoff 的 `ededa9e13f1864be88add579b6724f45bc01fc50`。两个提交的核心模拟器、生成器、策略和协议代码一致；更新仅为 `mock/MACOS-WINDOWS-HANDOFF.md`、`models/q1q2/PLAN.md` 和 README。上游副本 `git status --porcelain` 均为空。

可以使用这个 benchmark。它具有完整的标准库物理/协议后端、可替换客户端、强制3位置×5误差压力矩阵和诚实的假设记录，适合作为我们的独立交叉验证后端。纯内存规则测试114项通过；本轮适配器在 `peer_benchmark.py`，未修改上游。

需要保留的区别：

- `mock/` 仍是独立实现，官方隐藏场景、误差分布和全部边界行为没有因此变成已知。
- 原有README“尚无官方实测”已过时；最新 handoff 指向 `practice-logs/REPORT.md` 的一次演练。该JSONL有1367条记录，本轮独立重算计时整数微秒零差异，详见 `recording_audit.json`。
- 该记录发现15频道、清除10频道，用于规则/延迟采集；它不是本轮策略的官方成绩，也不是 `mock.strategy.Baseline` 的成绩。
- 报告引用的GUI截图不在两个提交中。GUI显示总数15按同学报告保留，不能说已亲自检查截图；记录来源没有官方签名认证。
- 固定 ±1°、平滑或iid场仍是静态合成假设；校准代码存在不等于已经完成校准。
- 同学基线在本轮300个组合中也全部清除，但没有本轮的后验光学覆盖证明。样本成功不能代替保证。

最新 handoff 是 Mac 通过 Windows ARM64 VM 运行 Windows 官方软件的交接，不是原生Mac版。其“VM已准备好”是同学机器状态。当前只读检查为ARM64/macOS15.6，标准 `/Applications/Parallels Desktop.app/Contents/MacOS/prlctl` 未找到，仓库不含官方安装包。本轮不安装VM、不向非B目录中转文件、不使用对方录制中的报名身份，不操作官方GUI。

我们的Q3/Q4源码包比标准库benchmark多一个NumPy运行依赖，需在目标Windows实际做离线验证。当前包仅在Mac通过离线冒烟。完整策略通过第二后端的1200次执行后，仍需本队真实演练。

同学交接中关于共享目录、交互桌面、不得把guest回环当宿主回环、使用 `/enter` 的剩余时间、保留旧录制和不要把模态声明当服务器认证等说明是有用的。其安装命令、账户和绝对路径未在本机执行。部署本身属于后续任务，本轮保持用户最初规定的离线范围。
