# 适配器字段说明

`our_results/q1_circle_cover.json` 的 `diameter_circle_contains_by_existing_analysis_tolerance` 字段名不准确：它是本轮适配器从最远点对中点及点集计算的辅助诊断，使用绝对距离余量 1e-7 m，并非既有生产 API 返回的覆盖结论。本轮 PASS 只计原生圆心、半径、包含性、直径，以及存在测向输入时的区域流水线结果；该字段没有计入 PASS。

原始执行代码和 JSON 保留，以便复现。本轮不把该辅助布尔值当作精确 Thales 判定、独立覆盖状态 API 或“直径圆一定覆盖”的依据。完整支持索引、强制三点圆、数值未决状态等接口仍明确记为未覆盖。
