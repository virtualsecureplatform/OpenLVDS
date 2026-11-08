#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Complete native stage-delay diagnostics, preserving original failed gates."""
import argparse,hashlib,json,sys
from pathlib import Path
import numpy as np
import native_bank_300_v1 as baseline
import native_bank_300_v2 as single
import native_bank_mim4_300_v1 as mim
from native_binary_raw_v2 import validate
from regenerated_bank_periodic_measure_v67 import crossings
ROOT=baseline.ROOT
VERSION='complete-restored-bank-stage-history-300-v2'
NODES=('IN','XD:selected','XD:pre_out','XD:fine_node','OUT')


def stages(t,signals,spec,recorded):
    if (set(signals)!=set(NODES) or spec['cycles']!=8 or t[0]>1e-6 or t[-1]<39999
            or not np.isfinite(t).all() or np.any(np.diff(t)<=0)
            or any(len(v)!=len(t) or not np.isfinite(v).all() for v in signals.values())):
        raise ValueError('Require complete finite 40 ns stage history, including startup')
    result={}
    for edge,up in (('rise',True),('fall',False)):
        events={n:np.asarray(crossings(t,signals[n],.9,not up if n in ('XD:selected','XD:fine_node') else up)) for n in NODES}
        if any(len(v)!=8 for v in events.values()):raise ValueError('Missing or extra native stage event; never reassign epochs')
        delays={a+' -> '+b:events[b]-events[a] for a,b in zip(NODES,NODES[1:])}
        if any(np.any(v<=0) for v in delays.values()):raise ValueError('Noncausal stage correspondence')
        total=events['OUT']-events['IN']
        if not np.allclose(total,recorded['edge_delays_ps'][edge],rtol=0,atol=1e-6):
            raise ValueError('Recorded native unwrapped outer delays do not reproduce')
        expected=2100+(np.arange(8)+(0 if up else spec['duty']))*1e6/spec['frequency_mhz']
        if np.max(abs(events['IN']-expected))>1:raise ValueError('Wrong captured input epochs')
        result[edge]=dict(crossing_times_ps={n:v.tolist() for n,v in events.items()},
            stages={n:dict(delays_ps=v.tolist(),span_ps=float(np.ptp(v)),
                           first_to_last_change_ps=float(v[-1]-v[0])) for n,v in delays.items()},
            total_delays_ps=total.tolist(),total_span_ps=float(np.ptp(total)),
            maximum_stage_sum_residual_ps=float(np.max(abs(sum(delays.values())-total))))
    return result



def cap_side_nodes(observations):
    devices={d['name']:d for d in observations['devices']};nodes={}
    for unit,copy in ((0,0),(15,0),(30,3)):
        prefix=f'XD:Xfine_mim{unit}_c{copy}'
        for leaf,index,label in (('X0',2,'pfet_cap_side'),('X3',0,'nfet_cap_side')):
            name=prefix+':'+leaf
            if name not in devices:raise ValueError('Missing actual native MIM switch observation')
            d=devices[name];node=d['terminals'][index]
            if '__CAP.t' not in node:raise ValueError('Expected extracted switch-side capacitor net')
            nodes[node]=dict(device=name,terminal=('D','G','S','B')[index],role=label,fine_enable_index=unit)
    return nodes


def recovery_samples(t,pre_out,signals):
    # Observe before the input transition begins to drive the fine inverter.
    high=np.asarray(crossings(t,pre_out,.18,True))-20
    low=np.asarray(crossings(t,pre_out,1.62,False))-20
    if len(high)!=8 or len(low)!=8 or min(high.min(),low.min())<t[0]:
        raise ValueError('Require all eight pre-transition recovery observations')
    rows={}
    for name,values in signals.items():
        if len(values)!=len(t) or not np.isfinite(values).all():raise ValueError('Invalid native recovery signal')
        a=np.interp(high,t,values);b=np.interp(low,t,values)
        rows[name]=dict(before_pre_out_rise_voltage_v=a.tolist(),before_pre_out_fall_voltage_v=b.tolist(),
            high_first_to_last_change_v=float(a[-1]-a[0]),low_first_to_last_change_v=float(b[-1]-b[0]))
    return dict(sample_before_rising_10_percent_ps=high.tolist(),sample_before_falling_90_percent_ps=low.tolist(),
        nodes=rows,capacitor_charge_not_measured=True,
        scope='Observed fine-node and actual MOS switch-side voltage samples; MIM plate charge is not inferred from unobserved nets')

