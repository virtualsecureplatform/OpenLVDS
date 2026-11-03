#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Fresh compensated-driver layout, gated by actual full source qualification."""
import argparse
from collections import Counter
from decimal import Decimal
import fcntl
import hashlib
import json
from pathlib import Path
import shutil

import driver_finger_banks as banks
import driver_local_cmfb_geometry as geometry
import probe_driver_finger_pcells as original_source
import qualify_driver_cmfb_lead_source as qualification
from layout import circuits, flatten, invoke_magic, qualify
from receiver_static_diagnosis import capture_manifest

ROOT = Path(__file__).resolve().parents[1]
sha = qualification.sha
TOP = original_source.recipe.taper.TOP


def source_ready(receipt):
    if (receipt.name != 'summary.json' or not receipt.is_relative_to(
            ROOT / 'build/diagnostics/driver_cmfb_lead_source_verification')):
        raise ValueError('Require the actual compensated source verification receipt')
    report = json.loads(receipt.read_text())
    if (receipt.parent.name != hashlib.sha256(json.dumps(report, sort_keys=True).encode()).hexdigest()[:16]
            or report.get('recipe') != qualification.NEW
            or report.get('source_waveform_ready') is not True
            or report.get('required_cases') != 30 or report.get('required_pvt') != 15
            or report.get('physical_admission') is not False or report.get('qualified_phy') is not False):
        raise ValueError('Require all thirty actual schematic cases before physical preparation')
    campaign = ROOT / report['campaign']
    # Recompute the complete scientific receipt, not just its pass flag.
    if qualification.verify(campaign) != receipt:
        raise ValueError('Independent actual source remeasurement changed')
    return campaign, report


def checked_devices(original, candidate):
    if candidate != qualification.lead.transform(original, 'lvds_cmfb'):
        raise ValueError('Physical candidate differs from the single admitted compensation change')
    ports, old = flatten(circuits(original), TOP)
    new_ports, new = flatten(circuits(candidate), TOP)
    if (new_ports != ports or len(old) != 320 or len(new) != 321
            or sum(banks.mos(d) for d in old) != 302
            or Counter(banks.signature(d) for d in old if banks.mos(d)) !=
                Counter(banks.signature(d) for d in new if banks.mos(d))):
        raise ValueError('Compensation changed an original MOS, terminal or public port')
    def passives(devices):
        return Counter((d['model'], Decimal(d['params']['w']), Decimal(d['params']['l']))
            for d in devices if not banks.mos(d))
    expected = passives(old)
    expected[('sky130_fd_pr__res_high_po_0p35', Decimal('.35'), Decimal('1.25'))] += 1
    if passives(new) != expected:
        raise ValueError('Require exactly one additional PDK resistor and all original passives')
    return ports, new, banks.group(new)


def tile_context(parent):
    if not parent.is_relative_to(ROOT / 'build/diagnostics/driver_inverter_tiles'):
        raise ValueError('Require checked original driver inverter tiles')
    report = json.loads((parent / 'summary.json').read_text())
    if (parent.name != hashlib.sha256(json.dumps(report['identity'], sort_keys=True).encode()).hexdigest()[:16]
            or report.get('passed') is not True or len(report['tiles']) != 5
            or report['inverter_instances'] != 9 or not all(
                x['passed'] and x['drc_count'] == '0' and x['lvs_passed'] for x in report['tiles'])
            or any(sha(parent / n) != h for n, h in report['files'].items())
            or any(sha(ROOT / n) != h for n, h in report['identity']['inputs'].items())):
        raise ValueError('Require unchanged DRC/LVS-qualified original tiles')
    inputs = dict(report['identity']['inputs'])
    inputs[str((parent / 'summary.json').relative_to(ROOT))] = sha(parent / 'summary.json')
    inputs.update({str((parent / n).relative_to(ROOT)): h for n, h in report['files'].items()})
    ready = [ROOT / n for n in inputs if Path(n).is_relative_to(
        'build/diagnostics/driver_shape_source_verification') and Path(n).name == 'summary.json']
    if len(ready) != 1:
        raise ValueError('Require the exact original source underlying the reusable tiles')
    original, _, _ = original_source.source_ready(ready[0])
    bank_parent = ROOT / report['identity']['parent']
    bank_report = json.loads((bank_parent / 'summary.json').read_text())
    if (bank_parent.name != hashlib.sha256(json.dumps(bank_report['identity'], sort_keys=True).encode()).hexdigest()[:16]
            or bank_report.get('passed') is not True or not all(
            x['passed'] and x['drc_count'] == '0' and x['lvs_passed'] for x in bank_report['banks'])
            or any(sha(bank_parent / n) != h for n, h in bank_report['files'].items())):
        raise ValueError('Reusable MOS banks changed or failed')
    inputs[str((bank_parent / 'summary.json').relative_to(ROOT))] = sha(bank_parent / 'summary.json')
    inputs.update({str((bank_parent / n).relative_to(ROOT)): h for n, h in bank_report['files'].items()})
    library = {tuple(x['recipe'][n] for n in ['model', 'w', 'l', 'nf']): x for x in bank_report['banks']}
    tiles = {tuple(tuple(part) for part in x['recipe']): x for x in report['tiles']}
    return report, inputs, original, library, tiles


