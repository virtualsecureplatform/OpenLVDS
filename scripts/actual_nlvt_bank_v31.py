# SPDX-License-Identifier: GPL-3.0-only
"""Install actual low-Vt TG, inverter and coarse-buffer distributed RC."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import nlvt_data_path_v25 as previous
import verify_stacked_nlvt_tg_v28 as tgproof
import verify_nlvt_data_components_v30 as dataproof
from spice_library import replace, checked_netlist
from uniform_tree_parasitic_isolation_v4 import isolate

ROOT = previous.baseline.ROOT
PROFILES = ('actual_nlvt',)
MODEL = tgproof.NAME
NATIVE = previous.baseline.previous.native


def name(profile):
    if profile not in PROFILES: raise ValueError('Unknown actual low-Vt bank profile')
    return 'openlvds_dcdl_c16_f32_actual_nlvt_v31'


def merge_files(*collections):
    result = {}
    for collection in collections:
        for path, digest in collection.items():
            if path in result and result[path] != digest:
                raise ValueError('Component file bindings disagree: '+path)
            result[path] = digest
    return result


def witnesses(tg_evidence, data_evidence):
    identities = [json.loads((e/'manifest.json').read_text())['identity'] for e in (tg_evidence, data_evidence)]
    cad = identities[0]['cad_python']
    if identities[1]['cad_python'] != cad or tgproof.sha(Path(cad['path'])) != cad['sha256']:
        raise ValueError('Require identical pinned CAD Python for actual components')
    env = dict(os.environ)
    env['PATH'] = os.pathsep.join(dict.fromkeys(str(Path(t['path']).parent) for i in identities for t in i['tools'].values()))+os.pathsep+env['PATH']
    code = ('import sys; from pathlib import Path; sys.path.insert(0,str(Path(sys.argv[1])/"scripts")); '
            'import verify_stacked_nlvt_tg_v28 as t; import verify_nlvt_data_components_v30 as d; '
            't.bound(Path(sys.argv[2])); d.bound(Path(sys.argv[3]))')
    subprocess.run([cad['path'], '-c', code, str(ROOT), str(tg_evidence), str(data_evidence)], env=env, check=True)
    tg = json.loads((tg_evidence/'summary.json').read_text())
    data = json.loads((data_evidence/'summary.json').read_text())
    texts = {'tg': checked_netlist(tg['extraction'])}
    texts.update({r['profile']: checked_netlist(r['extraction']) for r in data['rows']})
    paths = []; external = {cad['path']: cad['sha256']}
    for evidence, identity in zip((tg_evidence, data_evidence), identities):
        paths += [evidence/'manifest.json', evidence/'summary.json', *[ROOT/n for n in identity['inputs']]]
        parent = ROOT/identity['parent']; pi = json.loads((parent/'manifest.json').read_text())['identity']
        external = merge_files(external, pi['external_files'])
        paths += [ROOT/n for n in pi['inputs']]
    for rc in [tg['extraction'], *[r['extraction'] for r in data['rows']]]:
        paths += [ROOT/rc[k] for k in ('raw_netlist', 'netlist')]
    return texts, paths, external, dict(cad_python=cad, actual_component_rc_used=True,
                                       tg=str(tg_evidence.relative_to(ROOT)), data=str(data_evidence.relative_to(ROOT)))


def transform(cells, bank, components):
    old = {key: model+'_nlvt_diagnostic_v25' for key, model in
           [('tg', previous.TG), ('inv3', previous.INV), ('bufpair', previous.BUF)]}
    definitions = NATIVE.definitions(cells); renames = {}; result = cells
    counts = {key: 0 for key in old}
    for key, model in old.items():
        actual = NATIVE.definitions(components[key])
        if len(actual) != 1: raise ValueError('Require one flat actual component definition')
        target = next(iter(actual))
        if model not in definitions or definitions[model][0] != actual[target][0]:
            raise ValueError('Actual low-Vt component public port order changed')
        result = replace(result, model, components[key].rstrip()); renames[model] = (target, key)
    after = NATIVE.definitions(result)
    if set(after) != (set(definitions)-set(renames))|{x[0] for x in renames.values()} or any(after[k] != definitions[k] for k in definitions if k not in renames):
        raise ValueError('Actual component installation changed unrelated cells')
    rows = []
    for line in bank.splitlines():
        w = line.split()
        if w and w[-1] in renames:
            if not w[0].startswith('X'):
                raise ValueError('Expected a native data-component instance')
            target, key = renames[w[-1]]; counts[key] += 1; w[-1] = target; line = ' '.join(w)
        rows.append(line)
    if counts != dict(tg=20, inv3=2, bufpair=16):
        raise ValueError('Require all twenty TGs, two data drivers and sixteen coarse buffers')
    bank = '\n'.join(rows)+'\n'; root = previous.name('data_nlvt')
    if bank.count('.subckt '+root+' ') != 1 or bank.count('.ends '+root+'\n') != 1:
        raise ValueError('Require complete original low-Vt data bank')
    bank = bank.replace('.subckt '+root+' ', '.subckt '+name('actual_nlvt')+' ', 1).replace('.ends '+root+'\n', '.ends '+name('actual_nlvt')+'\n', 1)
    return result, bank, dict(actual_component_counts=counts, component_rc_physically_equivalent=True,
                              tg_component_physically_equivalent=True, new_implant_physical_proof=True,
                              borrowed_changed_implant_rc=False, whole_bank_rc_retained=False, qualified_phy=False)


def gate_observations(tg, bank, expected_switches=20):
    _, report = isolate(tg, MODEL); aliases = report['wire_aliases']
    ports, body = NATIVE.definitions(tg)[MODEL]
    gates = []
    for w in body:
        if not w[0].startswith('X'):
            continue
        end = next((i for i, token in enumerate(w) if '=' in token), len(w))
        expected = 'EN' if w[end-1] == tgproof.physical.N else 'ENB' if w[end-1] == tgproof.physical.P else None
        if end != 6 or expected is None or aliases.get(w[2]) != expected:
            raise ValueError('Unexpected actual TG control gate')
        gates.append((w[0], w[2], expected))
    if len(gates) != 2 or {g[2] for g in gates} != {'EN', 'ENB'}:
        raise ValueError('Both native TG control gates are required')
    defs = NATIVE.definitions(bank)
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

