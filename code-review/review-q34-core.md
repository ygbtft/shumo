# Q3/Q4 几何、定位与覆盖核心只读审计

审计日期：2026-09-11。代码根目录：`/Users/flower/math/2026/B题/B/`。本报告所有 `文件:行号` 相对此目录，按本轮实读版本定位。仅新增本报告，没有修改被审代码、实验档案或注释，没有调用官方接口。

## 结论与证据范围

**未发现足以阻断当前 `range_area7` / `range_grid21_29` 主候选的 P1 错误。发现若干可复现的 P2 辅助验证/接口边界缺陷，其中最应先修的是整数验证器依赖 assert、回放包含检查遗漏退化区域、mock 幂等检查与执行之间的竞态。** 不把这些局部反例写成“七站/二十一站覆盖不成立”。

既有审计根目录为 `/Users/flower/math/2026/B题/models/q1q2/peer-audit/q34/`。已读其中 `audit-coverage-search.md`、`audit-directional.md`、`audit-localize-clear.md` 等审计材料，及实际位于仓库上一级的 `/Users/flower/math/2026/B题/Q34-SUMMARY.md`。逐行阅读指定八个文件，并针对调用关系补读七站布局、21站验证入口、负反馈/成对探测的相关实现。

- `visibility_certificate.verify_cells` 已检查分区、拒绝弱几何，并明确不提供绑定布局的强保证；`partition_check` 已使用 `raise ValueError`。旧“删除绝大多数叶子仍通过”的发现**不再列为现存缺陷**。
- 新 `certify_layout_coverage` 明确要求整个根方形覆盖；这比题目所需的半径1800源圆盘覆盖更强。其拒绝旧圆盘证书是当前接口的有意行为，不能据此判主布局漏覆盖。
- 八文件中，负反馈裁剪的直接实现不在范围内：`geometry.clip/hull` 是其底层原语，`signal_minimax.reception_certificate` 是全向保收判据。不能把它们称为完整 Q4 负反馈算法。本轮补读关联文件核对数学前提，未重新审计所有策略继承链和整局时间上界。
- 级别：P1＝阻断当前交付；P2＝该修（含可信验证工具和明确接口缺陷）；P3＝简化、可读性或说明优化。每条另标“真 bug / 契约风险 / 风格 / 注释”，避免混淆。

### 本轮实际执行的验证

环境：从 B 目录使用 `../mock/.venv/bin/python -B`；pytest 禁用缓存插件，未运行会写实验/manifest 的 `main()`。

| 检查 | 实测结果与限度 |
|---|---|
| `pytest tests/test_visibility_certificate.py -q -p no:cacheprovider` | **10 passed, 37 subtests passed**，含11份旧布局证书回归 |
| Q3 七站解析半径 | `covering_radius(6,1140) = 992.689147149632m`，距1000m约7.31m |
| Q4 `grid21_29` 当前保存的浮点证书 | 21站、7420叶格；严格距离/凸包及分区检查通过；证书点集和保存路线点集精确相等 |
| Q4 `grid21_29` 重新生成整数证书 | `certify_integer_stations` 默认深度16，通过独立整数验证：6976叶格、18837分区节点 |
| Q4 闭相切备选 `closed21_3` | 整数独立验证通过：8348叶格、22533分区节点 |
| 合法定位反馈小检查 | 固定随机种子811，160个源、每源3次成功读数，交替±1°端点与两位四舍五入/向下取整；480次更新均包含真源，包含圆检查通过，160次光学网格覆盖真源；最大网格覆盖半径18.322895m |
| 错误/边界输入 | 下文记录了实际复现输出；几何回放退化缺陷用其原判定表达式复现，未执行完整档案回放 |

这些小验证不代表任意浮点病态的形式化证明，不重计历史数万局，也不新增官方成绩。

## 1. geometry.py

### G1 — `geometry.py:135–141` — P2，真 bug：枚举“独立裁判”可能返回不包住输入的圆

`minimum_circle_enumerated` 用 `distance <= radius + 1e-7` 接纳候选，随后直接返回候选原半径。输入 `[[0,0],[1e-8,0]]` 实测返回圆心 `[0,0]`、半径 `0`，但到第二点距离为 `1e-8`。这不是正确的包含圆；其最小圆半径应为 `5e-9`。

