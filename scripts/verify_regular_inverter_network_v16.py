#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Bind fresh physical regular-inverter RC to the prior diagnostic network.

Only element identifiers, row ordering and the root model name may differ.
Every terminal token, native model/parameter token and R/C value must match.
This component proof does not qualify a bank or transfer PHY admission.
"""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import subprocess
import verify_regular_clock_inverter_v15 as proof
from build_compound_drivers_v3 import cell_definition

ROOT = proof.ROOT
VERSION = 'exact-element-bijection-regular-inverter-physical-rc-diagnostic-v16.1'
CONTEXT = 'regular_inverter_network_verification_v16'
REFERENCE_MODEL = proof.physical.OLD
sha = proof.sha


def elements(text):
    rows = []; ports = None; active = ended = False; names = set()
    for line in text.splitlines():
        w = line.split('$', 1)[0].split()
        if not w or w[0].startswith('*'):
            continue
        if w[0].lower() == '.subckt':
            if ports is not None or ended:
                raise ValueError('Require exactly one flat native component')
            ports = tuple(w[2:]); active = True; continue
        if w[0].lower() == '.ends':
            if not active:
                raise ValueError('Unmatched native component ending')
            active = False; ended = True; continue
        if not active or w[0][0] not in 'XRC' or w[0].lower() in names:
            raise ValueError('Changed or duplicate electrical element')
        names.add(w[0].lower())
        if w[0][0] in 'RC' and len(w) != 4:
            raise ValueError('Changed passive-element syntax')
        if w[0][0] == 'X':
            first = next((i for i, token in enumerate(w) if '=' in token), len(w))
            if first not in (4, 6) or not w[first-1].startswith('sky130_fd_pr__'):
                raise ValueError('Require explicit native MOS or MIM primitives')
        rows.append((w[0], (w[0][0], *w[1:])))
    if not ended or active or ports != ('A', 'Y', 'VGND', 'VPWR') or not rows:
        raise ValueError('Native inverter interface or completeness changed')
    return ports, rows


def compare(reference, actual):
    _, a = elements(reference); _, b = elements(actual)
    if Counter(key for _, key in a) != Counter(key for _, key in b):
        raise ValueError('Fresh physical RC differs electrically from the diagnostic component')
    available = defaultdict(list)
    for name, key in b:
        available[key].append(name)
    mapping = [dict(reference=name, physical=available[key].pop()) for name, key in a]
    counts = Counter(key[0] for _, key in a)
    if counts != {'X': 17, 'R': 181, 'C': 88}:
        raise ValueError('Require the entire native guarded-inverter RC network')
    return dict(element_counts=dict(counts), element_bijection=mapping,
                exact_electrical_elements_preserved=True, node_names_and_parameter_tokens_identical=True,
                numerical_tolerance_used=False, approximation_used=False)


def checked(diagnostic, physical):
    proof.bound(physical)
    # Scientific and CAD Python environments remain separate. Run the existing
    # scientific producer's full bound check in its pinned environment.
    code = 'import sys; from pathlib import Path; sys.path.insert(0,str(Path(sys.argv[1])/"scripts")); import probe_tg_driver_experiment_v9 as p; p.bound(Path(sys.argv[2]))'
    subprocess.run([str(ROOT/'build/tools/exact-rc-venv/bin/python'), '-c', code, str(ROOT), str(diagnostic)], check=True)
    actual_report = json.loads((physical/'summary.json').read_text())
    actual = proof.physical.checked_netlist(actual_report['extraction'])
    source = diagnostic/'cells_regular_quad.spice'
    reference = cell_definition(source.read_text(), REFERENCE_MODEL)
    return compare(reference, actual), reference, actual, actual_report


def verify(diagnostic, physical):
    comparison, reference, actual, r = checked(diagnostic, physical)
    paths = [diagnostic/'manifest.json', diagnostic/'cells_regular_quad.spice', physical/'manifest.json', physical/'summary.json',
             ROOT/r['extraction']['netlist'], Path(__file__), Path(proof.__file__), Path(proof.physical.__file__)]
    identity = dict(version=VERSION, diagnostic=str(diagnostic.relative_to(ROOT)), physical=str(physical.relative_to(ROOT)),
                    inputs={str(p.relative_to(ROOT)): sha(p) for p in paths})
    out = ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    if out.exists():
        bound(out); return out
    out.mkdir(parents=True)
    (out/'manifest.json').write_text(json.dumps(dict(identity=identity, qualified_phy=False), indent=2)+'\n')
    negatives = []
    for fault in ('changed_resistance', 'missing_mos'):
        lines = actual.splitlines()
        index = next(i for i, line in enumerate(lines) if line.startswith('R' if fault == 'changed_resistance' else 'X'))
        if fault == 'changed_resistance':
            words = lines[index].split(); words[3] = str(float(words[3])*1.01); lines[index] = ' '.join(words)
        else:
            del lines[index]
        text = '\n'.join(lines)+'\n'; (out/(fault+'.spice')).write_text(text)
        try:
            compare(reference, text)
        except ValueError:
            negatives.append(dict(fault=fault, rejected=True))
        else:
            raise ValueError('Electrical-equivalence negative control was accepted')
    checked(diagnostic, physical)
    outputs = {p.name: sha(p) for p in out.iterdir() if p.is_file() and p.name != 'manifest.json'}
    report = dict(comparison=comparison, negative_controls=negatives, outputs=outputs,
                  component_rc_has_own_physical_witness=True, passed=True, qualified_phy=False,
                  electrical_qualification_passed=False,
                  scope='Exact 286-element component-network bijection to independently verified regular-PMOS physical RC; no new whole-bank wiring, native waveform, dense/PVT or PHY admission')
    (out/'summary.json').write_text(json.dumps(report, indent=2)+'\n')
    bound(out); return out


def bound(out):
    i = json.loads((out/'manifest.json').read_text())['identity']; r = json.loads((out/'summary.json').read_text())
    if (out.parent != ROOT/'build/diagnostics'/CONTEXT or i['version'] != VERSION
            or out.name != hashlib.sha256(json.dumps(i, sort_keys=True).encode()).hexdigest()[:16]
            or any(sha(ROOT/n) != h for n, h in i['inputs'].items())
            or any(sha(out/n) != h for n, h in r['outputs'].items())
            or not r['passed'] or not r['component_rc_has_own_physical_witness']
            or r['qualified_phy'] or r['electrical_qualification_passed']
            or r['negative_controls'] != [dict(fault='changed_resistance', rejected=True), dict(fault='missing_mos', rejected=True)]):
        raise ValueError('Exact regular-inverter network witness changed')
    comparison, _, _, _ = checked(ROOT/i['diagnostic'], ROOT/i['physical'])
    if comparison != r['comparison']:
        raise ValueError('Component electrical-element bijection changed')
    return i


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('diagnostic', type=Path); p.add_argument('physical', type=Path)
    a = p.parse_args(); print(verify(a.diagnostic.resolve(), a.physical.resolve()), flush=True)
