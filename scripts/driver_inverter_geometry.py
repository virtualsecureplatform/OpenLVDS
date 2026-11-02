# SPDX-License-Identifier: GPL-3.0-only
"""Stack checked P/N banks with local input/output and separate supply rails."""
from layout import Geometry, GRID, pcell_info


def write(out, name, pbank, nbank):
    banks = [('P', pbank), ('N', nbank)]
    placed = []
    for role, row in banks:
        cell = row['name']
        info = pcell_info(out / (cell + '.mag'))
        bb = info['bbox']
        # Include the entire routed bank, including the bottom bulk escape.
        y = 2. - bb[1] if role == 'P' else -2. - bb[3]
        y = round(y / GRID) * GRID
        placed.append(dict(role=role, cell=cell, bbox=bb, y=y,
            ports={n:(v[0], v[1], v[2] + y) for n,v in info['ports'].items()}, recipe=row['recipe']))
    a_x = min(x['ports']['G'][1] for x in placed) - 3.
    y_x = max(x['ports']['D'][1] for x in placed) + 3.
    supply_x = y_x + 4.
    bulk_x = min(x['ports']['B'][1] for x in placed) - 3.
    g = Geometry()
    for pin, role, x in [('A', 'G', a_x), ('Y', 'D', y_x)]:
        ys = []
        for row in placed:
            _, px, py = row['ports'][role]
            g.wire('metal3', px, py, x, py, .8 if role == 'G' else 2.)
            g.via34(x, py)
            ys.append(py)
        g.wire('metal4', x, min(0., *ys), x, max(0., *ys), .8 if role == 'G' else 2.)
        g.via34(x, 0.)
    public = dict(A=('metal3', a_x, 0.), Y=('metal3', y_x, 0.))
    for row in placed:
        top = row['role'] == 'P'
        rail = row['y'] + row['bbox'][3 if top else 1] + (3. if top else -3.)
        for terminal, spine, width in [('S', supply_x, 2.), ('B', bulk_x, .8)]:
            _, px, py = row['ports'][terminal]
            g.wire('metal3', px, py, spine, py, width)
            g.via34(spine, py)
            g.wire('metal4', spine, py, spine, rail, width)
            g.via34(spine, rail)
        g.wire('metal3', bulk_x, rail, supply_x, rail, 2.)
        public['VP' if top else 'VN'] = ('metal3', supply_x, rail)
    lines = ['magic', 'tech sky130A', 'magscale 1 2', 'timestamp 0']
    for layer, rects in g.layers.items():
        lines += [f'<< {layer} >>']
        lines += ['rect ' + ' '.join(map(str, rect)) for rect in rects]
    for row in placed:
        lines += [f'use {row["cell"]} I{row["role"]}', 'timestamp 0',
                  f'transform 1 0 0 0 1 {round(row["y"] / GRID)}',
                  'box ' + ' '.join(str(round(v / GRID)) for v in row['bbox'])]
    lines += ['<< labels >>']
    for i, (pin, (layer, x, y)) in enumerate(public.items(), 1):
        x, y = round(x / GRID), round(y / GRID)
        lines += [f'rlabel {layer} {x} {y} {x} {y} 0 {pin}', f'port {i} nsew']
    (out / (name + '.mag')).write_text('\n'.join(lines + ['<< end >>', '']))
    source = ['* SPDX-License-Identifier: GPL-3.0-only', f'.subckt {name} A Y VP VN']
    for row in placed:
        params = row['recipe']
        rail = 'VP' if row['role'] == 'P' else 'VN'
        source += [f'X{row["role"]}{i} Y A {rail} {rail} {params["model"]} w={params["w"]} l={params["l"]}'
                   for i in range(params['nf'])]
    (out / (name + '.sch.spice')).write_text('\n'.join(source + [f'.ends {name}', '']))
    return dict(ports={n:dict(layer=v[0], x_um=v[1], y_um=v[2]) for n,v in public.items()},
                placements=placed, width_um=supply_x - bulk_x + 2.)