def build(receipt, parent):
    # The new circuit must qualify before any Magic preparation or dispatch.
    campaign, ready = source_ready(receipt)
    report, inputs, original, library, tiles = tile_context(parent)
    text = (campaign / 'tt_25_negative_op/source.spice').read_text()
    ports, devices, grouped = checked_devices(
        (original / 'tt_25_negative_op/source.spice').read_text(), text)
    if any(original_source.key(d) not in library for d in grouped if banks.mos(d)):
        raise ValueError('New circuit requires an unqualified MOS bank recipe')
    inputs.update(ready['proofs'])
    inputs[str(receipt.relative_to(ROOT))] = sha(receipt)
    code = dict(report['identity']['code'])
    code.update({n: sha(ROOT / 'scripts' / n) for n in [Path(__file__).name,
        'qualify_driver_cmfb_lead_source.py', 'probe_driver_cmfb_lead.py',
        'driver_local_cmfb_geometry.py', 'driver_compact_geometry.py',
        'build_driver_inverter_tiles.py', 'driver_inverter_geometry.py']})
    identity = dict(parent=str(parent.relative_to(ROOT)), source=str(campaign.relative_to(ROOT)),
        source_readiness=str(receipt.relative_to(ROOT)), inputs=inputs, code=code,
        technology=report['identity']['technology'], source_sha256=hashlib.sha256(text.encode()).hexdigest(),
        scope='Actual fully source-qualified lead-compensated circuit: all 302 original MOS '
        'fingers and eighteen original passives plus one PDK compensation resistor. '
        'Reuse qualified MOS/inverter recipes only after exact source-change and '
        'MOS-topology checks. Fresh complete placement/routing, DRC and strict LVS '
        'against this new circuit; no native electrical or PHY admission.')
    out = ROOT / 'build/diagnostics/driver_compact_layout' / hashlib.sha256(
        json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True, exist_ok=True)

    def unchanged():
        if (any(sha(ROOT / n) != h for n, h in inputs.items())
                or any(sha(ROOT / 'scripts' / n) != h for n, h in code.items())
                or any(sha(Path(n)) != h for n, h in identity['technology'].items())):
            raise ValueError('Compensated physical context changed')

    with (out / '.execution.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        unchanged()
        if (out / 'summary.json').exists():
            old = json.loads((out / 'summary.json').read_text())
            if old['identity'] != identity or any(sha(out / n) != h for n, h in old['files'].items()):
                raise ValueError('Compensated layout output changed')
            return out
        if (out / 'manifest.json').exists():
            raise ValueError('Prior partial compensated layout retained')
        capture_manifest(out / 'manifest.json', dict(identity=identity, qualified_phy=False))
        (out / 'candidate.spice').write_text(text)
        for path in parent.glob('*.mag'):
            shutil.copyfile(path, out / path.name)
        body, cells = [], set()
        for device in grouped:
            if banks.mos(device):
                continue
            key = device['model'], device['params']['w'], device['params']['l']
            cell = 'pass_' + hashlib.sha256(json.dumps(key).encode()).hexdigest()[:12]
            if cell in cells:
                continue
            cells.add(cell)
            body += [f'load {cell} -silent', 'box values 0 0 0 0',
                f'set p [sky130::{device["model"]}_defaults]',
                f'dict set p w {key[1]}', f'dict set p l {key[2]}',
                f'sky130::{device["model"]}_draw $p', f'save {cell}']
        invoke_magic(out, '\n'.join(body), 'passive_pcells')
        wrappers = {}
        for index, device in enumerate(d for d in grouped if not banks.mos(d)):
            key = device['model'], device['params']['w'], device['params']['l']
            cell = 'pass_' + hashlib.sha256(json.dumps(key).encode()).hexdigest()[:12]
            wrappers[device['name']] = geometry.passive(out, 'passive_' + str(index), cell, device)
        info = geometry.write(out, TOP, ports, devices, grouped, library, tiles, wrappers)
        info['scope'] = identity['scope']
        info.update(qualify(out, TOP))
        unchanged()
        files = {p.name: sha(p) for p in out.iterdir() if p.is_file()
            and p.name not in ['.execution.lock', 'summary.json']}
        capture_manifest(out / 'summary.json', dict(identity=identity,
            source_sha256=identity['source_sha256'], designs={TOP: info},
            passed=info['passed'], files=files, physical_admission=False, qualified_phy=False))
    return out


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('receipt', type=Path)
    p.add_argument('--tiles', type=Path, required=True)
    args = p.parse_args()
    print(build(args.receipt.resolve(), args.tiles.resolve()), flush=True)
