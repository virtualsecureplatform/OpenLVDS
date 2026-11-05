# SPDX-License-Identifier: GPL-3.0-only
"""Move branch regeneration after the mux and load the active inverter output.

Every path still has two serial inversions. The fine bank no longer directly
loads the passive root TG. Qualified component RC is retained; common routing
and placement of this new topology remain unqualified.
"""
from collections import Counter
from copy import deepcopy
import re
import moscap_component_rc_bank_v90 as base
from parallel_root_bank_v97 import rename
from build_compound_drivers_v3 import cell_definition

ROOT = base.ROOT
source = base.source
WIDTHS = base.WIDTHS
checked_cell = base.checked_cell
INV = 'openlvds_inv_8_nlvt_o2_v34'
TG = 'openlvds_tg_quad_stacked_nlvt_v27'


def name(profile):
    base.name(profile)
    return 'openlvds_post_mux_regeneration_'+profile+'_v108'


def rewrite_body(bank, top, reverse=False):
    defs = source.native.definitions(bank); ports, body = defs[top]
    group_names = [f'Xgroup_inverse{g}' for g in range(4)]
    if not reverse and [w[0] for w in body[-4:]] != group_names:
        raise ValueError('Branch inverter order changed')
    if reverse and [w[0] for w in body[-2:]] != ['Xbank_regenerator', 'Xfine_parallel']:
        raise ValueError('Common inverter order changed')
    unit = top+'_unit'; rows = []; roots = set(); fine = set(); groups = set(); driver = 0; new = set()
    for w in body:
        if not w[0].startswith('X'):
            raise ValueError('Unexpected inter-component element')
        word = list(w); tag = word[0]
        end = next((k for k,v in enumerate(word) if '=' in v),len(word)); model=word[end-1]
        if model not in defs:
            if re.fullmatch(r'X(?:group_inverse[0-3]|switch1_0_[0-3]|fine_driver|fine_unit\d+|bank_regenerator|fine_parallel)',tag):
                raise ValueError('Expected a qualified component hierarchy')
            rows.append(' '.join(word));continue
        if end!=len(word):raise ValueError('Parameterized component hierarchy')
        pins = dict(zip(defs[model][0], word[1:-1]))
        if tag in ('Xbank_regenerator', 'Xfine_parallel'):
            expected = dict(A='selected', Y='fine_slow', VGND='VGND', VPWR='VPWR') if tag == 'Xbank_regenerator' else dict(A='fine_slow', Y='OUT', VGND='VGND', VPWR='VPWR')
            if not reverse or tag in new or model != INV or pins != expected:
                raise ValueError('Common inverter data/body wiring changed')
            new.add(tag); continue
        match = re.fullmatch(r'Xgroup_inverse([0-3])', tag)
        if match:
            g = int(match[1])
            if reverse or g in groups or model != INV or pins != dict(A=f'tree0_{g}', Y=f'regenerated{g}', VGND='VGND', VPWR='VPWR'):
                raise ValueError('Branch inverter data/body wiring changed')
            groups.add(g); continue
        match = re.fullmatch(r'Xswitch1_0_([0-3])', tag)
        if match:
            g = int(match[1]); expected_input = f'tree0_{g}' if reverse else f'regenerated{g}'
            if g in roots or model != TG or pins != dict(A=expected_input, Z='selected', EN=f'en1_{g}', ENB=f'en_b1_{g}', VPWR='VPWR', VGND='VGND'):
                raise ValueError('Root mux data/control/body wiring changed')
            roots.add(g); pins['A'] = f'regenerated{g}' if reverse else f'tree0_{g}'
        elif tag == 'Xfine_driver':
            if driver or model != INV or pins != dict(A='fine_slow' if reverse else 'selected', Y='OUT', VGND='VGND', VPWR='VPWR'):
                raise ValueError('Final inverter data/body wiring changed')
            driver += 1; pins['A'] = 'selected' if reverse else 'fine_slow'
        else:
            match = re.fullmatch(r'Xfine_unit(\d+)', tag)
            if match:
                k = int(match[1]); expected_data = 'fine_slow' if reverse else 'selected'
                if k in fine or model != unit or pins != dict(NODE=expected_data, EN=f'fine{k}', ENB=f'fine_b{k}', VDD='VPWR', VSS='VGND'):
                    raise ValueError('Fine-bank data/control/body wiring changed')
                fine.add(k); pins['NODE'] = 'selected' if reverse else 'fine_slow'
        rows.append(' '.join([tag, *[pins[p] for p in defs[model][0]], model]))
    if (roots != set(range(4)) or fine != set(range(31)) or driver != 1
        or (not reverse and groups != set(range(4)))
        or (reverse and new != {'Xbank_regenerator', 'Xfine_parallel'})):
        raise ValueError('Incomplete post-mux graph conversion')
    if reverse:
        for g in range(4):
            pins = dict(A=f'tree0_{g}', Y=f'regenerated{g}', VGND='VGND', VPWR='VPWR')
            rows.append(f'Xgroup_inverse{g} '+' '.join(pins[p] for p in defs[INV][0])+' '+INV)
    else:
        for tag, a, y in [('Xbank_regenerator', 'selected', 'fine_slow'), ('Xfine_parallel', 'fine_slow', 'OUT')]:
            pins = dict(A=a, Y=y, VGND='VGND', VPWR='VPWR')
            rows.append(tag+' '+' '.join(pins[p] for p in defs[INV][0])+' '+INV)
    result='.subckt '+top+' '+' '.join(ports)+'\n'+'\n'.join(rows)+'\n.ends '+top+'\n'
    return bank.replace(cell_definition(bank, top), result, 1)


