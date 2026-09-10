from dataclasses import asdict, dataclass
from time import perf_counter

import numpy as np
from scipy.integrate import solve_ivp
from scipy.interpolate import PchipInterpolator
from scipy.sparse import coo_matrix
from scipy.special import expi

from data_io import inputs


@dataclass(frozen=True)
class Configuration:
    case: int = 3
    intervals: int = 512
    grid: str = "graded"
    axial_intervals: int = 0
    method: str = "BDF"
    rtol: float = 2e-9
    flux: str = "kirchhoff"
    plateau: str = "nominal"
    temperature_shift: float = 0.0
    moisture_shift: float = 0.0
    mass_transfer_scale: float = 1.0
    heat_transfer_scale: float = 1.0
    diffusivity_scale: float = 1.0
    radius_mode: str = "pchip"
    constant_air: bool = False


def make_grid(intervals, kind="graded"):
    base = np.linspace(0, 1, intervals + 1)
    positions = base if kind == "uniform" else 0.02 * base + 0.98 * (2 * base - base**2)
    faces = np.r_[0, (positions[1:] + positions[:-1]) / 2, 1]
    return positions, faces


class DryingModel:
    def __init__(self, config):
        self.config = config
        self.air, self.radii = inputs()
        self.radius_curve = PchipInterpolator(self.radii[:, 0], self.radii[:, 1])
        self.radial, self.radial_faces = make_grid(config.intervals, config.grid)
        self.radial_volumes = np.diff(self.radial_faces**2) / 2
        if config.axial_intervals:
            self.axial, self.axial_faces = make_grid(config.axial_intervals, "graded")
            self.axial_volumes = np.diff(self.axial_faces)
        else:
            self.axial = np.array([0.0])
            self.axial_faces = np.array([0.0, 1.0])
            self.axial_volumes = np.array([1.0])
        self.shape = (len(self.radial), len(self.axial))
        self.count = int(np.prod(self.shape))
        self.weights = (2 * self.radial_volumes[:, None] * self.axial_volumes[None, :]).ravel()
        self._prepare_jacobian()

    def radius(self, time):
        if self.config.case != 4 or self.config.radius_mode == "fixed":
            return 0.02
        if self.config.radius_mode == "linear":
            return float(np.interp(time, self.radii[:, 0], self.radii[:, 1]))
        return float(self.radius_curve(min(time, self.radii[-1, 0])))

    def boundary(self, time):
        config = self.config
        if time <= self.air[-1, 0] and not config.constant_air:
            return np.interp(time, self.air[:, 0], self.air[:, 1]), np.interp(time, self.air[:, 0], self.air[:, 2])
        plateau = {"nominal": (50.0, 0.05), "last": self.air[-1, 1:],
                   "tail_mean": self.air[self.air[:, 0] >= 10800, 1:].mean(axis=0)}[config.plateau]
        return plateau[0] + config.temperature_shift, plateau[1] + config.moisture_shift

    def properties(self, temperature, moisture):
        positive = np.maximum(moisture, 1e-10)
        if self.config.case == 1:
            density = np.full_like(moisture, 820.0)
            capacity = np.full_like(moisture, 2600.0)
            conductivity = np.full_like(moisture, 0.36)
            exponent = 0.89
            thermal_factor = np.full_like(moisture, 7e-9)
        elif self.config.case in (2, 3):
            density = 650 + 128 * moisture
            capacity = 1450 + 2736 * moisture / (moisture + 1)
            conductivity = 0.21 + 0.38 * moisture / (moisture + 1)
            exponent = 0.45
            thermal_factor = 2.4e-3 * np.exp(-3850 / (temperature + 273.15))
        else:
            density = 760 + 90 * moisture
            capacity = 1850 + 2150 * moisture / (moisture + 1)
            conductivity = 0.12 + 0.20 * moisture / (moisture + 1)
            exponent = 0.30
            thermal_factor = 4.2e-4 * np.exp(-3850 / (temperature + 273.15))
        thermal_factor *= self.config.diffusivity_scale
        potential = positive * np.exp(-exponent / positive) + exponent * expi(-exponent / positive)
        diffusivity = thermal_factor * np.exp(-exponent / positive)
        return density, capacity, conductivity, thermal_factor, potential, diffusivity

    def derivative(self, time, state):
        count = self.count
        temperature = state[:count].reshape(self.shape)
        moisture = state[count:2 * count].reshape(self.shape)
        density, capacity, conductivity, thermal, potential, diffusivity = self.properties(temperature, moisture)
        outside_temperature, outside_moisture = self.boundary(time)
        radius = self.radius(time)
        heat_exchange = 25 * self.config.heat_transfer_scale
        mass_exchange = 8e-7 * self.config.mass_transfer_scale
        heat_rate = np.zeros(self.shape)
        moisture_rate = np.zeros(self.shape)
        loss_rate = 0.0
        for axis in range(2 if self.config.axial_intervals else 1):
            positions = self.radial if axis == 0 else self.axial
            face_positions = self.radial_faces if axis == 0 else self.axial_faces
            lengths = radius if axis == 0 else 0.125
            values_temperature = np.moveaxis(temperature, axis, 0)
            values_moisture = np.moveaxis(moisture, axis, 0)
            values_conductivity = np.moveaxis(conductivity, axis, 0)
            values_thermal = np.moveaxis(thermal, axis, 0)
            values_diffusivity = np.moveaxis(diffusivity, axis, 0)
            values_potential = np.moveaxis(potential, axis, 0)
            heat_flux = np.zeros((len(positions) + 1, values_temperature.shape[1]))
            moisture_flux = np.zeros_like(heat_flux)
            geometric = face_positions[1:-1] if axis == 0 else np.ones(len(positions) - 1)
            conductance = geometric[:, None] / (np.diff(positions)[:, None] * lengths**2)
            harmonic_heat = 2 * values_conductivity[1:] * values_conductivity[:-1] / (values_conductivity[1:] + values_conductivity[:-1])
            heat_flux[1:-1] = conductance * harmonic_heat * np.diff(values_temperature, axis=0)
            if self.config.flux == "kirchhoff":
                face_thermal = np.sqrt(values_thermal[1:] * values_thermal[:-1])
                moisture_flux[1:-1] = conductance * face_thermal * np.diff(values_potential, axis=0)
            else:
                harmonic_mass = 2 * values_diffusivity[1:] * values_diffusivity[:-1] / (values_diffusivity[1:] + values_diffusivity[:-1])
                moisture_flux[1:-1] = conductance * harmonic_mass * np.diff(values_moisture, axis=0)
            heat_flux[-1] = heat_exchange * (outside_temperature - values_temperature[-1]) / lengths
            moisture_flux[-1] = mass_exchange * (outside_moisture - values_moisture[-1]) / lengths
            volumes = self.radial_volumes if axis == 0 else self.axial_volumes
            heat_rate += np.moveaxis(np.diff(heat_flux, axis=0) / volumes[:, None], 0, axis)
            moisture_rate += np.moveaxis(np.diff(moisture_flux, axis=0) / volumes[:, None], 0, axis)
            loss_rate -= 2 * float(moisture_flux[-1] @ (self.axial_volumes if axis == 0 else self.radial_volumes))
        return np.r_[(heat_rate / (density * capacity)).ravel(), moisture_rate.ravel(), loss_rate]

    def _prepare_jacobian(self):
        rows, columns = [], []
        radial_count, axial_count = self.shape
        for radial_index in range(radial_count):
            for axial_index in range(axial_count):
                column = radial_index * axial_count + axial_index
                neighbors = [(radial_index, axial_index), (radial_index - 1, axial_index),
                             (radial_index + 1, axial_index), (radial_index, axial_index - 1),
                             (radial_index, axial_index + 1)]
                for neighbor_radial, neighbor_axial in neighbors:
                    if 0 <= neighbor_radial < radial_count and 0 <= neighbor_axial < axial_count:
                        row = neighbor_radial * axial_count + neighbor_axial
                        for row_block in (0, 1):
                            for column_block in (0, 1):
                                rows.append(row + row_block * self.count)
                                columns.append(column + column_block * self.count)
                if radial_index == radial_count - 1 or (self.config.axial_intervals and axial_index == axial_count - 1):
                    rows.append(2 * self.count)
                    columns.append(self.count + column)
        self.jac_rows, self.jac_columns = np.asarray(rows), np.asarray(columns)
        radial_indices, axial_indices = np.indices(self.shape)
        colors = (radial_indices + 2 * axial_indices).ravel() % (5 if self.config.axial_intervals else 3)
        color_count = int(colors.max()) + 1
        colors = np.r_[colors, colors + color_count]
        self.jac_groups = []
        for group in range(2 * color_count):
            grouped_columns = np.flatnonzero(colors == group)
            selected = np.flatnonzero(np.isin(self.jac_columns, grouped_columns) & (self.jac_rows < 2 * self.count))
            self.jac_groups.append((grouped_columns, selected))

    def jacobian(self, time, state):
        baseline = self.derivative(time, state)
        steps = np.sqrt(np.finfo(float).eps) * np.maximum(np.abs(state), 1)
        entries = np.zeros(len(self.jac_rows))
        for columns, selected in self.jac_groups:
            perturbed = state.copy()
            perturbed[columns] += steps[columns]
            difference = self.derivative(time, perturbed) - baseline
            entries[selected] = difference[self.jac_rows[selected]] / steps[self.jac_columns[selected]]
        exchange = 8e-7 * self.config.mass_transfer_scale
        loss_derivative = np.zeros(self.shape)
        loss_derivative[-1, :] += 2 * exchange / self.radius(time) * self.axial_volumes
        if self.config.axial_intervals:
            loss_derivative[:, -1] += 2 * exchange / 0.125 * self.radial_volumes
        selected = self.jac_rows == 2 * self.count
        entries[selected] = loss_derivative.ravel()[self.jac_columns[selected] - self.count]
        return coo_matrix((entries, (self.jac_rows, self.jac_columns)), shape=(2 * self.count + 1,) * 2).tocsc()

    def run(self, end_time=None):
        started = perf_counter()
        initial = np.r_[np.full(self.count, 28.0), np.full(self.count, 2.55), 0.0]
        dry_run = end_time is None and self.config.case != 1
        horizon = end_time if end_time is not None else (1800 if self.config.case == 1 else 150 * 3600)

        def critical_event(time, state):
            return np.max(state[self.count:2 * self.count]) - 0.15

        critical_event.direction = -1
        critical_event.terminal = True
        options = dict(method=self.config.method, rtol=self.config.rtol, atol=self.config.rtol * 0.03,
                       jac=self.jacobian, max_step=120, dense_output=True)
        solution = solve_ivp(self.derivative, (0, horizon), initial, events=critical_event if dry_run else None, **options)
        if not solution.success:
            raise RuntimeError(solution.message)
        parts = [solution]
        critical_time = None
        stop_time = float(solution.t[-1])
        if dry_run:
            if not len(solution.t_events[0]):
                raise RuntimeError("在150小时内没有达到干燥阈值")
            critical_time = stop_time

            def safe_event(time, state):
                return np.max(state[self.count:2 * self.count]) - 0.14994

            safe_event.direction = -1
            safe_event.terminal = False
            tail = solve_ivp(self.derivative, (stop_time, stop_time + 3600), solution.y[:, -1], events=safe_event, **options)
            if not tail.success or not len(tail.t_events[0]):
                raise RuntimeError("无法认证四位小数下的严格达标时刻")
            stop_time = float(60 * np.ceil(tail.t_events[0][0] / 60))
            parts.append(tail)
        result = Simulation(self, parts, critical_time, stop_time)
        result.elapsed_seconds = perf_counter() - started
        return result


