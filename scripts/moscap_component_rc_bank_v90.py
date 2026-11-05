# SPDX-License-Identifier: GPL-3.0-only
"""Compose the bank with actual fine-cell RC and rebuild native gate probes.

Inter-component routing is still ideal. Do not collapse multiple subcircuit
definitions together: their local RC node names are separate namespaces.
"""
from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import moscap_fine_bank_v75 as original
import moscap_fine_unit_v77 as physical
import native_bank_inventory_v51 as inventory
from audit_rc_comments_v2 import collapse
from build_compound_drivers_v3 import cell_definition

ROOT = Path(__file__).resolve().parents[1]
source = original.source
WIDTHS = original.WIDTHS


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def name(profile):
    physical.name(profile)
    return 'openlvds_moscap_component_rc_'+profile+'_v90'


def checked_cell(parent):
    parent = parent.resolve()
    i = json.loads((parent/'manifest.json').read_text())
    r = json.loads((parent/'summary.json').read_text())
    if (parent.parent != ROOT/'build/diagnostics/moscap_fine_rc_v87'
        or i['version'] != 'compact-moscap-native-mask-derived-junctions-and-component-rc-v87.1'
        or parent.name != hashlib.sha256(json.dumps(i, sort_keys=True).encode()).hexdigest()[:16]
        or any(sha(ROOT/n) != h for n, h in i['inputs'].items())
        or any(sha(Path(n)) != h for n, h in i['external_files'].items())
        or any(sha(parent/n) != h for n, h in r['files'].items())
        or any(sha(ROOT/n) != h for n, h in r['original_extracted_files'].items())
        or any(sha(Path(t['path'])) != t['sha256'] for t in i['tools'].values())
        or not r['fine_cell_geometry_and_component_rc_passed']
        or not r['rc_proof']['component_rc_passed'] or not r['rc_proof']['native_topology_verified']
        or not r['rc_proof']['independent_terminal_current_witness']['proof']['passed']
        or not r['original_extraction_preserved'] or r['qualified_phy']):
        raise ValueError('Require unchanged complete measured fine-cell component RC')
    net = ROOT/r['extraction']['netlist']
    if sha(net) != r['extraction']['netlist_sha256']:
        raise ValueError('Measured fine-cell RC netlist changed')
    fine_pattern(net.read_text(), physical.name(r['profile']))
    return i, r, net.read_text()


def fine_pattern(text, top):
    # Collapse only this single fine-cell definition, never the whole library.
    cell = cell_definition(text, top)
    ports, devices = inventory.native_leaves(collapse(cell), top)
    if ports != ['NODE', 'EN', 'ENB', 'VDD', 'VSS'] or len(devices) != 6:
        raise ValueError('Measured fine-cell interface/inventory changed')
    mos = [d for d in devices if 'fet_' in d['model']]
    if len(mos) != 5:
        raise ValueError('Measured fine-cell MOS inventory changed')
    private = {n for d in devices for n in d['nodes'] if n not in ports}
    if len(private) != 1:
        raise ValueError('Measured fine cell has no unique private capacitor node')
    cap = next(iter(private)); roles = []; signatures = []; capacitor_rails = []
    for d in mos:
        nodes = ['CAP' if n == cap else n for n in d['nodes']]
        if nodes[1] not in ('EN', 'ENB'):
            if not (nodes[1] == 'CAP' and nodes[0] == nodes[2] == nodes[3] and nodes[3] in ('VDD', 'VSS')):
                raise ValueError('Gate-cap rail/body topology changed')
            capacitor_rails.append((d['model'], nodes[3]))
            continue
        signatures.append((d['model'], inventory.exact_number(d['params']['w']),
            inventory.exact_number(d['params']['l']), nodes[1], nodes[3], tuple(sorted((nodes[0], nodes[2])))))
        roles.append(dict(instance=d['name'].removeprefix('native__'), control_port=nodes[1]))
    n = 'sky130_fd_pr__nfet_01v8'; p = 'sky130_fd_pr__pfet_01v8'; number = inventory.exact_number
    expected = [(n, number('.42'), number('.15'), 'EN', 'VSS', ('CAP', 'NODE')),
                (p, number('.84'), number('.15'), 'ENB', 'VDD', ('CAP', 'NODE')),
                (n, number('.42'), number('.15'), 'ENB', 'VSS', ('CAP', 'VSS'))]
    if Counter(signatures) != Counter(expected):
        raise ValueError('Fine programming-switch topology changed')
    if Counter(capacitor_rails) != Counter([(n, 'VSS'), (p, 'VDD')]):
        raise ValueError('Complementary gate-cap devices changed')
    guard = next(d for d in devices if 'fet_' not in d['model'])
    if (guard['model'] != 'sky130_fd_pr__cap_mim_m3_1' or set(guard['nodes']) != {'ENB', 'VSS'}
        or number(guard['params']['w']) != number(2) or number(guard['params']['l']) != number(2)):
        raise ValueError('Fine-cell control guard changed')
    return roles