**建议：**选定候选后按全部输入顶点重算最大距离，至少保证外包；若要作为最小圆独立精度裁判，应进一步区分“判等容差”和真实包含半径。`minimum_circle` 的131行已有最终外包重算，枚举函数也要保留同类安全收尾。不要用这个反例宣称当前生产 MEC 已不包含真源；出错的是验证辅助函数。

### G2 — `geometry.py:190–203` — P2，参数契约缺陷：可选 step 能破坏光学兜底的20m承诺

文档承诺格心的半径小于20m，但任何 `step` 都被接受。对正方形 `[[0,0],[49,0],[49,49],[0,49]]`，`optical_cover(poly,0,step=50)` 实测只需一格、返回半径 `34.64823369235439m`，四角均不在其20m清除范围内。

**建议：**一次性竞赛核心直接固定28m，删除公开可调 `step`；如果确需保留实验变量，必须约束 `0 < step < 20*sqrt(2)`，并核对输出覆盖半径。默认28m正确，当前调用方也有检查，非当前漏清反例。不要为历史参数增加多个兜底分支。

### G3 — `geometry.py:48–82,101–132,190–203` — P2，注释缺口：补上保证链的关键口径

最该补的注释如下，解释约束而非逐句翻译：

- 53–62行：法向量约定为 `n·g <= b`；测向角是**测点指向源**；误差为零时前两平面仅限定整条直线，第三平面才保留前向射线。`normals[:2 if error_deg else 3]` 宜先写 `plane_count` 再切片。
- 74–81行：1800是源域半径、1500是成功接收距离上界；两者使用圆的**外切**多边形，不是内接近似；这里没有使用无信号反馈排除1000m圆，也没有建模未知天线朝向。
- 104–108、131行：近共线时允许牺牲最优性；最后按所有顶点重算半径，是清除/删测安全的关键，不可当重复计算删除。
- 195–202行：`basis` 的列是正交基，右乘完成世界坐标到局部坐标变换；28m意味着最坏格心距离 `28/sqrt(2)<20`；`1e-6` 是外放边界余量。

### G4 — `geometry.py:135–187,199–200` — P3，职责/语法简化

Q1 LP 分类、Q3/Q4有界外包、独立验证裁判混在同一核心文件。`halfplane_region/solve_bearings` 是其他题目的真实实现，**不是后向兼容空壳**，但可移至Q1专用模块，验证枚举移至检查辅助文件，更新真实调用方，不保留转发别名。不要误删Q3/Q4共用的 `bearing_planes/minimum_circle`。

199–200行嵌套推导式还包含蛇形奇偶分支；改成外层遍历行、选正序/逆序x轴、内层追加格心。15行的去重/转换也可拆为“转为Nx2、转tuple集合、排序”三步。NumPy向量化本身有明确数学含义，不建议全改成标量循环。

## 2. signal_minimax.py

### S1 — `signal_minimax.py:7–22` — P2，注释/适用域缺口，不是当前算法反例

判据 `d(q,g) <= max(1000,d(anchor,g))` 的逻辑正确：成功锚点给半径下界，距离优势的补集由仿射半平面裁剪，再验顶点距离。**保证只适用于全向源，且 anchor 必须是该源实际成功接收点，poly 必须包含源。** 模块标题和函数docstring没有把这些前提说全。

例如源在原点、朝东、半径1000，成功锚点 `(100,0)`、新点 `(-100,0)`：小邻域 `poly` 会让本函数返回 `guaranteed=True`，而Q4源在新点背向、实际收不到。这是跨模型误用的明确反例，不是本函数在全向前提下的 bug。

**建议：**名称改为 `omni_reception_certificate` 并直接更新调用，不留旧名字兼容别名；docstring写清三个前提。在16–20行注明 `difference = d(q,g)^2-d(anchor,g)^2`，为什么保留非负侧、为什么 `clip` 的外放只会保守拒绝。无需增加 `mixed` 参数和Q4分支。

### S2 — `signal_minimax.py:15–21,25–50` — P3，晦涩语法与魔法常数

多处一行组合赋值、条件与返回，把判据最重要的边界藏起来。例如15行应拆成位置比较、命名布尔量、返回；16行分别写 `normal`、`bound`、`distance_difference`；29、34、41、42、47行也应拆行。

