#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Export and check a physical netlist against the bound native pilot bank."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import uniform_tree_netlist_v3 as view
import probe_dcdl_uniform_tree_v3 as pilot

ROOT = pilot.ROOT
VERSION = 'bound-native-uniform-tree-physical-netlist-export-v3.1'
CONTEXT = 'uniform_tree_netlist_v3'


def native_graph(bank, cells):
    definitions = view.native.native.definitions(cells)
    orders = {model: definition[0] for model, definition in definitions.items()}
    roots = view.native.native.definitions(bank)
    if set(roots) != {view.native.name()} or roots[view.native.name()][0] != view.native.ports():
        raise ValueError('Native pilot bank top interface changed')
    result = []
    for words in roots[view.native.name()][1]:
        if (not words[0].startswith('X') or words[-1] not in orders
                or len(words[1:-1]) != len(orders[words[-1]])):
            raise ValueError('Non-native or changed bank component interface')
        result.append(dict(name='u_'+words[0][1:], model=words[-1],
                           pins=dict(zip(orders[words[-1]], words[1:-1]))))
    if result != view.connections(orders):
        raise ValueError('Physical netlist differs from retained native SPICE graph')
    return orders, result


def export(parent):
    manifest = pilot.bound(parent)
    cells = (parent/'cells.spice').read_text(); bank = (parent/'bank.spice').read_text()
    orders, graph = native_graph(bank, cells)
    yosys = shutil.which('yosys')
    if yosys is None:
        raise ValueError('Use scripts/env.sh --tools --ngspice with the scientific Python')
    inputs = [parent/n for n in ('manifest.json', 'cells.spice', 'bank.spice')]
    inputs += [ROOT/n for n in manifest['identity']['inputs']]
    inputs += [Path(__file__), Path(view.__file__)]
    identity = dict(version=VERSION, parent=str(parent.relative_to(ROOT)),
                    inputs={str(p.relative_to(ROOT)): pilot.sha(p) for p in inputs},
                    pdk_files=manifest['identity']['pdk_files'],
                    yosys=dict(path=yosys, sha256=pilot.sha(Path(yosys))),
                    orders=orders, native_graph=graph, qualified_phy=False)
    out = ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True, exist_ok=False)
    pilot.atomic(out/'manifest.json', identity)
    pilot.write(out/'bank.v', view.verilog(orders))
    pilot.write(out/'cells.v', view.blackboxes(orders))
    script = f'read_verilog -lib cells.v\nread_verilog bank.v\nhierarchy -check -top {view.name()}\nwrite_json bank.json\n'
    pilot.write(out/'check.ys', script)
    p = subprocess.run([yosys, '-s', 'check.ys'], cwd=out, capture_output=True, text=True)
    pilot.write(out/'yosys.log', p.stdout+p.stderr)
    result = None; error = None
    try:
        p.check_returncode()
        result = view.verify_json(json.loads((out/'bank.json').read_text()), orders)
    except Exception as e:
        error = str(e)
    pilot.bound(parent)
    if (any(pilot.sha(ROOT/n) != h for n, h in identity['inputs'].items())
            or pilot.sha(Path(yosys)) != identity['yosys']['sha256']):
        raise ValueError('Native netlist export inputs changed')
    files = {p.name: pilot.sha(p) for p in out.iterdir() if p.is_file()}
    pilot.atomic(out/'summary.json', dict(identity=identity, result=result, error=error,
               files=files, qualified_phy=False, electrical_qualification_passed=False))
    return out


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('artifact', type=Path)
    a = p.parse_args(); print(export(a.artifact.resolve()), flush=True)
