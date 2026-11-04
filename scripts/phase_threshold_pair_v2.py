# SPDX-License-Identifier: GPL-3.0-only
"""Matched native switchable-load threshold branches after edge conditioning.

Explore one 2x2 MIM unit behind each buf_8 driver. Complementary selection
loads only one branch, producing signed relative delay without advancing an
edge. Absolute threshold and detector bias must be characterized at every PVT;
no ideal picosecond delay or nominal capacitor timing is assumed.
"""
VERSION='native-phase-threshold-pair-v2.1'
N='sky130_fd_pr__nfet_01v8'
P='sky130_fd_pr__pfet_01v8'
CAP='sky130_fd_pr__cap_mim_m3_1'


def circuit():
    lines=['.subckt phase_threshold_pair REF FDB POS RTH FTH VDD VSS',
        'XER POS VSS VSS VDD VDD er sky130_fd_sc_hd__inv_1',
        'XEF POS VSS VSS VDD VDD ef sky130_fd_sc_hd__buf_1',
        'XEBR er VSS VSS VDD VDD ebr sky130_fd_sc_hd__inv_1',
        'XEBF ef VSS VSS VDD VDD ebf sky130_fd_sc_hd__inv_1']
    devices=[]
    for suffix,source,out in [('r','REF','RTH'),('f','FDB','FTH')]:
        node='node_'+suffix;cap='cap_'+suffix;en='e'+suffix;enb='eb'+suffix
        lines.append(f'XDRV{suffix} {source} VSS VSS VDD VDD {node} sky130_fd_sc_hd__buf_8')
        entries=[('NSW',[node,en,cap,'VSS'],N,.42),('PSW',[cap,enb,node,'VDD'],P,.84),
                 ('CLR',[cap,enb,'VSS','VSS'],N,.42)]
        for name,terminals,model,width in entries:
            instance='X'+name+suffix
            lines.append(instance+' '+' '.join(terminals)+f' {model} w={width:g} l=0.15')
            mapped=['0' if n=='VSS' else 'VDD' if n=='VDD' else 'XT:'+n for n in terminals]
            devices.append(dict(name='XT:'+instance,model=model,width_um=width,length_um=.15,terminals=mapped))
        for name,terminal in [('UNIT',cap),('BASE',node),('CTRL',enb)]:
            lines.append(f'XC{name}{suffix} {terminal} VSS {CAP} w=2 l=2')
        lines.append(f'XOUT{suffix} {node} VSS VSS VDD VDD {out} sky130_fd_sc_hd__buf_4')
    return '\n'.join(lines+['.ends phase_threshold_pair','']),devices