`1e-5` 的距离平方余量与21行的米制距离余量量纲不同，不宜笼统命名同一个EPS。分别命名并说明量纲。`error_deg=1.01` 与 geometry 的常量同义，直接引用常量；不要保留两套“旧/新角误差模式”。

### S3 — `signal_minimax.py:38–50` — P2，注释缺口：这是成功反馈后的上界，不含 no_signal 分支

`worst=min(5,initial)` 为 near 分支；每个读数桶加半桶宽后裁角锥，包住这个桶内所有可能真读数。`min(initial,new_radius)` 的成立依据是：允许继续使用旧包含圆，两份圆各自都能覆盖相应后验，因此后验最优半径不超过二者较小值。

**建议：**明确“输入非空保守区域；上界条件于成功 reception；调用前必须有保收保证，或单独把无信号时的原半径加入最坏值”。不能把这个输出当成Q4任意下一测点的无条件收缩保证。`save_bins` 在 `q2_minimax_experiments.py` 确有诊断用途，不属于无依据的兼容冗余；若最终交付不保留该实验，才删除记录分支，不新增结果类。

本文件未发现全向有效输入、当前默认参数下的错误肯定保收反例。

## 3. coverage.py

### C1 — `coverage.py:7–17` — P2，真 bug：退化线段/三角形判交错误

- `segment_distance_origin([10,0],[10,0])` 的分母为0，实测返回 `nan` 并警告，正确距离为10。
- `triangle_intersects_disk([[10,0],[11,0],[12,0]],1)` 所有叉积为0，实测返回True，实际线段距原点至少10，和半径1圆不交。

**建议：**先判断线段长度平方为0，直接返回端点范数；三角形先判断退化，退化时检查三条线段距离，不能用“同号叉积”认定原点在内部。若只支持固定非退化格子，则把帮助函数收为私有并显式限定调用前提，勿再宣称通用判交。正常正边长三角格不产生这些退化输入，当前布局未受影响。

### C2 — `coverage.py:20–43` — P2，注释缺口：生成站点与覆盖认证不是同一件事

方格裁剪使用到**格子**的最短距离，保留相交格子的全部四顶点；三角格也保留全部顶点。必须注释“源受1800圆约束，测站可在圆外，不能再把域外顶点投影/删除”。补写当前Q4充分条件：方格 `sqrt(2)*h <=1000`、三角形 `side<=1000`（实际选参保留严格余量）。参数任取不自动获证。

**建议：**若最终只交付7/21站方案，把格子生成器移入离线布局实验；若还需对照则保留，文档去掉无条件“Certified”的暗示。这里的 `cropped` 是确有实验含义的选择，不应仅因为是布尔分支就定性为兼容旧接口。

### C3 — `coverage.py:46–78` — P3，语法/配置简化

47行改为“空路线直接返回0；计算含start的相邻差；累加范数”三步。对于最终固定流程，调用方应明确使用固定起点、自由终点的开放路线；第62行已有正确注释，应保留。

`optimized` 对比开关和30轮上限属于优化实验口径，不是路线正确性的保证。若删除旧对照入口，可以只留固定优化函数并同步删除开关调用；若仍需对照，应说明30轮仅限CPU，不保证2-opt局部最优。勿加策略类或路由工厂。

## 4. visibility_certificate.py

### V1 — `visibility_certificate.py:56–58` — P2，真 bug：未传接收半径，错误见证尚未修复

调用：

```python
rectangle_certificate([[1200,0],[1300,0],[1200,100]],
                      arena_radius=500, receive_radius=2000, max_depth=0)
```

实测返回源在原点、朝向0°、`reason='no_station_in_range'` 的见证；实际上三个站全在2000m内且朝东可接收。原因是58行调用 `directional_witness(p,c)`，使用默认1000m。

**建议：**竞赛固定半径1000，则删除生成器的任意接收半径参数及对应可变口径；若仍保留该实验参数，就传 `receive_radius=receive_radius`。这是旧审计B1仍存在的错误，错误限于返回的具体见证；`unresolved_cell` 本来不等于证明不覆盖，当前1000m主证书不受影响。

### V2 — `visibility_certificate.py:101–109` — P2，真 bug：允许tuple索引却按多维索引使用

