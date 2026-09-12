# 敏感性分析：论文表格与结论段落草稿

本稿只供父 agent 选取并入正文；所有长度单位为米，时间为秒。下述 J_hat 是最坏物理后验直径的数值估计，R_hat 为代表合法反馈的条件最小覆盖半径估计，r_U 为经浮点残差检查的保守外包覆盖半径；条件 R_hat 不等同于最坏半径目标 J_R。

## 角界与最近舍入外包（S1）

| 场景 | 1°默认 J_hat | 旧 q 保收 | 1.005°固定旧 q | 1.005°重新选点 | 重新选点坐标 |
| --- | --- | --- | --- | --- | --- |
| standard | 129.741396 | IN | 130.322388 | 130.322388 | [750.0, -500.0] |
| ordinary | 132.958744 | IN | 133.551885 | 133.551885 | [324.9999999999998, 824.9999999999998] |
| tangent | 19.929646 | IN | 20.054749 | 20.054749 | [1500.0, 500.0] |

三个场景分别覆盖跨0°、普通交会及目标圆近切边。1.005°仅表示“潜在误差不超过1°后最近舍入到0.01°”的连续外包，未实现精确量化模型。表中先列旧点的保收判定；若旧点失效，则不比较其目标值。角界增幅不能直接解释为目标值增幅，表中数值还受有限候选与源分辨率限制。

## 条件覆盖与形状（S2）

| 场景 | 代表反馈 | J_hat | 条件 R_hat | r_U | 20m 三态 | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| standard_default | direction | 129.741396 | 64.870698 | 64.870698 | NOT_YET_GUARANTEED | impossible_pair |
| ordinary_default | direction | 132.958744 | 66.479372 | 66.479372 | NOT_YET_GUARANTEED | impossible_pair |
| tangent_default | direction | 19.929646 | 9.964823 | 10.390906 | MOVE_TO_COVER_CENTER | outer_polygon_float64_checked |
| edge_default | direction | 119.147871 | 59.573935 | 59.573935 | NOT_YET_GUARANTEED | impossible_pair |
| standard_S1 | direction | 130.322388 | 65.161194 | 65.161194 | NOT_YET_GUARANTEED | impossible_pair |
| ordinary_S1 | direction | 133.551885 | 66.775943 | 66.775943 | NOT_YET_GUARANTEED | impossible_pair |
| tangent_S1 | direction | 20.054749 | 10.027375 | 10.469389 | MOVE_TO_COVER_CENTER | outer_polygon_float64_checked |
| 标准B=10轴向终选对照（未获选） | near | 1485.004589 | 5.000000 | 5.000000 | ON_SITE | near_analytic |

直径同为36 m时，等边三角形的最小覆盖半径为 20.784610 m，超过20 m；线段的最小覆盖半径为18 m，可以由一个落点覆盖。这说明直径小于40 m不足以单独保证统一清除。三态中的 NOT_YET_GUARANTEED 还需区分已有合法点对/三点不可清除见证与仅证据不足；本表以 evidence 列作此区分。

## 半径信息与行动域（S3/S4）

| 场景 | 半径信息 | 旧 q 状态 | 固定旧 q J_hat | 重新选点 J_hat | 实际移动/m |
| --- | --- | --- | --- | --- | --- |
| standard | 未知[1000,1500] | 默认IN | 129.741396 | 129.741396 | 901.387819 |
| edge | 未知[1000,1500] | 默认IN | 119.147871 | 119.147871 | 1044.030651 |
| standard | 1000 | IN | 55.021304 | 55.021304 | 901.387819 |
| standard | 1250 | IN | 83.250780 | 83.250780 | 901.387819 |
| standard | 1500 | IN | 129.741396 | 129.741396 | 901.387819 |
| edge | 1000 | IN | 114.392138 | 67.761003 | 969.619235 |
| edge | 1250 | IN | 114.392138 | 84.701254 | 1212.024046 |
| edge | 1500 | IN | 119.147871 | 119.147871 | 1044.030651 |

已知ρ同时改变首测外径和每个一致世界的最小允许接收半径，因而重新建立F和保收候选域。其性能变化反映额外信息的价值，不能据此称未知半径方法失效。首站(2900,0)、朝西时，ρ=1000与首次direction不一致，模型为空，标为不可用；ρ=1250/1500仍有一致源点。标准场景的S本身属于C_sig，而源点(1499,0)距S超过1000，直接否定“对所有源统一取1000圆盘交”的错误替代。

| 行动域 | 旧 q 状态 | 固定旧 q J_hat | 重新选点 J_hat | 实际移动/m | 重新选点坐标 |
| --- | --- | --- | --- | --- | --- |
| 附件允许域外 | 默认 | 119.147871 | 119.147871 | 1044.030651 | [850.0, -300.0] |
| 人为 q∈A | IN | 119.147871 | 119.147871 | 1044.030651 | [850.0, -300.0] |

