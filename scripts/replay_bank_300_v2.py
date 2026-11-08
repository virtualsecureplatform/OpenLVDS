#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Replay completed fresh bank cases and independently check native metrology."""
import argparse,hashlib,json,sys
from pathlib import Path
import numpy as np
import native_bank_300_v1 as first
import native_bank_300_v2 as single
import native_bank_mim4_300_v1 as mim
import clocking_profile_300 as policy
from native_binary_raw_v2 import validate
from dcdl_tg_tree_v5 import control_targets
ROOT=policy.ROOT
VERSION='independent-fresh-bank-native-metrology-300-v2'


def independent_timing(t,inp,out,s):
    def edges(v,threshold,up):
        a=v[:-1]-threshold;b=v[1:]-threshold
        mask=(a<0)&(b>=0) if up else (a>0)&(b<=0)
        k=np.flatnonzero(mask)
        return t[k]+(-a[k])/(b[k]-a[k])*(t[k+1]-t[k])
    delays={};slews={};event={};periods={};counts={};input_errors=[];ordered=True
    for edge,up in (('rise',True),('fall',False)):
        a=edges(inp,.9,up);b=edges(out,.9,up);lo=edges(out,.18,up);hi=edges(out,1.62,up)
        if any(len(v)!=s['cycles'] for v in (a,b,lo,hi)):
            raise ValueError('Independent replay requires every full-swing native input/output event')
        expected=2100+(np.arange(s['cycles'])+(0 if up else s['duty']))*1e6/s['frequency_mhz']
        input_errors.extend(abs(a-expected));delays[edge]=(b-a).tolist();slews[edge]=abs(hi-lo).tolist()
        ordered=ordered and bool(np.all((lo<b)&(b<hi) if up else (hi<b)&(b<lo)))
        event[edge]=b;periods[edge]=(np.diff(b)-1e6/s['frequency_mhz']).tolist()
        counts[edge]=dict(input=len(a),output=len(b),output_10_percent=len(lo),output_90_percent=len(hi))
    high=(event['fall']-event['rise']).tolist();low=(event['rise'][1:]-event['fall'][:-1]).tolist()
    span={e:max(v)-min(v) for e,v in delays.items()};max_period=max(abs(v) for a in periods.values() for v in a)
    max_slew=max(v for a in slews.values() for v in a);zero=s['coarse']==s['fine']==0
    head=policy.budgets()['minimum_quarter_ps']-max(v for a in delays.values() for v in a) if zero else None
    return dict(pulse_counts=counts,edge_delays_ps=delays,output_slews_10_90_ps=slews,
        high_widths_ps=high,low_widths_ps=low,period_errors_ps=periods,repeated_delay_span_ps=span,
        maximum_output_slew_ps=max_slew,maximum_period_error_ps=max_period,
        output_duty_percent=[v*s['frequency_mhz']/1e4 for v in high],
        all_input_output_pulses_present=True,input_timing_stimulus_passed=bool(max(input_errors)<=1),
        full_swing_pulses_passed=ordered,unwrapped_native_epoch_passed=all(0<v<1e6/s['frequency_mhz'] for a in delays.values() for v in a),
        pulse_order_and_widths_passed=all(v>0 for v in high+low),period_screen_passed=max_period<=20,
        repeated_delay_screen_passed=all(v<=20 for v in span.values()),
        current_downstream_250ps_slew_domain_passed=ordered and max_slew<=250,
        downstream_slew_domain_widening_required=ordered and max_slew>250,
        zero_code_quarter_check_required=zero,zero_code_fast_quarter_headroom_ps=head,
        zero_code_quarter_passed=bool(head>=0) if zero else True)


def same(a,b):
    if isinstance(a,dict):return isinstance(b,dict) and a.keys()==b.keys() and all(same(v,b[k]) for k,v in a.items())
    if isinstance(a,list):return isinstance(b,list) and len(a)==len(b) and all(same(v,w) for v,w in zip(a,b))
    if isinstance(a,bool) or a is None:return a is b
    if isinstance(a,(int,float)) and isinstance(b,(int,float)):return bool(np.isfinite(a) and np.isfinite(b) and abs(a-b)<=1e-6)
    return a==b