class Simulation:
    def __init__(self, model, parts, critical_time, stop_time):
        self.model = model
        self.parts = parts
        self.critical_time = critical_time
        self.stop_time = stop_time
        self.elapsed_seconds = 0.0

    def states(self, times):
        times = np.atleast_1d(np.asarray(times, dtype=float))
        if times.min() < 0 or times.max() > self.stop_time + 1e-7:
            raise ValueError("请求时刻超出已验证的积分范围")
        values = np.empty((2 * self.model.count + 1, len(times)))
        for index, part in enumerate(self.parts):
            selected = (times >= part.t[0] - 1e-8) & (times <= part.t[-1] + 1e-8)
            if index:
                selected &= times > self.parts[index - 1].t[-1]
            if selected.any():
                values[:, selected] = part.sol(times[selected])
        return values

    def profiles(self, times, distances_cm):
        times = np.asarray(times, dtype=float)
        distances = np.asarray(distances_cm) / 100
        output_temperature = np.full((len(times), len(distances)), np.nan)
        output_moisture = output_temperature.copy()
        surfaces = np.empty((len(times), 3))
        for start in range(0, len(times), 256):
            selected_times = times[start:start + 256]
            states = self.states(selected_times)
            if self.model.config.case != 4 or self.model.config.radius_mode == "fixed":
                temperature = states[:self.model.count].reshape(*self.model.shape, len(selected_times))[:, 0, :]
                moisture = states[self.model.count:2 * self.model.count].reshape(*self.model.shape, len(selected_times))[:, 0, :]
                output_temperature[start:start + len(selected_times)] = PchipInterpolator(self.model.radial, temperature, axis=0)(distances / 0.02).T
                output_moisture[start:start + len(selected_times)] = PchipInterpolator(self.model.radial, moisture, axis=0)(distances / 0.02).T
                surfaces[start:start + len(selected_times)] = np.c_[np.full(len(selected_times), 2.0), temperature[-1], moisture[-1]]
                continue
            for offset, time in enumerate(selected_times):
                radius = self.model.radius(time)
                positions = distances / radius
                valid = positions <= 1 + 1e-10
                temperature = states[:self.model.count, offset].reshape(self.model.shape)[:, 0]
                moisture = states[self.model.count:2 * self.model.count, offset].reshape(self.model.shape)[:, 0]
                output_temperature[start + offset, valid] = PchipInterpolator(self.model.radial, temperature)(np.minimum(1, positions[valid]))
                output_moisture[start + offset, valid] = PchipInterpolator(self.model.radial, moisture)(np.minimum(1, positions[valid]))
                surfaces[start + offset] = radius * 100, temperature[-1], moisture[-1]
        return output_temperature, output_moisture, surfaces

    def summary(self):
        times = np.unique(np.r_[np.linspace(0, self.stop_time, 1501), self.stop_time])
        sampled = self.states(times)
        count = self.model.count
        moisture = sampled[count:2 * count]
        final = moisture[:, -1]
        balance_error = np.max(np.abs(self.model.weights @ moisture + sampled[-1] - 2.55))
        density_initial = self.model.properties(np.array([28.0]), np.array([2.55]))[0][0]
        apparent_masses = []
        for index, time in enumerate(times):
            density = self.model.properties(sampled[:count, index], moisture[:, index])[0]
            apparent_masses.append((self.model.radius(time) / 0.02)**2 * float(self.model.weights @ (density / (1 + moisture[:, index]))) / (density_initial / 3.55))
        reshaped = moisture.reshape(*self.model.shape, len(times))
        return {
            "configuration": asdict(self.model.config), "elapsed_seconds": self.elapsed_seconds,
            "critical_time_s": self.critical_time, "stop_time_s": self.stop_time,
            "critical_time_h": None if self.critical_time is None else self.critical_time / 3600,
            "stop_time_h": self.stop_time / 3600,
            "final_max_moisture": float(final.max()), "final_surface_moisture": float(final.reshape(self.model.shape)[-1, 0]),
            "moisture_min": float(moisture.min()), "moisture_max": float(moisture.max()),
            "balance_error": float(balance_error),
            "radial_monotonicity_violation": float(max(0, np.diff(reshaped, axis=0).max())),
            "apparent_dry_mass_ratio_min": min(apparent_masses), "apparent_dry_mass_ratio_max": max(apparent_masses),
            "apparent_dry_mass_ratio_final": apparent_masses[-1],
            "nfev": sum(part.nfev for part in self.parts), "nlu": sum(part.nlu for part in self.parts),
        }