在首站(1850,0)的边缘场景，附加域内限制在同一已保存候选总体中排除 46/2090 个原可行点，并排除首站S。该计数为有限候选损失，不是候选域面积比例；域内限制是消融，不表示题面规则含糊。

## 数值变化与排序（S7）

| 扰动 | 样本数 | 固定旧 q 状态 | 固定旧 q J_hat | 该池重新选点 | 该池最小选择值 |
| --- | --- | --- | --- | --- | --- |
| source_0 | 81 | IN | 34.973623 | [750.0, -475.0] | 34.973623 |
| source_1 | 258 | IN | 80.670261 | [750.0, -475.0] | 80.670261 |
| source_2 | 903 | IN | 106.306566 | [750.0, -475.0] | 106.306566 |
| shifted | 1318 | IN | 120.105498 | [750.0, -475.0] | 120.105498 |
| tolerance_0.1 | 903 | IN | 106.306566 | [750.0, -475.0] | 106.306566 |
| offset_0.1 | 903 | IN | 106.306566 | [750.0, -475.0] | 106.306566 |
| tolerance_10.0 | 903 | IN | 106.306566 | [750.0, -475.0] | 106.306566 |
| offset_10.0 | 903 | IN | 106.306566 | [750.0, -475.0] | 106.306566 |

源三级、容差和边界偏移各次均在各自统一池内重选，上表不是用不同精度给同一组候选混合排名。固定旧点相对于无增强第三级源池的最大变化分别为：delta_source=71.332943 m, delta_tol=0.000000 m, delta_offset=0.000000 m, delta_shift=13.798932 m。接触点/点对细化带来的公共终选变化另属数值补采，不与物理模型变化合并。

| 站点阶段 | 统一终选 J_hat | q |
| --- | --- | --- |
| grid_50 | 129.741396 | [750.0, -500.0] |
| grid_25 | 133.371777 | [750.0, -475.0] |
| local_and_shifted_station | 129.741396 | [750.0, -500.0] |

相同终选精度下站点阶段变化 Δ_station=3.630381 m；50/25m阶段粗评分到终评的严格排序翻转 0 次（两个网格优胜点的粗评分相等，终评后打破平局）。

| tie 倍数 | 阈值/m | 固定旧点 J_hat | 重新选点 J_hat | 实际移动/s | q |
| --- | --- | --- | --- | --- | --- |
| 0.0 | 0.000000 | 129.741396 | 129.741396 | 180.277564 | [750.0, -500.0] |
| 0.5 | 0.050000 | 129.741396 | 129.741396 | 180.277564 | [750.0, -500.0] |
| 1.0 | 0.100000 | 129.741396 | 129.741396 | 180.277564 | [750.0, -500.0] |
| 2.0 | 0.200000 | 129.741396 | 129.741396 | 180.277564 | [750.0, -500.0] |

对称候选的坐标无需唯一，微小排序变化也不等于物理结论翻转。上述变化只描述已执行的采样和有限候选审计，不能作为连续最坏值的误差保证。原搜索的稳定状态与停止原因见T6；不能把补充终评写成全域收敛。

## 信息裁剪（S8，复用F11）

| 场景 | 加入信息 | 状态 | d估计/外包 | R估计/外包 | 计算口径 |
| --- | --- | --- | --- | --- | --- |
| standard_default | P | POLYGON | 129.741396 | 64.870698 | exact wedges |
| standard_default | P_intersect_A | POLYGON | 129.741396 | 64.870698 | 64-side tangent outer estimate |
| standard_default | plus_receiving_disks | POLYGON | 129.741396 | 64.870698 | 64-side tangent outer estimate |
| standard_default | exclude_both_5m_disks | SAMPLE_AND_OUTER | 129.741396 | 64.870698 | nonconvex K sample lower estimates; r_U conservative outer; open disks not polygon clipping |
| ordinary_default | P | POLYGON | 132.958744 | 66.479372 | exact wedges |
| ordinary_default | P_intersect_A | POLYGON | 132.958744 | 66.479372 | 64-side tangent outer estimate |
| ordinary_default | plus_receiving_disks | POLYGON | 132.958744 | 66.479372 | 64-side tangent outer estimate |
| ordinary_default | exclude_both_5m_disks | SAMPLE_AND_OUTER | 132.958744 | 66.479372 | nonconvex K sample lower estimates; r_U conservative outer; open disks not polygon clipping |
| tangent_default | P | POLYGON | 44.175405 | 22.087702 | exact wedges |
| tangent_default | P_intersect_A | POLYGON | 20.781811 | 10.390906 | 64-side tangent outer estimate |
| tangent_default | plus_receiving_disks | POLYGON | 20.781811 | 10.390906 | 64-side tangent outer estimate |
| tangent_default | exclude_both_5m_disks | SAMPLE_AND_OUTER | 19.929646 | 9.964823 | nonconvex K sample lower estimates; r_U conservative outer; open disks not polygon clipping |
| same_station_unbounded_control | P | UNBOUNDED | 无界 | 无界 | exact wedges |
| same_station_unbounded_control | P_intersect_A | POLYGON | 1800.274190 | 900.274211 | 64-side tangent outer estimate |
| same_station_unbounded_control | plus_receiving_disks | POLYGON | 1500.228492 | 750.228509 | 64-side tangent outer estimate |
| same_station_unbounded_control | exclude_both_5m_disks | SAMPLE_AND_OUTER | 1495.003056 | 747.615393 | nonconvex K sample lower estimates; r_U conservative outer; open disks not polygon clipping |

