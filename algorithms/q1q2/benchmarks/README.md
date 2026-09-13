# Q1/Q2 正确性 Benchmark

目标：用**独立于被测生产代码**的真值，检测 `algorithms/q1q2/` 的 Q1/Q2 算法是否正确。

## 铁律：真值必须独立

每个 benchmark 的期望答案（ground truth）**绝不能调用被测的生产函数**得到。允许的真值来源：
- **闭式解析**：手推公式的规则族（正多边形、等边/等腰三角形、正交双测点、线段 F 等）。
- **精确算术**：`fractions.Fraction` 有理数、`decimal` 高精度做几何谓词与交点，避免 float 噪声。
- **暴力/独立参考**：全对枚举、稠密网格/蒙特卡洛世界采样、`scipy.optimize.linprog` 的 LP 可行性（与自研半平面法独立）。
- **不变量**：刚体变换/缩放/反射不变性、单调性（加约束直径不增、嵌套采样最坏直径不降）、对称镜像一致。

若某真值只能用生产代码近似，必须显式标注为"弱对照"，不计入通过判定。

## 目录划分（每个 agent 独占一个，互不写对方文件）

```
algorithms/q1q2/benchmarks/
  README.md                  本文件（契约）
  q1_geometry/               半平面交分类 + 旋转卡壳直径
  q1_circle_cover/           最小覆盖圆 + Thales 覆盖判定 + κ/η
  q2_candidate/              F、C_sig、C_dir、四圆盘约化
  q2_worst_diameter/         不可区分点对最坏直径 J(q) + 第二点选择 + 短基线下界
  index.json                 汇总（由父 agent 生成）
```

## 每个子目录必须包含

- `generate.py`：产出案例（随机 + 对抗 + 退化 + 闭式族），每例带独立真值；写 `cases.jsonl`（含 input、ground_truth、truth_method、类别标签）。
- `run.py`：把案例输入喂给生产代码，与真值比较，按**明确记录的容差**判定，写 `report.json`。可 `python -m algorithms.q1q2.benchmarks.<area>.run`。
- `README.md`：说明覆盖了哪些构型、每类真值怎么独立算出、容差依据、已知边界。

## `report.json` 统一格式

```json
{
  "area": "q1_geometry",
  "generated_utc": "...",
  "n_cases": 1234,
  "n_pass": 1230,
  "n_fail": 4,
  "categories": {"random": {...}, "adversarial": {...}, "degenerate": {...}, "closed_form": {...}},
  "tolerances": {"length_m": 1e-9, "angle_deg": 1e-9, "...": "..."},
  "failures": [
    {"case_id": "...", "input": {...}, "expected": ..., "actual": ..., "error": 0.0, "truth_method": "closed_form", "note": "..."}
  ],
  "weak_comparisons_excluded": 0
}
```

## 环境与约束

- 复用 `algorithms/q1q2/.venv`（已含 numpy/matplotlib/pytest）。独立真值可用 `fractions`/`decimal`（标准库）；如需 `mpmath`/`scipy` 装进本 venv 并写进本目录的 `requirements-bench.txt`，不改生产 `requirements.txt`。
- **不修改任何生产代码**。benchmark 只读地调用生产 API。
- 真值代码与生产代码**不共享实现**（不能 import 生产的 diameter/circle/candidate 再当真值）。
- benchmark 的目的是**抓 bug**：要真的运行、要包含已知难例与退化例，如实报告 pass/fail，别只测正常路径。


## 边界与尺度修正的共同约束

- q1_circle_cover 的 scale_limit 包括坐标幅度 >1e6 米或非零特征 <1e-3 米；三点强制圆的特征必须包含三角形高度，不能只看边长。这是与绝对容差和病态放大相关的工程范围，不是 float64 的统一硬界。仅在该类接受 NUMERICAL_UNRESOLVED，返回 OK 仍检查原独立精确真值和原容差。
- q2_candidate 源/后验布尔探针按提交的浮点坐标使用原定义的严格开闭边界；解析世界见证的表示裕度不套到 API 布尔探针上。核心 IN/OUT、sector/four-disk 真值和见证检查不变。
- q2_worst_diameter 的 J 分档与采样契约分别报告。有限点云下界被满足不构成连续 J 上界证明；采样不嵌套不能误报为 J 低估，也不能因此删除已有嵌套检查。
- q1_geometry 顶点归一化及顶点集检查本次不改，由生产侧任务处理。
