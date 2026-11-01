#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Measure full-trace current, headroom and observed terminal stress after rate tests."""
import argparse
import itertools
import json
from pathlib import Path
import re

import numpy as np
from dll_measurements import read_wave
from layout import circuits
from receiver_architecture_observations import THIN_GUARD_V
from receiver_static_diagnosis import capture_manifest
import receiver_architecture_rate as rate

ROOT = Path(__file__).resolve().parents[1]


def observed_devices(source):
    # layout.circuits intentionally accepts PDK devices only. Remove only
    # the four known ideal meter statements from this parsing copy; retain
    # their observed drain aliases on the MOS terminals themselves.
    for node, label in [('CT', 'TAIL'), ('NBC', 'REPLICA')]:
        for line in [f'VOBS_{label} {node} OBS_{label}_D 0',
                     f'HOBS_{label} OBS_I{label} VSS VOBS_{label} 1']:
            if source.splitlines().count(line) != 1:
                raise ValueError('Missing or changed ideal observation meter')
            source = source.replace(line+'\n', '')
    definitions = circuits(source); rows = {r[0]: r for r in definitions['openlvds_receiver_core'][1]}
    devices = {name: rows[name] for name in ['XCT', 'XC0', 'XC1', 'XCD', 'XCM', 'XNCB']}
    for name in ['XIB0', 'XIB1', 'XIB2']:
        _, nodes, helper, _ = rows[name]; ports, children = definitions[helper]
        mapping = dict(zip(ports, nodes, strict=True))
        for child, terminals, model, params in children:
            if not re.fullmatch(r'sky130_fd_pr__(?:n|p)fet_.*', model) or len(terminals) != 4:
                raise ValueError('Expected a directly observable two-MOS restorer')
            if any(n not in mapping for n in terminals):
                raise ValueError('Unobserved internal restoration terminal')
            key = name+'/'+child
            devices[key] = (key, [mapping[n] for n in terminals], model, params)
    return devices


def measure(wave, headers, devices):
    t = wave[:, 1]
    def voltage(node):
        if node == 'VSS':
            return np.zeros(len(t))
        key = {'PB': 'IREF', 'VDDIO': 'VDDIO', 'VDDD': 'VDDD', 'Q': 'Q'}.get(node, 'XR:XCORE:'+node)
        return wave[:, headers['V('+key.upper()+')']]
    result = {}
    for name, (_, nodes, model, params) in devices.items():
        values = [voltage(n) for n in nodes]; peaks = []
        for a, b in itertools.combinations(range(4), 2):
            delta = abs(values[a]-values[b]); i = int(np.argmax(delta))
            peaks.append(dict(pair=['DGSB'[a], 'DGSB'[b]], voltage_v=float(delta[i]), time_ns=float(t[i]*1e9)))
        thin = bool(re.fullmatch(r'sky130_fd_pr__(?:n|p)fet_01v8(?:_lvt)?', model))
        peak = max(peaks, key=lambda p: p['voltage_v']); vds = values[0]-values[2]
        result[name] = dict(model=model, nodes=nodes, params=params, maximum_terminal_difference=peak,
            minimum_absolute_vds_v=float(abs(vds).min()), maximum_absolute_vds_v=float(abs(vds).max()),
            thin_guard_applies=thin, thin_guard_passed=peak['voltage_v'] <= THIN_GUARD_V if thin else None)
    currents = {}
    for label, node in [('tail', 'OBS_ITAIL'), ('replica', 'OBS_IREPLICA')]:
        v = voltage(node)
        currents[label] = dict(minimum_signed_a=float(v.min()), maximum_signed_a=float(v.max()),
            mean_absolute_a=float(np.sum((abs(v[1:])+abs(v[:-1]))*.5*np.diff(t))/(t[-1]-t[0])))
    return dict(devices=result, currents=currents, full_trace_interval_ns=[float(t[0]*1e9), float(t[-1]*1e9)],
        thin_guard_v=THIN_GUARD_V,
        observed_thin_guard_passed=all(d['thin_guard_passed'] for d in result.values() if d['thin_guard_applies']),
        scope='Full 60 ns trace, six decision/bias MOS plus six downshift/restoration MOS. Project 1.95 V screen, not a foundry rating. Frontend and remaining bias devices are not covered; VDS does not establish saturation without VDSAT. Ideal one-ohm transresistance outputs encode signed amperes.')


def diagnose(root):
    if not (root/'summary.json').is_file():
        raise ValueError('Complete the rate screen before observation')
    rate.run(root)  # Cached full scientific remeasurement; never admits missing work.
    source = (root/'source.spice').read_text(); wave, headers = read_wave(root/'bench.cir.prn')
    observations = measure(wave, headers, observed_devices(source))
    files = [root/n for n in ['manifest.json', 'summary.json', 'source.spice', 'bench.cir', 'bench.cir.prn']]
    files += [Path(__file__), ROOT/'scripts/receiver_architecture_observations.py', ROOT/'scripts/layout.py']
    identity = dict(inputs={str(p.relative_to(ROOT)): rate.digest(p) for p in files})
    import hashlib
    out = root/'completed_observations'/hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True, exist_ok=True)
    capture_manifest(out/'summary.json', dict(identity=identity, observations=observations, qualified_phy=False))
    return out, observations


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('root', type=Path); a = p.parse_args()
    out, result = diagnose(a.root.resolve()); print(out/'summary.json', flush=True)
    print(json.dumps(result, indent=2), flush=True)