def run(cases):
    if not cases or len(set(cases))!=len(cases):raise ValueError('Require unique complete native cases')
    inputs={};selected=[];cache={}
    for folder in cases:
        parent=folder.parent
        if parent not in cache:
            raw=json.loads((parent/'manifest.json').read_text());version=raw['identity']['version']
            producer={baseline.VERSION:baseline,single.VERSION:single,mim.VERSION:mim}.get(version)
            if producer is None:raise ValueError('Require original fresh 300 MHz restored-bank contexts')
            m=producer.bound(parent);i=m['identity']
            if i['kind']!='restored':raise ValueError('Stage polarity requires complete restored topology')
            if producer is baseline:
                original,source=producer.PARENTS['restored']
                if i['source_identity']!=original.bound(source,full=False)['identity']:raise ValueError('Original source identity changed')
            inputs.update({**i['inputs'],**i['source_identity']['pdk_files'],**i['source_identity']['external_files']})
            for path in (parent/'manifest.json',parent/'bank.spice'):inputs[str(path.relative_to(ROOT))]=producer.sha(path)
            cache[parent]=(producer,m)
        producer,m=cache[parent];row=json.loads((folder/'summary.json').read_text())
        if row['error'] is not None or row['task'] not in m['tasks'] or row['task']['id']!=folder.name:
            raise ValueError('Require exact completed native case')
        for name,digest in row['files'].items():
            if producer.sha(folder/name)!=digest:raise ValueError('Original completed native case changed')
            inputs[str((folder/name).relative_to(ROOT))]=digest
        inputs[str((folder/'summary.json').relative_to(ROOT))]=producer.sha(folder/'summary.json');selected.append((folder,row))
    inputs.update({str(Path(m.__file__).resolve().relative_to(ROOT)):baseline.sha(Path(m.__file__).resolve())
        for m in list(sys.modules.values()) if getattr(m,'__file__',None) and Path(m.__file__).resolve().parent==ROOT/'scripts'})
    identity=dict(version=VERSION,cases=[str(p.relative_to(ROOT)) for p in cases],inputs=inputs)
    out=ROOT/'build/diagnostics/bank_stage_history_300_v2'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);baseline.atomic(out/'manifest.json',dict(identity=identity,qualified_phy=False))
    baseline.atomic(out/'state.json',dict(status='running',qualified_phy=False))
    try:
        rows=[];column=lambda n:'v('+n.replace(':','.').lower()+')'
        for folder,row in selected:
            producer,manifest=cache[folder.parent]
            extra=cap_side_nodes(manifest['identity']['source_identity']['observations']) if producer is mim else {}
            names,w=validate(folder/'bench.raw',{column(n) for n in (*NODES,*extra)},40e-9)
            t=w[:,names.index('time')]*1e12
            signals={n:w[:,names.index(column(n))] for n in (*NODES,*extra)}
            proof=stages(t,{n:signals[n] for n in NODES},row['task']['spec'],row['result'])
            record=dict(case=str(folder.relative_to(ROOT)),task=row['task'],history=proof,
                original_recorded_gates={k:v for k,v in row['result'].items() if k.endswith('_passed')})
            if extra:
                record['native_switch_side_observations']=extra
                record['recovery']=recovery_samples(t,signals['XD:pre_out'],
                    {n:signals[n] for n in ('XD:fine_node',*extra)})
            rows.append(record)
        if any(baseline.sha(ROOT/n)!=h for n,h in inputs.items()):raise ValueError('Captured stage history changed during analysis')
        baseline.atomic(out/'summary.json',dict(rows=rows,original_outer_delays_reproduced=True,
            original_results_preserved=True,qualified_phy=False,
            scope='Complete fixed-epoch stage diagnostics only; no replacement for native stress/control, numerical parity, load or PVT qualification'))
        baseline.atomic(out/'state.json',dict(status='complete',cases=len(rows),qualified_phy=False))
    except Exception as exc:
        baseline.atomic(out/'state.json',dict(status='failed',error=str(exc),qualified_phy=False));raise
    return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('cases',type=Path,nargs='+');a=p.parse_args()
    print(run([f.resolve() for f in a.cases]),flush=True)
