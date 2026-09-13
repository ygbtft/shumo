# 标准场景外层全域排除证书（新增套件）

本套件落实 `review-opt/opt-q12.md` 建议 A，新增可选模块
`algorithms/q1q2/optional/outer_exclusion.py`、独立复核器 `check_exclusion.py`、
CLI `exclusion_run.py` 和证书完整性测试。不修改 `q2.py`、`geometry.py`、
`circle.py`、`certified.py` 的算法、判据或 J/F/C_sig 定义。
原 `run.py`、`report.json`、`paper-results.md` 及所有原有搜索数据保留。
**不要为本任务运行旧 `run paper`：它会写论文。**

## 复现命令

从仓库根目录执行，使用既有可选依赖环境（Python、numpy、mpmath、pytest）：

```sh
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
.venv/bin/python -m algorithms.q1q2.benchmarks.q2_outer.exclusion_run solve
.venv/bin/python -m algorithms.q1q2.benchmarks.q2_outer.exclusion_run verify
.venv/bin/python -m pytest -q algorithms/q1q2/benchmarks/q2_outer/tests
# 可另选输出目录，不覆盖本次证书：
.venv/bin/python -m algorithms.q1q2.benchmarks.q2_outer.exclusion_run solve --output /tmp/q2-outer-replay
.venv/bin/python -m algorithms.q1q2.benchmarks.q2_outer.exclusion_run verify --output /tmp/q2-outer-replay
# 预算退出及其完整域覆盖也必须通过复核：
.venv/bin/python -m algorithms.q1q2.benchmarks.q2_outer.exclusion_run solve --max-nodes 9 --output /tmp/q2-outer-budget
.venv/bin/python -m algorithms.q1q2.benchmarks.q2_outer.exclusion_run verify --output /tmp/q2-outer-budget
# 原有四块 benchmark、Q12/Q34 tests、新套件、两项主候选 owned mock-http：
.venv/bin/python -m algorithms.q1q2.benchmarks.q2_outer.exclusion_regression --output /tmp/q2-outer-regression
```

回归入口只重定向原 benchmark 的 `report.json` 写入，原始夹具、比较代码及既有报告不变；
Q34 pytest 以 `B/` 为 cwd。mock-http 显式选该模式，使用自己创建的随机回环端口，
不访问官方模拟器、不调用 practice 或正式测试。主候选每局完整 HTTP 轨迹由原 runner
保存到 `B/robot_runs/`，新回归报告记录其路径并复制 summary。

## 认证结果

推荐点仍为实际 binary64 坐标 `(843.035666,545.527004)` m。
已有固定点区间认证器重新计算得到：

- `J(q_hat)` ∈ `[110.96913484045108,110.97010129273485]` m（两个 binary64 端点），2144 节点，固定点认证收敛。
- `U = 244025833413685/2199023255552` m。
- `L = U - 1/100 = 6100096079528237/54975581388800` m。
- `L <= inf_{q in C_sig} J(q) <= J(q_hat) <= U`；精确有理端点差 `U-L=1/100` m。
- 展示端点向外取到小数点后六位：**110.960101 ≤ J* ≤ 110.970102 m**，展示宽度 **0.010001 m**。
- 5319 个处理节点，2660 个闭叶盒：862 个圆盘排除、1798 个源对下界，未决 0。
- 独立精确覆盖扫描为 650 个 x 薄片，总面积 `1005000 m²`，无缺口、无正面积重叠。
- 复核 866 个不同的实际源点，使用 60 位区间运算；全部满足首次严格 `>5`、闭外径和闭角界。

这些计数与原型一致。模块不依赖 `/tmp` 原型或读取其结果；可从零生成证书。
运行时间是机器/环境相关量，JSON 分开保存初始化后搜索时间和包含固定点认证的总时间，
不作为与历史完整外层搜索的同工作量加速比。

## 证明范围与证书合同

标准连续模型限定为 `S=(0,0), theta=0, epsilon1=epsilon2=1°`，
`rho in [1000,1500]` 固定未知，`near=5`，目标圆中心 `(0,0)`、半径1800；
行动矩形 `[-2000000,2000000]^2` 不截断本次候选域。
首次源域是完整扇环 `5<r<=1500, |alpha|<=1°`。
配置在搜索器与复核器分别显式构造，不能传入非对称/裁剪模型或随意换根域。