101行明确接受 `ids` 为list或tuple；109行 `p[ids]` 对tuple解释为多维索引，而非行索引列表。使用现有测试的64格完整合法证书，仅令 `cells[0][3]=tuple(cells[0][3])`：原list版本验证通过，tuple版本实测 `IndexError: too many indices for array: array is 2-dimensional, but 4 were indexed`。

**建议：**统一证书JSON口径为list，删除tuple适配；或在读取时一次转为整数索引数组，随后保持单一类型。前者更符合一次性竞赛代码要求。不要增加异常捕获后重试另一套索引的兼容分支。

### V3 — `visibility_certificate.py:75–85`；`icra_final_checks.py:14–17,24–39` — P3，过度耦合：纯几何检查反向依赖整套实验入口

`verify_cells` 为取得 `partition_check`，延迟导入会再导入自己、策略构建器及 `icra_confirmation` 等实验模块。lazy import解决了循环导入时机，但没有消除职责反向依赖。纯证书核查因而依赖无关实验模块可导入。

**建议：**把分区函数直接移入 `visibility_certificate.py`，实验脚本从这里导入；更新调用方，不保留旧入口转发。无需为一段分区函数新建验证器类/工厂。距离与凸包验证方法不同的浮点、整数两套实现是有用交叉证据，不能为“去重复”合并成同一个几何谓词。

### V4 — `visibility_certificate.py:75–81,121–160` — P3，兼容冗余/保证口径简化

强接口的 `layout_points/route/problem/layout_problem` 全都不能省略，却声明默认None后又构建缺失项列表；两个problem参数也是重复的裸整数声明，不构成布局来源认证。

**建议：**这些参数改为必填keyword参数；如果保留固定Q4入口，只留一个问题类型校验，布局坐标和实际路线精确集合比较仍保留。弱检查继续明确其结论是“源圆盘分区及叶几何”，强检查明确是“整个根方形及上下文”，不要为兼容旧证书再增加隐式升级分支。

本轮实测主21站圆盘证书面积为 `10259338.824748993m²`，小于根方形 `12960000m²`，所以强接口按设计拒绝；这并不是主布局证书变坏。**完整根方形不是题目源域要求。** 若最终需要一个“题目覆盖通过”入口，应直接定义并绑定圆盘域，显式迁移调用方；不要把现在的更强接口悄悄改语义。当前 `Fraction` 面积检查有明确精确性用途，不属于炫技。

### V5 — `visibility_certificate.py:7–65` — P3，语法与注释

拆开9、12、14、38–41、47–48、55、60行的分号/一行条件。变量 `h` 注释为半边长；51行解释为“每条单位外法向下，矩形支撑函数的最坏值”，从而四角扩展到连续方块。10–16行的容差使见证搜索偏保守，`None` 只是没找到见证，不能当覆盖成功。`max_cells` 在成功叶/圆外分支不会立即截止，应称搜索失败预算的检查阈值，或统一在循环入口检查；不要把它称严格内存上界。

## 5. integer_visibility_certificate.py

### I1 — `integer_visibility_certificate.py:27–28,55,67–100` — P2，真 bug：优化模式下可以认证明显错误的覆盖

关键距离、三角形包含、分区、坐标整数性与int64安全前提全是assert。用如下明显错误的一格证书：

```python
points = [[-1,-1],[1,-1],[0,1]]
cert = dict(scale=1, covered=True, arena_radius=1800, receive_radius=1000,
            cells=[[0,0,1800,[0,1,2]]])
verify_integer_certificate(points, cert)
```

普通Python实测抛AssertionError；**`python -B -O` 实测返回** `verified_leaves=1, partition_nodes=1, independent_exact_corner_triangles=True, integer_partition=True`。三个原点附近站点显然无法接收根方形角点，验证仍宣称通过。

**建议：**所有影响“认证成功”的前提用显式if/raise，和已加固的浮点验证器保持一致。生成器27–28行尤其是int64溢出边界，不可删成注释。包含证明不能以启动Python时是否带 `-O` 为前提；若将来用 `-O` 发布，该项应升级为P1发布阻断。当前正常解释器与冻结合法证书的既有通过结果未被此反例推翻。

### I2 — `integer_visibility_certificate.py:64–70,80–100` — P2，契约风险：验证器没有固定竞赛域和索引口径

