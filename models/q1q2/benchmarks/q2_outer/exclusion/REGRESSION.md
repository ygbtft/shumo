# 建议 A：验收与前后对照

本次只新增外层可选模块、独立证书套件和文档，没有编辑论文或既有几何/Q2算法。
最终验收见 `after-final/summary.json`：9项命令退出码全部为0，运行期间所记录
Q12/Q34 Python 文件的SHA256无变化（`changed_during_run=[]`）。
本次证书记录的七个实现/认证文件哈希也与验收后的文件一致。

## 正确性回归

| 项目 | 开工后首轮实测 | 最终实测 |
|---|---:|---:|
| Q1 geometry | 285/285 | 285/285 |
| Q1 circle cover | 330/330 | 330/330 |
| Q2 candidate | 531/531 | 531/531 |
| Q2 worst diameter | 48/48 | 48/48 |
| models/q1q2/tests | 1289 passed | 1290 passed |
| 新增外层证书测试 | 无该套件 | 37 passed |
| B/tests | 并行变更期间1项临时失败，见下文 | 157 passed + 238 subtests passed |
| Q3 主候选 seed42 mock-http | 历史主候选全清 | 10/10，all_cleared=true |
| Q4 主候选 seed42 mock-http | 历史主候选全清 | 10/10，all_cleared=true |

用户给出的 Q12 tests 基线为1172；工作区在开工首轮已含1289项，最终为1290项。
新增37项证书测试位于 benchmark 子目录，单独运行，不混入该1290。
工作区存在其他并行任务对Q12/Q34的修改，本任务不把这些新增项或策略变化归为建议A的成果。

首轮 `B/tests` 从仓库根目录运行因裸导入失败（保留 `before/q34-tests.log`）；
改在 `B/` 中运行时，Q3主候选类和其快照夹具正在被并行任务更新，出现1个临时快照不匹配
（`before/q34-tests-correct-cwd.log`）。本任务没有编辑B代码、夹具或豁免测试。
随后完整运行已通过，最终固定文件哈希的验收再次全过。

新增回归汇总器第一次解析 mock 输出路径时没有去掉 `Local logs: ` 前缀而报错；
属于汇总器路径解析错误，当次实际pytest与Q3 mock已成功。修正后完整重跑，
最终Q3/Q4 summary和所有退出码以 `after-final/` 为准。中间日志仅作审计，不能替代最终报告。

## 外层认证与原型对照

| 项目 | 建议A原型 | 生产模块+独立复核 |
|---|---:|---:|
| 展示最优值区间/m | [110.960101,110.970102] | [110.960101,110.970102] |
| 展示宽度/m | 0.010001 | 0.010001 |
| 目标差/m | 约0.01（二进制减法后向下） | 精确1/100（Fraction端点差） |
| 处理节点 | 5319 | 5319 |
| 叶盒 | 2660 | 2660 |
| 圆盘/源对排除 | 862/1798 | 862/1798 |
| 未决盒 | 0 | 0 |
| 精确x薄片 | 650 | 650 |
| 覆盖面积/m² | 1005000 | 1005000 |
| 源成员复核精度 | 60位 | 60位，866个不同实际源点 |

固定点重新认证的原始上界为110.97010129273485（binary64），与原型及既有报告一致。
`verification.json` 中的 L、U、gap 是无损有理数字符串；展示值向外舍入。
`reproducibility.json` 记录独立从零重跑的根域、q、k、target、L/U/gap、节点、状态和
**完整叶盒列表全部相同**。重跑的验证另外使用 `python -O`，仍然通过，
说明安全拒绝没有依赖可关闭的assert。

保存的节点预算示例 `budget/certificate.json` 在9节点退出，有2个圆盘排除叶和6个未决叶，
`budget/verification.json` 证明整个闭分区仍覆盖根域；报告 `[0,U]`，没有把局部闭合充作全域gap。
新测试还验证时间预算、零节点、固定点认证预算退出、非法源、near等号、恶意提议、
源点/上界/下界/切线k/根域/状态篡改、漏盒、重复盒和相同面积却有重叠缺口的反例。

## 当前主候选mock结果

| 项目 | Q3 range_area7 | Q4 range_grid21_29 |
|---|---:|---:|
| seed | 42 | 42 |
| 清除数/源数 | 10/10 | 10/10 |
| 虚拟总秒 | 3396.191321 | 5847.482087 |
| 请求数 | 140 | 293 |
| transport_failures | 0 | 0 |
| entered / exited | true / true | true / true |
| official_calls | 0 | 0 |

Q3结果反映同时更新后的当前主候选，不把它的虚拟时间变化归因于外层可选模块。
summary路径及完整请求轨迹目录由 `after-final/summary.json` 记录；
两局只用自建随机端口回环HTTP服务，不访问官方模拟器，也不触发正式测试。

## 可复现命令

从工作区根目录：

```sh
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
models/q1q2/.venv/bin/python -m models.q1q2.benchmarks.q2_outer.exclusion_run solve --output /tmp/q2-outer-new
models/q1q2/.venv/bin/python -O -m models.q1q2.benchmarks.q2_outer.exclusion_run verify --output /tmp/q2-outer-new
models/q1q2/.venv/bin/python -m pytest -q models/q1q2/benchmarks/q2_outer/tests
models/q1q2/.venv/bin/python -m models.q1q2.benchmarks.q2_outer.exclusion_regression --output /tmp/q2-outer-regression
```

回归脚本运行原四块benchmark，不重新生成案例、不改正确性容差或原始report。
其 `--worker q1_geometry|q1_circle_cover|q2_candidate|q2_worst_diameter` 可单独复现各块，
并将报告写入 `--output`。原始 `q2_outer/run.py` 和报告没有被替换；完整数学边界见 `../EXCLUSION.md`。
