# SPDX-License-Identifier: GPL-3.0-only
"""PDK-binned implementation of the two-stage topology, with explicit fingers."""
import re
import dll_analog_frontend_v2 as original

VERSION='dll-analog-frontend-v2-fingered-v1'
PAIR='lvds_slew_analog_pair_v2f'
PORTS=original.PORTS
VARIANTS=original.VARIANTS
N,P,P5=original.N,original.P,original.P5


def circuit(variant):
    text,devices=original.circuit(variant)
    pattern=r'(?m)^(X\S+) (\S+ \S+ \S+ \S+) (sky130_fd_pr__(?:nfet|pfet)_01v8) w=(200|400) l=0\.3$'
    def fingers(m):
        return '\n'.join(f'{m[1]}_F{i} {m[2]} {m[3]} w=20 l=0.3' for i in range(int(m[4])//20))
    text,count=re.subn(pattern,fingers,text)
    if count!=5:raise ValueError('Expected three bias and two receiver wide-device declarations')
    text=text.replace('_v2','_v2f').replace(original.VERSION,VERSION)
    actual=[]
    for device in devices:
        if device['width_um'] in (200,400) and device['model'] in (N,P):
            actual += [dict(device,name=device['name']+'_F'+str(i),width_um=20) for i in range(int(device['width_um'])//20)]
        else:actual.append(device)
    return text,actual


def groups():
    return {'n_reference':dict(path='xf.xbias.xnref',polarity='n',fingers=10),
            'p_reference':dict(path='xf.xbias.xpref',polarity='p',fingers=20),
            **{name:dict(role,fingers=10 if role['polarity']=='n' else 20) for name,role in original.tail_roles().items()}}


def tail_roles():return original.tail_roles()


def op_parameters():
    return {name+'_f'+str(i)+'_'+field:'@m.'+r['path']+'_f'+str(i)+'.msky130_fd_pr__'+('nfet' if r['polarity']=='n' else 'pfet')+'_01v8['+field+']'
            for name,r in groups().items() for i in range(r['fingers']) for field in ('id','gm','gds','vdsat')}
