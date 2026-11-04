# SPDX-License-Identifier: GPL-3.0-only
"""Native static NAND DCC with physical MIM shunts on private stack nodes."""
import dcc_nand_latch_v2 as unshunted

NAME='openlvds_dcc_nand_mid_shunt_v2'
PORTS=unshunted.PORTS
CAP='sky130_fd_pr__cap_mim_m3_1'


def devices(text):
    result=[]
    for line in text.splitlines():
        words=line.split()
        if not words or not words[0].startswith('X'):continue
        first=next((i for i,w in enumerate(words) if '=' in w),len(words));model=words[first-1];nodes=words[1:first-1]
        if model.startswith('sky130_fd_pr__') and ('nfet_' in model or 'pfet_' in model):
            if len(nodes)!=4:raise ValueError('Native MOS port count changed')
            result.append(dict(name=words[0],model=model,nodes=nodes))
        elif model==CAP:
            if len(nodes)!=2:raise ValueError('Native MIM port count changed')
        else:raise ValueError('Unknown native static DCC device: '+model)
    if not result:raise ValueError('No native static DCC transistors')
    return result


def source(drive,library):
    original=unshunted.source(drive,library)
    private=sorted({n for d in devices(original) for n in d['nodes'] if '__' in n})
    if not private:raise ValueError('No native private stack nodes')
    lines=original.splitlines()
    if lines[-1]!='.ends '+unshunted.NAME:raise ValueError('Unexpected static DCC boundary')
    lines=lines[:-1];lines[0]='.subckt '+NAME+' '+' '.join(PORTS)
    lines += [f'XSTACKCAP{i} {node} VGND {CAP} w=2 l=2' for i,node in enumerate(private)]
    return '\n'.join(lines+['.ends '+NAME,'']),private
