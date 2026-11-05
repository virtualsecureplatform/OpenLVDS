# SPDX-License-Identifier: GPL-3.0-only
"""Install actual TG component RC and observe both internal gates of every TG."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import numpy as np
import small_guard_bank_v19 as previous
import verify_tg_quad_cell_v22 as proof
import dcdl_tg_tree_v5 as controls
from build_compound_drivers_v3 import cell_definition
from spice_library import replace, checked_netlist
from uniform_tree_parasitic_isolation_v4 import isolate
from native_binary_raw_v2 import validate

ROOT = proof.ROOT
PROFILES = previous.PROFILES
OLD = controls.tg_name('double_direct')
MODEL = proof.NAME


def name(profile):
    previous.name(profile)
    return 'openlvds_dcdl_tg_c16_f32_'+profile+'_component_rc_v23'


def witnesses(evidence):
    i = json.loads((evidence/'manifest.json').read_text())['identity']
    if (evidence.parent != ROOT/'build/diagnostics'/proof.CONTEXT or i['version'] != proof.VERSION
            or evidence.name != hashlib.sha256(json.dumps(i, sort_keys=True).encode()).hexdigest()[:16]
            or proof.sha(Path(i['cad_python']['path'])) != i['cad_python']['sha256']):
        raise ValueError('Require unchanged independent native TG physical/RC proof')
    env = dict(os.environ)
    env['PATH'] = os.pathsep.join(dict.fromkeys(str(Path(t['path']).parent) for t in i['tools'].values()))+os.pathsep+env['PATH']
    code = 'import sys; from pathlib import Path; sys.path.insert(0,str(Path(sys.argv[1])/"scripts")); import verify_tg_quad_cell_v22 as p; p.bound(Path(sys.argv[2]))'
    subprocess.run([i['cad_python']['path'], '-c', code, str(ROOT), str(evidence)], env=env, check=True)
    r = json.loads((evidence/'summary.json').read_text()); info = r['extraction']
    paths = [evidence/'manifest.json', evidence/'summary.json', Path(__file__), Path(proof.__file__)]
    paths += [ROOT/n for n in i['inputs']]
    paths += [ROOT/info[n] for n in ('netlist', 'raw_netlist')]
    return checked_netlist(info), paths, dict(evidence=str(evidence.relative_to(ROOT)), cad_python=i['cad_python'],
                                             actual_tg_component_rc_used=True)


def transform(cells, bank, tg, profile):
    previous.name(profile)
    before = previous.native.definitions(cells); actual = previous.native.definitions(tg)
    if set(actual) != {MODEL} or OLD not in before or before[OLD][0] != actual[MODEL][0]:
        raise ValueError('Actual TG component interface changed')
    ideal, report = isolate(tg, MODEL)
    # Collapse only for connectivity/geometry comparison; install the full RC.
    proof.physical.native_check(ideal)
    proof.physical.native_check(cell_definition(cells, OLD))
    new_cells = replace(cells, OLD, tg.rstrip())
    after = previous.native.definitions(new_cells)
    if set(after) != (set(before)-{OLD})|{MODEL} or any(after[n] != before[n] for n in before if n != OLD):
        raise ValueError('TG replacement changed unrelated native definitions')
    old_name = previous.name(profile)
    if bank.count('.subckt '+old_name+' ') != 1 or bank.count('.ends '+old_name+'\n') != 1:
        raise ValueError('Require the complete original small-guard bank')
    rows = []; switches = []
    for line in bank.splitlines():
        w = line.split()
        if w and w[-1] == OLD:
            if len(w) != 8 or not w[0].startswith('Xswitch'):
                raise ValueError('TG switch instance/interface changed')
            switches.append(w[0]); w[-1] = MODEL; line = ' '.join(w)
        rows.append(line)
    if len(switches) != len(set(switches)) or len(switches) != 20:
        raise ValueError('Require all twenty native TGs')
    new_bank = '\n'.join(rows)+'\n'
    new_bank = new_bank.replace('.subckt '+old_name+' ', '.subckt '+name(profile)+' ', 1).replace('.ends '+old_name+'\n', '.ends '+name(profile)+'\n', 1)
    return new_cells, new_bank, dict(actual_tg_instances=20,
                                    tg_component_resistors=report['removed_explicit_resistors'],
                                    tg_component_parasitic_capacitors=report['removed_explicit_parasitic_capacitors'],
                                    tg_native_geometry_preserved=True, tg_component_rc_retained=True,
                                    whole_bank_rc_retained=False, qualified_phy=False)


def gate_observations(tg, bank, expected_switches=20):
    _, report = isolate(tg, MODEL); aliases = report['wire_aliases']
    ports, body = previous.native.definitions(tg)[MODEL]
    gates = []
    for w in body:
        if not w[0].startswith('X'):
            continue
        end = next((i for i, token in enumerate(w) if '=' in token), len(w))
        expected = 'EN' if w[end-1] == proof.physical.N else 'ENB' if w[end-1] == proof.physical.P else None
        if end != 6 or expected is None or aliases.get(w[2]) != expected:
            raise ValueError('Unexpected actual TG control gate')
        gates.append((w[0], w[2], expected))
    if len(gates) != 2 or {g[2] for g in gates} != {'EN', 'ENB'}:
        raise ValueError('Both native TG control gates are required')
    defs = previous.native.definitions(bank)
    if len(defs) != 1:
        raise ValueError('Require one complete bank')
    root_ports, instances = next(iter(defs.values())); result = []; switches = []
    def node(n):
        return '0' if n == 'VGND' else 'VDD' if n == 'VPWR' else n if n in root_ports else 'XD:'+n
    for w in instances:
        if w[-1] != MODEL:
            continue
        if len(w[1:-1]) != len(ports) or not w[0].startswith('Xswitch'):
            raise ValueError('Native TG bank pin mapping changed')
        switches.append(w[0]); mapping = dict(zip(ports, w[1:-1]))
        for leaf, gate, control in gates:
            result.append(dict(device='XD:'+w[0]+':'+leaf,
                               gate_node=node(mapping[gate]) if gate in mapping else 'XD:'+w[0]+':'+gate,
                               control_node=node(mapping[control]), control_name=mapping[control], kind=control))
    if len(switches) != len(set(switches)) or len(switches) != expected_switches:
        raise ValueError('Incomplete actual TG gate coverage')
    return result


def gate_measurements(names, waveform, gates, spec):
    targets = controls.control_targets(spec['coarse'], spec['fine'])
    idx = {n: i for i, n in enumerate(names)}
    if 'time' not in idx:
        raise ValueError('Missing native gate observation time vector')
    stable = waveform[:, idx['time']] >= 1.5e-9
    if not np.any(stable) or len({g['device'] for g in gates}) != len(gates):
        raise ValueError('Missing stable interval or duplicate TG observation')
    result = []
    for gate in gates:
        column = 'v('+gate['gate_node'].replace(':', '.').lower()+')'
        if column not in idx or gate['control_name'] not in targets:
            raise ValueError('Missing actual TG gate vector or unknown static target')
        target = 1.8*targets[gate['control_name']]
        deviation = float(np.max(np.abs(waveform[stable, idx[column]]-target)))
        result.append(dict(gate, target_v=target, maximum_deviation_v=deviation, passed=bool(deviation <= .18)))
    return result
