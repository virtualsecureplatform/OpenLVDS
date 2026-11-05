#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Measure isolated native MOS junctions before tied-terminal reconstruction.

Each D/G/S/B remains separate during this measurement. No bank or RC model is
corrected here; this supplies independent actual-geometry evidence for a fix.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import layout
import native_bank_inventory_v51 as inventory
from inspect_mim_switch_2x3_pcells_v2 import tools, sha

ROOT = layout.ROOT


def run(parent):
    pi = json.loads((parent/'manifest.json').read_text())
    if (parent.parent != ROOT/'build/diagnostics/moscap_fine_pcells_v77'
        or parent.name != hashlib.sha256(json.dumps(pi, sort_keys=True).encode()).hexdigest()[:16]
        or any(sha(ROOT/n) != h for n, h in pi['code'].items())
        or any(sha(Path(n)) != h for n, h in pi['pdk_files'].items())
        or tools() != pi['tools']):
        raise ValueError('Native primitive inspection changed')
    source = json.loads((parent/'summary.json').read_text())
    devices = [d for d in source['library'] if 'fet_' in d['model']]
    for d in devices:
        if sha(parent/(d['cell']+'.mag')) != d['sha256']:
            raise ValueError('Native primitive geometry changed')
    paths = [parent/'manifest.json', parent/'summary.json',
             *[parent/(d['cell']+'.mag') for d in devices], Path(__file__),
             Path(layout.__file__), Path(inventory.__file__), ROOT/'scripts/lvs_utils.py',
             ROOT/'scripts/inspect_mim_switch_2x3_pcells_v2.py']
    identity = dict(version='isolated-native-gate-cap-junction-measurement-v85.1',
                    inputs={str(p.relative_to(ROOT)): sha(p) for p in paths}, tools=tools())
    out = ROOT/'build/diagnostics/moscap_primitive_junctions_v85'/hashlib.sha256(
        json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True, exist_ok=False)
    (out/'manifest.json').write_text(json.dumps(identity, indent=2)+'\n')
    print(out, flush=True); rows = []
    for d in devices:
        top = d['cell']; folder = out/top; folder.mkdir()
        shutil.copy2(parent/(top+'.mag'), folder/(top+'.mag'))
        # The raw PCell gate landing alone is below met1 minimum area.
        # Add the same gate escape used in the qualified fine-cell layout;
        # this changes only metal, retaining the diffusion junction geometry.
        _, x, y = d['geometry']['ports']['G']
        g = layout.Geometry(); g.wire('metal1', x, y, x, y+.3, .18)
        path = folder/(top+'.mag'); text = path.read_text()
        marker = '<< metal1 >>\n'
        if text.count(marker) != 1:
            raise ValueError('Unexpected native PCell metal section')
        rects = ''.join('rect '+' '.join(map(str, r))+'\n' for r in g.layers['metal1'])
        path.write_text(text.replace(marker, marker+rects, 1))
        commands = [f'load {top}']
        for i, port in enumerate(('D', 'G', 'S', 'B'), 1):
            _, x, y = d['geometry']['ports'][port]
            commands += [f'box values {x-.05}um {y-.05}um {x+.05}um {y+.05}um', f'port make {i}']
        commands.append(f'save {top}')
        layout.invoke_magic(folder, '\n'.join(commands), 'ports')
        reference = (f'.subckt {top} D G S B\nX0 D G S B {d["model"]} '
                     f'w={d["width_um"]} l={d["length_um"]}\n.ends {top}\n')
        (folder/(top+'.sch.spice')).write_text(reference)
        geometry = layout.qualify(folder, top)
        if not geometry['passed']:
            raise ValueError('Isolated primitive DRC/LVS failed')
        _, expected = inventory.native_leaves(reference, top)
        text = re.sub(r'\n[ \t]*\+[ \t]*', ' ', (folder/(top+'.lvs.spice')).read_text())
        _, actual = inventory.native_leaves(text, top+'_flat')
        parameters = inventory.compare_parameters(expected, actual)
        if len(actual) != 1 or set(actual[0]['nodes']) != {'D', 'G', 'S', 'B'}:
            raise ValueError('Isolated primitive lost separate terminal identity')
        rows.append(dict(primitive=d, geometry=geometry, parameters=parameters, actual=actual[0]))
    if any(sha(ROOT/n) != h for n, h in identity['inputs'].items()):
        raise ValueError('Primitive measurement inputs changed')
    report = dict(rows=rows, isolated_primitive_junction_measurements_passed=True,
                  corrected_rc_model_qualified=False, qualified_phy=False)
    report['files'] = {str(p.relative_to(out)): sha(p) for p in out.rglob('*') if p.is_file()}
    (out/'summary.json').write_text(json.dumps(report, indent=2)+'\n')
    print(out, flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('parent', type=Path)
    run(p.parse_args().parent.resolve())
