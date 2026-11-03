# SPDX-License-Identifier: GPL-3.0-only
"""Versioned source and native coverage for a repaired DLL input frontend.

Coverage describes required experiments, never electrical admission. In
particular, the original native suite remains a subset of the new suite.
"""
import hashlib
import itertools
import json

import dll_native_evidence as original

VERSION = 'dll-slew-repair-v1'
PROCESSES = ('tt', 'ff', 'ss', 'fs', 'sf')
TEMPERATURES = (0, 25, 40)
FREQUENCIES = (390, 400, 410)
SLEWS = ((20, 200), (200, 20))
OFFSETS = (-150, -50, -20, 0, 20, 50, 150)
SOURCE_OFFSETS = (-300, *OFFSETS, 300)


def validate_requirements(requirements):
    if (requirements.get('supply_sweep') is not False or
            requirements.get('analog_supply_v') != 3.3 or
            requirements.get('digital_supply_v') != 1.8 or
            requirements.get('nominal_clock_mhz') != 400 or
            requirements.get('bits_per_cycle') != 2 or
            sorted(requirements.get('process_corners', [])) != sorted(PROCESSES) or
            sorted(requirements.get('temperatures_c', [])) != list(TEMPERATURES) or
            sorted(requirements.get('clock_test_mhz', [])) != list(FREQUENCIES) or
            sorted(requirements.get('clock_duty', [])) != [.45, .5, .55]):
        raise ValueError('Slew coverage requires the fixed-rail, fifteen-PVT clock contract')


def phase(process, temperature, mhz, slew, offset):
    return dict(kind='phase', process=process, temperature=temperature, mhz=mhz,
                reference_slew_ps=slew[0], feedback_slew_ps=slew[1], offset_ps=offset)


def source_specs(requirements):
    """All PVT/frequency combinations, matched and both extreme input slews."""
    validate_requirements(requirements)
    return [phase(p, t, f, slew, offset) for p, t, f, slew, offset in
            itertools.product(PROCESSES, TEMPERATURES, FREQUENCIES,
                              ((100, 100), *SLEWS), SOURCE_OFFSETS)]


def native_additions(requirements, worst_pvt):
    validate_requirements(requirements)
    worst_pvt = tuple(worst_pvt)
    if worst_pvt not in tuple(itertools.product(PROCESSES, TEMPERATURES)):
        raise ValueError('Worst screened PVT must be one of the fifteen qualified points')
    points = list(itertools.product(PROCESSES, TEMPERATURES, (400,)))
    points += [(p, t, f) for p, t in dict.fromkeys([('ss', 40), worst_pvt])
               for f in (390, 410)]
    return [phase(p, t, f, slew, offset)
            for (p, t, f), slew, offset in itertools.product(points, SLEWS, OFFSETS)]


def required_cases(requirements, worst_pvt, captures=()):
    return original.required_cases(requirements, captures) | {
        original.signature(spec) for spec in native_additions(requirements, worst_pvt)}


def descriptor(requirements, worst_pvt, captures=()):
    signatures = sorted(required_cases(requirements, worst_pvt, captures), key=repr)
    digest = hashlib.sha256(json.dumps(signatures, separators=(',', ':')).encode()).hexdigest()
    return dict(version=VERSION, worst_screened_pvt=list(worst_pvt),
                required_signatures_sha256=digest, required_case_count=len(signatures))


def check_native_coverage(manifest, requirements):
    """Reject old-count, incomplete, duplicate or foreign-version manifests."""
    coverage = manifest['identity'].get('slew_coverage')
    if not isinstance(coverage, dict) or coverage.get('version') != VERSION:
        raise ValueError('Require an explicit repaired-DLL coverage version')
    captures = manifest['identity'].get('captured_clocks', [])
    worst = coverage.get('worst_screened_pvt', [])
    if coverage != descriptor(requirements, worst, captures):
        raise ValueError('Repaired DLL coverage descriptor changed')
    tasks = manifest['tasks']
    signatures = [original.signature(t['spec'], t['fast_rc']) for t in tasks]
    if (len(signatures) != len(set(signatures)) or
            set(signatures) != required_cases(requirements, worst, captures) or
            len({t['id'] for t in tasks}) != len(tasks)):
        raise ValueError('Repaired DLL coverage is incomplete, duplicated or unexpected')
    for t in tasks:
        spec = t['spec']
        if spec['kind'] == 'loop' and spec.get('architecture') != 'averaged_pfd_ota':
            raise ValueError('Repaired DLL requires the OTA architecture')
        if spec['kind'] == 'logic' and spec.get('expected') is not True:
            raise ValueError('Stuck detector fixture must require a fault')
    return {t['id']: t for t in tasks}
