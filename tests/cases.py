"""Fixed v0.2 input definitions; hidden, not candidate-visible. No solver code."""
from copy import deepcopy

BASE = {
    'geometry': {'width_m': 0.0002, 'height_m': 0.0002},
    'flow': {'mean_inlet_m_s': 2e-6, 'inlet_beta': 0.65,
        'permeability_m2': 1e-11, 'viscosity_pa_s': 0.003,
        'density_kg_m3': 1200.0, 'fiber_diameter_m': 1e-5},
    'material': {'porosity': 0.75, 'sigma_s_m': 80.0, 'area_m_inv': 20000.0,
        'temperature_k': 298.15, 'formal_potential_v': -0.36, 'alpha': 0.5,
        'k0_m_s': 8e-7, 'diffusivity_m2_s': [2e-10, 3e-10, 6e-9, 1.3e-9, 1.1e-9]},
    'inlet_mol_m3': {'v2': 300.0, 'v3': 450.0, 'h': 800.0, 'hso4': 800.0},
    'stages': [{'duration_s': 40.0, 'current_a_m2': 8.0}]}


def case(description, axis, *, geometry=None, flow=None, material=None, inlet=None, stages=None):
    value = deepcopy(BASE)
    for key, edits in [('geometry', geometry), ('flow', flow), ('material', material), ('inlet_mol_m3', inlet)]:
        if edits:
            value[key].update(edits)
    if stages is not None:
        value['stages'] = [{'duration_s': dt, 'current_a_m2': current} for dt, current in stages]
    return {'description': description, 'axis': axis, 'request': value, 'kind': 'physical'}


