#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Measure the full-RC DDR capture aperture through its published parallel ports."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import itertools
import json
import math
import os
from pathlib import Path
import subprocess
import time

import numpy as np
from dll_measurements import read_wave, column, complete, edges
from spice_engine import command, engine, provenance
from spice_library import checked_netlist, digital_current

ROOT = Path(__file__).resolve().parents[1]
CODE = ['characterize_rx_aperture.py', 'dll_measurements.py', 'spice_engine.py',
        'run_ngspice.py', 'spice_library.py', 'spice_scope.py']
PERIOD_NS = 1000 / 410
BRACKET_PS = (-800., 800.)
RESOLUTION_PS = 5
GUARD_PS = 20


def sha(data):
    return hashlib.sha256(data).hexdigest()


def atomic(path, value):
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')
    tmp.replace(path)


def code_hashes():
    return {name: sha((ROOT / 'scripts' / name).read_bytes()) for name in CODE}


def conditions(requirements):
    return [dict(process=p, temperature=t, edge=e, polarity=d, clock_slew_ps=cs,
                 data_slew_ps=ds, kind=k)
            for p, t, e, d, cs, ds, k in itertools.product(
                requirements['process_corners'], requirements['temperatures_c'],
                ['rising', 'falling'], ['rise', 'fall'], [20, 200], [20, 200], ['setup', 'hold'])]


def condition_id(spec):
    return '_'.join(str(spec[k]) for k in ['process', 'temperature', 'edge', 'polarity',
                                         'clock_slew_ps', 'data_slew_ps', 'kind'])


def pwl(points):
    return 'PWL(' + ' '.join(f'{t:.12g}n {v:.12g}' for t, v in points) + ')'


def fixture(spec, distance_ps, ports):
    """Times denote 50% crossings; the requested slew is measured at 10--90%."""
    rise = 5 + 12 * PERIOD_NS
    target = rise + (PERIOD_NS / 2 if spec['edge'] == 'falling' else 0)
    transition = target + (-distance_ps if spec['kind'] == 'setup' else distance_ps) / 1000
    clock_ramp = spec['clock_slew_ps'] / 800  # ns, full 0--100% ramp
    data_ramp = spec['data_slew_ps'] / 800
    clock = [(0, 0)]
    for i in range(16):
        at = 5 + i * PERIOD_NS
        clock += [(at - clock_ramp / 2, 0), (at + clock_ramp / 2, 1.8),
                  (at + PERIOD_NS / 2 - clock_ramp / 2, 1.8),
                  (at + PERIOD_NS / 2 + clock_ramp / 2, 0)]
    old = 0 if spec['polarity'] == 'rise' else 1
    new = 1 - old
    data = [(0, 1.8 * old), (transition - data_ramp / 2, 1.8 * old),
            (transition + data_ramp / 2, 1.8 * new)]
    nodes = {'VGND': '0', 'VPWR': 'VDDD', 'clk': 'CLK', 'reset_n': 'RST',
             'serial': 'D', 'data[0]': 'Q0', 'data[1]': 'Q1', 'valid': 'VALID'}
    if set(ports) != set(nodes):
        raise ValueError('Capture core terminal names changed')
    body = (f'VD VDDD 0 1.8\nVR RST 0 PWL(0 0 2n 0 2.05n 1.8)\n'
            f'VC CLK 0 {pwl(clock)}\nVS D 0 {pwl(data)}\n'
            'XR ' + ' '.join(nodes[p] for p in ports) + ' openlvds_ddr_rx\n'
            'C0 Q0 0 20f\nC1 Q1 0 20f\nCV VALID 0 20f\n')
    targeted = new if spec['kind'] == 'setup' else old
    expected = [targeted, new] if spec['edge'] == 'rising' else [old, targeted]
    stop = 5 + 16 * PERIOD_NS
    return body, dict(target_ns=target, transition_ns=transition,
                     publication_ns=rise + PERIOD_NS, stop_ns=stop, expected=expected)


