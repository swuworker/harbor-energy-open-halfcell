# Open negative half-cell: inlet distribution and galvanostatic response

Implement `python /app/src/halfcell.py`. The command reads one JSON object from stdin and writes one JSON object to stdout. You may modify all of `/app/src/`. NumPy 2.2.6 and SciPy 1.15.3 are installed. Implement the continuous physical model below; any numerical method meeting the observable error contract is accepted.

Each request runs in a fresh process with a 60-second wall-time limit on one CPU and 2 GiB RAM, with at most 8 MiB of stdout. Keep all implementation files within `/app/src/`, the directory exported for evaluation. Inputs contain all required physical data; runtime network access is available but no external data is needed.

## Purpose and scope

Predict how an uneven inlet distribution changes the hydraulic load, spatial reaction utilization and transient polarization of a porous vanadium negative half-cell. The model adapts the Darcy flow, multicomponent transport, interfacial mass transfer and charge-balance equations of RFBniCS (arXiv:2610.01840v1). Allowing the specified nonuniform inlet is an extension of the same boundary-value problem, not a claim that the paper used this inlet profile. The electrode is a two-dimensional rectangle of thickness W and flow length H, with unit depth perpendicular to the plane. Temperature and material properties are constant. There is no positive electrode, tank, membrane interior/Donnan jump, heating, degradation, double-layer capacitance or protection event.

## Geometry, flow, and interfaces

The domain is 0<x<W, 0<y<H. The collector is x=0, the membrane is x=W, the inlet is y=0 and the outlet is y=H. The outward unit normal is n. Pressure is measured relative to the outlet. The time-independent Darcy velocity u and pressure p obey

`u = -(K/mu) grad(p)`, `div(u)=0`.

Here K is permeability in m^2 and mu is dynamic viscosity in Pa s. At the inlet, the normal inward velocity is `u_y(x,0)=u0*(1+beta*cos(pi*x/W))`; at the outlet p=0; collector and membrane are impermeable to bulk liquid (`u dot n=0`). The given profile is strictly positive. There is no separate imposed inlet pressure or outlet velocity. Darcy flow is not altered by the electrochemical state.

The five ionic species, always in the order `v2`, `v3`, `h`, `hso4`, `so4`, have charge numbers (2,3,1,-1,-2). Concentrations c_j are mol/m^3 of pore liquid. At every point, `sum(z_j*c_j)=0`; only the first four concentrations are independent. Let F=96485.33212 C/mol and R=8.314462618 J/(mol K). The species molar fluxes (mol/(m^2 s)) and electrolyte current (A/m^2) are

`N_j = u*c_j - D_eff,j*(grad(c_j) + z_j*F*c_j/(R*T)*grad(phi_l))`,

`i_l = F*sum(z_j*N_j)`, `D_eff,j = epsilon^(3/2)*D_j`.

The solid current is `i_s = -sigma_eff*grad(phi_s)`, where `sigma_eff=(1-epsilon)^(3/2)*sigma`. Potentials are volts; sigma is the intrinsic solid conductivity (S/m), epsilon is porosity, and the D_j are intrinsic diffusivities (m^2/s).

At each point the unresolved pore-scale interfacial coefficients are `km_j=7*D_j/df*Re^0.4` for j=v2,v3, with `Re=rho*|u|*df/mu`. Here rho is liquid density (kg/m^3), df is fiber diameter (m), and |u| is the local Darcy speed. These coefficients use the intrinsic D_j, without a second porosity factor.

Let r be the molar reaction rate per internal area, positive for oxidation V2+ -> V3+ + electron. The two surface concentrations and rate satisfy

`r=km_v2*(c_v2-c_v2,s)`,

`r=km_v3*(c_v3,s-c_v3)`,

`r=k0*(c_v2,s*exp(alpha*F*delta/(R*T)) - c_v3,s*exp(-(1-alpha)*F*delta/(R*T)))`,

where `delta=phi_s-phi_l-E0`, E0 is the formal potential and k0 is m/s. Define `i_F=F*r` (A/m^2 of internal area). The bulk internal area density a is m^-1. The local phase balances are `div(i_s)=-a*i_F` and `div(i_l)=+a*i_F`.

The first four species obey `epsilon*partial_t(c_j)+div(N_j)=S_j`, with `(S_v2,S_v3,S_h,S_hso4)=(-a*r,+a*r,0,0)`. Sulfate is determined by electroneutrality. There are no additional acid equilibrium or sulfate reaction terms.

## Boundary and initial data

The applied current density J is constant along the collector and membrane, and piecewise constant in time as listed in `stages`. Positive J denotes oxidation/discharge; negative J denotes reduction/charge.

| Boundary | Solid current | Liquid current | Species |
|---|---|---|---|
| Collector x=0 | i_s dot n=-J | i_l dot n=0 | N_j dot n=0 for all j |
| Membrane x=W | i_s dot n=0 | i_l dot n=J | N_h dot n=J/F, all other species normal fluxes zero |
| Inlet y=0 | i_s dot n=0 | i_l dot n=0 | Four independent c_j equal the fixed inlet values; sulfate follows electroneutrality |
| Outlet y=H | i_s dot n=0 | i_l dot n=0 | Nonadvective normal species flux is zero, so N_j dot n=(u dot n)*c_j |

