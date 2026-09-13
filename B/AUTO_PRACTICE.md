# 官方演练 GUI 自动入口

入口：[`auto_practice.py`](auto_practice.py)。仅支持 Q3/Q4 官方**演练**，默认 dry-run，不点击、不启动机器狗。没有正式模式、正式确认参数、自定义按钮、坐标或启动 HTTP 接口。

## 使用

前提：Parallels 的 `Windows 11` 已运行，`flower` 已在 **session 2** 手动登录模拟器，窗口位于前台，当前停在“演练测试”列表页。不要在自动运行期间操作模拟器。登录密码不传给脚本；脚本不读取输入框值，发现输入框/密码框时中止，避免截取凭据。

在宿主执行：

```bash
cd '/Users/flower/math/2026/B题'

# 默认不点击；分别验证 Q3/Q4 的真实按钮
python3 B/auto_practice.py --problem 3
python3 B/auto_practice.py --problem 4 --dry-run

# 读取真实“问题3正式测试”导航控件，验证拒绝后整进程退出
# 预期退出码 1、DENY_FORMAL、clicks=0、robot_started=false
python3 B/auto_practice.py --problem 3 --reject-formal

# 实际运行 1 局演练，读取权威结果，再返回演练列表
python3 B/auto_practice.py --problem 3 --execute

# 同一题连跑 N 局；任一步失败都会停止整个批次
python3 B/auto_practice.py --problem 4 --execute --runs 3
```

上面的多局命令是使用示例，**本次没有执行额外三局**。本次只打开 Q3、Q4 各一局。

队号默认 `202623001141`，可通过 `--robot-id` 覆盖，仅接受 ASCII 数字。guest 工作目录固定为 `C:\BRobot`，Python 固定为 `C:\Python314-arm64\python.exe`，机器狗参数固定：

| 题号 | 方法 | 共同参数 |
|---|---|---|
| 3 | `range_area7` | `--mode practice --base-url http://127.0.0.1:2026 --robot-id <队号> --confirm-practice` |
| 4 | `range_grid21_29` | 同上 |

不重新部署或修改机器狗策略。辅助文件复制到 `C:\BRobot\auto-practice\<运行编号>`。宿主经 `Downloads/AutoPractice` 共享目录传文件；长命令写入带 UTF-8 BOM 的 `.ps1`。GUI 使用 `schtasks /it /ru flower`，删除时间触发器后按需运行，并允许电池供电；任务结束后删除。SYSTEM/session 0 只用于调度、文件拷贝与副本查询。

## 总开关与停止

唯一允许的策略值为 `practice-only`，也是默认值。其他任何值均禁用：

```bash
AUTO_PRACTICE_POLICY=off python3 B/auto_practice.py --problem 3 --execute
```

运行中可创建全局停止文件：

```bash
touch "$HOME/Downloads/AutoPractice/STOP"
```

每次截图、点击前和机器狗启动前、运行监视期间均检查停止文件。也可在某次运行目录或其 GUI 作业目录创建 `STOP`，仅停止该次任务。恢复使用时由操作者删除自己创建的 STOP 文件。停止只终止本脚本启动的机器狗，不发送 `/exit`、不点击“中止测试”，不改变模拟器会话。

宿主使用文件锁，guest 使用命名互斥锁，防止两个入口并发；每个 GUI 作业有一次性 `started.once`，防止计划任务重放。Ctrl-C 会给当前作业写 STOP。没有把该开关转换成“允许正式”的途径。

## 护栏及识别方式

