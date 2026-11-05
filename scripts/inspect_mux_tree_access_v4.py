#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Prove native mux private-node access before implementing the physical tree.

Import actual PDK masks and add extraction labels only. Exact-source strict LVS
checks every private node separately. This does not add a shunt or qualify mux
timing, terminal voltage, DRC, whole-bank wiring, legal codes or the PHY.
"""
import hashlib
import itertools
import json
import os
import re
from pathlib import Path
import subprocess
import inspect_clock_cell_access_v2 as access
from build_compound_drivers_v3 import cell_definition
from label_nand_mid_access_v2 import connected_labels
from lvs_utils import strict_setup, clean_match

ROOT = access.ROOT
VERSION = 'native-balanced-tree-mux-layer-aware-private-node-access-v4.1'
CONTEXT = 'mux_tree_access_v4'
MODELS = ['mux4_4', 'mux2_4']
sha = access.sha


def unchanged_masks(original, labelled):
    """Require identical native file content outside its extraction labels."""
    def masks(text):
        result = []; labels = False
        for line in text.splitlines():
            if line.startswith('<< '):
                labels = line == '<< labels >>'
            if not labels:
                result.append(line)
        return result
    if original.count('<< labels >>') != 1 or labelled.count('<< labels >>') != 1:
        raise ValueError('Require exactly one extraction-label section')
    return masks(original) == masks(labelled)



def annotate(text, mapping):
    """Place each private label on its actual native diffusion layer.

    A metal conductor at the same coordinate may be a different net. Never
    infer electrical identity from geometric overlap with an upper layer.
    """
    labelled, points = access.annotate(text, mapping)
    rectangles = []
    layer = None
    for line in text.splitlines():
        if line.startswith('<< '):
            layer = line[3:-3]
        if line.startswith('rect ') and layer in ('ndiff', 'pdiff'):
            rectangles.append((layer, list(map(int, line.split()[1:]))))
    for private, public in mapping.items():
        match = re.fullmatch(r'a_(\d+)_(\d+)#', private)
        if match is None:
            raise ValueError('Missing native private coordinate')
        x, y = [int(v)+2 for v in match.groups()]
        layers = {layer for layer, (a, b, c, d) in rectangles if a <= x < c and b <= y < d}
        if len(layers) != 1:
            raise ValueError('Private coordinate lacks unique actual diffusion')
        old = f'rlabel ndiff {x} {y} {x} {y} 0 {public}'
        if labelled.count(old+'\n') != 1:
            raise ValueError('Missing unique private extraction label')
        labelled = labelled.replace(old+'\n', f'rlabel {next(iter(layers))} {x} {y} {x} {y} 0 {public}\n', 1)
    if not unchanged_masks(text, labelled):
        raise ValueError('Layer-aware labels changed native masks')
    return labelled, points


def inspect():
    pdk = Path(os.environ['PDK_ROOT'])/'sky130A'
    sc = pdk/'libs.ref/sky130_fd_sc_hd'
    pdks = [sc/'gds/sky130_fd_sc_hd.gds', sc/'spice/sky130_fd_sc_hd.spice',
            pdk/'libs.tech/magic/sky130A.magicrc', pdk/'libs.tech/netgen/sky130A_setup.tcl']
    code = [Path(__file__), Path(access.__file__), Path(access.layout.__file__), Path(access.environment.__file__),
            ROOT/'scripts/build_compound_drivers_v3.py', ROOT/'scripts/label_nand_mid_access_v2.py', ROOT/'scripts/lvs_utils.py']
    identity = dict(version=VERSION, models=MODELS, pdk_files={str(p): sha(p) for p in pdks},
                    code={str(p.relative_to(ROOT)): sha(p) for p in code}, tools=access.environment.tools())
    out = ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True, exist_ok=False)
    (out/'manifest.json').write_text(json.dumps(identity, indent=2)+'\n')
    library = pdks[1].read_text(); rows = []
    for short in MODELS:
        model = 'sky130_fd_sc_hd__'+short
        folder = out/short; folder.mkdir()
        source = cell_definition(library, model)
        extended, mapping = access.reference(source)
        if not mapping:
            raise ValueError('Missing native mux private nodes')
        (folder/'native_source.spice').write_text(source)
        (folder/'reference.spice').write_text(extended)
        access.layout.invoke_magic(folder, f'gds readonly false\ngds read {{{pdks[0]}}}\nload {model} -silent\nsave {{{folder/model}}}', 'native_geometry')
        native = folder/(model+'.mag')
        original = native.read_text()
        labelled, points = annotate(original, mapping)
        if not unchanged_masks(original, labelled):
            raise ValueError('Mux inspection changed native masks or placements')
        probe = model+'_access_probe'
        (folder/(probe+'.mag')).write_text(labelled)
        access.layout.invoke_magic(folder, f'load {probe} -silent\nextract all\next2spice lvs\next2spice -o labelled.spice {probe}.ext', 'labelled')
        setup = strict_setup(folder/'setup.tcl', pdks[3]); log = folder/'lvs.log'
        process = subprocess.run(['netgen', '-batch', 'lvs', f'{folder/"labelled.spice"} {probe}',
                                  f'{folder/"reference.spice"} {model}', str(setup), str(log)], cwd=folder, capture_output=True, text=True)
        (folder/'console.log').write_text(process.stdout+process.stderr)
        matched = clean_match(log.read_text() if log.exists() else '', process.returncode)
        ext = (folder/(probe+'.ext')).read_text(); nodes = {}; groups = {}
        for private, public in mapping.items():
            labels = connected_labels(ext, public); groups[public] = labels
            nodes[public] = dict(private_source_node=private,
                                 existing_li_access={n: p for n, p in points.items() if n in labels})
        distinct = all(not (a & b) for a, b in itertools.combinations(groups.values(), 2))
        existing = all(n['existing_li_access'] for n in nodes.values())
        files = [p for p in folder.iterdir() if p.is_file()]
        row = dict(model=model, source_ports=source.splitlines()[0].split()[2:], private_nodes=nodes,
                   private_node_count=len(nodes), exact_source_topology_passed=matched,
                   private_nodes_distinct=distinct, all_private_nodes_have_existing_li_access=existing,
                   native_mask_geometry_unchanged=True, passed=bool(matched and distinct and existing),
                   files={str(p.relative_to(ROOT)): sha(p) for p in files}, qualified_phy=False)
        rows.append(row)
        (folder/'summary.json').write_text(json.dumps(row, indent=2)+'\n')
    if (any(sha(Path(n)) != h for n, h in identity['pdk_files'].items())
            or any(sha(ROOT/n) != h for n, h in identity['code'].items())):
        raise ValueError('Native mux PDK or producer changed during inspection')
    report = dict(identity=identity, rows=rows, passed=all(r['passed'] for r in rows), qualified_phy=False,
                  scope='Label-only actual native mux geometry and exact-source private-node access; no added contacts, DRC, shunts, RC, electrical timing or PHY admission')
    (out/'summary.json').write_text(json.dumps(report, indent=2)+'\n')
    return out


if __name__ == '__main__':
    print(inspect(), flush=True)