依 `PLAN.md §5.8`，令 `u±=(cos 1°,±sin 1°)`，C_sig 恰为
`D(5u±,1000)` 与 `D(1000u±,1000)` 四盘交。
后两盘相加推出 `qx>=0`；近端圆盘推出 `qx<=1005`，
对 y 符号选相反的近端圆心得 `|qy|<=1000`。
故完整包围盒为 `[0,1005]×[-1000,1000]`。标准 F、C_sig、共同反馈角条件与同站规则均在
`(x,y)->(x,-y)` 下不变，所以只需覆盖 `[0,1005]×[0,1000]`。
这不是任意场景的对称缩域接口。

实际源点由 binary64 坐标表示，转换 Fraction 无损。每个点单独通过 mpmath.iv 成员检查；
目标圆包含整个1500米圆，故闭外径同时保证目标圆约束。5米圆心属于极限位置，仅用于
候选域四盘约化，不被当成合法源见证。

取正有理数 `k=5032613263056833/144115188075855872`，区间证明 `k<tan(2°)`。
固定源对的 `w=(x-q)·(y-q)`、`z=cross(x-q,y-q)` 满足 `w>=0, kw±z>=0`，
且两源到全盒的距离严格大于5时，全盒中每个不同于 S 的站点都允许该源对共同 direction。
因此对可行站点 `J(q)>=|x-y|`；q=S 按 diam(F) 规则也满足同一下界。

搜索器将上述三个二次式及两个距离平方按
`k(qx²+qy²)+bx*qx+by*qy+c` 展开，以 `clip(-b/(2k), B)` 精确求最小值。
点对距离平方与目标平方也使用 Fraction 比较，不用浮点开根作为下界。
圆盘排除首先将真实三角圆心向外包在 binary64 有理矩形中，再精确计算站点全盒到
该圆心矩形的最小距离；只有其平方严格大于1000²才能排除。

静态183点库与动态旋转求交/缩短均只提议源对。浮点筛选容差不进入剪枝证明，
区间 F 检查或精确全盒判据失败即继续尝试证据/分裂。
最长边由精确有理长度比较，x方向在并列时优先；两个闭子盒共享精确中点。
每节点最多继承最近8对提议，不影响覆盖或证明。

`certificate.json` 保存模型标识、完整根域、q、k、精确 target/U/L/gap、固定点区间结果、
每个闭叶盒及对应圆盘索引或实际源对、未决盒、预算、版本和代码SHA256。
区间上界从原 `certify` 获取，其 `_up` 向外舍入保留。tau 默认十进制字符串 `0.01`，
转成精确有理数；目标直接为 `U-tau`，避免二次浮点减法舍入。

预算中断保存全部栈中未决盒及其**保守下界0**。整个 partition 仍完整；
有未决盒时报告 `[0,U]`、`CERTIFIED_OUTER_BOUNDS`、`converged=false`，
不将已闭叶盒的 target 当全域下界。这里尚未实现未决盒更强的继承下界和 incumbent 更新。
固定点认证若预算退出仍只使用它的合法上界；不会把其 converged 字段伪造为 true。
搜索秒数预算从证据库初始化后开始，初始化/固定点认证另计；节点预算可确定复现。

独立复核器不导入搜索模块或搜索谓词。它按完成平方的“矩形到中心最近距离”公式
重算全部源对最小值，以60位区间重新检查真实三角圆盘和实际源成员，
并精确扫线核对**全部闭叶盒（包括预算未决盒）**覆盖。
有限闭盒对各开薄片的覆盖也覆盖薄片边界；单独面积相等并不被当成覆盖证明。
最后重新调用固定点认证器，要求新上界不大于归档U，核对上下界包含、目标、状态、节点计数。
所有拒绝用 ValueError，不依赖可被 `python -O` 移除的 assert。

本证书依赖既有 mpmath.iv 包含合同及上述模型化约定，不是形式化证明系统。
不证明唯一坐标、坐标误差、最优值是否达到，也不解决次级移动距离优化。
不外推非标准首测、非对称行动约束、目标圆裁剪、经验误差场、离散读数或官方成绩。
即使相同算法其他输入不能有限闭合，也应诚实返回未决。
