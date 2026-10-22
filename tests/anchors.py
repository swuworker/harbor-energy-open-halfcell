"""Independently derived analytic anchors; no reference solver imports."""
import math

F = 96485.33212
R = 8.314462618
SPECIES = ('v2', 'v3', 'h', 'hso4', 'so4')


def hydraulics(request):
    W = request['geometry']['width_m']
    H = request['geometry']['height_m']
    flow = request['flow']
    u = flow['mean_inlet_m_s']
    beta = flow['inlet_beta']
    inverse_mobility = flow['viscosity_pa_s']/flow['permeability_m2']
    amplitude = beta*W/math.pi*math.tanh(math.pi*H/W)
    mean_pressure = u*inverse_mobility*H
    variation = u*inverse_mobility*amplitude/math.sqrt(2)
    return {'inlet_pressure_pa': [mean_pressure+variation, mean_pressure-variation],
        'dissipation_w_m': u*u*inverse_mobility*(W*H+beta*beta*W*W/(2*math.pi)*math.tanh(math.pi*H/W))}


def equilibrium(request):
    if any(stage['current_a_m2'] != 0 for stage in request['stages']):
        raise RuntimeError('Equilibrium fixture has a nonzero current')
    c = {key: float(request['inlet_mol_m3'][key]) for key in SPECIES[:4]}
    c['so4'] = (2*c['v2']+3*c['v3']+c['h']-c['hso4'])/2
    m = request['material']
    voltage = m['formal_potential_v'] + R*m['temperature_k']/F*math.log(c['v3']/c['v2'])
    states, elapsed = [], 0.0
    for stage in request['stages']:
        elapsed += stage['duration_s']
        states.append({'time_s': elapsed, 'collector_voltage_v': voltage,
            'mean_mol_m3': dict(c), 'outlet_mol_m3': dict(c),
            'reaction_quadrants_a_m': [0.0]*4,
            'surface_mean_mol_m3': {key: c[key] for key in SPECIES[:2]}})
    return {'hydraulics': hydraulics(request), 'states': states}