生成器只接受1800/1000和整数站点；验证器却直接信任证书的arena/receive字段，`scale` 仅上界检查，未显式要求正整数/有效二进制尺度，也没有像浮点验证器一样检查非空叶、正半宽及合法站点索引。实测半径1域、接收10、四个 `(±2,±2)` 站点的一格证书能通过。

**判定：**上述小域通过对“小域命题”本身是正确的，不是数学误证；风险是 `cover21_experiments.py:64–67` 直接把其返回当成竞赛连续覆盖核查，而没有同浮点路径等价的1800/1000检查。

**建议：**在验证器入口固定题设口径、有限整数点集、正有效尺度、非空正半宽叶子及有效索引，和生成器约束保持一致；不必为任意源域/半径再扩展一套配置。明确88行验证的是严格小于原接收半径，而非重验生成器的 `1e-5m` 内缩；若返回/报告要声称该余量获独立验证，应使用同一有理阈值复核。

### I3 — `integer_visibility_certificate.py:29–49,68–89` — P2，注释缺口：整数与浮点边界必须解释

29行说明统一放大尺度为何能使每层四叉划分保持整数；33行说明向下取整的是平方距离上限，所以不会纳入超距点；48行补矩形支撑函数与逆时针边的符号解释，强调闭凸包允许等号，对应闭180°接收边界。

68行必须明确为何转为Python int再做独立角点检查：这是无固定宽度溢出的整数运算；主生成器的NumPy int64依赖28行的界。不要为了统一写法把这两套都变成同一个NumPy谓词。

### I4 — `integer_visibility_certificate.py:11–22,71–89` — P3，语法/中间层简化

拆开 `lower=[];upper=[]`、while体、坐标解包与赋值。`leaves` 只存True却按字典维护，可直接用set表达。三角形组合仅在当前单元使用，可保留其列表以便四角复用，不必改成一次性迭代器（否则第二角可能已耗尽）。局部 `triangle_contains` 和独立行列式服务于独立验证，有实际价值，不建议为了“减少函数”内联成晦涩长表达式。

## 6. icra_final_checks.py

### F1 — `icra_final_checks.py:68–75` — P2，真 bug：回放的真源包含检查漏验点与线段端部

代码只验证非零长度边的半平面。实测同一表达式：

- `poly=[[0,0]], source=[100,100]`：没有有效边，直接跳过，误通过。
- `poly=[[0,0],[1,0]], source=[2,0]`：两条反向边只限定同一条直线，区间外的共线点仍误通过。

**建议：**显式分空集、点、线段、二维凸多边形。空集失败；点验距离；线段验投影参数范围和垂距；二维才验边半平面。这里是审计辅助程序漏报，未复现生产裁剪把源丢掉。旧审计另一个文件的退化包含问题不能代替本文件修复。

### F2 — `icra_final_checks.py:24–36` — P2，真 bug（直接调用的非法输入）：分区检查仍可能不终止

虽然遗漏分区已改raise，函数本身仍不验证 `r>0`、有限正半宽和非空叶。`partition_check(dict(arena_radius=0,cells=[[1,0,0,[]]]))` 在根 `(0,0,0)` 不断产生相同四个孩子：根不是叶、不在圆外、`h<minimum` 为False，永远不退出。本轮在独立子进程执行，1秒超时后终止；未让该循环长期运行。

**建议：**把有限正尺寸、非空叶及固定根域的检查放在分区函数入口；或将它收为只能由已验证入口调用的私有函数，并更新所有外部直接调用。经 `verify_cells` 进入时这些尺寸已被拒绝，所以这不是已加固入口的漏洞；不要重复宣称旧“部分叶通过”仍在。

### F3 — `icra_final_checks.py:59,63,74,85–105,115,121` — P2，真 bug/验证可靠性：其余成功判据仍依赖assert

分区检查加固不等于整个 `main` 加固。`-O` 下请求是否匹配、是否消耗完trace、区域包含、归档全清/计数/哈希等都跳过，却继续写 `passed=True` 和 `failed=0`。

**建议：**决定最终审计结论的assert全部换if/raise；这是失败时应立即中止的批处理脚本，直接抛错即可，不需要新的检查框架或多层结果类。未运行 `main()`，本条依据是Python对assert的确定语义及逐个源码位置，不声称已经重验所有归档。

### F4 — `icra_final_checks.py:42–46,78,91–92,117–126` — P3，职责/历史适配简化

