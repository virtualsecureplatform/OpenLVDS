# SPDX-License-Identifier: GPL-3.0-only
"""Local comparator islands for the diagnostic DLL layout generator."""
from collections import Counter
from layout import GRID, Geometry, draw_macro


def partition(devices, ports):
    groups = {name: [] for name in ['passive', 'positive', 'negative', 'low', 'high', 'logic']}
    comparators = dict(XPOS='positive', XNEG='negative', XLOW='low', XHIGH='high')
    for device in devices:
        name = device['name']
        matches = [group for instance, group in comparators.items()
                   if '__XAREA__' + instance + '__' in name]
        if len(matches) > 1:
            raise ValueError('Ambiguous monitor comparator instance')
        group = matches[0] if matches else ('passive' if 'res_' in device['model'] else 'logic')
        groups[group].append(device)
    if any(not group for group in groups.values()):
        raise ValueError('Expected four comparators, passives and logic')
    nets = {name: {n for d in group for n in d['nodes']} for name, group in groups.items()}
    counts = Counter(n for group in nets.values() for n in group)
    shared = sorted(n for n, count in counts.items() if count > 1)
    public = {name: [p for p in ports if p in net] + [p for p in shared if p in net and p not in ports]
              for name, net in nets.items()}
    if set(ports) - set(counts):
        raise ValueError('Unconnected monitor port')
    # High-impedance analog nodes must never become parent routing trunks.
    for name, group in groups.items():
        if name not in comparators.values():
            continue
        internal = {n for d in group for n in d['nodes']
                    if any(n.endswith('__' + suffix) for suffix in ['O', 'OB', 'L', 'T'])}
        if internal & set(public[name]):
            raise ValueError('Comparator internal node escaped its local island')
    return groups, public, shared


def draw(out, top, ports, devices, library):
    from layout_dll_candidate import bounds
    groups, public, shared = partition(devices, ports)
    children = {}; cursor = 100.; ceiling = 0.
    for name, group in groups.items():
        cell = 'monitor_' + name
        info = draw_macro(out, cell, public[name], group, library)
        bb = bounds(out / (cell + '.mag'))
        xy = (cursor - bb[0], 10. - bb[1])
        ceiling = max(ceiling, bb[3] + xy[1])
        children[name] = dict(cell=cell, info=info, bbox=bb, xy=xy)
        cursor += bb[2] - bb[0] + 110.
    geometry = Geometry(); labels = []; pin_map = {}; y = ceiling + 20.
    positions = {}
    for name, child in children.items():
        ox, oy = child['xy']
        positions[name] = {net: dict(pin, x_um=pin['x_um'] + ox, y_um=pin['y_um'] + oy)
                           for net, pin in child['info']['ports'].items()}
    for i, net in enumerate(shared):
        width = 5. if net in ['VDDD', 'VSS', 'VDDIO'] else .4
        y += width / 2 + 1.4
        ends = []
        for name, child in children.items():
            if net not in positions[name]:
                continue
            pin = positions[name][net]
            if pin['layer'] != 'metal3':
                raise ValueError('Expected local child ports on metal3')
            x = child['xy'][0] + child['bbox'][0] - 10. - 4. * i
            geometry.wire('metal3', x, pin['y_um'], pin['x_um'], pin['y_um'], width)
            geometry.via34(x, pin['y_um'])
            geometry.wire('metal4', x, pin['y_um'], x, y, .6)
            geometry.via34(x, y); ends.append(x)
        geometry.wire('metal3', min(ends), y, max(ends), y, width)
        labels.append((net, min(ends), y, ports.index(net) + 1 if net in ports else None, 'metal3'))
        if net in ports:
            pin_map[net] = dict(layer='metal3', x_um=min(ends), y_um=y, width_um=width)
        y += width / 2 + 1.4
    for net in ports:
        if net in pin_map:
            continue
        locations = [p[net] for p in positions.values() if net in p]
        if len(locations) != 1:
            raise ValueError('Invalid local monitor port ownership')
        pin = locations[0]; pin_map[net] = pin
        labels.append((net, pin['x_um'], pin['y_um'], ports.index(net) + 1, pin['layer']))
    lines = ['magic', 'tech sky130A', 'magscale 1 2', 'timestamp 0']
    for layer, rects in geometry.layers.items():
        lines += ['<< ' + layer + ' >>'] + ['rect ' + ' '.join(map(str, r)) for r in rects]
    for child in children.values():
        x, cy = [round(v / GRID) for v in child['xy']]
        lines += [f'use {child["cell"]} {child["cell"]}', 'timestamp 0',
                  f'transform 1 0 {x} 0 1 {cy}',
                  'box ' + ' '.join(str(round(v / GRID)) for v in child['bbox'])]
    lines += ['<< labels >>']
    for net, x, cy, index, layer in labels:
        x, cy = round(x / GRID), round(cy / GRID)
        lines.append(f'rlabel {layer} {x} {cy} {x} {cy} 0 {net}')
        if index:
            lines.append(f'port {index} nsew')
    lines += ['<< end >>']
    (out / (top + '.mag')).write_text('\n'.join(lines) + '\n')
    return dict(ports=pin_map, width_um=cursor, height_um=y + 10.,
                comparator_islands={name: dict(devices=len(groups[name]), ports=public[name])
                                    for name in groups}, shared_nets=shared)
