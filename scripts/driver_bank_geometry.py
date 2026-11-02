# SPDX-License-Identifier: GPL-3.0-only
"""Connect checked independent MOS fingers into one four-terminal physical bank."""
from driver_finger_banks import terminal_groups
from layout import Geometry, GRID


def via12(g, x, y):
    # Magic via layers include the cut plus its surrounding rule margin.
    # Use the pinned technology's 0.26 um via1 drawing, not a bare 0.15 cut.
    x, y = [round(v / GRID) * GRID for v in [x, y]]
    g.via12(x, y)


def via23(g, x, y):
    x, y = [round(v / GRID) * GRID for v in [x, y]]
    g.via23(x, y)


def write(out, name, cell, info, parameters):
    nf = parameters['nf']
    roles = terminal_groups(info['ports'], nf)
    bb = info['bbox']
    p = info['ports']
    g = Geometry()
    mean_y = sum(p[n][2] for role in ['D', 'S'] for n in roles[role]) / (2 * nf)
    stripe = dict(D=mean_y + 2., S=mean_y - 2.)
    right = bb[2] + 4.
    gate_x = bb[0] - 4.
    bulk_x = bb[0] - 8.
    public = {}

    # Each D/S column retains its own M2 collector. M3 joins only matching
    # columns, so the two collector networks never cross on the same layer.
    for role in ['D', 'S']:
        xs = []
        for n in roles[role]:
            layer, x, y = p[n]
            xs.append(x)
            # Stagger opposite-terminal landings. Adjacent thin-oxide D/S
            # columns are only 0.44 um apart: two aligned 0.4 um pads fail
            # spacing, while one pad beside a 0.14 um collector is legal.
            landing = y + (1 if role == 'D' else -1) * min(1., float(parameters['w']) / 4)
            g.wire('metal1', x, y, x, landing, .17)
            via12(g, x, landing)
            g.wire('metal2', x, landing, x, stripe[role], .14)
            via23(g, x, stripe[role])
        g.wire('metal3', min(xs) - .4, stripe[role], right, stripe[role], 2.)
        public[role] = ('metal3', right, stripe[role])

    # Gate access alternates above/below short-channel arrays. Keep gate
    # escapes outside the active D/S collectors and join their local M3 bars
    # through a separate M4 spine on the left.
    bars = {}
    for n in roles['G']:
        layer, x, y = p[n]
        sign = 1 if y >= mean_y else -1
        landing = y + sign * .15
        g.wire('metal1', x, y, x, landing, .18)
        via12(g, x, landing)
        rail = max(bb[3] + 1.2, stripe['D'] + 1.8) if sign > 0 else min(bb[1] - 1.2, stripe['S'] - 1.8)
        g.wire('metal2', x, landing, x, rail, .32)
        g.via23(x, rail)
        bars.setdefault(rail, []).append(x)
    for y, xs in bars.items():
        g.wire('metal3', gate_x, y, max(xs) + .4, y, .8)
        g.via34(gate_x, y)
    g.wire('metal4', gate_x, min(0., *bars), gate_x, max(0., *bars), .8)
    g.via34(gate_x, 0.)
    public['G'] = ('metal3', gate_x, 0.)

    # Leave the bulk contact vertically before crossing any bottom-side
    # gate contacts. The horizontal bulk route sits below all gate bars.
    layer, bx, by = p[roles['B'][0]]
    body_y = min(by - 2., min(bars) - 2.)
    g.pad('locali', bx, by, .33)
    g.pad('viali', bx, by, .17)
    g.pad('metal1', bx, by, .29)
    g.wire('metal1', bx, by, bx, body_y, .18)
    via12(g, bx, body_y)
    g.wire('metal2', bulk_x, body_y, bx, body_y, .4)
    g.via23(bulk_x, body_y)
    g.pad('metal3', bulk_x, body_y, .6)
    public['B'] = ('metal3', bulk_x, body_y)

    lines = ['magic', 'tech sky130A', 'magscale 1 2', 'timestamp 0']
    for layer, rects in g.layers.items():
        lines += [f'<< {layer} >>']
        lines += ['rect ' + ' '.join(map(str, rect)) for rect in rects]
    lines += [f'use {cell} I0', 'timestamp 0', 'transform 1 0 0 0 1 0',
              'box ' + ' '.join(str(round(v / GRID)) for v in bb), '<< labels >>']
    for index, role in enumerate(['D', 'G', 'S', 'B'], 1):
        layer, x, y = public[role]
        x, y = round(x / GRID), round(y / GRID)
        lines += [f'rlabel {layer} {x} {y} {x} {y} 0 {role}', f'port {index} nsew']
    lines += ['<< end >>']
    (out / (name + '.mag')).write_text('\n'.join(lines) + '\n')
    source = ['* SPDX-License-Identifier: GPL-3.0-only', f'.subckt {name} D G S B']
    source += [f'XF{i} D G S B {parameters["model"]} w={parameters["w"]} l={parameters["l"]}' for i in range(nf)]
    source += [f'.ends {name}', '']
    (out / (name + '.sch.spice')).write_text('\n'.join(source))
    return dict(ports={n:dict(layer=v[0], x_um=v[1], y_um=v[2]) for n,v in public.items()},
                fingers=nf, primitive=cell)
