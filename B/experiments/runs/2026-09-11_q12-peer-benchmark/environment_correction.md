# 首次隔离环境遗漏mock依赖

首次仅复制models目录，而Q1/Q2生产几何与适配器依赖同一仓库mock.geometry/mock.strategy，导致pytest收集和四个runner均在导入阶段退出。没有执行任何benchmark案例。这是本次隔离环境搭建遗漏，不是生产算法错误。

完整原日志、命令和upstream_completion.json保留。现补齐同一提交的mock目录，未改models生产代码、真值或案例；在attempt-02另存新运行记录。仍只离线，不调用官方接口。
