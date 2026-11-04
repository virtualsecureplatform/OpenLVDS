# SPDX-License-Identifier: GPL-3.0-only
"""Inline exact native transistor cells without resizing or private-node aliases."""
from build_compound_drivers_v3 import cell_definition


def inline(cells,library):
    definitions={};result=[]
    for short in sorted({short for _,short,_ in cells}):
        model='sky130_fd_sc_hd__'+short;block=cell_definition(library,model)
        definitions[short]=(block.splitlines()[0].split()[2:],block.splitlines()[1:-1])
    for tag,short,pins in cells:
        ports,body=definitions[short];pins=dict(VGND='VGND',VNB='VGND',VPWR='VPWR',VPB='VPWR',**pins)
        if set(pins)!=set(ports):raise ValueError('Native static cell interface changed')
        for line in body:
            words=line.split()
            if not words or words[0].startswith('*'):continue
            if not words[0].startswith('X') or len(words)<6 or not words[5].startswith('sky130_fd_pr__'):
                raise ValueError('Unexpected native static cell transistor')
            nodes=[pins.get(n,tag+'__'+n) for n in words[1:5]]
            result.append('X'+tag+'__'+words[0]+' '+' '.join([*nodes,*words[5:]]))
    return '\n'.join(result)+'\n'
