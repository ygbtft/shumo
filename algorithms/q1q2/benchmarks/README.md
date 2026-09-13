# Q1/Q2 数学基准

基准使用独立于被测算法的真值：闭式公式、有理数精确几何、高精度角函数、独立枚举或线性规划。稠密采样只能给出所检范围内的证据，不能充当连续全域认证。

| 目录 | 验证内容 | 已保存结果 |
|---|---|---|
| [q1_geometry](q1_geometry/README.md) | 区域分类、顶点、直径与几何不变量 | 285/285 |
| [q1_circle_cover](q1_circle_cover/README.md) | 最小覆盖圆、直径圆与清除判据 | 330/330 |
| [q2_candidate](q2_candidate/README.md) | 源域、保收域、近场与边界语义 | 531/531 |
| [q2_worst_diameter](q2_worst_diameter/README.md) | 同反馈点对目标、源采样、移动预算 | 48/48 |
| [q2_outer](q2_outer/README.md) | 标准场景第二站搜索与连续认证 | 结果与证书分别保存 |

从仓库根目录安装 `requirements.txt`，使用根目录 `.venv`：

```sh
.venv/bin/python -m algorithms.q1q2.benchmarks.q1_geometry.run
.venv/bin/python -m algorithms.q1q2.benchmarks.q1_circle_cover.run
.venv/bin/python -m algorithms.q1q2.benchmarks.q2_candidate.run
.venv/bin/python -m algorithms.q1q2.benchmarks.q2_worst_diameter.run
```

各目录 `cases.jsonl` 保存输入与独立真值，`report.json` 保存逐例比较、容差、异常、源码哈希与运行时间。分类标签可能重叠，不将分类计数相加作为案例总数。具体尺度限制与未决状态按各基准说明解释；Q3/Q4 官方演练数据在 [data/experiments](../../../data/experiments/)。
