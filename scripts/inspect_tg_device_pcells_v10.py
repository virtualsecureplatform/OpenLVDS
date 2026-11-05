#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Inspect candidate primitive geometry; never select or qualify a bank.

Generate native PCells, write GDS, import GDS in a fresh Magic process and
extract each single transistor. These junctions belong to those standalone
PCell diffusions, not yet to any routed TG or modified inverter.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import inspect_mim_switch_2x3_pcells_v2 as environment
import tg_driver_experiment_v9 as circuit

ROOT = environment.ROOT
VERSION = 'native-tg-and-driver-primitive-gds-geometry-inspection-v10.1'
CONTEXT = 'tg_device_pcells_v10'
sha = environment.sha


def candidates():
    widths = set()
    n, p = circuit.baseline.previous.PROFILES[circuit.baseline.PROFILE]
    for _, factor in circuit.PROFILES.values():
        widths.update({('sky130_fd_pr__nfet_01v8', n*factor), (circuit.REGULAR, p*factor)})
    widths.update({(circuit.HVT, 1.), (circuit.REGULAR, 1.)})
    return [dict(model=m, w=w, l=.15, cell='p'+hashlib.sha256(f'{m}:{w}:0.15'.encode()).hexdigest()[:12])
            for m, w in sorted(widths)]


def prepare():
    pdk = Path(os.environ['PDK_ROOT'])/'sky130A/libs.tech/magic'
    code = [Path(__file__), Path(environment.__file__), Path(environment.layout.__file__),
            Path(environment.unit.__file__), Path(circuit.__file__), Path(circuit.baseline.__file__),
            Path(circuit.baseline.previous.__file__), ROOT/'scripts/lvs_utils.py', ROOT/'scripts/spice_library.py',
            ROOT/'scripts/build_compound_drivers_v3.py', ROOT/'build/apptainer/openlvds.sif.sha256']
    identity = dict(version=VERSION, candidates=candidates(), tools=environment.tools(),
                    code={str(p.relative_to(ROOT)): sha(p) for p in code},
                    technology={str(p): sha(p) for p in sorted(pdk.rglob('*')) if p.is_file()})
    out = ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True, exist_ok=False)
    (out/'manifest.json').write_text(json.dumps(dict(identity=identity, qualified_phy=False), indent=2)+'\n')
    return out


def bound(out):
    i = json.loads((out/'manifest.json').read_text())['identity']
    if (out.parent != ROOT/'build/diagnostics'/CONTEXT or i['version'] != VERSION
            or i['candidates'] != candidates() or i['tools'] != environment.tools()
            or out.name != hashlib.sha256(json.dumps(i, sort_keys=True).encode()).hexdigest()[:16]
            or any(sha(ROOT/n) != h for n, h in i['code'].items())
            or any(sha(Path(n)) != h for n, h in i['technology'].items())):
        raise ValueError('Primitive PCell inspection context changed')
    return i


def run(out):
    i = bound(out)
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (out/'pcells.tcl').exists() or (out/'summary.json').exists():
            raise ValueError('Retain prior or partial primitive geometry inspection')
        commands = []
        for c in i['candidates']:
            model, name = c['model'], c['cell']
            commands += [f'load {name} -silent', 'box values 0 0 0 0', f'set p [sky130::{model}_defaults]',
                         f'dict set p w {c["w"]}', f'dict set p l {c["l"]}', 'dict set p botc 0',
                         f'sky130::{model}_draw $p', f'save {name}', f'gds write {name}.gds']
        environment.layout.invoke_magic(out, '\n'.join(commands), 'pcells')
        fresh = ['gds readonly true']
        for c in i['candidates']:
            name = c['cell']
            fresh += [f'gds read {name}.gds', f'load {name}', 'select top cell', 'extract all',
                      'ext2spice lvs', f'ext2spice -o {name}.gds.spice {name}.ext']
        environment.layout.invoke_magic(out, '\n'.join(fresh), 'fresh_gds_extract')
        observed = []
        for c in i['candidates']:
            name = c['cell']; text = (out/(name+'.gds.spice')).read_text()
            text = re.sub(r'\n\+\s*', ' ', text)
            devices = [line.split() for line in text.splitlines()
                       if line.startswith(('X', 'M')) and 'sky130_fd_pr__' in line]
            if len(devices) != 1 or devices[0][5] != c['model']:
                raise ValueError('Fresh GDS must extract exactly the requested native single MOS')
            params = dict(w.split('=', 1) for w in devices[0][6:] if '=' in w)
            if (set(('w', 'l', 'ad', 'as', 'pd', 'ps'))-set(params)
                    or abs(float(params['w'])-c['w']) > 1e-9 or abs(float(params['l'])-c['l']) > 1e-9
                    or any(float(params[k]) <= 0 for k in ('ad', 'as', 'pd', 'ps'))):
                raise ValueError('Fresh native primitive geometry is incomplete or mismatched')
            observed.append(dict(recipe=c, geometry=environment.layout.pcell_info(out/(name+'.mag')),
                                 fresh_gds_native_parameters=params, native_terminals=devices[0][1:5]))
        bound(out)
        files = {p.name: sha(p) for p in out.iterdir() if p.is_file() and p.name not in ('.execution.lock', 'manifest.json')}
        report = dict(identity=i, cells=observed, files=files, primitive_gds_native_geometry_verified=True,
                      routed_tg=False, modified_inverter_layout_verified=False, macro_drc_lvs_passed=False,
                      electrical_qualification_passed=False, qualified_phy=False,
                      scope='Standalone candidate primitive PCells and fresh-GDS native extraction only; no routed TG/inverter, macro DRC/LVS, circuit RC or electrical equivalence')
        (out/'summary.json').write_text(json.dumps(report, indent=2)+'\n')
        return out


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('action', choices=['prepare', 'run', 'campaign']); p.add_argument('artifact', type=Path, nargs='?')
    a = p.parse_args()
    if a.action in ('prepare', 'campaign'):
        out = prepare(); print(out, flush=True)
    elif a.artifact is None:
        p.error('Provide a prepared artifact')
    else:
        out = a.artifact.resolve()
    if a.action in ('run', 'campaign'):
        print(run(out), flush=True)