The inlet concentrations are fixed throughout the run. Initially the four independent bulk concentrations are spatially uniform and equal to the inlet values, with electroneutral sulfate. The surface concentrations, reaction and potentials are quasistatic variables determined by the current and bulk state; they are not stored capacitive states. Potentials have a common additive gauge freedom; all requested outputs are gauge invariant.

Stages are consecutive. Concentrations remain continuous at a current change; flow and inlet data do not change. Each output is the state at the end of its stage, with that stage's current (the left time limit if another stage follows). Internal timesteps, mesh, spatial discretization, quadrature and nonlinear solver are your choice. The target is the continuous model, not a particular backward-Euler time grid or a particular finite-volume stencil. The solution remains in the positive, unique physical regime described below.

## Input

All shown keys are required. Additional keys may be ignored. There are no optional physics switches.

```
{
  "geometry": {"width_m": 0.0002, "height_m": 0.0004},
  "flow": {"mean_inlet_m_s": 0.000001, "inlet_beta": 0.5,
           "permeability_m2": 1e-11, "viscosity_pa_s": 0.003,
           "density_kg_m3": 1200.0, "fiber_diameter_m": 0.00001},
  "material": {"porosity": 0.75, "sigma_s_m": 2000.0,
               "area_m_inv": 20000.0, "temperature_k": 298.15,
               "formal_potential_v": -0.36, "alpha": 0.5,
               "k0_m_s": 0.00000025,
               "diffusivity_m2_s": [2e-10, 3e-10, 9e-9, 1.3e-9, 1.1e-9]},
  "inlet_mol_m3": {"v2": 300.0, "v3": 300.0, "h": 1000.0, "hso4": 1000.0},
  "stages": [{"duration_s": 10.0, "current_a_m2": 5.0},
             {"duration_s": 5.0, "current_a_m2": 0.0}]
}
```

The supported numeric box is W in [1e-4,5e-4] m, H in [2e-4,1e-3] m with H/W in [1,3]; mean inlet speed in [2e-7,4e-6] m/s; beta in [-0.8,0.8]; K in [1e-12,1e-9] m^2; viscosity in [1e-3,8e-3] Pa s; density in [1000,1400] kg/m^3; fiber diameter in [5e-6,2e-5] m; porosity in [0.55,0.9]; intrinsic sigma in [20,10000] S/m; area in [5e3,8e4] m^-1; T in [280,330] K; E0 in [-0.5,-0.2] V; alpha in [0.3,0.7]; k0 in [2e-8,2e-6] m/s; and each D in [1e-10,1e-8] m^2/s. The four inlet concentrations are in [50,3000] mol/m^3 and the implied inlet sulfate is in [50,6000]. There are 1–4 stages, each duration in [0.5,60] s and J in [-20,20] A/m^2. To bound the transport regime, `u0*H/min(D_eff,j) <= 5`.

Scored physical inputs additionally satisfy throughout the evolution: all five bulk concentrations >=10 mol/m^3, both surface concentrations >=1 mol/m^3, and `|F*(phi_s-phi_l-E0)/(R*T)|<=8`. A unique positive solution exists. These physical guarantees restrict the combinations tested; arbitrary box-bound combinations outside this regime need not be solved. No negative-concentration clipping is part of the physical model.

Malformed JSON, missing required keys, wrong types/shapes, nonfinite values, booleans used as numbers, and violations of the explicit box/aspect/Peclet/inlet-sulfate constraints must return exactly `{"error":"invalid_input"}` with exit status 0. No traceback belongs on stdout. Behavior outside the additional physical guarantees is not tested.

## Outputs and accuracy

Return an object with `hydraulics` and `states`.

`hydraulics` contains:

- `inlet_pressure_pa`: a two-element array of p(W/4,0), p(3W/4,0).
- `dissipation_w_m`: integral over the rectangle of `(mu/K)*|u|^2`, the Darcy dissipation per unit perpendicular depth (W/m).

`states` has one object per stage, in order. Each object contains:

- `time_s`: total elapsed time.
- `collector_voltage_v`: `(1/H)*integral_0^H [phi_s(0,y)-phi_l(W,y)] dy`. This is a negative-half-cell voltage, not full-cell voltage.
- `mean_mol_m3`: five-key object of volume averages `(1/(W*H))*integral c_j dx dy`.
- `outlet_mol_m3`: five-key object of **flow-weighted** outlet concentrations `integral_0^W u_y(x,H)*c_j(x,H) dx / integral_0^W u_y(x,H) dx`.
- `reaction_quadrants_a_m`: four integrals of `a*i_F` over the rectangles in the order lower-left, lower-right, upper-left, upper-right, split at x=W/2 and y=H/2. Values are A/m of perpendicular depth, may be negative, and are not absolute-value integrals.
- `surface_mean_mol_m3`: object with `v2` and `v3`, their surface concentrations averaged over the rectangle.

All numbers must be finite. Extra output keys are ignored. Errors are compared as `atol+rtol*abs(expected)`. For mean, outlet and surface concentrations use rtol=0.003 and atol=0.1 mol/m^3. For voltage use rtol=0.001 and atol=0.0001 V. For each signed reaction integral use rtol=0.005 and atol=0.000002 A/m. Hydraulic outputs use rtol=0.00002, with atol=0.000001 Pa for pressures and 1e-13 W/m for dissipation. Time uses rtol=1e-10 and atol=1e-10 s. Spatial and temporal numerical errors both count toward these tolerances. No exact grid, internal state representation, symbolic formula or derivative output is required.
