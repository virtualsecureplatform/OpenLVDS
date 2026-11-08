#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Width-only fine-switch intervention; native components, no timing admission."""
from copy import deepcopy
import json
import subprocess
import p40n32_pre_distributed_bank_300 as parent
import mim_fine_bank_300 as old

SOURCE = parent.SOURCE
ROOT = old.ROOT
TOP = 'openlvds_tg2_p40n32_split_c1_300'
MODEL = 'openlvds_mim_switch_2x3_tg2_v1'
MATERIAL = ROOT/'build/diagnostics/mim_switch_2x3_tg2_rc_proof_300_v1/97729cdbade089d6'
sha = old.retained.sha


def qualified_cell():
    report = json.loads((MATERIAL/'summary.json').read_text())
    row = report['rows'][0]
    info = row['extraction']
    if (report['component_rc_qualified'] is not True or len(report['rows']) != 1
            or row['macro'] != MODEL or row['component_rc_qualified'] is not True
            or sha(ROOT/info['netlist']) != info['netlist_sha256']):
        raise ValueError('Double-TG qualified numerical model changed')
    return SOURCE.definition((ROOT/info['netlist']).read_text(), MODEL)


def materials():
    command = ('import sys;from pathlib import Path;sys.path.insert(0,"scripts");'
               'import qualify_mim_switch_2x3_tg2_rc_300_v1 as q;q.bound(Path(sys.argv[1]))')
    result = subprocess.run([old.retained.CAD, '-c', command, str(MATERIAL)],
                            cwd=ROOT, capture_output=True, text=True)
    if result.returncode:
        raise ValueError('Double-TG physical/native/math binding failed: '+result.stderr[-2000:])
    identity = json.loads((MATERIAL/'manifest.json').read_text())['identity']
    report = json.loads((MATERIAL/'summary.json').read_text())
    row = report['rows'][0]; proof = row['rc_proof']
    if (json.loads((MATERIAL/'state.json').read_text()) != dict(status='complete', passed=True, qualified_phy=False)
            or any(sha(MATERIAL/n) != h for n,h in report['files'].items())
            or any(proof[k] is not True for k in
                   ('component_rc_passed', 'exact_reduction_regenerated', 'native_topology_verified'))
            or proof['independent_terminal_current_witness']['proof']['passed'] is not True
            or report['qualified_phy'] is not False):
        raise ValueError('Double-TG complete RC proof required')
    paths = [MATERIAL/n for n in ('manifest.json','summary.json','state.json',*report['files'])]
    paths += [ROOT/n for n in identity['inputs']]
    return qualified_cell(), paths, identity


def transform(original, observations):
    text, previous, revision = parent.transform(original, observations)
    cell = qualified_cell()
    definitions = SOURCE.native.definitions(text)
    ports, body = definitions[parent.TOP]
    expected = {f'Xfine_mim{k}_c{j}': [f'Xfine_mim{k}_c{j}',
                'pre_out' if j else 'fine_node', f'fine{k}', f'fine_b{k}',
                'VPWR','VGND',old.MODEL] for k in range(31) for j in range(2)}
    if (MODEL in definitions or TOP in definitions
            or {w[0]:w for w in body if w[-1] == old.MODEL} != expected
            or sum(w[-1] == old.MODEL for w in body) != 62):
        raise ValueError('Require exact P40/N32 split one-plus-one baseline')
    changed = [w[:-1]+[MODEL] if w[0] in expected else w for w in body]
    block = '\n'.join(['.subckt '+TOP+' '+' '.join(ports),
                       *[' '.join(w) for w in changed], '.ends '+TOP, ''])
    result = text.replace(SOURCE.definition(text,parent.TOP), block, 1)+'\n'+cell
    if any(SOURCE.definition(result,n) != SOURCE.definition(text,n)
           for n in definitions if n != parent.TOP):
        raise ValueError('Unrelated numerical component changed')
    pins = {p:'0' if p=='VGND' else 'VDD' if p=='VPWR' else p for p in ports}
    devices = SOURCE.native.mapped_mos(result,TOP,pins,'XD')
    before = {d['name']:d for d in previous['devices']}
    after = {d['name']:d for d in devices}
    prefixes = tuple('XD:'+n+':' for n in expected)
    if (len(after) != len(devices) or len(after) != 2056
            or any(after.get(n) != d for n,d in before.items() if not n.startswith(prefixes))):
        raise ValueError('Non-fine transistor terminal maps changed')
    gates = deepcopy([g for g in previous['programming_gates'] if not g['device'].startswith(prefixes)])
    if len(gates) != 80:
        raise ValueError('Non-fine gate coverage changed')
    for name,call in expected.items():
        unit = SOURCE.native.mapped_mos(cell,MODEL,dict(zip(old.PORTS,
            ['XD:'+call[1], 'XD:'+call[2], 'XD:'+call[3], 'VDD','0'])), 'XD:'+name)
        if len(unit) != 3 or any(after.get(d['name']) != d for d in unit):
            raise ValueError('Fine transistor terminal maps differ from qualified unit')
        # Resolve each actual extracted gate through the resistor graph.
        graph = {}
        for w in SOURCE.native.definitions(cell)[MODEL][1]:
            if w[0][0].upper() == 'R':
                graph.setdefault(w[1],set()).add(w[2]);graph.setdefault(w[2],set()).add(w[1])
        def reaches(start):
            seen={start}; todo=[start]
            while todo:
                for n in graph.get(todo.pop(),()):
                    if n not in seen: seen.add(n);todo.append(n)
            return seen
        networks={p:reaches(p) for p in ('EN','ENB')}
        if networks['EN'] & networks['ENB']: raise ValueError('Fine controls shorted')
        for d in unit:
            node=d['terminals'][1].removeprefix('XD:'+name+':')
            matches=[p for p,nodes in networks.items() if node in nodes]
            if len(matches)!=1: raise ValueError('Unresolved fine programming gate')
            gates.append(dict(device=d['name'],gate_node=d['terminals'][1],
                              control=call[2 if matches[0]=='EN' else 3],kind='fine'))
    _, leaves = SOURCE.inventory.native_leaves(SOURCE.collapse(result),TOP)
    if (sum('fet_' in d['model'] for d in leaves),sum('cap_mim' in d['model'] for d in leaves)) != (2056,202):
        raise ValueError('Native inventory changed')
    if len(gates)!=266 or len({g['device'] for g in gates})!=266:
        raise ValueError('Programming gate inventory changed')
    return result,dict(devices=devices,controls=deepcopy(previous['controls']),programming_gates=gates),dict(
        revision,macro_top=TOP,fine_switch='qualified_double_tg_width',qualified_phy=False,
        scope='One-factor switch-width pilot; bank timing and common routing unqualified')
