# SPDX-License-Identifier: GPL-3.0-only
"""Direct-port weighted fine bank, with an optional native NAND2B guard.

Keep every coarse choice and the five existing weighted MIM/TG geometries.
Guarded mode replaces each paired NAND2B with two actual guarded single-cell
macros. Their parallel interconnect and all common wiring need physical proof.
"""
import dcdl_weighted_fine_v2 as weighted
import dcdl_mim_bank_direct_v2 as direct
import static_phase_clock_release_v5 as release
import native_clock_components_v2 as parsing

NAME='openlvds_dcdl_weighted_direct_v2'
PORTS=weighted.PORTS
MODES=['guarded','plain']
GUARD=release.MACROS['o1']
FINE_PROFILE='root'


def core_instances(mode):
    if mode not in MODES:raise ValueError('Unknown direct weighted guard mode')
    result=[];paired=direct.COMPOUNDS[direct.native.SC+'nand2b_4']
    for cell in direct.instances():
        if cell['name'].startswith(('fine_unit','fine_buffer','fine_inverse')) or cell['name']=='shared_base':continue
        if mode=='guarded' and cell['model']==paired:
            result += [dict(name=cell['name']+'_guard'+str(i),model=GUARD,pins=dict(cell['pins'])) for i in range(2)]
        else:result.append(cell)
    return result


def source(mode,orders):
    rows=['.subckt '+NAME+' '+' '.join(PORTS)]
    pg=dict(VPWR='VDD',VPB='VDD',VGND='VSS',VNB='VSS')
    def add(name,model,pins):
        pins=dict(pg,**pins)
        if model not in orders or not set(orders[model])<=set(pins):raise ValueError('Missing native weighted-bank interface '+model)
        rows.append('X'+name+' '+' '.join(pg.get(pins[p],pins[p]) for p in orders[model])+' '+model)
    for cell in core_instances(mode):add(cell['name'],cell['model'],cell['pins'])
    for bit in range(5):
        add('fine_buffer'+str(bit),direct.native.SC+'buf_1',dict(A=f'B{bit}',X=f'fine{bit}'))
        add('fine_inverse'+str(bit),direct.native.SC+'inv_1',dict(A=f'fine{bit}',Y=f'fine_b{bit}'))
        rows.append(f'Xfine{bit} OUT fine{bit} fine_b{bit} VDD VSS weighted_{FINE_PROFILE}_{bit}')
    rows += [f'XBASE OUT VSS {weighted.CAP} w=4 l=4','.ends '+NAME,'']
    return weighted.fine_cells(FINE_PROFILE)+'\n'.join(rows)


def devices(text):
    # conb_1 contains real passive poly resistors as well as MOS. Retain all
    # electrical statements; skip only known passive leaves when saving MOS.
    defs=parsing.definitions(text);result=[]
    def walk(model,pins,path,ancestors):
        if model in ancestors:raise ValueError('Recursive direct weighted hierarchy')
        ports,body=defs[model]
        if set(pins)!=set(ports):raise ValueError('Direct weighted interface mismatch')
        def net(n):return '0' if n=='0' else pins.get(n,path+':'+n)
        for w in body:
            if w[0][0].upper() in ['R','C']:continue
            if w[0][0].upper()!='X':raise ValueError('Unknown direct weighted active element')
            first=next((i for i,v in enumerate(w) if '=' in v),len(w));child=w[first-1]
            nodes=[net(n) for n in w[1:first-1]];name=path+':'+w[0]
            if child in defs:
                if len(nodes)!=len(defs[child][0]):raise ValueError('Direct weighted child pin mismatch')
                walk(child,dict(zip(defs[child][0],nodes)),name,ancestors|{model})
            elif child in [weighted.CAP,'sky130_fd_pr__res_generic_po']:
                if len(nodes)!=2:raise ValueError('Passive native leaf port count changed')
            elif child in [weighted.N,weighted.P,'sky130_fd_pr__pfet_01v8_hvt']:
                if len(nodes)!=4:raise ValueError('Native MOS port count changed')
                result.append(dict(name=name,model=child,limit_v=1.95,terminals=nodes))
            else:raise ValueError('Unknown direct weighted native leaf '+child)
    walk(NAME,{p:'0' if p=='VSS' else p for p in PORTS},'XD',set())
    if len({d['name'] for d in result})!=len(result) or not result:raise ValueError('Missing/duplicate native MOS witnesses')
    return result
