#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Inspect real multi-finger PCell interfaces only after full source verification."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path

import driver_finger_banks as banks
import driver_geometric_shape as recipe
import driver_source_campaign as campaign
from layout import circuits, flatten, invoke_magic, pcell_info
from receiver_static_diagnosis import capture_manifest

ROOT = Path(__file__).resolve().parents[1]
sha = campaign.sha


def source_ready(receipt):
    if (receipt.name != 'summary.json' or
            not receipt.is_relative_to(ROOT / 'build/diagnostics/driver_shape_source_verification')):
        raise ValueError('Use the complete source verification receipt')
    r = json.loads(receipt.read_text())
    if (receipt.parent.name != hashlib.sha256(json.dumps(r, sort_keys=True).encode()).hexdigest()[:16] or
            r.get('source_waveform_ready') is not True or r.get('required_cases') != 30 or
            r.get('required_pvt') != 15 or r.get('physical_admission') is not False or
            any(sha(ROOT / n) != h for n, h in r['proofs'].items())):
        raise ValueError('Full source readiness evidence changed or incomplete')
    source = ROOT / r['campaign']
    m = campaign.context(source, recipe)
    if m['identity']['stage'] != 'full' or sha(source / 'tt_25_negative_op/source.spice') != r['source_sha256']:
        raise ValueError('Source verification selected another circuit')
    return source, m, r


def key(bank):
    return bank['model'], bank['params']['w'], bank['params']['l'], bank['nf']


def build(receipt):
    source, m, r = source_ready(receipt)
    text = (source / 'tt_25_negative_op/source.spice').read_text()
    ports, devices = flatten(circuits(text), recipe.taper.TOP)
    grouped = banks.group(devices)
    unique = {key(b): b for b in grouped if banks.mos(b)}
    pdk = Path(os.environ['PDK_ROOT']) / 'sky130A/libs.tech/magic'
    code = ['probe_driver_finger_pcells.py', 'driver_finger_banks.py', 'layout.py',
            'lvs_utils.py', 'receiver_static_diagnosis.py', 'dll_campaign.py']
    technology = {str(p):sha(p) for p in [pdk / 'sky130A.magicrc', pdk / 'sky130A.tcl', pdk / 'sky130A.tech']}
    inputs = dict(r['proofs'])
    inputs[str(receipt.relative_to(ROOT))] = sha(receipt)
    rows = json.loads((source / 'summary.json').read_text())['results']
    identity = dict(source=str(source.relative_to(ROOT)), inputs=inputs, technology=technology,
        code={n:sha(ROOT / 'scripts' / n) for n in code},
        cells=[dict(model=k[0], w=k[1], l=k[2], nf=k[3], parameters=banks.pcell_parameters(unique[k])) for k in sorted(unique)],
        source_observations=dict(mean_io_power_w=[min(x['metrics']['mean_supply_power_w']['io'] for x in rows),
            max(x['metrics']['mean_supply_power_w']['io'] for x in rows)],
            max_added_terminal_v=max(d[v] for x in rows for d in x['metrics']['added_mos_stress']
                for v in ['max_abs_vgs','max_abs_vgd','max_abs_vds','max_abs_vbs'])),
        scope='Post-source-gate PCell interface probe only. Same original physical '
              'finger widths/lengths/terminal groups, guarded one-row arrays and separate '
              'gate contacts. No macro routing, DRC/LVS, extraction, native, power/stress '
              'or PHY admission. Separate diffusions are retained; array/guard '
              'parasitics still require native checks.')
    out = ROOT / 'build/diagnostics/driver_finger_pcells' / hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True, exist_ok=True)

    def unchanged():
        source_ready(receipt)
        if any(sha(Path(n)) != h for n, h in technology.items()) or any(sha(ROOT / 'scripts' / n) != h for n, h in identity['code'].items()):
            raise ValueError('Physical PCell context changed')

    with (out / '.execution.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (out / 'summary.json').exists():
            old = json.loads((out / 'summary.json').read_text())
            if old['identity'] != identity or any(sha(out / n) != h for n, h in old['files'].items()):
                raise ValueError('Existing PCell probe changed')
            unchanged()
            return out
        if any((out / n).exists() for n in ['pcells.tcl','pcells.log']):
            raise ValueError('Prior partial PCell probe retained')
        capture_manifest(out / 'manifest.json', dict(identity=identity, qualified_phy=False))
        body = []
        cells = {}
        for row in identity['cells']:
            k = row['model'], row['w'], row['l'], row['nf']
            name = 'p' + hashlib.sha256(json.dumps(k).encode()).hexdigest()[:12]
            cells[name] = row
            body += [f'load {name} -silent', 'box values 0 0 0 0', f'set p [sky130::{row["model"]}_defaults]']
            body += [f'dict set p {n} {v}' for n, v in row['parameters'].items()]
            body += [f'sky130::{row["model"]}_draw $p', f'save {name}']
        invoke_magic(out, '\n'.join(body), 'pcells')
        observed = []
        for name, row in cells.items():
            info = pcell_info(out / (name + '.mag'))
            roles = banks.terminal_groups(info['ports'], row['nf'])
            observed.append(dict(cell=name, recipe=row, info=info, terminals=roles))
        unchanged()
        files = {p.name:sha(p) for p in [out / 'pcells.tcl', out / 'pcells.log'] + sorted(out.glob('*.mag'))}
        capture_manifest(out / 'summary.json', dict(identity=identity, files=files, cells=observed,
            interface_checks_passed=True, source_devices=len(devices), source_mos_fingers=sum(banks.mos(d) for d in devices),
            banked_placements=len(grouped), ports=ports, qualified_phy=False, physical_admission=False))
    return out


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('receipt', type=Path)
    args = parser.parse_args()
    print(build(args.receipt.resolve()), flush=True)
