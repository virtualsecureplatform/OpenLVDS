#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Repeat native graph import and retain actual-JSON corruption controls."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import export_uniform_tree_netlist_v3 as producer

ROOT = producer.ROOT
VERSION = 'uniform-tree-native-netlist-reimport-negative-controls-v3.1'
CONTEXT = 'uniform_tree_netlist_verification_v3'


def corruptions(data):
    top = producer.view.name()
    result = []
    def add(label, change):
        bad = copy.deepcopy(data); change(bad['modules'][top]); result.append((label, bad))
    add('dropped_tail_load', lambda m: m['cells'].pop('u_tail_load'))
    add('wrong_root_select', lambda m: m['cells']['u_mux1_0']['connections'].update(S1=m['netnames']['select2']['bits']))
    add('shorted_buffer_ground', lambda m: m['cells']['u_delay1']['connections'].update(VGND=m['netnames']['VPWR']['bits']))
    add('wrong_fine_attachment', lambda m: m['cells']['u_fine_unit15']['connections'].update(NODE=m['netnames']['tap0']['bits']))
    add('wrong_native_body_tie', lambda m: m['cells']['u_select_buffer0']['connections'].update(VPB=m['netnames']['VGND']['bits']))
    add('lost_preservation', lambda m: m['cells']['u_tail_load']['attributes'].pop('keep'))
    add('merged_select_wires', lambda m: m['netnames']['select1'].update(bits=m['netnames']['select0']['bits']))
    bad = copy.deepcopy(data)
    bad['modules'][producer.view.native.BUFFER]['attributes']['blackbox'] = '0'
    result.append(('replaced_native_blackbox', bad))
    return result


def verify(parent):
    i = json.loads((parent/'manifest.json').read_text())
    report = json.loads((parent/'summary.json').read_text())
    if (parent.parent != ROOT/'build/diagnostics'/producer.CONTEXT
            or parent.name != hashlib.sha256(json.dumps(i, sort_keys=True).encode()).hexdigest()[:16]
            or i['version'] != producer.VERSION or i['qualified_phy'] is not False
            or report['identity'] != i or report['error'] is not None
            or not report['result']['exact_native_component_graph_verified']
            or any(producer.pilot.sha(ROOT/n) != h for n, h in i['inputs'].items())
            or any(producer.pilot.sha(parent/n) != h for n, h in report['files'].items())
            or producer.pilot.sha(Path(i['yosys']['path'])) != i['yosys']['sha256']):
        raise ValueError('Retained native graph export changed or failed')
    native_parent = ROOT/i['parent']; producer.pilot.bound(native_parent)
    orders, graph = producer.native_graph((native_parent/'bank.spice').read_text(), (native_parent/'cells.spice').read_text())
    if orders != i['orders'] or graph != i['native_graph']:
        raise ValueError('Retained native graph does not regenerate')
    inputs = [parent/n for n in ('manifest.json', 'summary.json', *report['files'])]
    inputs += [ROOT/n for n in i['inputs']]
    inputs += [Path(__file__)]
    binding = dict(version=VERSION, parent=str(parent.relative_to(ROOT)),
                   inputs={str(p.relative_to(ROOT)): producer.pilot.sha(p) for p in inputs}, yosys=i['yosys'])
    out = ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(binding, sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True, exist_ok=False)
    producer.pilot.atomic(out/'manifest.json', binding)
    producer.pilot.write(out/'bank.v', producer.view.verilog(orders))
    producer.pilot.write(out/'cells.v', producer.view.blackboxes(orders))
    producer.pilot.write(out/'check.ys', (parent/'check.ys').read_text())
    for n in ('bank.v', 'cells.v'):
        if (out/n).read_bytes() != (parent/n).read_bytes():
            raise ValueError('Physical Verilog does not regenerate exactly')
    p = subprocess.run([i['yosys']['path'], '-s', 'check.ys'], cwd=out, capture_output=True, text=True)
    producer.pilot.write(out/'yosys.log', p.stdout+p.stderr); p.check_returncode()
    fresh = json.loads((out/'bank.json').read_text())
    result = producer.view.verify_json(fresh, orders)
    if fresh != json.loads((parent/'bank.json').read_text()) or result != report['result']:
        raise ValueError('Fresh Yosys import changed the native component graph')
    controls = []
    for label, bad in corruptions(fresh):
        path = out/(label+'.json'); producer.pilot.atomic(path, bad)
        try:
            producer.view.verify_json(bad, orders)
        except ValueError as e:
            controls.append(dict(control=label, rejected=True, reason=str(e), fixture_sha256=producer.pilot.sha(path)))
        else:
            raise ValueError('Native graph corruption accepted: '+label)
    producer.pilot.bound(native_parent)
    if any(producer.pilot.sha(ROOT/n) != h for n, h in binding['inputs'].items()):
        raise ValueError('Native netlist proof inputs changed during verification')
    files = {p.name: producer.pilot.sha(p) for p in out.iterdir() if p.is_file()}
    producer.pilot.atomic(out/'summary.json', dict(identity=binding, result=result, negative_controls=controls,
                          all_negative_controls_rejected=True, files=files,
                          qualified_phy=False, electrical_qualification_passed=False))
    return out


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('artifact', type=Path)
    a = p.parse_args(); print(verify(a.artifact.resolve()), flush=True)
