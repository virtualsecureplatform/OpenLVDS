#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Startup-inclusive four-section native transport; no DLL or PHY admission."""
import numpy as np
from native_binary_raw_v2 import validate
from dcdl_uniform_tree_v3 import encode
import two_bank_native_measure_300_v1 as original
import two_bank_independent_measure_300_v1 as independent

VERSION='four-section-relative-native-transport-300-v1'


def measure(folder,observations,s,*,codes=((0,0),(0,0),(0,0)),independent_reader=False):
    if len(codes)!=3 or set(observations)!={f'section{k}' for k in range(4)}:
        raise ValueError('Require four separate native section maps and three downstream codes')
    devices=[d['name'] for o in observations.values() for d in o['devices']]
    if (len(devices)!=len(set(devices)) or any(not o[key] for o in observations.values()
            for key in ('devices','controls','programming_gates'))):
        raise ValueError('Require nonempty disjoint native section observation maps')
    column=lambda n:'v('+n.replace(':','.').lower()+')'
    rowspec=[];required={'v(vdd)'}
    for k,(c,f) in enumerate([(s['coarse'],s['fine']),*codes]):
        a='IN' if k==0 else 'OUT' if k==1 else f'B{k-1}_OUT'
        b='OUT' if k==0 else f'B{k}_OUT'
        o=observations[f'section{k}'];prefix='' if k==0 else f'B{k}_'
        if k and any(o[key]!=value for key,value in dict(input_node=a,output_node=b,coarse=c,fine=f).items()):
            raise ValueError('Section observation wiring or code differs from fixture')
        pins={prefix+p:v for p,v in encode(c,f).items()}
        rowspec.append((k,a,b,c,f,o,pins))
        required.update(column(n) for n in (a,b,*pins))
        required.update(column(n) for d in o['devices'] for n in d['terminals'] if n!='0')
        required.update(column(x['node']) for x in o['controls'])
        required.update(column(x['gate_node']) for x in o['programming_gates'])
    names,w=validate(folder/'bench.raw',required,s['stop_ns']*1e-9)
    idx={n:k for k,n in enumerate(names)};time=w[:,idx['time']]*1e12
    if abs(time[0])>1e-6:raise ValueError('Four-section trace omits native DC/startup sample')
    zero=np.zeros(len(time));get=lambda n:zero if n=='0' else w[:,idx[column(n)]]
    reader=independent if independent_reader else original
    sections={}
    for k,a,b,c,f,o,pins in rowspec:
        timing=reader.stage(time,get(a),get(b),dict(s,coarse=c,fine=f),ideal_input=k==0)
        electrical=reader.electrical(time,get,o,c,f);external=[]
        for pin,value in pins.items():
            error=float(np.max(np.abs(get(pin)-1.8*value)))
            external.append(dict(node=pin,maximum_deviation_v=error,passed=bool(error<=.01)))
        passed=bool(timing['stage_transport_passed'] and electrical['terminal_screen_passed']
                    and electrical['control_settling_passed'] and all(r['passed'] for r in external))
        sections[f'section{k}']=dict(timing=timing,**electrical,external_controls=external,bank_screen_passed=passed)
    error=float(np.max(np.abs(get('VDD')-1.8)))
    return dict(sections=sections,four_section_transport_passed=bool(error<=1e-9 and all(
        r['bank_screen_passed'] for r in sections.values())),maximum_supply_error_v=error,
        fixed_supply_passed=bool(error<=1e-9),startup_samples_retained=True,
        detector_dcc_fanout_qualified=False,common_wire_rc_qualified=False,qualified_phy=False,
        scope='Four native section transport diagnostic only; no calibrated phase, fanout, routing or PHY admission')
