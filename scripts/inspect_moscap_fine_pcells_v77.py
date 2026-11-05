#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Inspect native PCells for all three complementary gate-cap fine candidates."""
import hashlib
import json
import os
from pathlib import Path
import layout
import lvs_utils
import moscap_fine_unit_v77 as unit
from inspect_mim_switch_2x3_pcells_v2 import tools, sha

ROOT = layout.ROOT


def main():
    pdk = Path(os.environ['PDK_ROOT']) / 'sky130A'
    files = [Path(__file__), Path(unit.__file__), Path(layout.__file__),
             Path(lvs_utils.__file__), ROOT/'scripts/inspect_mim_switch_2x3_pcells_v2.py']
    identity = dict(version='moscap-native-pcell-inspection-v77.1',
                    code={str(p.relative_to(ROOT)): sha(p) for p in files},
                    tools=tools(), pdk_files={str(pdk/'libs.tech/magic/sky130A.magicrc'):
                                             sha(pdk/'libs.tech/magic/sky130A.magicrc')})
    out = ROOT/'build/diagnostics/moscap_fine_pcells_v77'/hashlib.sha256(
        json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True, exist_ok=False)
    (out/'manifest.json').write_text(json.dumps(identity, indent=2)+'\n')
    designs = {p: layout.flatten(layout.circuits(unit.schematic(p)), unit.name(p))
               for p in unit.WIDTHS}
    keys = sorted({layout.primitive_key(d) for _, ds in designs.values() for d in ds})
    commands = []; cells = {}
    for model, w, l in keys:
        cell = 'p'+hashlib.sha256(f'{model}:{w}:{l}'.encode()).hexdigest()[:12]
        cells[model, w, l] = cell
        commands += [f'load {cell} -silent', 'box values 0 0 0 0',
                     f'set p [sky130::{model}_defaults]', f'dict set p w {w}',
                     f'dict set p l {l}']
        if 'fet_' in model:
            commands.append('dict set p botc 0')
        commands += [f'sky130::{model}_draw $p', f'save {cell}']
    layout.invoke_magic(out, '\n'.join(commands), 'pcells')
    library = [dict(model=k[0], width_um=k[1], length_um=k[2], cell=n,
                    geometry=layout.pcell_info(out/(n+'.mag')), sha256=sha(out/(n+'.mag')))
               for k, n in cells.items()]
    for p in unit.WIDTHS:
        (out/(unit.name(p)+'.spice')).write_text(unit.schematic(p))
    result = dict(library=library, qualified_phy=False, routed=False,
                  scope='Native primitive geometry only; no cell or electrical qualification')
    (out/'summary.json').write_text(json.dumps(result, indent=2)+'\n')
    print(out, flush=True)


if __name__ == '__main__':
    main()
