# SPDX-License-Identifier: GPL-3.0-only
"""Native TG selection between uniform taps and a separate fine-bank driver.

Two data inversions preserve polarity. Every mux group has one selected input
under static legal controls. New TG geometry, controls and common interconnect
require physical proofs; this source experiment cannot qualify a PHY.
"""
import dcdl_uniform_tree_v3 as dimensions

VERSION = 'uniform-taps-static-onehot-tg-tree-independent-fine-driver-v5.1'
SC = dimensions.SC
INVERTER = 'openlvds_inv_8_o4_shunted_v2'
BUFFER = 'openlvds_buf_4_pair_v2'
FINE = dimensions.fine.NAME
PROFILES = {'unit': (.42, .84), 'double': (.84, 1.68),
            'unit_direct': (.42, .84), 'double_direct': (.84, 1.68)}


def name(profile='unit', coarse=16, fine_count=32):
    dimensions.dimensions(coarse, fine_count)
    if profile not in PROFILES:
        raise ValueError('Unknown native TG sizing experiment')
    return f'openlvds_dcdl_tg_tree_c{coarse}_f{fine_count}_{profile}_v5'


def tg_name(profile):
    name(profile)
    return 'openlvds_tg_'+profile+'_v5'


def tg_source(profile):
    name(profile)
    n, p = PROFILES[profile]
    # Explicit prelayout junction estimates, not defaults of zero. 0.29 um
    # diffusion extension matches the retained fine-unit primitive convention;
    # new TG PCell/layout extraction must establish its actual junctions.
    def geometry(width):
        return f'w={width:g} l=0.15 ad={width*.29:.9g} as={width*.29:.9g} pd={2*(width+.29):.9g} ps={2*(width+.29):.9g}'
    model = tg_name(profile)
    return (f'.subckt {model} A Z EN ENB VPWR VGND\n'
            f'XN A EN Z VGND sky130_fd_pr__nfet_01v8 {geometry(n)}\n'
            f'XP Z ENB A VPWR sky130_fd_pr__pfet_01v8 {geometry(p)}\n'
            f'.ends {model}\n')


def levels(coarse=16, fine_count=32):
    dimensions.dimensions(coarse, fine_count)
    size = coarse; bit = level = 0; result = []
    while size > 1:
        radix = 4 if size >= 4 else 2
        result.append(dict(level=level, bit=bit, radix=radix, groups=size//radix))
        bit += 2 if radix == 4 else 1
        size //= radix; level += 1
    return result


def enables(level, index):
    if level['radix'] == 2:
        bit = level['bit']
        return (f'select{bit}', f'select_b{bit}') if index else (f'select_b{bit}', f'select{bit}')
    return f'en{level["level"]}_{index}', f'en_b{level["level"]}_{index}'


def instances(profile='unit', coarse=16, fine_count=32):
    name(profile, coarse, fine_count)
    bits = dimensions.dimensions(coarse, fine_count)
    cells = []
    def add(tag, model, **pins):
        cells.append(dict(name=tag, model=model, pins=pins))
    add('input_inverse', INVERTER, A='IN', Y='tap0')
    for i in range(1, coarse):
        add(f'delay{i}', BUFFER, A=f'tap{i-1}', X=f'tap{i}')
    add('tail_load', BUFFER, A=f'tap{coarse-1}', X='unused_tail')
    for i in range(bits):
        add(f'select_buffer{i}', SC+'buf_4', A=f'S{i}', X=f'select{i}')
        add(f'select_inverse{i}', SC+'inv_4', A=f'select{i}', Y=f'select_b{i}')
    nodes = [f'tap{i}' for i in range(coarse)]
    for level in levels(coarse, fine_count):
        k, bit, radix = level['level'], level['bit'], level['radix']
        if radix == 4:
            for value in range(4):
                a = f'select{bit}' if value & 1 else f'select_b{bit}'
                b = f'select{bit+1}' if value & 2 else f'select_b{bit+1}'
                en, enb = enables(level, value)
                add(f'decode{k}_{value}', SC+'and2_4', A=a, B=b, X=en)
                add(f'decode_inverse{k}_{value}', SC+'inv_4', A=en, Y=enb)
        outputs = []
        for group in range(level['groups']):
            output = 'selected' if level['groups'] == 1 else f'tree{k}_{group}'
            for value in range(radix):
                en, enb = enables(level, value)
                add(f'switch{k}_{group}_{value}', tg_name(profile), A=nodes[group*radix+value],
                    Z=output, EN=en, ENB=enb, VPWR='VPWR', VGND='VGND')
            outputs.append(output)
        nodes = outputs
    fine_node = 'OUT' if profile.endswith('_direct') else 'fine_node'
    add('fine_driver', INVERTER, A='selected', Y=fine_node)
    for i in range(fine_count-1):
        add(f'fine_buffer{i}', SC+'buf_1', A=f'E{i}', X=f'fine{i}')
        add(f'fine_inverse{i}', SC+'inv_1', A=f'fine{i}', Y=f'fine_b{i}')
        add(f'fine_unit{i}', FINE, NODE=fine_node, EN=f'fine{i}', ENB=f'fine_b{i}', VDD='VPWR', VSS='VGND')
    if not profile.endswith('_direct'):
        add('output_buffer', BUFFER, A='fine_node', X='OUT')
    return cells


def control_targets(coarse_code, fine_code, coarse=16, fine_count=32):
    encoded = dimensions.encode(coarse_code, fine_code, coarse, fine_count)
    result = {}
    for pin, value in encoded.items():
        i = int(pin[1:])
        if pin[0] == 'S':
            result[f'select{i}'] = value; result[f'select_b{i}'] = 1-value
        else:
            result[f'fine{i}'] = value; result[f'fine_b{i}'] = 1-value
    for level in levels(coarse, fine_count):
        active = (coarse_code >> level['bit']) & (level['radix']-1)
        if level['radix'] == 4:
            for value in range(4):
                en, enb = enables(level, value)
                result[en] = int(value == active); result[enb] = int(value != active)
    return result


def source(orders, profile='unit', coarse=16, fine_count=32):
    top = name(profile, coarse, fine_count)
    rows = ['.subckt '+top+' '+' '.join(dimensions.ports(coarse, fine_count))]
    rails = dict(VPWR='VPWR', VPB='VPWR', VGND='VGND', VNB='VGND')
    for cell in instances(profile, coarse, fine_count):
        model = cell['model']; pins = dict(rails, **cell['pins'])
        expected = set(pins)
        if model in (INVERTER, BUFFER):
            expected -= {'VPB', 'VNB'}
        elif model == FINE:
            expected = set(cell['pins'])
        elif model == tg_name(profile):
            expected = set(cell['pins'])
        order = orders.get(model, [])
        if len(order) != len(set(order)) or set(order) != expected:
            raise ValueError('Native TG-bank component interface changed: '+model)
        rows.append('X'+cell['name']+' '+' '.join(pins[p] for p in order)+' '+model)
    return '\n'.join(rows+['.ends '+top, ''])
