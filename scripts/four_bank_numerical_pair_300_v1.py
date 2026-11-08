#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Fresh four-section all-voltage/DC/edge and gate-classification comparison."""
from native_binary_raw_v2 import validate
from regenerated_bank_periodic_measure_v67 import crossings
import probe_tg2_p40n32_300 as SOURCE


def numerical_pair(out,rows,a,b):
    if rows[a]['error'] is not None or rows[b]['error'] is not None:
        return dict(passed=False,reason='Native pair incomplete')
    names,x=validate(out/str(a)/'bench.raw',set(),40e-9)
    other,y=validate(out/str(b)/'bench.raw',set(names),40e-9)
    method=SOURCE.prior.numerical
    forward=method.wave_difference(names,x,other,y);reverse=method.wave_difference(other,y,names,x)
    dc=max(abs(float(x[0,names.index(n)])-float(y[0,other.index(n)])) for n in names if n.startswith('v('))
    errors=[]
    for node in ('v(in)','v(out)','v(b1_out)','v(b2_out)','v(b3_out)'):
        for up in (True,False):
            first=crossings(x[:,0]*1e12,x[:,names.index(node)],.9,up)
            second=crossings(y[:,0]*1e12,y[:,other.index(node)],.9,up)
            if len(first)!=8 or len(second)!=8:return dict(passed=False,reason='Missing complete active events')
            errors.extend(abs(v-w) for v,w in zip(first,second))
    flags=True
    for label in ('section0','section1','section2','section3'):
        u=rows[a]['result']['sections'][label];v=rows[b]['result']['sections'][label]
        for key in ('bank_screen_passed','terminal_screen_passed','control_settling_passed'):
            flags=flags and u[key]==v[key]
        for key,value in u['timing'].items():
            if key.endswith('_passed'):flags=flags and value==v['timing'][key]
        for category in ('terminal_stress','controls','programming_gates','external_controls'):
            flags=flags and [q['passed'] for q in u[category]]==[q['passed'] for q in v[category]]
    flags=flags and rows[a]['result']['fixed_supply_passed']==rows[b]['result']['fixed_supply_passed']
    passed=bool(x[0,0]==y[0,0]==0 and dc<=1e-9 and flags and max(errors)<=.25
        and max(forward['maximum_all_vector_error_v'],reverse['maximum_all_vector_error_v'])<=.002)
    return dict(passed=passed,reference_difference=forward,reverse_difference=reverse,
                maximum_dc_voltage_error_v=dc,maximum_crossing_error_ps=max(errors),all_gate_classifications_preserved=flags)