def projection(bank, profile):
    return rename(rewrite_body(bank, name(profile), reverse=True), name(profile), base.name(profile))


def transform(text, profile, fine_rc):
    original = base.transform(text, profile, fine_rc)
    bank = rename(rewrite_body(original, base.name(profile)), base.name(profile), name(profile))
    if projection(bank, profile) != original:
        raise ValueError('Post-mux regeneration changes unrelated components')
    counts = source.primitive_counts(bank, name(profile))
    if sum(v for k,v in counts.items() if 'fet_' in k) != 981 or counts.get('sky130_fd_pr__cap_mim_m3_1') != 35:
        raise ValueError('Post-mux native inventory changed')
    return bank


def observations(bank, profile, previous):
    top = name(profile); defs = source.native.definitions(bank); ports, body = defs[top]
    mapping = {p:'0' if p=='VGND' else 'VDD' if p=='VPWR' else p for p in ports}
    devices = source.native.mapped_mos(bank,top,mapping,'XD'); byname={d['name']:d for d in devices}
    if len(devices)!=981 or len(byname)!=981:
        raise ValueError('Incomplete post-mux native observations')
    gates=[dict(g,gate_node=byname[g['device']]['terminals'][1]) for g in previous['programming_gates'] if g['kind']=='tg']
    roles=base.fine_pattern(bank,top+'_unit'); seen=set()
    for w in body:
        match=re.fullmatch(r'Xfine_unit(\d+)',w[0])
        if match is None:continue
        k=int(match[1]);pins=dict(zip(defs[top+'_unit'][0],w[1:-1]))
        if k in seen or pins!=dict(NODE='fine_slow',EN=f'fine{k}',ENB=f'fine_b{k}',VDD='VPWR',VSS='VGND'):
            raise ValueError('Post-mux fine data/control mapping changed')
        seen.add(k)
        for role in roles:
            device='XD:'+w[0]+':'+role['instance']
            gates.append(dict(device=device,gate_node=byname[device]['terminals'][1],control=pins[role['control_port']],kind='fine'))
    if (seen!=set(range(31)) or len(gates)!=133 or Counter((g['control'],g['kind']) for g in gates)!=Counter((g['control'],g['kind']) for g in previous['programming_gates'])):
        raise ValueError('Post-mux programming-gate coverage changed')
    return dict(deepcopy(previous),devices=devices,programming_gates=gates)
