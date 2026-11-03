# SPDX-License-Identifier: GPL-3.0-only
"""Compensate the measured low-VDS preamp-tail current deficit geometrically."""
import re
import dll_analog_frontend_v2_fingered as base

VERSION='dll-analog-frontend-v2-tail-trim-v1'
PAIR='lvds_slew_analog_pair_v2t'
PORTS=base.PORTS
VARIANTS=base.VARIANTS
N,P,P5=base.N,base.P,base.P5
# The retained aggregation engine uses this logical role schema only;
# actual saved operating-point vectors always come from op_parameters below.
original=base.original


def circuit(variant):
    text,devices=base.circuit(variant)
    pattern=r'(?m)^(XTAIL_F9 [^\n]+)$'
    text,count=re.subn(pattern,lambda m:m[0]+'\n'+m[0].replace('XTAIL_F9','XTAIL_F10')+'\n'+m[0].replace('XTAIL_F9','XTAIL_F11'),text)
    if count!=1:raise ValueError('Expected one matched preamp tail declaration')
    text=text.replace('_v2f','_v2t').replace(base.VERSION,VERSION)
    actual=list(devices)
    for d in devices:
        if d['name'].endswith(':XTAIL_F9'):
            actual += [dict(d,name=d['name'].replace(':XTAIL_F9',':XTAIL_F'+str(i))) for i in (10,11)]
    return text,actual


def groups():
    return {name:dict(role,fingers=12 if name in ('ref_pre','fb_pre') else role['fingers']) for name,role in base.groups().items()}


def tail_roles():return base.tail_roles()


def op_parameters():
    return {name+'_f'+str(i)+'_'+field:'@m.'+r['path']+'_f'+str(i)+'.msky130_fd_pr__'+('nfet' if r['polarity']=='n' else 'pfet')+'_01v8['+field+']'
            for name,r in groups().items() for i in range(r['fingers']) for field in ('id','gm','gds','vdsat')}
