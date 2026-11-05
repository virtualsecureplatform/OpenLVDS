#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Compare ordinary/RC junction allocation with Magic's documented -d option.

Copies the retained failed v79 extraction; never rewrites or admits that model.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import layout
from inspect_mim_switch_2x3_pcells_v2 import sha, tools

ROOT = layout.ROOT


def run(parent):
    if parent.parent != ROOT/'build/diagnostics/moscap_fine_rc_v79':
        raise ValueError('Require retained v79 fine-cell extraction')
    manifest = json.loads((parent/'manifest.json').read_text())
    physical = ROOT/manifest['parent']
    result = json.loads((physical/'summary.json').read_text())
    top = Path(result['gds']).stem
    gds = ROOT/result['gds']
    import extract_native_flat_v4 as extractor
    digest = hashlib.sha256(gds.read_bytes()+Path(extractor.__file__).read_bytes()).hexdigest()
    rc = ROOT/'build/extracted'/digest[:16]/top
    native = parent/'native'
    files = [*native.glob('*.ext'), *rc.glob('*.ext'), parent/'manifest.json',
             Path(__file__), Path(layout.__file__), ROOT/'scripts/lvs_utils.py',
             ROOT/'scripts/inspect_mim_switch_2x3_pcells_v2.py']
    identity = dict(version='gate-cap-junction-allocation-diagnostic-v80.1',
                    inputs={str(p.relative_to(ROOT)): sha(p) for p in files}, tools=tools())
    out = ROOT/'build/diagnostics/moscap_junction_partition_v80'/hashlib.sha256(
        json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True, exist_ok=False)
    (out/'manifest.json').write_text(json.dumps(identity, indent=2)+'\n')
    print(out, flush=True); rows = []
    for kind, source, name in [('ordinary', native, top+'_flat'), ('rc', rc, top+'_rcx')]:
        for distributed in (False, True):
            folder = out/(kind+('_distributed' if distributed else '_default')); folder.mkdir()
            for file in source.glob('*.ext'):
                shutil.copy2(file, folder/file.name)
            command = ('ext2spice lvs\next2spice hierarchy off\next2spice merge none\n'
                       'ext2spice extresist '+('on' if kind == 'rc' else 'off')+'\n'
                       'ext2spice '+('-d ' if distributed else '')+f'-o comparison.spice {name}.ext')
            layout.invoke_magic(folder, command, 'junction_partition')
            text = (folder/'comparison.spice').read_text()
            devices = [line for line in text.splitlines() if line.startswith('X')]
            rows.append(dict(kind=kind, distributed=distributed, devices=devices))
    if any(sha(ROOT/n) != h for n, h in identity['inputs'].items()):
        raise ValueError('Junction diagnostic inputs changed')
    (out/'summary.json').write_text(json.dumps(dict(rows=rows, qualified_phy=False,
        scope='Junction-allocation diagnostic only; no model correction or qualification'), indent=2)+'\n')
    print(json.dumps(rows, indent=2), flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('parent', type=Path)
    run(p.parse_args().parent.resolve())
