import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LogNorm
import numpy as np

from data_io import CACHE, FIGURES, RESULTS, inputs


plt.rcParams.update({"font.family": ["Microsoft YaHei", "SimHei", "DejaVu Sans"],
                     "axes.unicode_minus": False, "font.size": 11,
                     "axes.spines.top": False, "axes.spines.right": False,
                     "savefig.facecolor": "white"})


def save(figure, name):
    FIGURES.mkdir(parents=True, exist_ok=True)
    figure.savefig(FIGURES / (name + ".png"), dpi=180, bbox_inches="tight")
    figure.savefig(FIGURES / (name + ".pdf"), bbox_inches="tight")
    plt.close(figure)


def load(name):
    return json.loads((RESULTS / name).read_text(encoding="utf-8"))


def main():
    production = load("production.json")
    air, radii = inputs()
    figure = plt.figure(figsize=(8.2, 5.6), layout="constrained")
    layout = figure.add_gridspec(2, 2)
    axes = [figure.add_subplot(layout[0, 0]), figure.add_subplot(layout[0, 1]), figure.add_subplot(layout[1, :])]
    axes[0].plot(air[:, 0] / 3600, air[:, 1], color="#2466A2")
    axes[0].axhline(50, color="#8E3434", linestyle="--", linewidth=1)
    axes[0].set(xlabel="时间（h）", ylabel="烘房温度（℃）", title="温度边界")
    axes[1].plot(air[:, 0] / 3600, air[:, 2], color="#2466A2")
    axes[1].axhline(0.05, color="#8E3434", linestyle="--", linewidth=1)
    axes[1].set(xlabel="时间（h）", ylabel="有效水分浓度（kg/kg）", title="传质边界")
    axes[2].plot(radii[:, 0] / 3600, radii[:, 1] * 100, ".-", color="#357B5B", markersize=3)
    axes[2].set(xlabel="时间（h）", ylabel="半径（cm）", title="实测收缩曲线")
    save(figure, "01_boundaries")
    for name, index in (("result1", "02"), ("result2", "03")):
        data = np.load(CACHE / (name + ".npz"))
        figure, axes = plt.subplots(1, 2, figsize=(8.2, 3.7), layout="constrained")
        for axis, field, label in zip(axes, ("temperature", "moisture"), ("温度（℃）", "含水率（kg/kg）")):
            plot = axis.pcolormesh(data["times"] / 3600, data["distances"], data[field].T, shading="auto", cmap="viridis", rasterized=True)
            figure.colorbar(plot, ax=axis, label=label)
            axis.set(xlabel="时间（h）", ylabel="距中心距离（cm）", title=label, ylim=(0, 2))
        save(figure, index + "_" + name + "_fields")
    figure, axes = plt.subplots(1, 2, figsize=(8.2, 3.7), layout="constrained")
    for name, color, label in (("result3", "#2466A2", "固定半径"), ("result4", "#BA6834", "实测收缩")):
        data = np.load(CACHE / (name + ".npz"))
        times = np.r_[0, data["times"]] / 3600
        axes[0].semilogy(times, np.r_[2.55, data["moisture"][:, 0]], color=color, label=label + " 中心")
        axes[0].semilogy(times, np.r_[2.55, data["surfaces"][:, 2]], "--", color=color, label=label + " 表面")
        end = production["summaries"][name]
        axes[1].plot(data["times"] / 3600, data["moisture"][:, 0], color=color, label=label)
        axes[1].scatter([end["critical_time_h"]], [0.15], color=color, zorder=4)
    axes[0].axhline(0.15, color="black", linestyle=":", label="干燥阈值")
    axes[0].set(xlabel="时间（h）", ylabel="含水率（kg/kg）", title="中心与表面干燥进程")
    axes[0].legend(fontsize=9.5)
    axes[1].axhline(0.15, color="black", linestyle=":")
    axes[1].set(xlim=(45, 60), ylim=(0.14, 0.18), xlabel="时间（h）", ylabel="最大含水率（kg/kg）", title="临界时刻附近")
    axes[1].legend(fontsize=9.5)
    save(figure, "04_drying_times")
    figure, axes = plt.subplots(1, 2, figsize=(8.2, 3.7), layout="constrained")
    for axis, name, title in zip(axes, ("result3", "result4"), ("第三问 固定半径", "第四问 收缩边界")):
        data = np.load(CACHE / (name + ".npz"))
        plot = axis.pcolormesh(data["times"] / 3600, data["distances"], np.ma.masked_invalid(data["moisture"].T), shading="auto", cmap="viridis", norm=LogNorm(0.05, 2.55), rasterized=True)
        if name == "result4":
            axis.fill_between(data["times"] / 3600, data["surfaces"][:, 0], 2.1, color="white", zorder=3)
            axis.plot(data["times"] / 3600, data["surfaces"][:, 0], color="black", linewidth=1.2, label="实测半径", zorder=4)
            axis.legend(fontsize=9.5)
        figure.colorbar(plot, ax=axis, label="含水率（kg/kg，对数色标）")
        axis.set(xlabel="时间（h）", ylabel="距中心距离（cm）", title=title, ylim=(0, 2))
    save(figure, "05_moving_boundary")
    convergence = load("convergence.json")
    figure, axes = plt.subplots(1, 2, figsize=(8.2, 3.7), layout="constrained")
    for case, color in ((1, "#2466A2"), (3, "#357B5B"), (4, "#BA6834")):
        records = [record for record in convergence if record["case"] == case and "moisture_difference" in record]
        axes[0].loglog([record["intervals"] for record in records], [record["moisture_difference"] for record in records], "o-", color=color, label=f"问题{case}")
        if case != 1:
            axes[1].loglog([record["intervals"] for record in records], [record["critical_time_difference_s"] for record in records], "o-", color=color, label=f"问题{case}")
    axes[0].axhline(5e-5, linestyle=":", color="black", label="半个末位单位")
    axes[0].set(xlabel="细网格子区间数", ylabel="相邻网格含水率最大差", title="输出采样位置的空间收敛")
    axes[1].set(xlabel="细网格子区间数", ylabel="相邻网格临界时间差（s）", title="达标事件的空间收敛")
    for axis in axes:
        axis.legend(fontsize=9.5)
        axis.grid(alpha=0.2)
    save(figure, "06_convergence")
    methods = load("method_comparison.json")
    figure, axis = plt.subplots(figsize=(8, 3.8), layout="constrained")
    for flux, color, label in (("harmonic", "#BA6834", "普通调和平均"), ("kirchhoff", "#2466A2", "积分势通量")):
        records = [record for record in methods if record["configuration"]["grid"] == "uniform" and record["configuration"]["flux"] == flux]
        axis.plot([record["configuration"]["intervals"] for record in records], [record["critical_time_h"] for record in records], "o-", color=color, label=label)
    axis.set(xlabel="均匀径向子区间数", ylabel="第三问临界时间（h）", title="相同模型与网格下的通量方法对照")
    axis.legend()
    axis.grid(alpha=0.2)
    save(figure, "07_flux_comparison")
    sensitivity = load("sensitivity.json")
    figure, axes = plt.subplots(1, 2, figsize=(8.5, 3.8), layout="constrained")
    pairs = [("air_T_minus1", "air_T_plus1", "平台温度 ±1℃"),
             ("air_C_minus_001", "air_C_plus_001", "平台水分 ±0.001"),
             ("mass_transfer_minus10pct", "mass_transfer_plus10pct", "传质系数 ±10%"),
             ("diffusivity_minus10pct", "diffusivity_plus10pct", "扩散系数 ±10%")]
    for axis, case in zip(axes, (3, 4)):
        subset = {record["name"]: record["critical_time_h"] for record in sensitivity if record["configuration"]["case"] == case}
        for row, (lower, upper, label) in enumerate(pairs):
            axis.plot([subset[lower] - subset["baseline"], subset[upper] - subset["baseline"]], [row, row], "o-", linewidth=6, markersize=5, color="#2466A2")
        axis.axvline(0, color="black", linewidth=1)
        axis.set_yticks(range(len(pairs)), [entry[2] for entry in pairs])
        axis.set(xlabel="临界时间相对基准的变化（h）", title=f"问题{case} 单因素扰动")
    save(figure, "08_sensitivity")
    axial = load("axial_comparison.json")
    figure, axes = plt.subplots(1, 2, figsize=(8.2, 3.7), layout="constrained")
    for axis, case in zip(axes, (3, 4)):
        record = next(record for record in reversed(axial) if record["summary"]["configuration"]["case"] == case)
        plot = axis.pcolormesh(record["axial_cm"], record["radial_cm"], np.asarray(record["moisture_at_critical"]), shading="auto", cmap="viridis", rasterized=True)
        figure.colorbar(plot, ax=axis, label="含水率（kg/kg）")
        axis.set(xlabel="距轴向中面距离（cm）", ylabel="距轴线距离（cm）", title=f"问题{case} 二维临界场")
    save(figure, "09_axial_check")
    print("Created 9 figure pairs", flush=True)


if __name__ == "__main__":
    main()
