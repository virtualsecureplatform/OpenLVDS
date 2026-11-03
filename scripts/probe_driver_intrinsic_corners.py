#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Extend the completed ideal-wire TT control to SS25/FF40, without a TT rerun."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import driver_source_campaign as campaign
import probe_driver_compact_native as pilot
import probe_driver_wire_loading as control
from receiver_static_diagnosis import capture_manifest
from spice_probes import ProbeNetwork

ROOT=Path(__file__).resolve().parents[1]
sha=control.sha
NEW='native_device_geometry_ideal_wires_ss25_ff40'
POINTS=[('ss',25),('ff',40)]


def measure(folder):
    return pilot.measure(folder)[0]


def prepare(completed):
    m=control.bound(completed);r=json.loads((completed/'summary.json').read_text())
    if r.get('diagnostic_complete') is not True or r.get('manifest_sha256')!=sha(completed/'manifest.json'):
        raise ValueError('Complete both audited ideal-wire TT25 cases first')
    paths=[completed/'manifest.json',completed/'summary.json']
    for task in m['tasks']:
        folder=completed/task['id'];row=json.loads((folder/'summary.json').read_text())
        if (row['returncode']!=0 or row['error'] is not None or
                row['manifest_sha256']!=sha(completed/'manifest.json') or
                any(sha(folder/n)!=h for n,h in row['files'].items()) or
                pilot.measure(folder)!=(row['metrics'],row['initial_dc'])):
            raise ValueError('Completed ideal-wire TT25 evidence changed')
        paths += [folder/n for n in set(row['files'])|set(task['files'])|{'summary.json'}]
    parent=ROOT/m['identity']['parent'];pm=pilot.bound(parent)
    model=(completed/'negative_op/source.spice').read_text()
    inputs=dict(m['identity']['inputs']);inputs.update({str(p.relative_to(ROOT)):sha(p) for p in paths})
    tasks=campaign.tasks(POINTS)
    for task in tasks:
        old=parent/task['id'];inputs.update({str((old/n).relative_to(ROOT)):sha(old/n) for n in ['source.spice','bench.cir']})
    code=dict(m['identity']['code']);code.update({n:sha(ROOT/'scripts'/n) for n in
        ['probe_driver_intrinsic_corners.py','driver_source_campaign.py']})
    identity=dict(parent=str(completed.relative_to(ROOT)),inputs=inputs,code=code,simulator=pilot.provenance(),
        recipe=NEW,stage='pilot',points=[list(p) for p in POINTS],scope='Four additional '
        'SS25/FF40 ideal-wire device-geometry controls, both initial polarities, '
        'after completed TT25 controls. Same audited extracted MOS/junction and '
        'intentional PDK passive devices, original source bias, fixed rails and '
        'reference, 100 ohm plus 2 pF/pin, full 80 ns/1 ps fixtures. Existing '
        'generic source-campaign runner and independent remeasurement reused. '
        'No TT rerun, actual wire model, physical selection or PHY admission.')
    out=ROOT/'build/diagnostics/driver_source_pilot'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=True)
    for task in tasks:
        folder=out/task['id'];folder.mkdir(exist_ok=True);old=parent/task['id']
        deck=pilot.fixture((old/'bench.cir').read_text(),old,folder)
        ProbeNetwork(model).validate(deck,['D','P','N'])
        for n,body in [('source.spice',model),('bench.cir',deck)]:
            path=folder/n
            if path.exists() and path.read_text()!=body:raise ValueError('Prepared intrinsic corner control changed')
            if not path.exists():path.write_text(body)
        task['files']={n:sha(folder/n) for n in ['source.spice','bench.cir']}
    capture_manifest(out/'manifest.json',dict(identity=identity,tasks=tasks,qualified_phy=False));return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','verify']);p.add_argument('artifact',type=Path);a=p.parse_args()
    if a.action=='prepare':print(prepare(a.artifact.resolve()),flush=True)
    elif a.action=='run':campaign.run(a.artifact.resolve(),sys.modules[__name__])
    else:
        _,proofs=campaign.verified(a.artifact.resolve(),sys.modules[__name__]);print(json.dumps(dict(verified=True,proofs=len(proofs))),flush=True)