- 78行在 `verify_cells` 内部已验分区后再次调用 `partition_check`，计算重复。统一从可信入口取得分区统计，删除重复调用，不能删掉唯一的分区验证。
- 91–92行对旧档案的两种文件名适配是真实历史数据差异；最终版本可在一张显式档案清单里直接给路径，删除按名称猜格式分支，不改旧档案、不新增兼容版本开关。
- 117行 `feedback_replays=40` 应从实际回放数量得出；当前循环看起来匹配40不等于以后修改SPECS仍匹配。
- `RecordedRegions` 的 `__setitem__` 隐式记录需要拆行并注释“在赋值时复制，防止以后原地修改污染证据”。这个类在 `mission_final_checks.py` 也复用，且用于不侵入策略地记录轨迹，**不是应无条件拍平的单次包装**。

## 7. intelligent.py

### T1 — `intelligent.py:17–18,39–42,54,72` — P2，真 bug：GA在单点/重复坐标上失败

实测 `genetic_route([[0,0]], population=8, generations=1)` 在选两个变异位置时报ValueError。`[[0,0],[0,0],[1,0]]` 同参数则AssertionError：18行按最近坐标反查原索引，把两个相同坐标映成同一个索引，破坏排列不变量。

**建议：**覆盖站点语义可直接在入口去重、统一空/单点返回；若需要保留重复访问，则从始至终按索引排序，不按坐标最近邻反查。最终主流程不用GA时，把整段移到离线优化模块，不在核心保留多个替代优化器。当前7/21站非退化、互异，此处不是主布局路径丢站反例。

### T2 — `intelligent.py:80–85,114–127,150–168` — P2，注释缺口：概率、代价与保证分清

- 83–84行两种全向充分证书可与signal模块判据建立明确关系：前者是廉价的两个全区域充分条件，后者允许不同位置由不同分支保收。不能直接用较强新判据替换旧判据后声称启发式轨迹不变；若统一，以新实验结果评估。
- 115–127行：半径在 `[lower,1500]` 上均匀、48个朝向等权是人为先验；没有可用朝向时乘0.5是经验回退。`mixed=True` 并未显式对“全向/定向源比例”作概率混合。补这些口径；其输出只准用于排序。
- 155–161行仅枚举三种误差，不是连续最坏误差证明；167行 `max_hypothesis_radius_m` 名称应继续保留hypothesis限定。near分支按后续清除后剩余误差0评分，不是说反馈给出了精确源位置。
- 163行费用只有移动/5+RF5秒，没有切频、clear和将来失收代价；需注明是同频道下一次测量的局部代理分数，不能称整局时间上界。时间权重的单位是米/秒。

### T3 — `intelligent.py:130–143,169–170` — P3，契约简化

`candidates=None` 的内部生成/外部传入两路若最终实验均不用外部候选，应删除该可选参数，统一由一个候选生成器提供。若保留，则明确非空合法区域/观测前提，且无合格候选时返回中心并**没有在本处重新核验**保收；建议返回明确无候选结果，让调用方走既有光学兜底，或对中心再证一次。没有用不相容于真实观测的任意多边形去冒充主流程反例。

### T4 — `intelligent.py:19–37,51–69,88–111` — P3，语法/封装

GA的 `length/polish` 闭包共享距离矩阵，复用多次且作用清楚，不必建类或机械搬为公开函数。把53行“抽三人锦标赛取排名最小者”拆成命名步骤；给精英8、0.35变异率、每10代抛光4条等参数注释实验用途。103–104行的候选过滤改为普通循环，命名“离当前点足够远”“不是已有测点”。若最终不保留GA，直接搬走该整段，比抽象出多算法工厂更合适。

## 8. simulator.py（本地 mock 世界）

### M1 — `simulator.py:192–205` — P2，真 bug：幂等缓存查询不在执行锁内，存在重复计费竞态

第一次查cache发生在取得锁之前。合法时序为：A查无缓存后暂停；同ID同内容重试B查无缓存、取得锁、执行、写缓存并释放；A恢复后取得锁，**不再查缓存便再次执行**。即使两个World.act实际串行，仍可重复执行。

本轮用只在A线程获取锁前等待的测试锁强制这个时序，实际两响应均HTTP200，第一次 `virtual_time_s=5`，第二次为10；`world.measures=2`、`commands=3`（含enter）。同ID应返回第一次响应，测量只能一次。