def transform(text, profile, fine_rc):
    top = name(profile); old = original.name(profile); unit = old+'_unit'
    fine_pattern(fine_rc, physical.name(profile))
    _, leaves = inventory.native_leaves(collapse(cell_definition(fine_rc, physical.name(profile))), physical.name(profile))
    for d in leaves:
        if 'fet_' in d['model'] and d['nodes'][0] == d['nodes'][2] == d['nodes'][3]:
            if (inventory.exact_number(d['params']['w']) != inventory.exact_number(WIDTHS[profile])
                or inventory.exact_number(d['params']['l']) != inventory.exact_number('.15')):
                raise ValueError('Measured capacitor dimensions differ from bank profile')
    body = cell_definition(fine_rc, physical.name(profile))
    body = body.replace('.subckt '+physical.name(profile)+' ', '.subckt '+unit+' ', 1)
    body = re.sub(r'(?im)^\.ends[ \t]+'+re.escape(physical.name(profile))+r'\b', '.ends '+unit, body)
    bank = original.transform(text, profile)
    before = cell_definition(bank, unit)
    if bank.count(before) != 1:
        raise ValueError('Ambiguous prototype fine-cell definition')
    bank = bank.replace(before, body, 1)
    bank = re.sub(r'\b'+re.escape(old)+r'(?=_unit\b|\b)', top, bank)
    counts = source.primitive_counts(bank, top)
    if sum(v for k, v in counts.items() if 'fet_' in k) != 1013 or counts.get('sky130_fd_pr__cap_mim_m3_1') != 37:
        raise ValueError('Component-RC gate-cap bank inventory changed')
    return bank


def observations(bank, profile, previous):
    top = name(profile); defs = source.native.definitions(bank); ports, body = defs[top]
    mapping = {p: '0' if p == 'VGND' else 'VDD' if p == 'VPWR' else p for p in ports}
    devices = source.native.mapped_mos(bank, top, mapping, 'XD'); byname = {d['name']: d for d in devices}
    if len(devices) != 1013 or len(byname) != 1013:
        raise ValueError('Incomplete or duplicate component-RC MOS observations')
    gates = [dict(g, gate_node=byname[g['device']]['terminals'][1])
             for g in previous['programming_gates'] if g['kind'] == 'tg']
    roles = fine_pattern(bank, top+'_unit'); seen = set()
    for w in body:
        match = re.fullmatch(r'Xfine_unit(\d+)', w[0])
        if match is None:
            continue
        k = int(match[1]); pins = dict(zip(defs[top+'_unit'][0], w[1:-1]))
        if (k in seen or w[-1] != top+'_unit' or pins != dict(NODE='selected', EN=f'fine{k}',
                ENB=f'fine_b{k}', VDD='VPWR', VSS='VGND')):
            raise ValueError('Fine bank data/control/body connection changed')
        seen.add(k)
        for role in roles:
            device = 'XD:'+w[0]+':'+role['instance']
            gates.append(dict(device=device, gate_node=byname[device]['terminals'][1],
                              control=pins[role['control_port']], kind='fine'))
    if (seen != set(range(31)) or len(gates) != 133
        or Counter((g['control'], g['kind']) for g in gates) !=
           Counter((g['control'], g['kind']) for g in previous['programming_gates'])):
        raise ValueError('Programming-gate control coverage changed')
    return dict(deepcopy(previous), devices=devices, programming_gates=gates)
