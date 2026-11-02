#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Build the five distinct inverter tiles used by the source-verified driver."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import shutil

import driver_inverter_geometry as geometry
import driver_finger_banks as banks
import probe_driver_finger_pcells as source
from layout import circuits, flatten, qualify
from receiver_static_diagnosis import capture_manifest

ROOT = Path(__file__).resolve().parents[1]
sha = source.sha


def inverter_pairs(devices):
    """Find original CMOS inverters by shared D/G and supply-tied S/B."""
    pairs = []
    for p in devices:
        if 'pfet' not in p['model'] or p['nodes'][2:] not in [['VDDIO', 'VDDIO'], ['VDDD', 'VDDD']]:
            continue
        matches = [n for n in devices if 'nfet' in n['model'] and
                   n['nodes'][:2] == p['nodes'][:2] and n['nodes'][2:] == ['VSS', 'VSS']]
        if len(matches) > 1:
            raise ValueError('Ambiguous CMOS inverter pair')
        if matches:
            pairs.append((p, matches[0]))
    return pairs


def build(parent):
    if not parent.is_relative_to(ROOT / 'build/diagnostics/driver_connected_banks'):
        raise ValueError('Require connected bank evidence')
    r = json.loads((parent / 'summary.json').read_text())
    if (parent.name != hashlib.sha256(json.dumps(r['identity'], sort_keys=True).encode()).hexdigest()[:16] or
            r.get('passed') is not True or len(r['banks']) != 19 or
            not all(x['passed'] and x['drc_count'] == '0' and x['lvs_passed'] for x in r['banks']) or
            any(sha(parent / n) != h for n,h in r['files'].items())):
        raise ValueError('Require all nineteen unchanged DRC/LVS-qualified banks')
    inputs = dict(r['identity']['inputs'])
    inputs[str((parent / 'summary.json').relative_to(ROOT))] = sha(parent / 'summary.json')
    inputs.update({str((parent / n).relative_to(ROOT)):h for n,h in r['files'].items()})
    ready = [ROOT / n for n in inputs if Path(n).is_relative_to('build/diagnostics/driver_shape_source_verification') and Path(n).name == 'summary.json']
    if len(ready) != 1:
        raise ValueError('Require exact source readiness')
    campaign, _, _ = source.source_ready(ready[0])
    text = (campaign / 'tt_25_negative_op/source.spice').read_text()
    devices = banks.group(flatten(circuits(text), source.recipe.taper.TOP)[1])
    pairs = inverter_pairs(devices)
    unique = {tuple(source.key(x) for x in pair):pair for pair in pairs}
    if len(pairs) != 9 or len(unique) != 5:
        raise ValueError('Expected nine original inverters in five physical recipes')
    library = {tuple(x['recipe'][n] for n in ['model', 'w', 'l', 'nf']): x for x in r['banks']}
    code = ['build_driver_inverter_tiles.py', 'driver_inverter_geometry.py', 'driver_bank_geometry.py',
            'driver_finger_banks.py', 'probe_driver_finger_pcells.py', 'layout.py', 'lvs_utils.py', 'receiver_static_diagnosis.py']
    identity = dict(parent=str(parent.relative_to(ROOT)), inputs=inputs,
        technology=r['identity']['technology'], code={n:sha(ROOT / 'scripts' / n) for n in code},
        recipes=[[list(part) for part in k] for k in sorted(unique)],
        scope='Local P/N inverter tiles only, with original fingers and supply-tied bodies. '
              'No complete driver, native electrical or PHY admission.')
    out = ROOT / 'build/diagnostics/driver_inverter_tiles' / hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True, exist_ok=True)

    def unchanged():
        if (any(sha(ROOT / n) != h for n,h in inputs.items()) or
                any(sha(ROOT / 'scripts' / n) != h for n,h in identity['code'].items()) or
                any(sha(Path(n)) != h for n,h in identity['technology'].items())):
            raise ValueError('Inverter tile context changed')

    with (out / '.execution.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        unchanged()
        if (out / 'summary.json').exists():
            old = json.loads((out / 'summary.json').read_text())
            if old['identity'] != identity or any(sha(out / n) != h for n,h in old['files'].items()):
                raise ValueError('Inverter tile evidence changed')
            return out
        if (out / 'manifest.json').exists():
            raise ValueError('Prior partial tile build retained')
        capture_manifest(out / 'manifest.json', dict(identity=identity, qualified_phy=False))
        for path in parent.glob('*.mag'):
            shutil.copyfile(path, out / path.name)
        results = []
        for key in sorted(unique):
            name = 'inv_' + hashlib.sha256(json.dumps(key).encode()).hexdigest()[:12]
            info = geometry.write(out, name, library[key[0]], library[key[1]])
            info.update(qualify(out, name))
            results.append(dict(name=name, recipe=key, **info))
            print(name, info['drc_count'], info['lvs_passed'], flush=True)
        unchanged()
        files = {p.name:sha(p) for p in out.iterdir() if p.is_file() and p.name not in ['.execution.lock', 'summary.json']}
        capture_manifest(out / 'summary.json', dict(identity=identity, tiles=results, inverter_instances=len(pairs),
            passed=all(x['passed'] for x in results), files=files, qualified_phy=False,
            physical_admission=False, complete_driver=False))
    return out


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('parent', type=Path)
    args = parser.parse_args()
    print(build(args.parent.resolve()), flush=True)