def independent(folder,identity,s,recorded):
    o=identity['observations'];column=lambda n:'v('+n.replace(':','.').lower()+')'
    required={column(n) for d in o['devices'] for n in d['terminals'] if n!='0'}
    required.update(column(c['node']) for c in o['controls']);required.update(column(g['gate_node']) for g in o['programming_gates'])
    required.update({'v(in)','v(out)','v(vdd)'})
    names,w=validate(folder/'bench.raw',required,40e-9);idx={n:k for k,n in enumerate(names)}
    t=w[:,idx['time']]*1e12;zero=np.zeros(len(t))
    if t[0]>1e-6:raise ValueError('Independent native replay requires startup')
    get=lambda n:zero if n=='0' else w[:,idx[column(n)]]
    timing=independent_timing(t,get('IN'),get('OUT'),s)
    if any(not same(v,recorded[k]) for k,v in timing.items()):raise ValueError('Independent native timing does not reproduce')
    stress=[]
    for d in o['devices']:
        voltages=[get(n) for n in d['terminals']]
        peak=float(np.max(np.maximum.reduce(voltages)-np.minimum.reduce(voltages)))
        stress.append(dict(device=d['name'],maximum_terminal_difference_v=peak,limit_v=d['limit_v'],passed=peak<=d['limit_v']))
    if not same(stress,recorded['terminal_stress']):raise ValueError('Independent terminal envelope does not reproduce')
    targets=control_targets(s['coarse'],s['fine']);settled=t>=1500;checks={}
    for category,key in (('controls','node'),('programming_gates','gate_node')):
        checks[category]=[]
        for c in o[category]:
            values=get(c[key])[settled];target=1.8*targets[c['control']]
            deviation=max(abs(float(values.min())-target),abs(float(values.max())-target))
            checks[category].append(dict(c,maximum_deviation_v=deviation,passed=deviation<=.18))
        if not same(checks[category],recorded[category]):raise ValueError('Independent '+category+' settling does not reproduce')
    return dict(independent_timing_reproduced=True,independent_terminal_envelope_reproduced=True,
        independent_control_and_gate_settling_reproduced=True,native_mos=len(stress),controls=len(checks['controls']),
        programming_gates=len(checks['programming_gates']),timing=timing,
        worst_terminal=max(stress,key=lambda r:r['maximum_terminal_difference_v']))


def run(parent,numbers):
    raw=json.loads((parent/'manifest.json').read_text());version=raw['identity']['version']
    producer={first.VERSION:first,single.VERSION:single,mim.VERSION:mim}.get(version)
    if producer is None:raise ValueError('Require a fresh captured 300 MHz bank campaign')
    m=producer.bound(parent);i=m['identity'];original,_=producer.PARENTS[i['kind']]
    if producer is first and i['source_identity']!=original.bound(producer.PARENTS[i['kind']][1],full=False)['identity']:
        raise ValueError('Original source identity must match the bound parent exactly')
    if i['bench_current_offset_a']!=.001 or i['power_excludes_external_bench_load'] is not True:
        raise ValueError('Require declared external bench offset and power exclusion')
    if not numbers or len(set(numbers))!=len(numbers) or any(n not in [t['id'] for t in m['tasks']] for n in numbers):
        raise ValueError('Require explicit unique captured case IDs')
    inputs={**i['inputs'],**i['source_identity']['pdk_files'],**i['source_identity']['external_files'],
        str((parent/'manifest.json').relative_to(ROOT)):producer.sha(parent/'manifest.json'),
        str((parent/'bank.spice').relative_to(ROOT)):producer.sha(parent/'bank.spice')}
    selected=[]
    for n in numbers:
        folder=parent/n;row=json.loads((folder/'summary.json').read_text())
        if row['error'] is not None or row['task']!=m['tasks'][int(n)] or not {'bench.raw','bench.cir'}<=set(row['files']):
            raise ValueError('Require complete error-free original native case')
        for name,digest in row['files'].items():
            if producer.sha(folder/name)!=digest:raise ValueError('Completed native case changed: '+n+'/'+name)
            inputs[str((folder/name).relative_to(ROOT))]=digest
        inputs[str((folder/'summary.json').relative_to(ROOT))]=producer.sha(folder/'summary.json');selected.append(row)
    inputs.update({str(Path(mod.__file__).resolve().relative_to(ROOT)):producer.sha(Path(mod.__file__).resolve())
        for mod in list(sys.modules.values()) if getattr(mod,'__file__',None) and Path(mod.__file__).resolve().parent==ROOT/'scripts'})
    identity=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),cases=numbers,inputs=inputs)
    out=ROOT/'build/diagnostics/bank_native_replay_300_v2'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);producer.atomic(out/'manifest.json',dict(identity=identity,qualified_phy=False))
    producer.atomic(out/'state.json',dict(status='running',qualified_phy=False))
    try:
        rows=[]
        for row in selected:
            folder=parent/row['task']['id'];spec=row['task']['spec']
            again=producer.contract(original.measure(folder,i['source_identity'],spec),spec)
            if again!=row['result']:raise ValueError('Full original measurement no longer reproduces')
            proof=independent(folder,i['source_identity'],spec,again)
            rows.append(dict(case=str(folder.relative_to(ROOT)),task=row['task'],all_original_metrics_reproduced=True,**proof))
        if any(producer.sha(ROOT/n)!=h for n,h in inputs.items()):raise ValueError('Replay inputs changed during analysis')
        producer.atomic(out/'summary.json',dict(rows=rows,all_selected_native_metrics_reproduced=True,
            parameters_changed=False,qualified_phy=False,whole_bank_admitted=False,
            scope='Explicit completed cases only; aggregate active numerical parity, overlap, actual loading and full PVT remain required'))
        producer.atomic(out/'state.json',dict(status='complete',cases=len(rows),qualified_phy=False))
    except Exception as exc:
        producer.atomic(out/'state.json',dict(status='failed',error=str(exc),qualified_phy=False));raise
    return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('artifact',type=Path);p.add_argument('cases',nargs='+');a=p.parse_args()
    print(run(a.artifact.resolve(),a.cases),flush=True)
