#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Reimport native mux GDS and independently repeat label-only topology LVS."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import inspect_mux_tree_access_v4 as producer

ROOT = producer.ROOT
VERSION = 'fresh-native-gds-mux-private-node-access-verification-v4.1'
CONTEXT = 'mux_tree_access_verification_v4'


def verify(parent):
    identity = json.loads((parent/'manifest.json').read_text())
    report = json.loads((parent/'summary.json').read_text())
    if (parent.parent != ROOT/'build/diagnostics'/producer.CONTEXT
            or parent.name != hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
            or identity['version'] != producer.VERSION or identity['models'] != producer.MODELS
            or report['identity'] != identity or report['qualified_phy'] is not False
            or identity['tools'] != producer.access.environment.tools()
            or any(producer.sha(ROOT/n) != h for n, h in identity['code'].items())
            or any(producer.sha(Path(n)) != h for n, h in identity['pdk_files'].items())
            or len(report['rows']) != 2):
        raise ValueError('Native mux access context changed')
    inputs = [parent/'manifest.json', parent/'summary.json', Path(__file__)]
    inputs += [ROOT/n for n in identity['code']]
    for short, row in zip(producer.MODELS, report['rows']):
        if (row['model'] != 'sky130_fd_sc_hd__'+short
                or any(producer.sha(ROOT/n) != h for n, h in row['files'].items())):
            raise ValueError('Native mux retained geometry/source/proof changed')
        inputs += [ROOT/n for n in row['files']]
    binding = dict(version=VERSION, parent=str(parent.relative_to(ROOT)),
                   inputs={str(p.relative_to(ROOT)): producer.sha(p) for p in inputs},
                   pdk_files=identity['pdk_files'], tools=identity['tools'])
    out = ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(binding, sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True, exist_ok=False)
    (out/'manifest.json').write_text(json.dumps(binding, indent=2)+'\n')
    gds = next(Path(n) for n in binding['pdk_files'] if n.endswith('/sky130_fd_sc_hd.gds'))
    library = next(Path(n) for n in binding['pdk_files'] if n.endswith('/sky130_fd_sc_hd.spice')).read_text()
    pdk_setup = next(Path(n) for n in binding['pdk_files'] if n.endswith('/sky130A_setup.tcl'))
    rows = []
    for short, retained in zip(producer.MODELS, report['rows']):
        model = retained['model']; original = parent/short; folder = out/short; folder.mkdir()
        source = producer.cell_definition(library, model)
        extended, mapping = producer.access.reference(source)
        if (source != (original/'native_source.spice').read_text()
                or extended != (original/'reference.spice').read_text()):
            raise ValueError('Native source cannot be regenerated')
        producer.access.layout.invoke_magic(folder, f'gds readonly false\ngds read {{{gds}}}\nload {model} -silent\nsave {{{folder/model}}}', 'fresh_native_geometry')
        text = (folder/(model+'.mag')).read_text()
        if text != (original/(model+'.mag')).read_text():
            raise ValueError('Retained native masks differ from freshly imported PDK GDS')
        labelled, points = producer.annotate(text, mapping)
        probe = model+'_access_probe'
        if labelled != (original/(probe+'.mag')).read_text():
            raise ValueError('Native extraction labels cannot be regenerated')
        (folder/(probe+'.mag')).write_text(labelled)
        (folder/'reference.spice').write_text(extended)
        producer.access.layout.invoke_magic(folder, f'load {probe} -silent\nextract all\next2spice lvs\next2spice -o labelled.spice {probe}.ext', 'fresh_labelled')
        setup = producer.strict_setup(folder/'setup.tcl', pdk_setup); log = folder/'lvs.log'
        p = subprocess.run(['netgen', '-batch', 'lvs', f'{folder/"labelled.spice"} {probe}',
                            f'{folder/"reference.spice"} {model}', str(setup), str(log)], cwd=folder, capture_output=True, text=True)
        (folder/'console.log').write_text(p.stdout+p.stderr)
        if not producer.clean_match(log.read_text() if log.exists() else '', p.returncode):
            raise ValueError('Fresh native mux exact-source LVS failed')
        ext = (folder/(probe+'.ext')).read_text(); nodes = {}; groups = []
        for private, public in mapping.items():
            labels = producer.connected_labels(ext, public); groups.append(labels)
            nodes[public] = dict(private_source_node=private, existing_li_access={n: v for n, v in points.items() if n in labels})
        if nodes != retained['private_nodes'] or any(a & b for a, b in producer.itertools.combinations(groups, 2)):
            raise ValueError('Fresh native private-node access differs or merges nodes')
        rows.append(dict(model=model, exact_source_topology_passed=True, fresh_native_masks_identical=True,
                         private_nodes_distinct=True, private_nodes=nodes,
                         nodes_with_existing_li_candidates=sum(bool(n['existing_li_access']) for n in nodes.values()),
                         private_node_count=len(nodes), all_private_nodes_have_existing_li_access=all(n['existing_li_access'] for n in nodes.values())))
    if (any(producer.sha(ROOT/n) != h for n, h in binding['inputs'].items())
            or any(producer.sha(Path(n)) != h for n, h in binding['pdk_files'].items())):
        raise ValueError('Native mux evidence changed during independent verification')
    files = {str(p.relative_to(out)): producer.sha(p) for p in out.rglob('*') if p.is_file()}
    result = dict(identity=binding, rows=rows, native_masks_and_topology_verified=True,
                  all_private_nodes_have_existing_li_access=all(r['all_private_nodes_have_existing_li_access'] for r in rows),
                  files=files, qualified_phy=False, electrical_qualification_passed=False,
                  scope='Fresh GDS import, label-only geometry and repeated strict native-source LVS; LI candidates require route/contact checks, no new mask, shunt, RC or timing admission')
    (out/'summary.json').write_text(json.dumps(result, indent=2)+'\n')
    return out


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('artifact', type=Path)
    a = p.parse_args(); print(verify(a.artifact.resolve()), flush=True)