**建议：**在取得锁后再次核对缓存，或者把“查缓存/判断冲突/执行/写缓存”整体置于同一互斥区；同ID返回已存原响应，不再推进状态。保留World与Protocol的职责分离，不要为了拍平把解析、物理与幂等合成一个大函数。正常单线程调用不会触发，但mock用于网络重试测试，这项影响测试可信度；未指称官方模拟器也有这个错误。

### M2 — `simulator.py:16–22,98–110,208–209` — P2，注释缺口：朝向与反馈角单位不同

`Source.facing` 直接喂给sin/cos，单位是**弧度**；`svd_deg` 是检测点指向源的**角度**。关联 `mock.scenario_gen`/某些外部fixture使用角度朝向，不能无转换共享结构相似的数据。

**建议：**把字段改名 `facing_rad`，同步一次性更新本地调用/序列化，不保留 `facing` 与 `facing_deg` 自动猜单位的兼容层；或者至少在Source和序列化函数处明确单位。101行已有闭90°边界容差说明，保留；再解释“near仍受方向限制，clear不受方向限制”。这是可误用口径，不是当前一致内部调用的角度bug。

### M3 — `simulator.py:26–30,40–51,108–109` — P3，配置契约/简化

未知noise字符串静默退到hash；未知rounding静默当floor。比如拼错 `nearest` 不报错，会换误差模型。plus/minus/alternating/smooth/hash是实际对抗实验，不应一律称为兼容冗余。

**建议：**固定枚举入口显式拒绝未知值；最终若只保留某一mock配置，则直接删除其余实验选项和调用，而非保留“unknown自动兼容”。World的源唯一性、坐标与半径约束也宜用ValueError代替assert，避免优化模式构造不合法物理世界。这里不强加10–16源检查：单源fixture有明确测试用途。

### M4 — `simulator.py:53–55,67–110` — P2，注释缺口：精确时间账本

应明确微秒整数账本：每次移动按该段 `round(distance/5*1e6)`；检测加5秒及必要的1秒切频；clear成功5秒/失败3秒，并**不改变RF当前频道**；拒绝响应返回0不表示把World累计时间清零。

67行在动作开始前检查截止，允许已登记动作完成后超过虚拟上限，和附件2第129行“截止前登记的唯一动作允许完成”一致。**不把跨上限的最后动作列成时间bug。** 本地fixture不模拟身份/GUI/限流，文件头已经说明，不要求为本次审计扩建完整官方服务。

### M5 — `simulator.py:144–162,192–203` — P3，语法/资源口径

解析函数中的 `unique/bad_constant/depth` 是JSON合法性控制，重复键、非有限常量和嵌套深度各有用途，不建议“为了简单”删掉。拆开嵌套推导与一行返回即可；深度函数可普通遍历求最大值。

cache生命周期是单会话，每个唯一动作保留完整首响应，以支持重试。当前没有容量限制且文件头声明不模拟限流，不把理论上的无限请求当竞赛主策略内存bug。若把Protocol做长期复用服务，届时再定义会话释放/容量；本项目无须提前加LRU、版本适配或资源管理框架。

## 跨文件数学结论与建议执行顺序

1. **保留当前安全骨架。** 成功测向得到源位置凸外包；最终包含圆半径支持20m充分清除证书；Q4无信号不能单独推出距测点大于1000。负反馈凸包可能填回已排除点，这是保守损失信息，不是漏包。7站证明是全向最近站覆盖；21站证明是局部可接收站凸包包含源，处理闭180°任意朝向。
2. **先修可信验证与mock真缺陷：** I1、F1、F2、F3、M1；再修V1/V2和G1/C1/T1的辅助边界。P2不等于“当前主算法必错”。
3. **再统一参数和口径：**固定28m、固定1800/1000、明确全向保收/成功后验/源域圆盘与根方形的区别；只移除确实弃用的实验入口，不把有独立验证价值的两套谓词当重复代码合并。
4. **最后做纯可读性整理：**分号拆行、嵌套候选循环展开、常数命名并标量纲、分区函数解除实验入口循环依赖。不要趁注释任务更换启发式、调参或改布局坐标；这类改变会使既有轨迹与证书证据失配。

## 关键反例复现代码

