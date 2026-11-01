#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Prepare one DLL storage-capacitor correction from measured native G/Y evidence."""
import argparse
import hashlib
import json
from pathlib import Path

from dll_campaign import text_block
from dll_candidate_library import audited
from layout import circuits
from receiver_static_diagnosis import capture_manifest
from spice_library import replace

ROOT = Path(__file__).resolve().parents[1]
TOP = 'openlvds_dll_analog'
NAME = Path(__file__).name
MODEL = 'sky130_fd_pr__cap_mim_m3_1'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def transform(source):
    """Retain the four existing CTRL capacitors and add six identical pairs."""
    block = text_block(source, TOP)
    _, rows = circuits(source)[TOP]
    original = [r for r in rows if r[2] == MODEL and 'CTRL' in r[1]]
    expected = [(f'XCC{i}_{suffix}', ['CTRL', 'VSS'], MODEL,
                 dict(w=str(size), l=str(size)))
                for i in range(2) for suffix, size in [('0', 30), ('1', 10)]]
    if original != expected:
        raise ValueError('Require the original four 4 pF nominal CTRL storage devices')
    labels = {r[0].lower() for r in rows}
    added = [f'XCC{i}_{suffix} CTRL VSS {MODEL} w={size} l={size}'
             for i in range(2, 8) for suffix, size in [('0', 30), ('1', 10)]]
    if any(line.split()[0].lower() in labels for line in added):
        raise ValueError('Compensation capacitor name collision')
    # All existing device rows and all other subcircuits retain exact bytes.
    at = block.lower().rfind('.ends')
    changed = block[:at]+'\n'.join(added)+'\n'+block[at:]
    return replace(source, TOP, changed)


def prepare(layout, observations):
    if not layout.is_relative_to(ROOT/'build/diagnostics/dll_layout'):
        raise ValueError('Use the isolated audited baseline DLL layout')
    physical = json.loads((layout/'summary.json').read_text())
    info = json.loads((layout/'extraction.json').read_text())
    if not physical.get('passed') or digest(layout/'candidate.spice') != physical['source_sha256']:
        raise ValueError('Baseline DLL source/physical evidence changed')
    audit = audited(layout, info)
    if info['source_sha256'] != physical['source_sha256']:
        raise ValueError('Baseline DLL extraction source changed')
    gds = ROOT/physical['designs'][TOP]['gds']
    if digest(gds) != info['gds_sha256']:
        raise ValueError('Baseline DLL GDS changed')
    corners = set(); proofs = {}
    for path in observations:
        if not path.is_relative_to(ROOT/'build/diagnostics/dll_qualification'):
            raise ValueError('Use bound native model compensation observations')
        report = json.loads(path.read_text())
        qualification = path.parent.parent.parent.parent/'manifest.json'
        if (report['proofs'].get(str(qualification.relative_to(ROOT))) != digest(qualification) or
                json.loads(qualification.read_text())['identity']['full_models']['layout'] != str(layout.relative_to(ROOT))):
            raise ValueError('Compensation model belongs to another native DLL layout')
        if report['corner'] in corners:
            raise ValueError('Duplicate compensation observation corner')
        corners.add(report['corner'])
        selected = [c for c in report['compensation_estimates'] if c['added_ctrl_capacitance_pf'] == 12]
        if (report.get('qualified_phy') is not False or len(selected) != 1 or
                selected[0].get('all_models_passed') is not True or len(selected[0]['models']) != 3 or
                any(not m['passed'] or not m['model_valid'] or m['phase_margin_min_deg'] < 60 or
                    m['gain_margin_min_db'] < 6 for m in selected[0]['models'])):
            raise ValueError('Require three passing measured-model estimates for the 12 pF addition')
        for name, stamp in report['proofs'].items():
            if digest(ROOT/name) != stamp:
                raise ValueError('Native compensation observation input changed')
        proofs.update(report['proofs']); proofs[str(path.relative_to(ROOT))] = digest(path)
    if corners != {'ss_0', 'tt_25', 'ff_0'}:
        raise ValueError('Require SS0, TT25 and FF0 measured compensation estimates')
    paths = [layout/n for n in ['candidate.spice', 'summary.json', 'extraction.json', 'rc_audit.json']]
    paths.extend([gds, ROOT/info['netlist'], ROOT/audit['report'], ROOT/'requirements.json'])
    identity = dict(baseline=str(layout.relative_to(ROOT)), nominal_original_storage_pf=4,
        nominal_added_storage_pf=12, nominal_total_storage_pf=16,
        inputs=dict(proofs, **{str(p.relative_to(ROOT)): digest(p) for p in paths}),
        code={n: digest(ROOT/'scripts'/n) for n in [NAME, 'dll_campaign.py', 'dll_candidate_library.py',
            'layout.py', 'spice_library.py', 'receiver_static_diagnosis.py']},
        scope='One source-only storage-capacitor correction. Measured native G/Y estimates motivate it; new layout/extraction, all PVT margins, native acquisition/steps/recovery/readiness and OTA checks remain required. No automatic promotion.')
    root = ROOT/'build/diagnostics/dll_compensation'/hashlib.sha256(
        json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    source = transform((layout/'candidate.spice').read_text())
    root.mkdir(parents=True, exist_ok=True); target = root/'candidate.spice'
    if target.exists() and target.read_text() != source:
        raise ValueError('Prepared compensation source changed')
    if not target.exists():
        target.write_text(source)
    capture_manifest(root/'manifest.json', dict(identity=identity, qualified_phy=False,
        files={'candidate.spice': digest(target)}))
    return root


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('layout', type=Path)
    p.add_argument('observations', nargs=3, type=Path); a = p.parse_args()
    print(prepare(a.layout.resolve(), [p.resolve() for p in a.observations]), flush=True)