使用 Windows 原生 **UI Automation 的 Name、ControlType、ClassName、IsEnabled、IsOffscreen 和 InvokePattern**，不是 OCR、固定坐标、DOM 注入或模拟器绑定。UIA 公开接口说明见 [Microsoft AutomationElement 文档](https://learn.microsoft.com/en-us/dotnet/api/system.windows.automation.automationelement?view=windowsdesktop-10.0) 和 [InvokePattern 文档](https://learn.microsoft.com/en-us/dotnet/api/system.windows.automation.invokepattern.pattern?view=windowsdesktop-10.0)。

每次操作都先保存窗口截图和 UIA 文本，再检查：

1. 当前进程确实在 session 2，模拟器窗口在前台，连接正常、队号匹配。
2. 唯一选中的 `nav-item active` 必须精确为“演练测试”。主内容 `workspace-main` 和所有弹窗的文本/类名不得命中拒绝名单：`正式 / formal / production / real test / official test`，英文不区分大小写。
3. 开始按钮必须唯一、可见、可用，文本**精确等于**“开始问题3演练测试”或“开始问题4演练测试”，且与本次题号一致。先检查拒绝名单，再检查“演练”和白名单；命中正式立即退出，不另找按钮。
4. 用 UIA 的可点击点反查控件身份，确认没有遮挡。最后再次核对文字及总开关，才执行该控件的 UIA Invoke。记录的坐标仅用于身份/遮挡检查，不用于鼠标点击。
5. 点击后再截图，要求主内容含“演练”且无正式关键词；只读等待数据准备完成，最长 30 秒，期间不再点击。必须确认“问题N 演练 测试”“等待机器狗进入”“尚未进入”和唯一真实案例编码；`XXXX-XXXX-XXXX-XXXX` 不接受。启动机器狗前再截图、再核对同一案例。
6. 运行期间持续截图及检查正式关键词/总开关；出现错误终止本脚本的机器狗，整个批次退出。结束后核对演练结果页、同一案例和“测试已结束”。

演练页自身的左侧**未选中**正式导航、顶部截止公告、全局公告也有“正式”。这些固定区域会完整记录，但不当作当前正式页。当前选中导航、主内容和弹窗不豁免。结构改变、控件缺失/重复、窗口被遮挡或实际候选无法确认时均中止。

**完成弹窗唯一例外（用户在本任务中明确授权）：**仅当标题精确为“问题N演练测试完成”、弹窗全文无正式关键词，正文明确“测试正常结束”“行为日志已保存”，当前页面案例编码与刚核对的权威结果一致，并且弹窗只有一个可见可用“确认”按钮时，将“弹窗标题＋确认按钮”作为整体目标。截图留证后关闭，再截图核实，最后以同样护栏点击“返回演练测试”。其他“确认”、启动确认、错误弹窗一律没有关闭路径。

UIA 比 OCR 更适合这里的中文按钮及高 DPI 窗口：本机能直接读到精确控件文字并验证身份。不过依赖当前 WebView2 无障碍树，不能把有限验证视为所有窗口状态都可靠。只读取证期间消失的非候选节点记录为 `Unavailable-during-render`；实际操作仍要求重新查询到完整的页面与目标身份，不能据此放行失效候选。

## 权威库与汇总

只处理：`C:\Jammers\JammersSimulatorData\practice-statistics-queue.sqlite3` 中的 `practice_statistics_tasks`。

- **从不让 SQLite 打开实时库，也不访问正式统计库。**仅以普通只读文件方式把主库和 `-wal` 连续拷贝两份到 guest 临时目录。
- 两份 SHA-256 必须一致，否则重新拷贝，最多 10 轮。SQLite 仅以 `mode=ro`、`query_only=ON` 打开本地副本，通过 `quick_check` 后查询。副本产生的 SHM 也仅在副本目录；查询结束显式关闭连接，再把证据导出到共享目录。
- 不在 UNC 上直接打开 SQLite，不对实时库 checkpoint、backup、更新或写入。权威字段查询只选择所需统计列，不选择票据字段。
- 开局前后比较行 ID，要求恰好一条新增结果；同时核对界面案例编码、题号、队号、`entered=1`、有效结束原因和非负整数统计值。缺行、多个新增局或关联不符都停止，不把“最新一条”随便当作本局结果。
- 每局结果落入 `summary.json`：`jammer_count / cleared_jammer_count / clear_failure_count / virtual_time_us / end_reason`，保留完整整数微秒与大整数局号；同时汇总总干扰源数、总清除数、总失败数、总虚拟时间与是否全部清除。
- 正式拒绝立即退出；其他 GUI/机器狗错误后仍拷贝权威库作为事故证据，但不自动续跑或点击返回。机器狗日志/请求记录保存在作业的 `robot-run/`，独立于权威成绩。

## 证据路径与验证结果（2026-09-12）

实时证据：`~/Downloads/AutoPractice/<时间-随机编号>/`。退出时复制到本仓库 [`auto_practice_evidence/`](auto_practice_evidence/)。每个作业包含 `NNN-步骤.png`、同名 `.uia.json`、`decisions.jsonl`、`job.json`、`result.json`；宿主另有 `host-decisions.jsonl`、代码哈希、数据库双拷贝和 `rows.json`。失败截图不覆盖。

| 检查 | 结果 / 证据 |
|---|---|
| Q3/Q4 首次 dry-run | 均定位正确，0 点击；`20260912-212041-5cfa4af3`、`20260912-212105-13688f03` |
| 真实正式控件负测 | [Q3 日志](auto_practice_evidence/20260912-212120-da966c1e/001-0-reject-formal/decisions.jsonl)：实际读取“问题3正式测试”，`DENY_FORMAL`、0 点击、未启动机器狗，宿主退出码 1 |
| 完成弹窗与返回 | [Q3 关闭日志](auto_practice_evidence/20260912-212753-fac38aa5/001-1-return/decisions.jsonl)，以及 Q4 续跑目录的 `002-1-return`，均验证了限定复合目标和返回路径 |
| 拒绝名单回归 | [policy-test-results.json](auto_practice_evidence/policy-test-results.json)，30 项通过；包含 mixed“演练＋正式”、大写 FORMAL、错误题号、无演练字样；0 GUI/HTTP 调用 |
| 本地自动测试 | `python3 -m unittest discover -s B/tests -p test_auto_practice.py -v`，5 项通过；覆盖 WAL 拷贝实时文件哈希不变、错误/重复/旧结果、大整数、多局顺序、正式拒绝不回退 |
| 请求范围审计 | [verified-robot-commands.json](auto_practice_evidence/verified-robot-commands.json)：两局仅 `/enter /measure /clear /exit`，配置均为 practice，无正式确认 |

实际只打开两局，权威数据如下：

| 题号 / 案例 | jammer_count | cleared_jammer_count | clear_failure_count | virtual_time_us | end_reason |
|---|---:|---:|---:|---:|---|
| Q3 / `5AUG-JKMW-D9T2-RZ8E` | 15 | 15 | 1 | 3522849773 | user_exit |
| Q4 / `YNPU-UFZ7-P8AS-UR3C` | 11 | 11 | 0 | 6276090594 | user_exit |

结果：[Q3 权威记录](auto_practice_evidence/20260912-212337-dc2fcb0d/summary.json)、[Q4 权威记录](auto_practice_evidence/20260912-213052-132883d0/summary.json)。

**验证边界：这两局都曾在机器狗进入前安全中止，修复后按固定案例编码在同一局续跑；不能宣称最终版本已经完成一次从头到尾不中断的一键实跑。**Q3 开始记录在 `20260912-212222-2041146c`，Q4 在 `20260912-212904-df319012`。中止原因分别是运行页的复合类名、页面刷新时旧 UIA 节点失效。两项已修正；Q3 还遇到快速进程退出导致 ExitCode 为 null 的包装问题，已通过保存进程句柄修正并以独立退出码测试验证；Q4 修复续跑的机器狗退出码为 0。

一次性续跑脚本仅用于这两个已打开的固定案例，归档在证据目录，**正常入口不提供恢复/跳过护栏参数**。没有再次点击开始来掩盖失败，也没有超过两局验证上限。连跑调度已做隔离测试，真实环境验证了两次关闭完成弹窗和返回，未另跑 N 局压力测试。

## 已知失效与人工兜底

- 模拟器升级导致文字、无障碍树或弹窗结构变化，窗口失去前台、VM 锁屏、session ID 改变、网络断开、数据准备超过 30 秒：保存证据后停止。先查看最后的 PNG/UIA JSON/决策日志，修复或恢复环境后重新 dry-run；不提供坐标点击或泛化“确认”兜底。
- 若中止时已开演练、机器狗尚未进入，正常入口不会自动接管已有局。由操作者核对确为演练后在界面处理，再回演练列表；本次调试采用了固定案例的人工审查续跑，未做成通用绕过路径。
- 正式页/正式候选被识别时，立即退出，不自动导航回演练。请人工回到演练列表后另起一次 dry-run。负测从当前演练页读取正式导航文字，**没有为验证而进入真实正式页**。
- 不自动登录，不接收密码，不关闭未知弹窗，不发送补偿 HTTP 请求。VM/共享目录整体断开时，宿主可能无法即时送达停止文件；guest 的监视和任务时限仍生效。重新连通后先确认旧任务已结束。
- 多人或其他程序同时操纵模拟器会造成状态竞态；不要在自动运行期间切换页面或另开会话。截图、UIA 核验和点击不是与外部操作原子同步的，应保持独占操作时段。
