"""Reference: conservative 2D continuous negative-half-cell response.

Model adapted from RFBniCS commit 8ad0b6414be39bea0b39dcb08b44abfcdff91b27.
MIT attribution is retained in the task environment. This implementation uses a
different spatial discretization, with sparse Newton solves and BDF2 stepping.
It never reads verifier data or writes a reward.
"""

import json
import math
import sys
import warnings

import numpy as np
from scipy.optimize._numdiff import approx_derivative, group_columns
from scipy.sparse import coo_matrix
from scipy.sparse.linalg import MatrixRankWarning, spsolve

F = 96485.33212
R = 8.314462618
Z = np.array([2.0, 3.0, 1.0, -1.0, -2.0])
NAMES = ("v2", "v3", "h", "hso4", "so4")


class InvalidInput(ValueError):
    pass


def number(value, lo, hi):
    if isinstance(value, bool) or not isinstance(value, (float, int)):
        raise InvalidInput("number required")
    x = float(value)
    if not math.isfinite(x) or not lo <= x <= hi:
        raise InvalidInput("number outside domain")
    return x


def validate(data):
    if not isinstance(data, dict):
        raise InvalidInput("object required")
    g, q, m, inlet, stages = (data[k] for k in
                             ("geometry", "flow", "material", "inlet_mol_m3", "stages"))
    if not all(isinstance(o, dict) for o in (g, q, m, inlet)):
        raise InvalidInput("object required")
    w = number(g["width_m"], 1e-4, 5e-4)
    h = number(g["height_m"], 2e-4, 1e-3)
    if not 1.0 <= h / w <= 3.0:
        raise InvalidInput("aspect")
    speed = number(q["mean_inlet_m_s"], 2e-7, 4e-6)
    number(q["inlet_beta"], -0.8, 0.8)
    number(q["permeability_m2"], 1e-12, 1e-9)
    number(q["viscosity_pa_s"], 1e-3, 8e-3)
    number(q["density_kg_m3"], 1000, 1400)
    number(q["fiber_diameter_m"], 5e-6, 2e-5)
    eps = number(m["porosity"], 0.55, 0.9)
    number(m["sigma_s_m"], 20, 10000)
    number(m["area_m_inv"], 5e3, 8e4)
    number(m["temperature_k"], 280, 330)
    number(m["formal_potential_v"], -0.5, -0.2)
    number(m["alpha"], 0.3, 0.7)
    number(m["k0_m_s"], 2e-8, 2e-6)
    diffusion = m["diffusivity_m2_s"]
    if not isinstance(diffusion, list) or len(diffusion) != 5:
        raise InvalidInput("diffusion shape")
    ds = [number(x, 1e-10, 1e-8) for x in diffusion]
    if speed * h / (min(ds) * eps ** 1.5) > 5.0:
        raise InvalidInput("Peclet")
    ci = [number(inlet[k], 50, 3000) for k in NAMES[:4]]
    number((2 * ci[0] + 3 * ci[1] + ci[2] - ci[3]) / 2, 50, 6000)
    if not isinstance(stages, list) or not 1 <= len(stages) <= 4:
        raise InvalidInput("stages")
    for stage in stages:
        if not isinstance(stage, dict):
            raise InvalidInput("stage object")
        number(stage["duration_s"], 0.5, 60)
        number(stage["current_a_m2"], -20, 20)


def hydraulics(data):
    g, f = data["geometry"], data["flow"]
    w, h = g["width_m"], g["height_m"]
    u, b, mu, k = (f[key] for key in
                   ("mean_inlet_m_s", "inlet_beta", "viscosity_pa_s", "permeability_m2"))
    wave = math.pi / w
    amplitude = b * math.tanh(wave * h) / wave
    probes = [mu / k * u * (h + amplitude * math.cos(wave * x))
              for x in (w / 4, 3 * w / 4)]
    power = mu / k * u * u * w * (h + b * b * math.tanh(wave * h) / (2 * wave))
    return {"inlet_pressure_pa": probes, "dissipation_w_m": power}


