# Q3、Q4 当前维护命令

在B目录执行；项目已有Python依赖环境为`../mock/.venv/bin/python`。

```sh
../mock/.venv/bin/python -B run_q34_official.py --problem 3 --check-config
../mock/.venv/bin/python -B run_q34_official.py --problem 4 --check-config
python3 package_robot.py
python3 experiments/paper_materials/2026-09-13_formal2_baselines/build_tables.py
```

官方会话命令及程序计时定义见[Q34_CURRENT.md](Q34_CURRENT.md)。准确逐指令回放应使用原Windows/Python环境运行`verify_q34_formal2_replay.py`，需要相对位置相同的已归档日志；不同平台浮点运算可能改变Q4对称探针的先后顺序。
