#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Route and DRC/LVS every checked driver finger-bank recipe in isolation."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import shutil

import driver_bank_geometry as geometry
import probe_driver_finger_pcells as source
from layout import qualify
from receiver_static_diagnosis import capture_manifest

ROOT = Path(__file__).resolve().parents[1]
sha = source.sha


def build(parent):
    if not parent.is_relative_to(ROOT / 'build/diagnostics/driver_finger_pcells'):
        raise ValueError('Use the complete physical finger-interface probe')
    r = json.loads((parent / 'summary.json').read_text())
    if (parent.name != hashlib.sha256(json.dumps(r['identity'], sort_keys=True).encode()).hexdigest()[:16] or
            r.get('interface_checks_passed') is not True or
            any(sha(parent / n) != h for n,h in r['files'].items())):
        raise ValueError('Physical finger-interface evidence changed')
    ready = [ROOT / n for n in r['identity']['inputs']
             if Path(n).is_relative_to('build/diagnostics/driver_shape_source_verification') and Path(n).name == 'summary.json']
    if len(ready) != 1:
        raise ValueError('Require the exact complete source-readiness receipt')
    source.source_ready(ready[0])
    code = ['connect_driver_finger_banks.py', 'driver_bank_geometry.py', 'driver_finger_banks.py',
            'probe_driver_finger_pcells.py', 'layout.py', 'lvs_utils.py', 'dll_campaign.py', 'receiver_static_diagnosis.py']
    inputs = dict(r['identity']['inputs'])
    inputs[str((parent / 'summary.json').relative_to(ROOT))] = sha(parent / 'summary.json')
    inputs.update({str((parent / n).relative_to(ROOT)):h for n,h in r['files'].items()})
    identity = dict(parent=str(parent.relative_to(ROOT)), inputs=inputs,
        code={n:sha(ROOT / 'scripts' / n) for n in code}, technology=r['identity']['technology'],
        scope='Connected four-terminal primitive banks, retaining independent original '
              'MOS fingers. DRC/LVS against every original finger before any inverter '
              'tile or complete driver. No macro/native, power/stress or PHY admission.')
    out = ROOT / 'build/diagnostics/driver_connected_banks' / hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True, exist_ok=True)

    def unchanged():
        if (any(sha(ROOT / n) != h for n,h in inputs.items()) or
                any(sha(ROOT / 'scripts' / n) != h for n,h in identity['code'].items()) or
                any(sha(Path(n)) != h for n,h in identity['technology'].items())):
            raise ValueError('Connected bank context changed')

    with (out / '.execution.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        unchanged()
        if (out / 'summary.json').exists():
            old = json.loads((out / 'summary.json').read_text())
            if old['identity'] != identity or any(sha(out / n) != h for n,h in old['files'].items()):
                raise ValueError('Connected bank outputs changed')
            return out
        if (out / 'manifest.json').exists():
            raise ValueError('Prior partial connected-bank build retained')
        capture_manifest(out / 'manifest.json', dict(identity=identity, qualified_phy=False))
        results = []
        for row in r['cells']:
            cell = row['cell']
            shutil.copyfile(parent / (cell + '.mag'), out / (cell + '.mag'))
            name = 'bank_' + cell
            info = geometry.write(out, name, cell, row['info'], row['recipe'])
            info.update(qualify(out, name))
            results.append(dict(name=name, recipe=row['recipe'], **info))
            print(name, info['drc_count'], info['lvs_passed'], flush=True)
        unchanged()
        files = {p.name:sha(p) for p in out.iterdir() if p.is_file() and p.name != '.execution.lock' and p.name != 'summary.json'}
        capture_manifest(out / 'summary.json', dict(identity=identity, banks=results,
            passed=all(x['passed'] for x in results), files=files, qualified_phy=False,
            physical_admission=False, complete_driver=False))
    return out


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('parent', type=Path)
    args = parser.parse_args()
    print(build(args.parent.resolve()), flush=True)