class Slab:
    def __init__(self, data, nx=16, steps_per_stage=40):
        self.data = data
        g, f, m = data["geometry"], data["flow"], data["material"]
        self.w, self.h = float(g["width_m"]), float(g["height_m"])
        self.nx = int(nx)
        self.ny = 2 * max(2, int(math.ceil(nx * self.h / self.w / 2)))
        self.size = self.nx * self.ny
        self.dx, self.dy = self.w / self.nx, self.h / self.ny
        self.steps_per_stage = int(steps_per_stage)
        self.trace = []
        self.eps = m["porosity"]
        self.area = m["area_m_inv"]
        self.thermal = R * m["temperature_k"] / F
        self.formal = m["formal_potential_v"]
        self.sigma = m["sigma_s_m"] * (1 - self.eps) ** 1.5
        self.diffusion = np.asarray(m["diffusivity_m2_s"], dtype=float)
        self.deff = self.diffusion * self.eps ** 1.5
        self.alpha = m["alpha"]
        self.k0 = m["k0_m_s"]
        ci = [data["inlet_mol_m3"][key] for key in NAMES[:4]]
        ci.append((2 * ci[0] + 3 * ci[1] + ci[2] - ci[3]) / 2)
        self.inlet = np.asarray(ci, dtype=float)
        self.electric_scale = max(1.0, F * self.area * self.k0 * max(ci[:2]))
        x = (np.arange(self.nx) + 0.5) * self.dx
        y = (np.arange(self.ny) + 0.5) * self.dy
        wave = math.pi / self.w
        xf = np.arange(self.nx + 1) * self.dx
        yf = np.arange(self.ny + 1) * self.dy
        speed0, beta = f["mean_inlet_m_s"], f["inlet_beta"]
        self.ux = (speed0 * beta * np.sin(wave * xf)[None, :]
                   * (np.cosh(wave * (self.h - yf[:-1]))
                      - np.cosh(wave * (self.h - yf[1:])))[:, None]
                   / (wave * self.dy * math.cosh(wave * self.h)))
        self.uy = speed0 * (1 + beta * np.cosh(wave * (self.h - yf))[:, None]
                           * np.diff(np.sin(wave * xf))[None, :]
                           / (wave * self.dx * math.cosh(wave * self.h)))
        vcx, vcy = self.velocity(x[None, :], y[:, None])
        speed = np.hypot(vcx, vcy)
        reynolds = f["density_kg_m3"] * speed * f["fiber_diameter_m"] / f["viscosity_pa_s"]
        self.kmr = 7 * self.diffusion[0] / f["fiber_diameter_m"] * reynolds ** 0.4
        self.kmo = 7 * self.diffusion[1] / f["fiber_diameter_m"] * reynolds ** 0.4
        self.pattern, self.groups = self.make_sparsity()

    def velocity(self, x, y):
        f = self.data["flow"]
        u, b = f["mean_inlet_m_s"], f["inlet_beta"]
        wave = math.pi / self.w
        arg = wave * (self.h - y)
        den = math.cosh(wave * self.h)
        vx = u * b * np.sin(wave * x) * np.sinh(arg) / den
        vy = u * (1 + b * np.cos(wave * x) * np.cosh(arg) / den)
        return vx, vy

    def make_sparsity(self):
        rows, cols = [], []
        n = self.size
        for iy in range(self.ny):
            for ix in range(self.nx):
                cell = iy * self.nx + ix
                neighbours = [cell]
                if ix:
                    neighbours.append(cell - 1)
                if ix + 1 < self.nx:
                    neighbours.append(cell + 1)
                if iy:
                    neighbours.append(cell - self.nx)
                if iy + 1 < self.ny:
                    neighbours.append(cell + self.nx)
                for rb in range(6):
                    row = rb * n + cell
                    if row == 6 * n - 1:
                        rows.append(row)
                        cols.append(row)
                        continue
                    for cb in range(6):
                        for other in neighbours:
                            rows.append(row)
                            cols.append(cb * n + other)
        pattern = coo_matrix((np.ones(len(rows)), (rows, cols)), shape=(6*n, 6*n)).tocsr()
        return pattern, group_columns(pattern)

    def unpack(self, flat):
        values = flat.reshape(6, self.ny, self.nx)
        c4 = 1000.0 * values[:4]
        sulfate = (2 * c4[0] + 3 * c4[1] + c4[2] - c4[3]) / 2
        c = np.concatenate((c4, sulfate[None, :, :]), axis=0)
        return c, values[4], values[5]

    def fields(self, flat, current):
        c, us, ul = self.unpack(flat)
        delta = us - ul
        aa = self.k0 * np.exp(np.clip(self.alpha * delta, -60, 60))
        bb = self.k0 * np.exp(np.clip(-(1 - self.alpha) * delta, -60, 60))
        denominator = 1 + aa / self.kmr + bb / self.kmo
        reaction = (aa * c[0] - bb * c[1]) / denominator
        surface_r = c[0] - reaction / self.kmr
        surface_o = c[1] + reaction / self.kmo
        fx = np.zeros((5, self.ny, self.nx + 1))
        fy = np.zeros((5, self.ny + 1, self.nx))
        cc = 0.5 * (c[:, :, 1:] + c[:, :, :-1])
        fx[:, :, 1:-1] = (self.ux[None, :, 1:-1] * cc
                          - self.deff[:, None, None] / self.dx *
                          (np.diff(c, axis=2) + Z[:, None, None] * cc * np.diff(ul, axis=1)[None]))
        cc = 0.5 * (c[:, 1:, :] + c[:, :-1, :])
        fy[:, 1:-1, :] = (self.uy[None, 1:-1, :] * cc
                          - self.deff[:, None, None] / self.dy *
                          (np.diff(c, axis=1) + Z[:, None, None] * cc * np.diff(ul, axis=0)[None]))
        fx[2, :, -1] = current / F
        inlet_gradient = (c[:, 0, :] - self.inlet[:, None]) / (self.dy / 2)
        phi_gradient = -(Z[:, None] * self.deff[:, None] * inlet_gradient).sum(axis=0)
        phi_gradient /= np.sum(Z**2 * self.deff * self.inlet)
        fy[:, 0, :] = (self.uy[0, :][None] * self.inlet[:, None]
                       - self.deff[:, None] *
                       (inlet_gradient + Z[:, None] * self.inlet[:, None] * phi_gradient[None]))
        fy[:, -1, :] = self.uy[-1, :][None] * c[:, -1, :]
        ilx = F * (Z[:, None, None] * fx).sum(axis=0)
        ily = F * (Z[:, None, None] * fy).sum(axis=0)
        sx = np.zeros((self.ny, self.nx + 1))
        sy = np.zeros((self.ny + 1, self.nx))
        sx[:, 0] = current
        sx[:, 1:-1] = -self.sigma * self.thermal / self.dx * np.diff(us, axis=1)
        sy[1:-1, :] = -self.sigma * self.thermal / self.dy * np.diff(us, axis=0)
        return c, reaction, surface_r, surface_o, fx, fy, sx, sy, ilx, ily

    def residual(self, flat, base, time_factor, current):
        c, r, _, _, fx, fy, sx, sy, lx, ly = self.fields(flat, current)
        divergence = np.diff(fx[:4], axis=2) / self.dx + np.diff(fy[:4], axis=1) / self.dy
        divergence[0] += self.area * r
        divergence[1] -= self.area * r
        species = (c[:4] - base + time_factor / self.eps * divergence) / 1000
        solid = (np.diff(sx, axis=1) / self.dx + np.diff(sy, axis=0) / self.dy + self.area * F * r)
        liquid = (np.diff(lx, axis=1) / self.dx + np.diff(ly, axis=0) / self.dy - self.area * F * r)
        result = np.concatenate((species.ravel(), solid.ravel() / self.electric_scale,
                                 liquid.ravel() / self.electric_scale))
        result[-1] = flat[-1]
        return result

    def newton(self, start, base, time_factor, current):
        x = start.copy()
        fun = lambda v: self.residual(v, base, time_factor, current)
        residual = fun(x)
        for _ in range(18):
            norm = np.linalg.norm(residual)
            if np.max(np.abs(residual)) < 3e-9:
                return x
            jacobian = approx_derivative(fun, x, method="2-point", abs_step=1e-6,
                                        f0=residual, sparsity=(self.pattern, self.groups))
            with warnings.catch_warnings():
                warnings.simplefilter("error", MatrixRankWarning)
                correction = spsolve(jacobian.tocsc(), -residual)
            if not np.all(np.isfinite(correction)):
                raise RuntimeError("nonfinite Newton correction")
            fraction = 1.0
            accepted = False
            for _ in range(14):
                trial = x + fraction * correction
                c, ps, pl = self.unpack(trial)
                if np.min(c) > 0.1 and np.max(np.abs(ps - pl)) < 35:
                    rr = fun(trial)
                    if np.all(np.isfinite(rr)) and np.linalg.norm(rr) < norm * (1 - 1e-4*fraction):
                        x, residual, accepted = trial, rr, True
                        break
                fraction *= 0.5
            if not accepted:
                raise RuntimeError("Newton line search")
        raise RuntimeError("Newton iteration limit")

    def initial(self):
        state = np.zeros((6, self.ny, self.nx))
        state[:4] = self.inlet[:4, None, None] / 1000
        state[4] = math.log(self.inlet[1] / self.inlet[0])
        return state.ravel()

    def evolve(self, flat, duration, current):
        elapsed = 0.0
        previous_concentration = None
        previous_step = None
        nominal = duration / self.steps_per_stage
        step = nominal
        failures = 0
        while elapsed < duration - 1e-12 * max(1, duration):
            step = min(step, duration - elapsed)
            old = self.unpack(flat)[0][:4].copy()
            if previous_step is None:
                base, factor = old, step
            else:
                ratio = step / previous_step
                coefficient = (1 + 2*ratio) / (1 + ratio)
                base = ((1 + ratio)*old - ratio**2/(1 + ratio)*previous_concentration) / coefficient
                factor = step / coefficient
            try:
                new = self.newton(flat, base, factor, current)
            except (RuntimeError, MatrixRankWarning):
                step *= 0.5
                failures += 1
                if failures > 12 or step < 1e-7:
                    raise
                continue
            previous_concentration, previous_step = old, step
            flat = new
            elapsed += step
            c, rr, csr, cso, *_ = self.fields(flat, current)
            _, ps, pl = self.unpack(flat)
            self.trace.append({"stage_time_s": float(elapsed), "step_s": float(step),
                               "min_bulk_mol_m3": float(c.min()),
                               "min_surface_mol_m3": float(min(csr.min(), cso.min())),
                               "max_abs_reduced_potential": float(np.max(np.abs(ps-pl))),
                               "summed_reaction_a_m": float(self.area*F*rr.sum()*self.dx*self.dy)})
            failures = 0
            step = min(nominal, step * 1.5)
        return flat

    def observe(self, flat, current, time):
        c, reaction, sr, so, _, _, _, _, _, _ = self.fields(flat, current)
        _, us, ul = self.unpack(flat)
        wall_c = c[:, :, -1]
        wall_flux = np.zeros((5, 1))
        wall_flux[2, 0] = current / F
        half = self.dx / 2
        numerator = wall_c - half * wall_flux / self.deff[:, None]
        gradient = -np.sum(Z[:, None] * wall_flux / self.deff[:, None], axis=0)
        gradient = np.broadcast_to(gradient, (self.ny,)).copy() / np.sum(Z[:, None]**2 * wall_c, axis=0)
        for _ in range(8):
            den = 1 + half * Z[:, None] * gradient[None]
            value = np.sum(Z[:, None] * numerator / den, axis=0)
            derivative = -half * np.sum(Z[:, None]**2 * numerator / den**2, axis=0)
            gradient -= value / derivative
        liquid_membrane = self.thermal * (ul[:, -1] + half * gradient)
        solid_collector = self.formal + self.thermal * us[:, 0] + current * half / self.sigma
        voltage = float(np.mean(solid_collector - liquid_membrane))
        volume_mean = c.mean(axis=(1, 2))
        flow_weighted = (c[:, -1, :] * self.uy[-1, :][None]).sum(axis=1) / self.uy[-1, :].sum()
        density = self.area * F * reaction
        mx, my = self.nx // 2, self.ny // 2
        quadrants = [density[:my, :mx], density[:my, mx:], density[my:, :mx], density[my:, mx:]]
        return {
            "time_s": float(time),
            "collector_voltage_v": voltage,
            "mean_mol_m3": {key: float(volume_mean[j]) for j, key in enumerate(NAMES)},
            "outlet_mol_m3": {key: float(flow_weighted[j]) for j, key in enumerate(NAMES)},
            "reaction_quadrants_a_m": [float(v.sum() * self.dx * self.dy) for v in quadrants],
            "surface_mean_mol_m3": {"v2": float(sr.mean()), "v3": float(so.mean())},
        }


