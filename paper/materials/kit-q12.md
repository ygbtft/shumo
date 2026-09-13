# Q1/Q2 论文素材

本目录索引当前算法对应的推导、数学实验与认证结果。Q3/Q4 的官方模拟器结果见 [Q3/Q4 素材](kit-q34.md)，两类实验分别使用各自的评价指标。

## 正文与代码

| 内容 | 文件 |
|---|---|
| Q1/Q2 完整数学推导 | [modeling-q1q2.md](../modeling-q1q2.md) |
| 输入、计算过程与结论范围 | [实现说明](../../docs/q1q2-design.md) |
| 算法与命令入口 | [算法目录](../../algorithms/q1q2/README.md) |
| 文献论证与适用范围 | [文献素材](../../algorithms/q1q2/reviews/literature-review.md) |
| 参数与假设敏感性 | [实验说明](../../algorithms/q1q2/reviews/sensitivity/README.md)、[T6](../../algorithms/q1q2/reviews/sensitivity/T6.md) |
| 图件和绘图数据 | [数学求解输出](../../algorithms/q1q2/outputs/) |

## Q1 可用于论文的结论

有界示向误差对应角锥交集；集合可能为空、退化或无界。对有界凸区域，直径 d 与最小覆盖圆半径 R 满足 d/2≤R≤d/√3。边长 20 米的等边三角形直径为 20 米，最小覆盖圆半径为 20/√3 米，因此直径圆不一定覆盖区域。

统一 20 米清除要求 R≤20；d≤20√3 时一定存在清除落点，d>40 时不存在，中间区间取决于形状。空域不代表定位成功；仅有覆盖半径上界超过 20 也不足以证明不可能清除。

## Q2 标准场景的数值与认证

首站 (0,0)、首测 0°、两次误差半宽 1°、目标圆半径 1800 米、接收半径固定未知且位于 [1000,1500] 米、近场半径 5 米。推荐第二站为 **(843.035666,545.527004) 米**。固定坐标的连续最坏直径认证区间向外展示为 **[110.969134,110.970102] 米**。

数据来自 [统一复评报告](../../algorithms/q1q2/benchmarks/q2_outer/report.json)，其中同时保存固定对照点 (750,400)、共同源样本复评、移动耗时、条件覆盖量及容差检查。坐标小数位数是复现精度，不是最优坐标误差保证；条件覆盖量只对应报告所列共同反馈。

[全域排除证书](../../algorithms/q1q2/benchmarks/q2_outer/exclusion/certificate.json) 与 [独立复核结果](../../algorithms/q1q2/benchmarks/q2_outer/exclusion/verification.json) 给出标准模型的 **110.960101≤inf J(q)≤110.970102 米**。精确有理端点相差 0.01 米；2660 个闭叶格覆盖所需根域。证书依赖所述模型和区间算术包含约定，不是形式化证明，也不适用于任意首测输入。

固定点认证与全域下界是两种不同结论。论文可据此说明推荐点目标值距标准场景全域下确界至多 0.01 米；不能据此断言坐标唯一或官方任务耗时最优。

## 数学基准与敏感性数据

| 基准 | 案例数 | 结果文件 |
|---|---:|---|
| Q1 区域与直径 | 285 | [report.json](../../algorithms/q1q2/benchmarks/q1_geometry/report.json) |
| Q1 圆覆盖 | 330 | [report.json](../../algorithms/q1q2/benchmarks/q1_circle_cover/report.json) |
| Q2 候选可行性 | 531 | [report.json](../../algorithms/q1q2/benchmarks/q2_candidate/report.json) |
| Q2 最坏直径 | 48 | [report.json](../../algorithms/q1q2/benchmarks/q2_worst_diameter/report.json) |

这些是数学模型基准，不计入官方演练局数。Q1/Q2 敏感性数据在 `algorithms/q1q2/reviews/sensitivity/results/`，汇总见 T6；未执行的场景及未完成细化的状态均在其说明中列明。采样变化范围不应写成连续最坏值的认证误差。

## 复现

在仓库根目录安装 `requirements.txt` 后执行：

```sh
python -m algorithms.q1q2.benchmarks.q2_outer.exclusion_run verify
python -m pytest algorithms/q1q2/tests -q --import-mode=importlib
```

重新搜索、固定点认证与全域证书生成见 [外层实验说明](../../algorithms/q1q2/benchmarks/q2_outer/README.md)。Q1/Q2 敏感性计算与派生报告命令见 [敏感性实验说明](../../algorithms/q1q2/reviews/sensitivity/README.md)。