def measure(wave, header, spec, timing, distance_ps):
    t = wave[:, 1]
    if not complete(wave, timing['stop_ns']):
        return dict(passed=False, error='Incomplete capture transient')
    clock = column(wave, header, 'CLK')
    data = column(wave, header, 'D')
    ce = edges(t, clock, rising=spec['edge'] == 'rising')
    de = edges(t, data, rising=spec['polarity'] == 'rise')
    if not len(ce) or len(de) != 1:
        return dict(passed=False, error='Missing or extra stimulus edge')
    actual = ce[np.argmin(abs(ce - timing['target_ns'] * 1e-9))]
    separation = (actual - de[0] if spec['kind'] == 'setup' else de[0] - actual) * 1e12
    if abs(separation - distance_ps) > .5:
        return dict(passed=False, error='Stimulus separation differs from requested value')
    # Observe the complete, public pair. No internal sampler labels are needed.
    sample = (timing['publication_ns'] + np.arange(.80, 1.051, .005)) * 1e-9
    values = [np.interp(sample, t, column(wave, header, n)) for n in ['Q0', 'Q1', 'VALID']]
    limits = [[float(v.min()), float(v.max())] for v in values]
    valid = limits[2][0] > 1.44
    legal = all(hi < .36 or lo > 1.44 for lo, hi in limits[:2])
    correct = all(lo > 1.44 if bit else hi < .36 for (lo, hi), bit in zip(limits, timing['expected']))
    return dict(passed=bool(valid and legal and correct), stimulus_separation_ps=float(separation),
                expected=timing['expected'], output_limits_v=limits, valid=valid, legal=legal)


def guarded_bound(passing_ps):
    return max(0, math.ceil((passing_ps + GUARD_PS) / 10) * 10)


def prepare():
    if engine() != 'ngspice':
        raise ValueError('Use the pinned --ngspice environment')
    requirements = (ROOT / 'requirements.json').read_bytes()
    models = json.loads((ROOT / 'build/extracted/digital.json').read_text())['designs']
    info = digital_current('openlvds_ddr_rx', models['openlvds_ddr_rx'])
    lib = checked_netlist(info).encode()
    identity = dict(code=code_hashes(), simulator_provenance=provenance(),
                    requirements_sha256=sha(requirements), library_sha256=sha(lib),
                    model=info, period_ns=PERIOD_NS, bracket_ps=BRACKET_PS,
                    resolution_ps=RESOLUTION_PS, guard_ps=GUARD_PS)
    root = ROOT / 'build/characterization/rx_aperture' / sha(json.dumps(identity, sort_keys=True).encode())[:16]
    if (root / 'manifest.json').exists():
        return root
    root.mkdir(parents=True, exist_ok=True)
    (root / 'library.spice').write_bytes(lib)
    (root / 'requirements.json').write_bytes(requirements)
    for name in CODE:
        (root / name).write_bytes((ROOT / 'scripts' / name).read_bytes())
    atomic(root / 'manifest.json', dict(identity=identity, conditions=conditions(json.loads(requirements)),
                                       clock_mhz=410, supply_v=1.8, load_ff=20))
    atomic(root / 'state.json', dict(status='prepared'))
    return root


def validate(root, manifest):
    identity = manifest['identity']
    if identity['code'] != code_hashes() or identity['simulator_provenance'] != provenance():
        raise ValueError('Aperture producer or simulator changed')
    for filename, key in [('library.spice', 'library_sha256'), ('requirements.json', 'requirements_sha256')]:
        if sha((root / filename).read_bytes()) != identity[key]:
            raise ValueError('Captured aperture input changed: ' + filename)


def point(root, manifest, spec, distance):
    out = root / condition_id(spec) / ('point_' + f'{distance:.6f}'.replace('-', 'm').replace('.', 'p'))
    out.mkdir(parents=True, exist_ok=True)
    body, timing = fixture(spec, distance, manifest['identity']['model']['ports'])
    pdk = Path(os.environ['PDK_ROOT']) / 'sky130A/libs.tech/ngspice/sky130.lib.spice'
    deck = (f'OpenLVDS full-RC DDR aperture {condition_id(spec)} {distance:g}ps\n'
            f'.lib "{pdk}" {spec["process"]}\n.include "{root}/library.spice"\n'
            f'.options device temp={spec["temperature"]}\n'
            '.options timeint method=gear reltol=1e-4 abstol=1e-12\n' + body +
            f'.tran 5p {timing["stop_ns"]:.12g}n 0 5p\n'
            '.print tran V(CLK) V(D) V(Q0) V(Q1) V(VALID)\n.end\n')
    recipe = sha(deck.encode())
    previous = out / 'summary.json'
    if previous.exists():
        result = json.loads(previous.read_text())
        if (result.get('deck_sha256') != recipe or sha((out / 'bench.cir').read_bytes()) != recipe or
                result.get('waveform_sha256') != sha((out / 'bench.cir.prn').read_bytes())):
            raise ValueError('Aperture point evidence changed')
        wave, header = read_wave(out / 'bench.cir.prn')
        recomputed = measure(wave, header, spec, timing, distance)
        if result['measurement'] != recomputed:
            raise ValueError('Aperture point analysis changed')
        return result['measurement']['passed']
    (out / 'bench.cir').write_text(deck)
    start = time.time()
    run = subprocess.run(command(out / (engine() + '.log'), out / 'bench.cir'), cwd=out, capture_output=True, text=True)
    (out / 'console.log').write_text(run.stdout + run.stderr)
    if run.returncode:
        raise ValueError('Aperture simulator failed: ' + str(out))
    wave, header = read_wave(out / 'bench.cir.prn')
    result = measure(wave, header, spec, timing, distance)
    if 'error' in result:
        raise ValueError(result['error'] + ': ' + str(out))
    atomic(previous, dict(measurement=result, spec=spec, distance_ps=distance, deck_sha256=recipe,
                          waveform_sha256=sha((out / 'bench.cir.prn').read_bytes()),
                          wall_seconds=time.time() - start))
    return result['passed']