def equilibrium(data):
    ci = [data["inlet_mol_m3"][key] for key in NAMES[:4]]
    ci.append((2*ci[0] + 3*ci[1] + ci[2] - ci[3]) / 2)
    m = data["material"]
    voltage = m["formal_potential_v"] + R*m["temperature_k"]/F*math.log(ci[1]/ci[0])
    time, states = 0.0, []
    for stage in data["stages"]:
        time += stage["duration_s"]
        states.append({
            "time_s": time, "collector_voltage_v": voltage,
            "mean_mol_m3": dict(zip(NAMES, ci)), "outlet_mol_m3": dict(zip(NAMES, ci)),
            "reaction_quadrants_a_m": [0.0]*4,
            "surface_mean_mol_m3": {"v2": ci[0], "v3": ci[1]},
        })
    return {"hydraulics": hydraulics(data), "states": states}


def solve(data, nx=16, steps_per_stage=40):
    try:
        validate(data)
    except (KeyError, TypeError, ValueError, OverflowError):
        return {"error": "invalid_input"}
    if all(stage["current_a_m2"] == 0 for stage in data["stages"]):
        return equilibrium(data)
    model = Slab(data, nx=nx, steps_per_stage=steps_per_stage)
    flat = model.initial()
    time, states = 0.0, []
    for stage in data["stages"]:
        current, duration = stage["current_a_m2"], stage["duration_s"]
        flat = model.evolve(flat, duration, current)
        time += duration
        states.append(model.observe(flat, current, time))
    return {"hydraulics": hydraulics(data), "states": states}


def main():
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError, TypeError):
        output = {"error": "invalid_input"}
    else:
        output = solve(data)
    json.dump(output, sys.stdout, allow_nan=False, separators=(",", ":"))
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
