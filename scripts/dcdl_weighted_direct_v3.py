# SPDX-License-Identifier: GPL-3.0-only
"""Full sixteen-choice candidate with routed guard pairs and physical fine RC.

All original coarse choices remain. Native fine drivers, guarded pairs and
five fine cells replace the corresponding earlier component views. Coarse
control cells, shared base MIM and common wiring still require physical RC.
"""
import dcdl_weighted_direct_v2 as previous
import static_phase_clock_release_v6 as pair
import weighted_fine_control_v3 as controls

NAME='openlvds_dcdl_weighted_direct_v3'
PORTS=previous.PORTS
MODES=['guarded']
direct=previous.direct
weighted=previous.weighted
parsing=previous.parsing
GUARD=pair.PAIR


def core_instances(mode):
    if mode not in MODES:raise ValueError('Unknown physical-component bank candidate')
    original=direct.COMPOUNDS[direct.native.SC+'nand2b_4']
    return [dict(c,model=GUARD if c['model']==original else c['model'])
            for c in direct.instances()
            if not c['name'].startswith(('fine_unit','fine_buffer','fine_inverse')) and c['name']!='shared_base']


def source(mode,orders):
    rows=['.subckt '+NAME+' '+' '.join(PORTS)]
    pg=dict(VPWR='VDD',VPB='VDD',VGND='VSS',VNB='VSS')
    def add(name,model,pins):
        pins=dict(pg,**pins)
        if model not in orders or not set(orders[model])<=set(pins):raise ValueError('Missing native bank interface '+model)
        rows.append('X'+name+' '+' '.join(pg.get(pins[p],pins[p]) for p in orders[model])+' '+model)
    for cell in core_instances(mode):add(cell['name'],cell['model'],cell['pins'])
    for bit in range(5):
        add('fine_buffer'+str(bit),controls.native.CLOCK_BUFFER,dict(A=f'B{bit}',X=f'fine{bit}'))
        add('fine_inverse'+str(bit),controls.native.MODELS['inv_8'],dict(A=f'fine{bit}',Y=f'fine_b{bit}'))
        model=controls.unit.name(bit)
        if set(orders.get(model,[]))!=set(controls.unit.PORTS):raise ValueError('Missing complete physical fine interface')
        add('fine'+str(bit),model,dict(NODE='OUT',EN=f'fine{bit}',ENB=f'fine_b{bit}',VDD='VDD',VSS='VSS'))
    rows += [f'XBASE OUT VSS {weighted.CAP} w=4 l=4','.ends '+NAME,'']
    return '\n'.join(rows)


def devices(text):
    # Reuse the strict native MOS walker with the same top-level interface.
    # The name adapter changes only the parser's top header/end, never the
    # simulation library, hierarchy, electrical elements or observation paths.
    header='.subckt '+NAME+' ';end='.ends '+NAME
    if text.count(header)!=1 or text.count(end)!=1:raise ValueError('Missing/duplicate full native bank')
    return previous.devices(text.replace(header,'.subckt '+previous.NAME+' ').replace(end,'.ends '+previous.NAME))