def search(root, manifest, spec):
    out = root / condition_id(spec)
    out.mkdir(exist_ok=True)
    lo, hi = BRACKET_PS
    try:
        if point(root, manifest, spec, lo) or not point(root, manifest, spec, hi):
            raise ValueError('Aperture boundary is not bracketed')
        while hi - lo > RESOLUTION_PS:
            mid = (hi + lo) / 2
            if point(root, manifest, spec, mid):
                hi = mid
            else:
                lo = mid
            atomic(out / 'state.json', dict(status='running', failed_ps=lo, passed_ps=hi))
        bound = guarded_bound(hi)
        if not point(root, manifest, spec, bound):
            raise ValueError('Guarded aperture witness failed')
        result = dict(passed=True, spec=spec, failed_ps=lo, passed_ps=hi, bound_ps=bound,
                      resolution_ps=hi-lo, guard_ps=GUARD_PS)
    except (ValueError, KeyError, OSError) as e:
        result = dict(passed=False, spec=spec, error=str(e))
    atomic(out / 'summary.json', result)
    print(condition_id(spec), result, flush=True)
    return result


def run(root, jobs):
    manifest = json.loads((root / 'manifest.json').read_text())
    lease = ROOT / 'build/diagnostics/dll_architecture/.supervisor.lock'
    lease.parent.mkdir(parents=True, exist_ok=True)
    atomic(root / 'state.json', dict(status='waiting_for_simulator_lease'))
    with lease.open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        validate(root, manifest)
        atomic(root / 'state.json', dict(status='running', max_jobs=jobs))
        with ThreadPoolExecutor(max_workers=jobs) as pool:
            results = list(pool.map(lambda s: search(root, manifest, s), manifest['conditions']))
        validate(root, manifest)
        passed = all(r['passed'] for r in results)
        bounds = {}
        for process, temp in itertools.product(json.loads((root / 'requirements.json').read_text())['process_corners'],
                                               json.loads((root / 'requirements.json').read_text())['temperatures_c']):
            subset = [r for r in results if r['spec']['process'] == process and r['spec']['temperature'] == temp]
            if len(subset) != 32 or not all(r['passed'] for r in subset):
                passed = False
                continue
            bounds[f'{process}_{temp}'] = {kind + '_ps': max(r['bound_ps'] for r in subset if r['spec']['kind'] == kind)
                                          for kind in ['setup', 'hold']}
        table = dict(passed=passed, clock_mhz=410, load_ff=20, guard_ps=GUARD_PS,
                     resolution_ps=RESOLUTION_PS, additional_link_margin_ps=200,
                     model_sha256=manifest['identity']['model']['netlist_sha256'],
                     producer_code=manifest['identity']['code'], simulator_provenance=manifest['identity']['simulator_provenance'],
                     manifest_sha256=sha((root / 'manifest.json').read_bytes()),
                     conditions=len(results), bounds=bounds, results=results)
        atomic(root / 'table.json', table)
        atomic(root / 'state.json', dict(status='complete', passed=passed))
        return 0 if passed else 1


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['prepare', 'run'])
    p.add_argument('artifact', nargs='?', type=Path)
    p.add_argument('--jobs', type=int, choices=range(1, 5), default=4)
    a = p.parse_args()
    root = a.artifact.resolve() if a.artifact else prepare()
    if not root.is_relative_to(ROOT):
        p.error('Artifacts must reside in OpenLVDS')
    print(root, flush=True)
    if a.action == 'run':
        return run(root, a.jobs)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
