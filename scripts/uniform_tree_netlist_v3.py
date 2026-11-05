# SPDX-License-Identifier: GPL-3.0-only
"""Structural physical netlist of the native uniform-tree experiment.

This view retains component boundaries and every load. Blackbox interfaces
carry no delay, voltage, layout or legal-code qualification.
"""
import dcdl_uniform_tree_v3 as native

VERSION = 'uniform-tree-explicit-power-structural-view-v3.1'
RAILS = dict(VPWR='VPWR', VPB='VPWR', VGND='VGND', VNB='VGND')


def name(coarse=16, fine_count=32):
    return native.name(coarse, fine_count).removesuffix('_v3')+'_physical_v3'


def connections(orders, coarse=16, fine_count=32):
    """Match every connection to the actual native component port interface."""
    result = []
    for cell in native.instances(coarse, fine_count):
        pins = dict(RAILS, **cell['pins'])
        order = orders.get(cell['model'], [])
        expected = set(pins)
        if cell['model'] == native.BUFFER:
            expected = {'A', 'X', 'VPWR', 'VGND'}
        elif cell['model'] == native.fine.NAME:
            expected = set(cell['pins'])
        if len(order) != len(set(order)) or set(order) != expected:
            raise ValueError('Physical component port mismatch: '+cell['model'])
        result.append(dict(name='u_'+cell['name'], model=cell['model'],
                           pins={p: pins[p] for p in order}))
    return result


def outputs(model):
    if model == native.fine.NAME:
        return set()
    if model in (native.BUFFER, native.SC+'buf_1', native.SC+'buf_4',
                 native.SC+'mux4_4', native.SC+'mux2_4'):
        return {'X'}
    if model == native.SC+'inv_1':
        return {'Y'}
    raise ValueError('Undeclared native physical cell '+model)


def direction(model, pin):
    if pin in ('VPWR', 'VGND', 'VPB', 'VNB', 'VDD', 'VSS'):
        return 'inout'
    return 'output' if pin in outputs(model) else 'input'


def verilog(orders, coarse=16, fine_count=32):
    top_ports = native.ports(coarse, fine_count)
    cells = connections(orders, coarse, fine_count)
    nets = sorted({n for c in cells for n in c['pins'].values()}-set(top_ports))
    rows = ['// SPDX-License-Identifier: GPL-3.0-only',
            '// Native structural experiment; no timing or PHY admission.',
            '`default_nettype none', 'module '+name(coarse, fine_count)+' (']
    declarations = []
    for p in top_ports:
        kind = 'inout' if p in ('VPWR', 'VGND') else 'output' if p == 'OUT' else 'input'
        declarations.append('    '+kind+' wire '+p)
    rows += [',\n'.join(declarations), ');']
    rows += ['    (* keep = 1 *) wire '+n+';' for n in nets]
    for cell in cells:
        rows.append('    (* keep = 1, dont_touch = 1 *) '+cell['model']+' '+cell['name']+' ('+
                    ', '.join('.'+p+'('+n+')' for p, n in cell['pins'].items())+');')
    return '\n'.join(rows+['endmodule', '`default_nettype wire', ''])


def blackboxes(orders, coarse=16, fine_count=32):
    cells = connections(orders, coarse, fine_count)
    rows = ['// SPDX-License-Identifier: GPL-3.0-only',
            '// Interface declarations only; no delay or functional clock model.', '`default_nettype none']
    for model in sorted({c['model'] for c in cells}):
        rows += ['(* blackbox *) module '+model+' (',
                 ',\n'.join('    '+direction(model, p)+' wire '+p for p in orders[model]), ');', 'endmodule']
    return '\n'.join(rows+['`default_nettype wire', ''])


def verify_json(data, orders, coarse=16, fine_count=32):
    """Require the imported graph to retain each native pin and load exactly."""
    top = name(coarse, fine_count)
    modules = data['modules']
    if top not in modules:
        raise ValueError('Missing physical uniform-tree module')
    module = modules[top]; expected_ports = native.ports(coarse, fine_count)
    if set(module['ports']) != set(expected_ports):
        raise ValueError('Physical top interface changed')
    nets = module['netnames']; scalar = {}
    for n, info in nets.items():
        if len(info['bits']) == 1:
            scalar[n] = info['bits'][0]
    cells = connections(orders, coarse, fine_count)
    required_nets = set(expected_ports) | {n for c in cells for n in c['pins'].values()}
    if (not required_nets <= set(scalar) or any(type(scalar[n]) is not int for n in required_nets)
            or len({scalar[n] for n in required_nets}) != len(required_nets)):
        raise ValueError('Physical nets are missing, constant or merged')
    for p in expected_ports:
        expected_direction = 'inout' if p in ('VPWR', 'VGND') else 'output' if p == 'OUT' else 'input'
        if module['ports'][p] != dict(direction=expected_direction, bits=[scalar[p]]):
            raise ValueError('Physical top pin direction or connection changed')
    if set(module['cells']) != {c['name'] for c in cells}:
        raise ValueError('Physical graph dropped or added native components')
    for cell in cells:
        actual = module['cells'][cell['name']]
        if (actual['type'] != cell['model'] or actual.get('parameters')
                or actual['connections'] != {p: [scalar[n]] for p, n in cell['pins'].items()}
                or actual['port_directions'] != {p: direction(cell['model'], p) for p in cell['pins']}):
            raise ValueError('Physical native component wiring or model changed: '+cell['name'])
        for attribute in ('keep', 'dont_touch'):
            if int(actual['attributes'].get(attribute, '0'), 2) != 1:
                raise ValueError('Physical native component preservation attribute lost')
    models = {c['model'] for c in cells}
    if set(modules) != models | {top}:
        raise ValueError('Unexpected physical hierarchy or missing native blackbox')
    for model in models:
        box = modules[model]
        if (int(box['attributes'].get('blackbox', '0'), 2) != 1 or box.get('cells')
                or set(box['ports']) != set(orders[model])
                or any(box['ports'][p]['direction'] != direction(model, p) for p in orders[model])):
            raise ValueError('Native blackbox interface contains changed semantics')
    return dict(exact_native_component_graph_verified=True, components=len(cells),
                coarse_taps=coarse, fine_settings=fine_count, qualified_phy=False,
                electrical_qualification_passed=False,
                scope='Yosys structural import and pin-exact native component graph only; no routed geometry, RC, electrical timing or PHY admission')