主导约束：standard_default：angular constraints dominate within tangent-outer resolution; ordinary_default：angular constraints dominate within tangent-outer resolution; tangent_default：P_intersect_A; same_station_unbounded_control：arena makes P bounded; receiving disks further reduce finite outer bound。

重复首站读数控制例的纯角锥P无界，加入目标域后成为有限集合；该变化按状态报告，不计算百分比。接收圆加入前后可比较同精度外包，排除5 m圆后的非凸集合仅报告合法源样本估计与独立r_U，不能把口径差当作排除圆的精确贡献。问题一始终只求纯角锥P。

## 预算与实际成本（S9，复用F9）

| 场景/预算B(m) | 固定旧 q 可行性 | 固定旧 q J_hat | 重新选点 J_hat | 实际移动/s | 条件 R_hat | r_U | 三态 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| F9_B10 | OUT | 未评估 | 1371.576477 | 1.999998 | 685.788238 | 685.788238 | NOT_YET_GUARANTEED |
| F9_B200 | OUT | 未评估 | 511.262117 | 39.999999 | 255.631058 | 255.631059 | NOT_YET_GUARANTEED |
| F9_B600 | OUT | 未评估 | 207.200320 | 119.999998 | 103.600160 | 103.600160 | NOT_YET_GUARANTEED |
| F9_tangent_B200 | OUT | 未评估 | 112.575948 | 39.999999 | 56.287974 | 58.706405 | NOT_YET_GUARANTEED |
| F9_tangent_B400 | OUT | 未评估 | 50.640939 | 79.999999 | 25.320469 | 26.327323 | NOT_YET_GUARANTEED |
| F9_tangent_B500 | OUT | 未评估 | 35.603478 | 100.000000 | 17.801739 | 18.483755 | MOVE_TO_COVER_CENTER |

本表旧点 OUT 均由移动预算排除，保收判定仍为 IN；行动不可行与失去保收资格分开记录于CSV。

现有近切边场景补充 B=200/400/500 m，重点观察条件覆盖半径20 m附近；是否跨过门槛须同时检查 R_hat 和 r_U，不能只用 J_hat/2 判断。

移动速度保持5 m/s，实际移动秒数由所选点距离计算，不能以预算直接替代；测量另需5 s，求解器墙钟时间不计入虚拟行动时间。只有标准场景B=10 m对应的长点对解析控制标注 V(10)≥1000 m，它不是最优值，也不推广到其他场景。tie敏感性复用S7；预算间已累计候选并用同一物理模型公共池重评；其数值曲线仍不代表连续全局最优值。

本次代表场景中，标准场景角界外包扩大后，旧点仍保收，统一终评 J_hat 从129.741396 m变为130.322388 m；额外已知ρ=1000 m时同点估计为55.021304 m。近切边场景的纯角锥直径为44.175405 m，目标域约束使切线外包直径降至20.781811 m，体现了目标域信息的作用。预算从400 m增至500 m时，该场景代表反馈的条件 R_hat 从25.320469 m降至17.801739 m，后者的 r_U=18.483755 m，支持移动到覆盖圆心后清除；这不能推广为所有合法反馈均可一次清除，也不能据此认定500 m为最小预算。

数值层面，未增强源三级评分存在71.332943 m的变化，且粗评分平局在统一终评后被打破。因此，本次结果可作为有限候选上的模型对照与行动证据，尚不足以给出连续最坏目标的误差保证或宣称搜索稳定。

S5（冻结误差场）和S6（仅direction候选限制）为选做，本次未执行。1.01°压力与精确量化亦未执行。未完成的终选审计、覆盖预算门槛尚未精确定位，均保留为数值局限。
