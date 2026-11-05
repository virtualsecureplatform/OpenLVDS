# SPDX-License-Identifier: GPL-3.0-only
"""Uniform native delay taps with balanced selection and equal fine capacitors.

Architecture prototype only. Source mux/control cells and common connections
require physical implementation and fresh whole-bank extraction. No timing,
legal-code, voltage or PHY qualification follows from topology alone.
"""
import mim_switch_2x3_v2 as fine
import native_clock_components_v2 as native

VERSION = 'uniform-tap-balanced-mux-thermometer-fine-v3.1'
SC = 'sky130_fd_sc_hd__'
BUFFER = native.CLOCK_BUFFER


def dimensions(coarse=16, fine_count=32):
    if type(coarse) is not int or coarse not in (16, 32, 64, 128, 256):
        raise ValueError('Unsupported coarse search dimension')
    if type(fine_count) is not int or fine_count not in (16, 32):
        raise ValueError('Unsupported fine search dimension')
    return coarse.bit_length()-1


def name(coarse=16, fine_count=32):
    dimensions(coarse, fine_count)
    return f'openlvds_dcdl_uniform_tree_c{coarse}_f{fine_count}_v3'


def ports(coarse=16, fine_count=32):
    bits = dimensions(coarse, fine_count)
    return ['IN', 'OUT', *[f'S{i}' for i in range(bits)],
            *[f'E{i}' for i in range(fine_count-1)], 'VPWR', 'VGND']


def encode(coarse_code, fine_code, coarse=16, fine_count=32):
    bits = dimensions(coarse, fine_count)
    if (type(coarse_code) is not int or not 0 <= coarse_code < coarse
            or type(fine_code) is not int or not 0 <= fine_code < fine_count):
        raise ValueError('Code outside complete native prototype')
    return {**{f'S{i}': (coarse_code >> i) & 1 for i in range(bits)},
            **{f'E{i}': int(i < fine_code) for i in range(fine_count-1)}}


def instances(coarse=16, fine_count=32):
    bits = dimensions(coarse, fine_count)
    cells = []
    def add(tag, model, **pins):
        cells.append(dict(name=tag, model=model, pins=pins))
    add('input', BUFFER, A='IN', X='tap0')
    for i in range(1, coarse):
        add(f'delay{i}', BUFFER, A=f'tap{i-1}', X=f'tap{i}')
    # Match the next-buffer fanout of every earlier tap; retain this load.
    add('tail_load', BUFFER, A=f'tap{coarse-1}', X='unused_tail')
    for i in range(bits):
        add(f'select_buffer{i}', SC+'buf_4', A=f'S{i}', X=f'select{i}')
    nodes = [f'tap{i}' for i in range(coarse)]
    bit = level = 0
    while len(nodes) > 1:
        radix = 4 if len(nodes) >= 4 else 2
        outputs = []
        for j in range(len(nodes)//radix):
            output = 'selected' if len(nodes) == radix else f'tree{level}_{j}'
            pins = {f'A{k}': nodes[radix*j+k] for k in range(radix)}
            if radix == 4:
                pins.update(S0=f'select{bit}', S1=f'select{bit+1}')
            else:
                pins.update(S=f'select{bit}')
            add(f'mux{level}_{j}', SC+f'mux{radix}_4', **pins, X=output)
            outputs.append(output)
        nodes = outputs
        bit += 2 if radix == 4 else 1
        level += 1
    for i in range(fine_count-1):
        add(f'fine_buffer{i}', SC+'buf_1', A=f'E{i}', X=f'fine{i}')
        add(f'fine_inverse{i}', SC+'inv_1', A=f'fine{i}', Y=f'fine_b{i}')
        add(f'fine_unit{i}', fine.NAME, NODE='selected', EN=f'fine{i}',
            ENB=f'fine_b{i}', VDD='VPWR', VSS='VGND')
    add('output', BUFFER, A='selected', X='OUT')
    return cells


def source(orders, coarse=16, fine_count=32):
    rows = ['.subckt '+name(coarse, fine_count)+' '+' '.join(ports(coarse, fine_count))]
    power = dict(VPWR='VPWR', VPB='VPWR', VGND='VGND', VNB='VGND')
    for cell in instances(coarse, fine_count):
        model = cell['model']
        pins = dict(power, **cell['pins'])
        order = orders.get(model, [])
        expected = set(pins)
        if model == BUFFER:
            expected = {'A', 'X', 'VPWR', 'VGND'}
        elif model == fine.NAME:
            expected = set(cell['pins'])
        if not order or len(set(order)) != len(order) or set(order) != expected:
            raise ValueError('Missing or changed native interface: '+model)
        rows.append('X'+cell['name']+' '+' '.join(pins[p] for p in order)+' '+model)
    return '\n'.join(rows+['.ends '+name(coarse, fine_count), ''])
