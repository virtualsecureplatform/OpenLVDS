# SPDX-License-Identifier: GPL-3.0-only
"""Recheck CAD proofs in their pinned Python without mixing scientific packages."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import verify_small_guard_inverter_v18 as small_proof
import verify_regular_inverter_network_v16 as network_proof
from spice_library import checked_netlist

ROOT = small_proof.ROOT


def witnesses(evidence, network):
    i = json.loads((evidence/'manifest.json').read_text())['identity']
    ni = json.loads((network/'manifest.json').read_text())['identity']
    if (evidence.parent != ROOT/'build/diagnostics'/small_proof.CONTEXT or i['version'] != small_proof.VERSION
            or evidence.name != hashlib.sha256(json.dumps(i, sort_keys=True).encode()).hexdigest()[:16]
            or network.parent != ROOT/'build/diagnostics'/network_proof.CONTEXT or ni['version'] != network_proof.VERSION
            or network.name != hashlib.sha256(json.dumps(ni, sort_keys=True).encode()).hexdigest()[:16]
            or small_proof.sha(Path(i['cad_python']['path'])) != i['cad_python']['sha256']):
        raise ValueError('Require unchanged independently verified physical driver components')
    env = dict(os.environ)
    env['PATH'] = os.pathsep.join(dict.fromkeys(str(Path(t['path']).parent) for t in i['tools'].values()))+os.pathsep+env['PATH']
    code = ('import sys; from pathlib import Path; sys.path.insert(0,str(Path(sys.argv[1])/"scripts")); '
            'import verify_small_guard_inverter_v18 as s; import verify_regular_inverter_network_v16 as n; '
            's.bound(Path(sys.argv[2])); n.bound(Path(sys.argv[3]))')
    subprocess.run([i['cad_python']['path'], '-c', code, str(ROOT), str(evidence), str(network)], env=env, check=True)
    parent = ROOT/i['parent']; pi = json.loads((parent/'manifest.json').read_text())['identity']
    if pi['evidence'] != ni['physical']:
        raise ValueError('Small guard and original driver network have different physical parents')
    normal = ROOT/pi['parent']
    big = json.loads((normal/'summary.json').read_text())['extraction']
    small = json.loads((evidence/'summary.json').read_text())['extraction']
    paths = [Path(__file__), Path(small_proof.__file__), Path(network_proof.__file__)]
    paths += [p for folder in (evidence, network, parent, normal) for p in (folder/'manifest.json', folder/'summary.json')]
    paths += [ROOT/n for binding in (i, ni, pi) for n in binding['inputs']]
    for info in (big, small):
        paths += [ROOT/info[n] for n in ('netlist', 'raw_netlist')]
    return {small_proof.physical.OLD: checked_netlist(big), small_proof.NAME: checked_netlist(small)}, paths, ROOT/ni['diagnostic'], dict(
        physical_small_guard=str(evidence.relative_to(ROOT)), original_driver_network=str(network.relative_to(ROOT)),
        cad_python=i['cad_python'], actual_component_rc_used=True)
