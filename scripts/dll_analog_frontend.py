# SPDX-License-Identifier: GPL-3.0-only
"""Bounded shared-bias differential clock receiver for the conditional fallback.

Circuit text is emitted only by the gated experiment producer. This private
eight-port pair interface does not change the public DLL interface.
"""
VERSION='dll-analog-frontend-v1'
PAIR='lvds_slew_analog_pair_v1'
PORTS='REF FDB REF_FAST FDB_FAST PB VDDIO VDDD VSS'.split()
VARIANTS={f'tail{tail}_w{width}':dict(tail_ua=tail,input_width_um=width,mirror_width_um=tail/35*2)
          for tail in (140,280) for width in (20,40)}
N='sky130_fd_pr__nfet_01v8'
P='sky130_fd_pr__pfet_01v8'
P5='sky130_fd_pr__pfet_g5v0d10v5'


def circuit(variant):
    if variant not in VARIANTS:raise ValueError('Unknown bounded analog frontend')
    spec=VARIANTS[variant];blocks=[];declared={}
    def block(name,ports,devices,extra=()):
        declared[name]=(ports,devices)
        rows=['.subckt '+name+' '+' '.join(ports)]
        for label,terminals,model,width,length in devices:
            rows.append(label+' '+' '.join(terminals)+' '+model+f' w={width:g} l={length:g}')
        blocks.append('\n'.join([*rows,*extra,'.ends '+name]))
    # The endpoint's 35 uA reference drives a 4x/8x HV PMOS mirror.
    # A local diode-connected 1.8 V NFET sets the two equal-size tail gates.
    # Connecting these wide 1.8 V tails directly to the endpoint HV NB is invalid.
    block('lvds_slew_analog_bias','PB VCM NTAIL VDDIO VDDD VSS'.split(),[
        ('XPM',('NTAIL','PB','VDDIO','VDDIO'),P5,spec['mirror_width_um'],1),
        ('XNREF',('NTAIL','NTAIL','VSS','VSS'),N,100,.3)],extra=[
        'XRT VDDD VCM VSS sky130_fd_pr__res_high_po_0p35 w=0.35 l=85',
        'XRB VCM VSS VSS sky130_fd_pr__res_high_po_0p35 w=0.35 l=85',
        # Approximately 1 pF in the pinned MIM model, with legal PCell dimensions.
        'XCM VCM VSS sky130_fd_pr__cap_mim_m3_1 w=22 l=22'])
    block('lvds_slew_analog_rx','CLK OUT VCM NTAIL VDDD VSS'.split(),[
        # Clock on the diode-load branch gives a non-inverting decision.
        ('XCLK',('L','CLK','T','VSS'),N,spec['input_width_um'],.15),
        ('XREF',('O','VCM','T','VSS'),N,spec['input_width_um'],.15),
        ('XPL',('L','L','VDDD','VDDD'),P,8,.3),
        ('XPR',('O','L','VDDD','VDDD'),P,8,.3),
        ('XTAIL',('T','NTAIL','VSS','VSS'),N,100,.3),
        ('XIP0',('MID','O','VDDD','VDDD'),P,4,.15),
        ('XIN0',('MID','O','VSS','VSS'),N,2,.15),
        ('XIP1',('OUT','MID','VDDD','VDDD'),P,16,.15),
        ('XIN1',('OUT','MID','VSS','VSS'),N,8,.15)])
    instances=[('XBIAS','lvds_slew_analog_bias','PB VCM NTAIL VDDIO VDDD VSS'.split()),
               ('XREF','lvds_slew_analog_rx','REF REF_FAST VCM NTAIL VDDD VSS'.split()),
               ('XFB','lvds_slew_analog_rx','FDB FDB_FAST VCM NTAIL VDDD VSS'.split())]
    blocks.append('\n'.join(['.subckt '+PAIR+' '+' '.join(PORTS),
                           *[label+' '+' '.join(nodes)+' '+name for label,name,nodes in instances],'.ends '+PAIR]))
    devices=[]
    top=dict(zip(PORTS,['REF','FDB','REF_FAST','FDB_FAST','PB','VDDIO','VDDD','0']))
    for label,name,nodes in instances:
        ports,decls=declared[name]
        mapping=dict(zip(ports,[top.get(n,'XF:'+n) for n in nodes]))
        for dev,terminals,model,w,l in decls:
            devices.append(dict(name='XF:'+label+':'+dev,model=model,width_um=w,length_um=l,
                                terminals=[mapping.get(n,'XF:'+label+':'+n) for n in terminals]))
    return '* '+VERSION+' '+variant+'\n'+'\n\n'.join(blocks)+'\n',devices


def op_parameters():
    result={}
    for label,path in [('reference','xf.xbias.xnref'),('ref_tail','xf.xref.xtail'),('fb_tail','xf.xfb.xtail')]:
        base='@m.'+path+'.msky130_fd_pr__nfet_01v8'
        for field in ('id','gm','gds','vdsat'):result[label+'_'+field]=base+'['+field+']'
    return result
