"""One fixed equal-weight behavior; incomplete oracle evidence invalidates grading."""
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import traceback

sys.path.insert(0, '/tests')
from anchors import equilibrium, hydraulics
from cases import CASES, fixture
from safe_candidate import CandidateFailure, run_payload
from validate_output import check_response


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
        separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def expectation(case_id, case):
    if case['axis'] == 'anchor':
        return equilibrium(case['request'])
    golden = json.loads(Path('/tests/golden.json').read_text())
    if golden.get('schema_version') != '1.0' or golden.get('status') != 'validated':
        raise RuntimeError('Independent numerical expectations are not validated/frozen')
    record = golden['cases'][case_id]
    if record['input_sha256'] != digest(case['request']):
        raise RuntimeError('Golden data belongs to a different fixed physical input')
    evidence = record['certification']
    if evidence.get('domain_checked') is not True or not evidence.get('evidence'):
        raise RuntimeError('Golden domain/independence evidence is missing')
    fraction = evidence.get('maximum_comparison_budget_fraction')
    if type(fraction) not in (int, float) or not 0 <= fraction <= 0.25:
        raise RuntimeError('Independent numerical uncertainty exceeds its frozen allowance')
    output = record['output']
    exact = hydraulics(case['request'])
    if any(abs(x-y) > 1e-10*max(1., abs(y))
           for x, y in zip(output['hydraulics']['inlet_pressure_pa'], exact['inlet_pressure_pa'])):
        raise RuntimeError('Golden hydraulic values contradict the independent analytic anchor')
    # Exact hydraulic values prevent accumulated numerical error in this subproblem.
    output['hydraulics'] = exact
    return output


def main():
    if os.geteuid() != 0 or len(sys.argv) != 2 or sys.argv[1] not in CASES:
        raise RuntimeError('Invalid trusted item invocation')
    case_id = sys.argv[1]
    case = fixture(case_id)
    started = time.monotonic()
    # Construct/check the oracle before executing any untrusted candidate.
    expected = expectation(case_id, case) if case['kind'] == 'physical' else None
    print(json.dumps({'event': 'case_input', 'case_id': case_id, 'input': case['request']}), flush=True)
    try:
        output = run_payload(case['request'], timeout_seconds=60, raw=case.get('raw', False))
        if case['kind'] == 'invalid':
            if output != {'error': 'invalid_input'}:
                raise CandidateFailure('Invalid input requires exactly the specified error object')
        else:
            check_response(output, expected)
    except CandidateFailure as error:
        print('CANDIDATE_FAIL '+case_id+': '+str(error), file=sys.stderr)
        return 1
    print(json.dumps({'event': 'case_pass', 'case_id': case_id,
                      'seconds': time.monotonic()-started}), flush=True)
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception:
        traceback.print_exc()
        raise SystemExit(2)
