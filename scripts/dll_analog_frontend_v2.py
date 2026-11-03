# SPDX-License-Identifier: GPL-3.0-only
"""Always-biased two-stage clock receiver, following measured v1 tail cutoff.

Matched resistor loads supply the NMOS input pair in both rail states.
Passive quarter-scale drain taps feed a PMOS differential decision stage;
its low input common mode preserves tail compliance and avoids a floating
mirror-loaded input branch. Both clocks share the same two local bias nodes.
"""
VERSION='dll-analog-frontend-v2'
PAIR='lvds_slew_analog_pair_v2'
PORTS='REF FDB REF_FAST FDB_FAST PB VDDIO VDDD VSS'.split()
VARIANTS={f'tail{tail}_w{width}':dict(tail_ua=tail,input_width_um=width,mirror_width_um=tail/35*2,load_parallel=tail//140)
          for tail in (140,280) for width in (20,40)}
N='sky130_fd_pr__nfet_01v8'
P='sky130_fd_pr__pfet_01v8'
P5='sky130_fd_pr__pfet_g5v0d10v5'


def circuit(variant):
    if variant not in VARIANTS:raise ValueError('Unknown bounded analog frontend v2')
    spec=VARIANTS[variant];blocks=[];declared={}
    def block(name,ports,devices,extra=()):
        declared[name]=(ports,devices)
        rows=['.subckt '+name+' '+' '.join(ports)]
        for label,terminals,model,width,length in devices:
            rows.append(label+' '+' '.join(terminals)+' '+model+f' w={width:g} l={length:g}')
        blocks.append('\n'.join([*rows,*extra,'.ends '+name]))
    block('lvds_slew_analog_bias_v2','PB VCM NTAIL PTAIL VDDIO VDDD VSS'.split(),[
        ('XPM',('NTAIL','PB','VDDIO','VDDIO'),P5,spec['mirror_width_um'],1),
        ('XNREF',('NTAIL','NTAIL','VSS','VSS'),N,200,.3),
        ('XNSINK',('PTAIL','NTAIL','VSS','VSS'),N,200,.3),
        ('XPREF',('PTAIL','PTAIL','VDDD','VDDD'),P,400,.3)],extra=[
        'XRT VDDD VCM VSS sky130_fd_pr__res_high_po_0p35 w=0.35 l=85',
        'XRB VCM VSS VSS sky130_fd_pr__res_high_po_0p35 w=0.35 l=85',
        'XCM VCM VSS sky130_fd_pr__cap_mim_m3_1 w=22 l=22'])
    resistors=[]
    for side,tap in [('L','DL'),('R','DR')]:
        for i in range(spec['load_parallel']):
            resistors.append(f'XLOAD_{side}_{i} VDDD {side} VSS sky130_fd_pr__res_high_po_0p35 w=0.35 l=5')
            chain=[side,f'{side}_A{i}',f'{side}_B{i}',tap,'VSS']
            for j,(a,b) in enumerate(zip(chain,chain[1:])):
                resistors.append(f'XDIV_{side}_{i}_{j} {a} {b} VSS sky130_fd_pr__res_high_po_0p35 w=0.35 l=0.5')
    block('lvds_slew_analog_rx_v2','CLK OUT VCM NTAIL PTAIL VDDD VSS'.split(),[
        ('XCLK',('L','CLK','T','VSS'),N,spec['input_width_um'],.15),
        ('XREF',('R','VCM','T','VSS'),N,spec['input_width_um'],.15),
        ('XTAIL',('T','NTAIL','VSS','VSS'),N,200,.3),
        # R rises with CLK, so the PMOS diode branch current decreases.
        # The mirrored sink falls while the L-gated output PMOS turns on.
        ('XDEC0',('QL','DR','TP','VDDD'),P,40,.15),
        ('XDEC1',('QO','DL','TP','VDDD'),P,40,.15),
        ('XNL',('QL','QL','VSS','VSS'),N,8,.3),
        ('XNR',('QO','QL','VSS','VSS'),N,8,.3),
        ('XTAIL2',('TP','PTAIL','VDDD','VDDD'),P,400,.3),
        ('XIP0',('MID','QO','VDDD','VDDD'),P,4,.15),
        ('XIN0',('MID','QO','VSS','VSS'),N,2,.15),
        ('XIP1',('OUT','MID','VDDD','VDDD'),P,16,.15),
        ('XIN1',('OUT','MID','VSS','VSS'),N,8,.15)],extra=resistors)
    instances=[('XBIAS','lvds_slew_analog_bias_v2','PB VCM NTAIL PTAIL VDDIO VDDD VSS'.split()),
               ('XREF','lvds_slew_analog_rx_v2','REF REF_FAST VCM NTAIL PTAIL VDDD VSS'.split()),
               ('XFB','lvds_slew_analog_rx_v2','FDB FDB_FAST VCM NTAIL PTAIL VDDD VSS'.split())]
    blocks.append('\n'.join(['.subckt '+PAIR+' '+' '.join(PORTS),
                           *[label+' '+' '.join(nodes)+' '+name for label,name,nodes in instances],'.ends '+PAIR]))
    devices=[];top=dict(zip(PORTS,['REF','FDB','REF_FAST','FDB_FAST','PB','VDDIO','VDDD','0']))
    for label,name,nodes in instances:
        ports,decls=declared[name];mapping=dict(zip(ports,[top.get(n,'XF:'+n) for n in nodes]))
        for dev,terminals,model,w,l in decls:
            devices.append(dict(name='XF:'+label+':'+dev,model=model,width_um=w,length_um=l,
                                terminals=[mapping.get(n,'XF:'+label+':'+n) for n in terminals]))
    return '* '+VERSION+' '+variant+'\n'+'\n\n'.join(blocks)+'\n',devices


def tail_roles():
    return {'ref_pre':dict(path='xf.xref.xtail',node='XF:XREF:T',polarity='n',reference='n_reference'),
            'fb_pre':dict(path='xf.xfb.xtail',node='XF:XFB:T',polarity='n',reference='n_reference'),
            'ref_dec':dict(path='xf.xref.xtail2',node='XF:XREF:TP',polarity='p',reference='p_reference'),
            'fb_dec':dict(path='xf.xfb.xtail2',node='XF:XFB:TP',polarity='p',reference='p_reference')}


def op_parameters():
    roles={'n_reference':dict(path='xf.xbias.xnref',polarity='n'),
           'p_reference':dict(path='xf.xbias.xpref',polarity='p'),**tail_roles()}
    return {name+'_'+field:'@m.'+r['path']+'.msky130_fd_pr__'+('nfet' if r['polarity']=='n' else 'pfet')+'_01v8['+field+']'
            for name,r in roles.items() for field in ('id','gm','gds','vdsat')}