从B目录执行；以下内容只读导入，不调用会写档案的main。

```bash
../mock/.venv/bin/python -B - <<'PY'
import numpy as np
from geometry import minimum_circle_enumerated, optical_cover
from coverage import segment_distance_origin, triangle_intersects_disk
from visibility_certificate import rectangle_certificate
from intelligent import genetic_route

p=np.array([[0.,0.],[1e-8,0.]])
c,r=minimum_circle_enumerated(p)
print('G1', c, r, np.linalg.norm(p-c,axis=1).max())
p=np.array([[0.,0.],[49.,0.],[49.,49.],[0.,49.]])
print('G2', optical_cover(p,0,step=50)[1])
print('C1 segment', segment_distance_origin(np.array([10.,0.]),np.array([10.,0.])))
print('C1 triangle', triangle_intersects_disk([[10.,0.],[11.,0.],[12.,0.]],1))
print('V1', rectangle_certificate([[1200,0],[1300,0],[1200,100]],
    arena_radius=500,receive_radius=2000,max_depth=0))
for p in ([[0.,0.]], [[0.,0.],[0.,0.],[1.,0.]]):
    try:
        genetic_route(p,population=8,generations=1)
    except Exception as e:
        print('T1', type(e).__name__, str(e))
PY
```

整数错误证书：分别去掉/保留 `-O` 对照，普通模式拒绝、优化模式误通过。

```bash
../mock/.venv/bin/python -B -O - <<'PY'
from integer_visibility_certificate import verify_integer_certificate
print(verify_integer_certificate([[-1,-1],[1,-1],[0,1]],dict(
    scale=1,covered=True,arena_radius=1800,receive_radius=1000,
    cells=[[0,0,1800,[0,1,2]]])))
PY
```

mock并发幂等的确定时序复现（无需网络）：

```python
import json, threading
from simulator import World, Protocol, Source
w=World([Source(1,100.,0.)]); p=Protocol(w)
base=dict(arena_id='default',robot_id='offline-robot')
p.dispatch('/enter',json.dumps(dict(base,request_id='enter')).encode())
raw=json.dumps(dict(base,request_id='same',position=dict(x=0.,y=0.),channel=1)).encode()
a_waiting=threading.Event(); b_done=threading.Event()
class ScheduledLock:
    def __init__(self): self.lock=threading.Lock()
    def acquire(self,blocking=False):
        if threading.current_thread().name=='A':
            a_waiting.set()
            if not b_done.wait(3): raise RuntimeError('schedule timeout')
        return self.lock.acquire(blocking=blocking)
    def release(self): self.lock.release()
p.lock=ScheduledLock(); result={}
def first(): result['A']=p.dispatch('/measure',raw)
t=threading.Thread(target=first,name='A'); t.start()
assert a_waiting.wait(3)
result['B']=p.dispatch('/measure',raw); b_done.set(); t.join(3)
print(w.measures, {k:v[1]['virtual_time_s'] for k,v in result.items()})
# 实测：2 {'B': 5.0, 'A': 10.0}；正确语义只能执行一次。
```

## 源码版本指纹

写报告后再次计算，八文件哈希均与读取时一致。审计读取时SHA256如下；便于父agent对照行号和辨认并行修改，不把本报告当作其他版本结论。

```text
geometry.py                       513bbabd4092b7aa98c1bee46380be2ca4ae3857232854d7cd87dcfeb835c9a6
signal_minimax.py                 b441bb73886c05d0272cc19fad0faa89a920b552734283dab0fb4a3805efc936
coverage.py                       35bcf544a6908eefcd7e98321216bea8f433d1fbe59feb26f34670c7e6e9949c
visibility_certificate.py         bc0012250816fd5da5bf74d8bcd921eb7a6940094f5d58a43cf9b17ecef89425
integer_visibility_certificate.py 571eaf8688657bc7f6916c30317aa8578fd77c5f313aa98c27131d78984526d8
icra_final_checks.py              affc1331ac851166975023984ee577746a3b4eeda8a7ad95ad18e45f504f0cb4
intelligent.py                    63aa0d5d05e6c8a893536f62ddb64517730a360ec5251068930203cf38100445
simulator.py                      ce436b0cbd51b8e0eb336447050383b1f7e7214627cf4782e5030b71da884a8a
```