CASES = {
 'T01': case('Uniform equilibrium with a nonuniform inlet velocity', 'anchor', stages=[(17, 0)]),
 'T02': case('Unequal redox equilibrium with asymmetric transfer exponent', 'anchor',
    flow={'inlet_beta': -0.7}, material={'alpha': 0.3, 'temperature_k': 330.0},
    inlet={'v2': 650.0, 'v3': 150.0}, stages=[(0.5, 0), (30, 0)]),
 'T03': case('Uniform-flow control with nonzero coupled transient', 'darcy', flow={'inlet_beta': 0.0}),
 'T04': case('Collector-side inlet loading and kinetic redistribution', 'darcy', flow={'inlet_beta': 0.8}),
 'T05': case('Membrane-side inlet loading at identical mean flow', 'darcy', flow={'inlet_beta': -0.8}),
 'T06': case('Intermediate inlet contrast with unequal transfer rates', 'darcy',
    flow={'inlet_beta': 0.4, 'fiber_diameter_m': 2e-5}, material={'k0_m_s': 1.5e-6}),
 'T07': case('Slow renewal with finite surface transfer over long duration', 'darcy',
    flow={'mean_inlet_m_s': 6e-7, 'inlet_beta': 0.8}, stages=[(60, 8)]),
 'T08': case('Moderate-Peclet fast renewal with inlet maldistribution', 'darcy',
    flow={'mean_inlet_m_s': 2.8e-6, 'inlet_beta': -0.75}, stages=[(50, 10)]),
 'T09': case('Viscosity-density dependence in hydraulic load and local transfer', 'darcy',
    flow={'viscosity_pa_s': 0.007, 'density_kg_m3': 1350.0, 'fiber_diameter_m': 2e-5,
          'inlet_beta': 0.75}, material={'k0_m_s': 1.2e-6}, stages=[(50, 9)]),
 'T10': case('Longer flow direction with unchanged through-plane thickness', 'darcy',
    geometry={'height_m': 0.0004}, flow={'mean_inlet_m_s': 1.2e-6, 'inlet_beta': -0.8,
    'permeability_m2': 4e-12}, stages=[(60, 6)]),
 'T11': case('Moderate supporting-ion concentration and nonconstant liquid conduction', 'electrolyte',
    inlet={'h': 150.0, 'hso4': 150.0}, stages=[(50, 8)]),
 'T12': case('Dependent sulfate contribution with increased sulfate mobility', 'electrolyte',
    material={'diffusivity_m2_s': [2e-10, 3e-10, 6e-9, 1.3e-9, 5e-9]}, stages=[(55, 8)]),
 'T13': case('Unequal redox diffusivities and diffusion-current feedback', 'electrolyte',
    flow={'mean_inlet_m_s': 1.5e-6},
    material={'diffusivity_m2_s': [1.5e-10, 8e-10, 4e-9, 1.5e-9, 8e-10]}, stages=[(50, 7)]),
 'T14': case('HSO4-rich inlet with positive dependent sulfate', 'electrolyte',
    inlet={'h': 500.0, 'hso4': 1200.0}, flow={'inlet_beta': -0.7}, stages=[(50, -7)]),
 'T15': case('Dilute active ions with comparable supporting-ion response', 'electrolyte',
    inlet={'v2': 100.0, 'v3': 150.0, 'h': 180.0, 'hso4': 120.0}, stages=[(45, 3)]),
 'T16': case('Equal intrinsic diffusivities as an electroneutral diffusion-current anchor', 'electrolyte',
    material={'diffusivity_m2_s': [5e-10]*5}, stages=[(50, -8)]),
 'T17': case('Lower porosity changes both storage and electrolyte transport', 'electrolyte',
    material={'porosity': 0.55}, flow={'mean_inlet_m_s': 1e-6}, stages=[(55, 7)]),
 'T18': case('High porosity couples reduced solid conductivity to ionic storage', 'electrolyte',
    material={'porosity': 0.85}, stages=[(45, 7)]),
 'T19': case('Fast kinetics with finite unequal mass-transfer resistance', 'reaction_current',
    material={'k0_m_s': 2e-6, 'area_m_inv': 10000.0},
    flow={'fiber_diameter_m': 2e-5}, stages=[(45, 10)]),
 'T20': case('Low solid conductivity requires spatial phase-current redistribution', 'reaction_current',
    material={'sigma_s_m': 20.0, 'k0_m_s': 1.8e-6}, stages=[(50, 12)]),
 'T21': case('Anodic coefficient at its low endpoint with finite transfer', 'reaction_current',
    material={'alpha': 0.3, 'k0_m_s': 1.5e-6}, stages=[(50, 10)]),
 'T22': case('Anodic coefficient at its high endpoint under reduction', 'reaction_current',
    material={'alpha': 0.7, 'k0_m_s': 1.5e-6}, stages=[(50, -10)]),
 'T23': case('Oxidation from low reduced fraction with bounded surface depletion', 'reaction_current',
    inlet={'v2': 200.0, 'v3': 600.0}, material={'area_m_inv': 12000.0}, stages=[(40, 9)]),
 'T24': case('Reduction from low oxidized fraction changes the limiting surface', 'reaction_current',
    inlet={'v2': 700.0, 'v3': 160.0}, material={'area_m_inv': 12000.0}, stages=[(40, -8)]),
 'T25': case('Large internal area with finite electronic conduction', 'reaction_current',
    material={'area_m_inv': 80000.0, 'sigma_s_m': 25.0}, stages=[(50, 12)]),
 'T26': case('Temperature-dependent kinetic and migration balance under reversal', 'reaction_current',
    material={'temperature_k': 280.0, 'alpha': 0.35, 'k0_m_s': 1.2e-6},
    flow={'inlet_beta': -0.75}, stages=[(45, -9)]),
 'T27': case('Oxidation-rest-reduction retains the formed concentration field', 'history',
    stages=[(40, 8), (20, 0), (40, -8)]),
 'T28': case('Immediate current reversal keeps continuous bulk inventories', 'history',
    stages=[(30, -6), (30, 6)]),
 'T29': case('Same-current stage split is a continuous trajectory', 'history',
    stages=[(40, 8), (40, 8)]),
 'T30': case('Open-boundary relaxation after a long oxidation stage', 'history',
    stages=[(60, 8), (30, 0)]),
 'T31': case('Positive prefix changes the response to the common suffix', 'history',
    stages=[(30, 6), (30, 4)]),
 'T32': case('Negative prefix changes the response to the common suffix', 'history',
    stages=[(30, -6), (30, 4)]),
 'T33': case('Short initial pulse followed by rest and a long opposite stage', 'history',
    stages=[(0.5, 10), (5, 0), (30, -4)]),
 'T34': case('Slow-flow multistage memory and membrane proton exchange', 'history',
    flow={'mean_inlet_m_s': 2e-7, 'inlet_beta': -0.8},
    stages=[(60, 8), (60, -8), (60, 6), (60, -6)]),
 'T35': case('Lower internal area with finite transfer across long stages', 'history',
    material={'area_m_inv': 5000.0, 'k0_m_s': 1.5e-6},
    stages=[(45, 7), (20, 0), (45, -7)]),
 'T36': case('Combined maldistribution-supporting-ion-current history', 'history',
    flow={'inlet_beta': -0.8, 'mean_inlet_m_s': 1.5e-6},
    material={'porosity': 0.85, 'alpha': 0.65, 'sigma_s_m': 35.0},
    inlet={'h': 220.0, 'hso4': 160.0},
    stages=[(20, -6), (25, 0), (40, 6), (15, 2)]),
}
CASES['T37'] = {'description': 'Malformed JSON is rejected without a traceback',
    'axis': 'interface', 'kind': 'invalid', 'raw': True, 'request': '{"geometry":'}
CASES['T38'] = {'description': 'Boolean numeric input is rejected', 'axis': 'interface',
    'kind': 'invalid', 'request': deepcopy(BASE)}
CASES['T38']['request']['material']['porosity'] = True
CASES['T39'] = {'description': 'Wrong diffusivity array shape is rejected', 'axis': 'interface',
    'kind': 'invalid', 'request': deepcopy(BASE)}
CASES['T39']['request']['material']['diffusivity_m2_s'] = [2e-10, 3e-10, 6e-9, 1.3e-9]
CASES['T40'] = {'description': 'Explicit Peclet-domain violation is rejected', 'axis': 'interface',
    'kind': 'invalid', 'request': deepcopy(BASE)}
CASES['T40']['request']['geometry'] = {'width_m': 0.0005, 'height_m': 0.001}
CASES['T40']['request']['flow']['mean_inlet_m_s'] = 4e-6


def fixture(case_id):
    return deepcopy(CASES[case_id])
