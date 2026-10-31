#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Double receiver decision current and reduce its restoration-input capacitance."""
import json
from pathlib import Path
import re
from layout import ROOT,circuits
from layout_receiver_tail_candidate import source_variant as input_source
from layout_receiver_variant import build
from spice_library import replace

MID='lvds_rx_restore_mid'


def source_variant(source,scale=2):
    if scale!=2:raise ValueError('This experiment retains doubled input tails')
    source=input_source(source,scale);definitions=circuits(source)
    if MID in definitions:raise ValueError('Receiver restoration helper already exists')
    ports,rows=definitions['openlvds_receiver_core']
    original=re.search(r'(?ims)^\.subckt openlvds_receiver_core\s.*?^\.ends[^\n]*',source)[0];changed=original
    expected={
        'XCT':(['CT','NBC','VSS','VSS'],'nfet',64,.5),
        'XC0':(['CL','PN','CT','VSS'],'nfet',8,.15),
        'XC1':(['CO','PP','CT','VSS'],'nfet',8,.15),
        'XCD':(['CL','CL','VDDD','VDDD'],'pfet',8,.15),
        'XCM':(['CO','CL','VDDD','VDDD'],'pfet',8,.15)}
    selected={r[0]:r for r in rows if r[0] in expected}
    if set(selected)!=set(expected):raise ValueError('Missing decision-stage devices')
    for name,(nodes,kind,width,length) in expected.items():
        _,actual,model,params=selected[name]
        if actual!=nodes or model!='sky130_fd_pr__'+kind+'_01v8' or set(params)!={'w','l'} or float(params['w'])!=width or float(params['l'])!=length:
            raise ValueError('Unknown receiver decision topology')
        old=next(line for line in changed.splitlines() if line.startswith(name+' '))
        new=re.sub(r'\bw=\S+',f'w={width*2}',old);changed=changed.replace(old,new,1)
    restore=[r for r in rows if r[0]=='XI']
    if len(restore)!=1 or restore[0][1:]!=(['CO','Q','VDDD','VSS'],'lvds_inv18_drive',{}):
        raise ValueError('Unknown receiver output restoration path')
    if any(n.endswith('__RESTORE0') or n.endswith('__RESTORE1') or n in ['RESTORE0','RESTORE1'] for _,ns,_,_ in rows for n in ns):
        raise ValueError('Restoration nodes already exist')
    old=next(line for line in changed.splitlines() if line.startswith('XI '))
    new=('XIB0 CO RESTORE0 VDDD VSS lvds_inv18\n'
         f'XIB1 RESTORE0 RESTORE1 VDDD VSS {MID}\n'
         'XIB2 RESTORE1 Q VDDD VSS lvds_inv18_drive')
    changed=changed.replace(old,new,1);source=replace(source,'openlvds_receiver_core',changed)
    source+=f'''\n.subckt {MID} A Y VDD VSS
XP Y A VDD VDD sky130_fd_pr__pfet_01v8 w=8 l=0.15
XN Y A VSS VSS sky130_fd_pr__nfet_01v8 w=4 l=0.15
.ends {MID}
'''
    if circuits(source)['openlvds_receiver_core'][0]!=ports:raise ValueError('Receiver ports changed')
    return source


def main():
    source=source_variant((ROOT/'analog/openlvds.spice').read_text())
    out,summary=build(source,dict(input_tail_scale=2,decision_scale=2,
        restoration='Three inverters: P/N widths 4/2, 8/4, 16/8; unchanged overall polarity'),
        [Path(__file__).name,'layout_receiver_tail_candidate.py'])
    info=summary['designs']['openlvds_receiver_core']
    print(json.dumps(dict(output=str(out),passed=summary['passed'],drc_count=info['drc_count'],lvs_passed=info['lvs_passed'])),flush=True)
    return 0 if summary['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
