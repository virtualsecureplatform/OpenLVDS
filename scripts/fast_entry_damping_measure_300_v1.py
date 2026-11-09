#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Keep all entry/stress gates and check every added fixed shunt control."""
import numpy as np
import fast_entry_damping_bank_300_v1 as architecture
import two_bank_entry_measure_300_v1 as previous
from native_binary_raw_v2 import validate


def fixed_gates(observation,kind,prefix):
    if kind not in architecture.KINDS:raise ValueError('Unknown fast-entry measurement intervention')
    actual={d['name']:d for d in observation['devices']}
    added={n:d for n,d in actual.items() if ':Xdamp:' in n}
    if kind=='decode_drive2':
        if added:raise ValueError('Unexpected shunt in drive-only intervention')
        return []
    cell=architecture.source.qualified_cell();model=architecture.source.MODEL
    ports,body=architecture.native.definitions(cell)[model];graph={}
    for w in body:
        if w[0][0].upper()=='R':
            graph.setdefault(w[1],set()).add(w[2]);graph.setdefault(w[2],set()).add(w[1])
    def reaches(start):
        seen={start};todo=[start]
        while todo:
            for n in graph.get(todo.pop(),()):
                if n not in seen:seen.add(n);todo.append(n)
        return seen
    control={p:reaches(p) for p in ('EN','ENB')}
    if control['EN']&control['ENB']:raise ValueError('Qualified shunt controls shorted')
    gates=[];expected={}
    for stage in [*[f'Xdelay{k}' for k in range(1,16)],'Xtail_load']:
        name=prefix+':'+stage+':Xdamp'
        pins=dict(zip(ports,[prefix+':'+stage+':mid','VDD','0','VDD','0']))
        unit=architecture.native.mapped_mos(cell,model,pins,name)
        for d in unit:
            if actual.get(d['name'])!=d:raise ValueError('Added shunt transistor map changed')
            expected[d['name']]=d
            local=d['terminals'][1].removeprefix(name+':')
            matches=[p for p,nodes in control.items() if local in nodes]
            if len(matches)!=1:raise ValueError('Unresolved fixed shunt control gate')
            gates.append(dict(device=d['name'],gate_node=d['terminals'][1],target_v=1.8 if matches[0]=='EN' else 0.0))
    if added!=expected or len(gates)!=48:raise ValueError('Require all sixteen complete fixed shunts')
    return gates


def check_fixed(get,gates,*,independent=False):
    rows=[]
    for g in gates:
        values=get(g['gate_node']);target=g['target_v']
        if not len(values) or not np.isfinite(values).all():raise ValueError('Invalid fixed-gate waveform')
        if independent:
            deviation=max(abs(float(values.min())-target),abs(float(values.max())-target))
        else:deviation=float(np.max(np.abs(values-target)))
        rows.append(dict(g,maximum_deviation_v=deviation,passed=bool(deviation<=.18)))
    return rows


def measure(folder,observations,s,*,independent_reader=False):
    result=previous.measure(folder,observations,s,next_coarse=0,next_fine=0,independent_reader=independent_reader)
    kind=s['fast_entry_intervention']
    controls={label:fixed_gates(observations[label],kind,prefix) for label,prefix in (('first','XD'),('next','XL'))}
    column=lambda n:'v('+n.replace(':','.').lower()+')'
    names,w=validate(folder/'bench.raw',{column(g['gate_node']) for gates in controls.values() for g in gates},40e-9)
    index={n:k for k,n in enumerate(names)}
    # Fixed rails must hold from DC, including the interval before the normal
    # programmable controls' 1.5 ns settling deadline.
    checks={label:check_fixed(lambda n:w[:,index[column(n)]],gates,independent=independent_reader)
            for label,gates in controls.items()}
    for label,rows in checks.items():
        passed=all(g['passed'] for g in rows)
        result['banks'][label]['fixed_shunt_gates']=rows
        result['banks'][label]['fixed_shunt_controls_passed']=passed
        result['banks'][label]['bank_screen_passed']=bool(result['banks'][label]['bank_screen_passed'] and passed)
    result['fixed_shunt_controls_passed']=all(g['passed'] for rows in checks.values() for g in rows)
    result['two_bank_zero_pilot_passed']=bool(result['two_bank_zero_pilot_passed'] and result['fixed_shunt_controls_passed'])
    return result
