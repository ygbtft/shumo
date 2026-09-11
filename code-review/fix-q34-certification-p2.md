# Q3/Q4 认证与校验工具 P2 修复记录

2026-09-11。对应 `review-q34-core.md` 的 I1/I2/I3、F1/F2/F3、V1/V2。仅修改三个指定工具，新增 `B/tests/test_q34_verifier_regressions.py`；保留工作区此前已有的加固和策略修改。

## 逐条修复与复现

| Finding | 根因与改法 | 修复前 → 修复后；回归覆盖 |
|---|---|---|
| I1 | 生成器与独立验证器的成功前提依赖 assert；全部改显式 if/ValueError，包括坐标、int64 安全界、距离、闭凸包及分区。 | 原点附近三站配根方形单叶，在 `-O` 下返回成功 → `ValueError: corner receiving distance must be strictly below 1000 m`。优化子进程还验证分数坐标、1951 坐标、深度17均拒绝；遗漏、重叠、重复叶、凸包外角点均拒绝。 |
| I2 | 验证器信任半径字段、scale 与 Python 索引语义。固定1800/1000，scale限定1至65536的二次幂整数，点集限定非空有限整数Nx2且坐标绝对值≤1950；叶子必须非空、有限、正半宽、落在根内且能按尺度整数化；索引为传入点集的零基行号，拒绝负数、布尔、浮点及越界。 | 域半径1/接收10的合法小域证书原来通过 → 明确拒绝非竞赛参数。12类元数据、6类点集、6类索引及叶几何反例覆盖。有效tuple索引通过。 |
| I3 | 缺少整数/浮点与算术界说明。注明二次幂尺度、平方阈值向下取整、逆时针边的矩形支撑项和闭凸包等号；独立角点用Python int，生成器依赖int64安全界。NumPy整数深度规范为Python整数，阈值按固定整数1800/1000计算。 | 文档缺口 → 明确距离平方和 `<1.21e17`、凸包支撑运算中间量 `<1.86e17`，均低于int64上限。原生整数与NumPy整数深度/整数值浮点半径生成完全相同证书；闭凸包边界允许，接收距离恰为1000拒绝。 |
| F1 | 原逻辑仅验非零边半平面，点直接跳过，线段仅限制整条直线。新增直接计算几何裕量的函数：空集拒绝，点验距离，共线区域取极端端点并计算有限线段距离，二维凸区域验逆时针边半平面；保留1e-5米包含容差。 | 点区域`[[0,0]]`、源`[100,100]`原误过；线段`[[0,0],[1,0]]`、源`[2,0]`原误过 → 均失败。覆盖点命中、两个端部外侧、垂向外侧、线段端点/内部、重复点、多顶点共线、正常二维内外点。main的点/线段/空集故障注入也失败。 |
| F2 | 分区入口未校验根域和尺寸，零半宽能不断生成相同孩子。入口固定根域并校验非空、有限、正尺寸；先验证叶子的四叉树路径，仅沿已验证祖先展开，缺叶立即报错。每条输入路径最多1086步（二进制浮点从1800缩至零的界）。 | `arena_radius=0,cells=[[1,0,0,[]]]`修复前子进程2秒超时 → 修复后立即ValueError。优化子进程还检查空叶、零/负/NaN/Inf/最小次正规半宽；现有重复、重叠、离树、缺叶检查均保留。 |
| F3 | 回放请求匹配、trace耗尽、归档计数/全清/一致性/时间命令上限/哈希/仓库状态/链接/旧manifest均依赖assert。逐处改为显式if/ValueError，不增加检查框架。 | 原判据可被`-O`移除 → 正常与优化模式下，临时完整归档成功，16类归档故障分别失败，请求端点/内容不匹配、trace未耗尽也失败；语法树检查确认两个目标模块无残留assert。 |
| V1 | unresolved_cell见证调用漏传receive_radius。传入本次接收半径。 | 半径2000例原错称`no_station_in_range` → 正确返回约182.3818°的方向缺口。覆盖500和2000两种半径，返回值与显式调用directional_witness一致。 |
| V2 | tuple通过索引合法性检查，却被NumPy解释为多轴索引。取站点前转换为list行索引，并注明口径。 | 合法tuple索引原会IndexError → 完整64叶证书通过，list语义不变。 |

根方形固定为 `[-1800,1800]²`，原有源圆盘外叶格可省略的语义保持。整数独立角点验证承诺严格 `<1000m`，不冒称独立重验生成器的 `1e-5m` 内缩余量。没有把圆盘证书升级为整方形证书；`certify_layout_coverage` 原有上下文绑定和Fraction整方形面积检查保留。浮点工具相对本轮开始仅改接收半径传递和tuple行索引两处。

## 测试结果

均在B目录使用指定解释器 `/Users/flower/math/2026/B题/mock/.venv/bin/python`：

```sh
/Users/flower/math/2026/B题/mock/.venv/bin/python -B -m pytest tests/ -q -p no:cacheprovider
# 132 passed, 230 subtests passed in 9.82s
/Users/flower/math/2026/B题/mock/.venv/bin/python -B -O -m pytest tests/test_q34_verifier_regressions.py tests/test_visibility_certificate.py -q -p no:cacheprovider
# 96 passed, 37 subtests passed in 3.89s
```

优化测试有一条pytest例行提示：非测试模块中的assert会被忽略；这正是本次覆盖的运行模式，两个被加固模块已无assert。新增文件共86项参数展开测试；其余为既有测试。全套包括既有网络失败与重试复用request_id回归。

11份旧浮点布局分区/几何检查仍通过；强接口仍按设计拒绝圆盘证书冒充整方形证书。重生成并独立验证：`grid21_29`保持6976叶，`closed21_3`保持8348叶，保存的对应证书也通过。没有运行会改写真实历史manifest的完整审计main；main的检查分支在临时构造归档上执行。

原始测试输出：[全套](q34-certification-p2-evidence/tests.txt)、[优化模式](q34-certification-p2-evidence/tests-optimized.txt)；[前后反例及HTTP对照](q34-certification-p2-evidence/reproductions-and-http.json)。

## 主候选未受影响的证据

同为seed42、cover21系列、mock-http模式；前版本从动手前复制的三个模块导入，其余代码与后版本使用同一工作区。

| 主候选 | 修复前后全清 | 命令数 | 虚拟时间 | 逐条请求/响应 |
|---|---:|---:|---:|---|
| Q3 range_area7 | 10/10 | 140 | 3304.341074秒 | 一致 |
| Q4 range_grid21_29 | 10/10 | 293 | 5847.482087秒 | 一致 |

比较只去除每次会话随机UUID前缀与实时时间戳，保留request_id序号、请求位置/频道、HTTP状态、反馈及虚拟时间；两组分别140/293条完全相等。均正常enter/exit，transport_failures=0，official_calls=0。没有修改网络重试或幂等逻辑。

- Q3修复后：[summary](../B/robot_runs/20260911-182337-368708-bounded-mock-http/summary.json)；修复前：[summary](../B/robot_runs/20260911-182406-060475-bounded-mock-http/summary.json)。
- Q4修复后：[summary](../B/robot_runs/20260911-182337-724064-bounded-mock-http/summary.json)；修复前：[summary](../B/robot_runs/20260911-182406-415122-bounded-mock-http/summary.json)。

该前后对照证明本次seed42轨迹未变；未将它表述为重新执行所有历史场景。
