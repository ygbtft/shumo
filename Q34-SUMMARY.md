# Q3、Q4 当前方案与材料

当前两题采用第二次正式测试方案，配置以[B/bounded_candidates.py](B/bounded_candidates.py)为准。

- Q3：最近邻任务排序，65米试清门限，主定位预算2轮，share_limit=6，localization_weight=0.08，remainder_weight=1.5。
- Q4：最近邻任务排序，35米试清门限，fraction=0.15，share_limit=6，share_cooldown=150，transverse_m=40，steps=10，pause_limit=16。

[运行说明](B/Q34_CURRENT.md) · [论文素材和四张实验表](writing-kit/kit-q34.md) · [当前数学模型](models/q34/modeling-q34.md) · [整理核验](B/cleanup_formal2/REPORT.md)

消融和参数实验基准为上述方案的官方演练数据：Q3共10局，Q4原消融10局；Q4另5局同配置复测单列。逐局等权算术平均，程序时间统一取官方进入/退出时间戳。第二次正式单局成绩用于核对版本，不混入演练均值。

旧论文统计与旧正式运行包已清理；原始实验日志供审计。不同方案使用不同官方案例，表中差异为描述性比较，不能据此宣称全局最优。
