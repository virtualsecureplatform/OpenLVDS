# SPDX-License-Identifier: GPL-3.0-only
"""Five digitally switched MIM weights with unchanged total fine-cap area.

This is an unqualified architecture experiment. Native compound core RC is
retained; weighted switches, control cells and common wiring need new physical
proofs. Production thermometer-bank RTL and its artifacts remain unchanged.
"""
import dcdl_mim_bank_physical_v2 as old
import native_clock_components_v2 as parsing

NAME='openlvds_dcdl_weighted_fine_v2'
PORTS=['IN','OUT',*[f'C{i}' for i in range(15)],*[f'B{i}' for i in range(5)],'VDD','VSS']
GEOMETRIES=[(2,3),(3,4),(4,6),(6,8),(8,12)]
SCALES={'unit':[1,1,1,1,1],'root':[1,2,2,3,4]}
N='sky130_fd_pr__nfet_01v8'
P='sky130_fd_pr__pfet_01v8'
CAP='sky130_fd_pr__cap_mim_m3_1'


def fine_cells(variant):
    if variant not in SCALES:raise ValueError('Unknown weighted-switch sizing profile')
    rows=[]
    for bit,((w,l),scale) in enumerate(zip(GEOMETRIES,SCALES[variant])):
        rows += [f'.subckt weighted_{variant}_{bit} NODE EN ENB VDD VSS',
            f'XSWN NODE EN CAP VSS {N} w={.42*scale:g} l=0.15',
            f'XSWP CAP ENB NODE VDD {P} w={.84*scale:g} l=0.15',
            f'XCLR CAP ENB VSS VSS {N} w={.42*scale:g} l=0.15',
            f'XCUNIT CAP VSS {CAP} w={w} l={l}',
            f'XCCTRL ENB VSS {CAP} w=2 l=2',f'.ends weighted_{variant}_{bit}']
    return '\n'.join(rows)+'\n'


def source(variant,orders):
    if variant not in SCALES:raise ValueError('Unknown weighted-switch sizing profile')
    rows=['.subckt '+NAME+' '+' '.join(PORTS)]
    pg=dict(VPWR='VDD',VPB='VDD',VGND='VSS',VNB='VSS')
    for c in old.instances():
        if c['name'].startswith(('fine_unit','fine_buffer','fine_inverse')) or c['name']=='shared_base':continue
        model=c['model']
        if model not in orders:raise ValueError('Missing native core pin order: '+model)
        pins=dict(pg,**c['pins']);nodes=[pg.get(pins[p],pins[p]) for p in orders[model]]
        rows.append('X'+c['name']+' '+' '.join(nodes)+' '+model)
    for bit in range(5):
        for suffix,model,pins in [('buffer',old.native.SC+'buf_1',dict(A=f'B{bit}',X=f'fine{bit}')),
                                  ('inverse',old.native.SC+'inv_1',dict(A=f'fine{bit}',Y=f'fine_b{bit}'))]:
            pins=dict(pg,**pins);rows.append(f'Xfine_{suffix}{bit} '+' '.join(pins[p] for p in orders[model])+' '+model)
        rows.append(f'Xfine{bit} r0 fine{bit} fine_b{bit} VDD VSS weighted_{variant}_{bit}')
    rows += [f'XBASE r0 VSS {CAP} w=4 l=4','.ends '+NAME]
    return '\n'.join(rows)+'\n'


def mapped_mos(text):
    defs=parsing.definitions(text);result=[]
    def visit(model,mapping,prefix,seen):
        if model in seen:raise ValueError('Recursive weighted-bank hierarchy')
        ports,body=defs[model]
        if len(ports)!=len(mapping):raise ValueError('Weighted-bank pin mismatch')
        def node(n):return '0' if n=='0' else mapping.get(n,prefix+':'+n)
        for w in body:
            if w[0][0].upper() in ['R','C']:continue
            if w[0][0].upper()!='X':raise ValueError('Unknown weighted-bank element')
            end=next((i for i,v in enumerate(w) if '=' in v),len(w));child=w[end-1];nodes=[node(n) for n in w[1:end-1]];name=prefix+':'+w[0]
            if child in defs:
                if len(nodes)!=len(defs[child][0]):raise ValueError('Weighted-bank child pin mismatch')
                visit(child,dict(zip(defs[child][0],nodes)),name,seen|{model})
            elif child in [N,P,'sky130_fd_pr__pfet_01v8_hvt']:
                if len(nodes)!=4:raise ValueError('Weighted-bank MOS pin mismatch')
                result.append(dict(name=name,model=child,terminals=nodes,limit_v=1.95))
            elif child.startswith('sky130_fd_pr__') and ('cap_mim_' in child or 'res_generic_' in child):continue
            else:raise ValueError('Unknown weighted-bank native primitive '+child)
    visit(NAME,{p:('0' if p=='VSS' else p) for p in PORTS},'XD',set())
    return result
