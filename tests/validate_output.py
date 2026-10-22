"""Public output schema and published expected-oriented numerical tolerances."""
import math
from safe_candidate import CandidateFailure

SPECIES = ('v2', 'v3', 'h', 'hso4', 'so4')


def object_at(value, name):
    if not isinstance(value, dict):
        raise CandidateFailure(name+' must be an object')
    return value


def required(mapping, key, name):
    if key not in mapping:
        raise CandidateFailure(name+' is missing required field '+key)
    return mapping[key]


def near(actual, expected, atol, rtol, name):
    if type(expected) not in (int, float) or not math.isfinite(expected):
        raise RuntimeError('Nonfinite or nonnumeric independent expected value')
    if type(actual) not in (int, float):
        raise CandidateFailure(name+' must be numeric, not a boolean')
    try:
        finite = math.isfinite(actual)
    except (OverflowError, ValueError):
        finite = False
    if not finite or abs(actual-expected) > atol+rtol*abs(expected):
        raise CandidateFailure(name+' differs from the independent physical expectation')


def array(actual, expected, atol, rtol, name):
    if not isinstance(actual, list) or len(actual) != len(expected):
        raise CandidateFailure(name+' has an incorrect shape')
    for i, (value, target) in enumerate(zip(actual, expected)):
        near(value, target, atol, rtol, name+'['+str(i)+']')


def species(actual, expected, keys, name):
    actual = object_at(actual, name)
    for key in keys:
        near(required(actual, key, name), expected[key], 0.1, 0.003, name+'.'+key)


def check_response(actual, expected):
    actual = object_at(actual, 'output')
    h = object_at(required(actual, 'hydraulics', 'output'), 'hydraulics')
    target = expected['hydraulics']
    array(required(h, 'inlet_pressure_pa', 'hydraulics'), target['inlet_pressure_pa'],
          1e-6, 2e-5, 'inlet_pressure_pa')
    near(required(h, 'dissipation_w_m', 'hydraulics'), target['dissipation_w_m'],
         1e-13, 2e-5, 'dissipation_w_m')
    states = required(actual, 'states', 'output')
    if not isinstance(states, list) or len(states) != len(expected['states']):
        raise CandidateFailure('One state per requested stage is required')
    for i, (raw, target) in enumerate(zip(states, expected['states'])):
        state = object_at(raw, 'state')
        prefix = 'state['+str(i)+'].'
        near(required(state, 'time_s', prefix), target['time_s'], 1e-10, 1e-10, prefix+'time_s')
        near(required(state, 'collector_voltage_v', prefix), target['collector_voltage_v'],
             1e-4, 0.001, prefix+'collector_voltage_v')
        for key in ('mean_mol_m3', 'outlet_mol_m3'):
            species(required(state, key, prefix), target[key], SPECIES, prefix+key)
        species(required(state, 'surface_mean_mol_m3', prefix), target['surface_mean_mol_m3'],
                SPECIES[:2], prefix+'surface_mean_mol_m3')
        array(required(state, 'reaction_quadrants_a_m', prefix), target['reaction_quadrants_a_m'],
              2e-6, 0.005, prefix+'reaction_quadrants_a_m')
