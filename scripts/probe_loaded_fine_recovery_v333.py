#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Replay the actual selected-node waveform into the retained native fine stage.

Baseline waveform parity gates a P24/N16 recovery experiment. The ideal input
boundary omits mux loading, so neither result qualifies a complete delay bank.
"""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import numpy as np
import probe_two_stage_fine_bank_v322 as source
import probe_discharge_isolated_fine_bank_v220 as drivers
from native_binary_raw_v2 import validate
from regenerated_bank_periodic_measure_v67 import crossings
from spice_dispatch import lease
from spice_engine import engine, provenance

ROOT=source.ROOT
VERSION='actual-selected-waveform-native-fine-recovery-p20-p24-v333.1'
CONTEXT='loaded_fine_recovery_v333'
TOP='openlvds_replayed_loaded_fine_v333'
MODELS={'baseline':drivers.DRIVERS['p20n16'],'p24':drivers.DRIVERS['p24n16']}
sha=source.sha
atomic=source.atomic
TIME_TOLERANCE_PS=.25
VOLTAGE_TOLERANCE_V=.002
SCOPE=('Recorded actual v322 selected waveform drives retained native fine control/31-cell/'
       'loaded-inverter/final-inverter subcircuit through an explicit 1mOhm diagnostic '
       'boundary; baseline parity gates P24 recovery experiment; no upstream loading, '
       'zero-code/coarse overlap/shared-wire/PVT/DLL/PHY admission')


def waveform(times,values):
    if (len(times)!=len(values) or len(times)<2 or not np.isfinite(times).all()
            or not np.isfinite(values).all() or times[0]!=0
            or np.any(np.diff(times)<=0) or abs(times[-1]-25e-9)>1e-15):
        raise ValueError('Require every finite, ordered native point from zero through 25ns')
    return 'VREPLAY REPLAY 0 PWL(\n'+''.join(f'+ {t:.17g} {v:.17g}\n' for t,v in zip(times,values))+'+ )\n'


def transform(bank,previous,p24,variant):
    if variant not in MODELS:raise ValueError('Unknown retained driver hypothesis')
    defs=source.source.native.definitions(bank)
    ports,body=defs[source.TOP]
    if any(w[0][0].upper()!='X' for w in body):
        raise ValueError('Shared top-level passives require an explicit boundary analysis')
    keep=[w for w in body if w[0].startswith(('Xfine_buffer','Xfine_inverse','Xfine_unit'))
          or w[0] in ('Xfine_isolate','Xfine_regenerate1')]
    expected={f'Xfine_{kind}{k}' for k in range(31) for kind in ('buffer','inverse','unit')}
    expected.update(('Xfine_isolate','Xfine_regenerate1'))
    if len(keep)!=95 or {w[0] for w in keep}!=expected:
        raise ValueError('Require all 31 native fine cells/controls and both original inverters')
    isolate=['Xfine_isolate','selected','fine_node','VGND','VPWR',MODELS['baseline']]
    if [w for w in keep if w[0]=='Xfine_isolate']!=[isolate]:
        raise ValueError('Original loaded native inverter changed')
    if variant=='p24':
        extra=source.source.native.definitions(p24)
        if set(extra)!={MODELS['p24']} or extra[MODELS['p24']][0]!=['A','Y','VGND','VPWR']:
            raise ValueError('Require exact qualified P24/N16 driver interface')
        if MODELS['p24'] in defs and source.source.cell_definition(bank,MODELS['p24'])!=p24:
            raise ValueError('Qualified P24 driver conflicts with original library')
        keep=[[*w[:-1],MODELS['p24']] if w[0]=='Xfine_isolate' else w for w in keep]
    top='\n'.join(['.subckt '+TOP+' '+' '.join(ports+['REPLAY']),
        *[' '.join(w) for w in keep],'Rboundary selected REPLAY 1m','.ends '+TOP,''])
    result=bank.replace(source.source.cell_definition(bank,source.TOP),top,1)
    if variant=='p24' and MODELS['p24'] not in defs:result+='\n'+p24
    pins={p:'0' if p=='VGND' else 'VDD' if p=='VPWR' else p for p in ports+['REPLAY']}
    devices=source.source.native.mapped_mos(result,TOP,pins,'XD')
    wanted=tuple('XD:'+w[0]+':' for w in keep)
    old={d['name']:d for d in previous['devices'] if d['name'].startswith(wanted)}
    new={d['name']:d for d in devices}
    unchanged=lambda n:variant=='baseline' or not n.startswith('XD:Xfine_isolate:')
    if (len(old)!=413 or len(new)!=len(devices) or len(devices)!=(413 if variant=='baseline' else 417)
            or any(new.get(n)!=d for n,d in old.items() if unchanged(n))):
        raise ValueError('Retained native terminal map or exact MOS census changed')
    controls=[c for c in previous['controls'] if re.fullmatch(r'XD:fine(?:_b)?\d+',c['node'])]
    gates=[g for g in previous['programming_gates'] if g['device'] in new]
    if len(controls)!=62 or len(gates)!=93:raise ValueError('Incomplete fine controls/programming gates')
    return result,dict(devices=devices,controls=controls,programming_gates=gates)


def fixture(out,identity,variant):
    original=identity['original_fixture'].splitlines()
    rows=['OpenLVDS '+VERSION,
          next(v for v in original if v.startswith('.lib ')),
          f'.include "{out/variant}/bank.spice"',f'.include "{out}/selected.spice"']
    rows += [v for v in original if v.startswith('.options ')]
    rows += [v for v in original if v.startswith(('VDD ','BIN ','VS','VE'))]
    instance=next(v for v in original if v.startswith('XD ')).split()
    if instance[-1]!=source.TOP:raise ValueError('Original fixture instance changed')
    rows.append(' '.join([*instance[:-1],'REPLAY',TOP]))
    rows += [next(v for v in original if v.startswith(prefix)) for prefix in ('CLOAD ','.tran ')]
    o=identity['observations'][variant]
    nodes={'IN','OUT','VDD','REPLAY','XD:selected','XD:fine_node'}
    nodes.update('S'+str(k) for k in range(4));nodes.update('E'+str(k) for k in range(31))
    nodes.update(n for d in o['devices'] for n in d['terminals'] if n!='0')
    nodes.update(c['node'] for c in o['controls']);nodes.update(g['gate_node'] for g in o['programming_gates'])
    return '\n'.join(rows+['.print tran '+' '.join('V('+n+')' for n in sorted(nodes)),'.end',''])


def prepare(parent,materials):
    m=source.bound(parent);i=m['identity'];case=parent/'1'
    row=json.loads((case/'summary.json').read_text())
    if (json.loads((parent/'state.json').read_text())!=dict(status='complete',cases=4,errors=0,qualified_phy=False)
            or row['task']!=m['tasks'][1] or row['error'] is not None
            or row['spec']!=source.specifications()[1]
            or any(sha(case/n)!=h for n,h in row['files'].items())
            or source.measure(case,i,row['spec'])!=row['result']
            or row['result']['period_screen_passed'] is not False):
        raise ValueError('Require naturally complete, reproduced native fine31/60% failure')
    texts,paths,di=drivers.checked_drivers(materials)
    p24=source.source.cell_definition(texts,MODELS['p24'])
    bank=(parent/'bank.spice').read_text()
    variants={v:transform(bank,i['observations'],p24,v) for v in MODELS}
    names,data=validate(case/'bench.raw',{'v(xd.selected)'},25e-9)
    wave=waveform(data[:,names.index('time')],data[:,names.index('v(xd.selected)')])
    paths += [parent/'manifest.json',parent/'bank.spice',parent/'state.json',case/'summary.json',*[case/n for n in row['files']]]
    paths += [ROOT/n for n in i['inputs']]
    paths += sorted({Path(mod.__file__).resolve() for mod in list(sys.modules.values())
        if getattr(mod,'__file__',None) and Path(mod.__file__).resolve().parent==ROOT/'scripts'})
    inputs={str(p.relative_to(ROOT)):sha(p) for p in sorted(set(paths))}
    identity=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),materials=str(materials.relative_to(ROOT)),
        spec=row['spec'],original_fixture=(case/'bench.cir').read_text(),
        observations={v:variants[v][1] for v in MODELS},inputs=inputs,guards=source.guard_inputs(inputs),
        simulator=i['simulator'],pdk_files=i['pdk_files'],external_files={**i['external_files'],**di['external_files']},
        wave_sha256=hashlib.sha256(wave.encode()).hexdigest(),native_source_points=len(data),
        parity_limits=dict(maximum_crossing_error_ps=TIME_TOLERANCE_PS,maximum_terminal_voltage_error_v=VOLTAGE_TOLERANCE_V),
        max_workers=1,priority=1,scope=SCOPE)
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);(out/'selected.spice').write_text(wave)
    tasks=[];libraries={}
    for k,v in enumerate(MODELS):
        library=out/v;library.mkdir();(library/'bank.spice').write_text(variants[v][0])
        libraries[v+'/bank.spice']=sha(library/'bank.spice')
        folder=out/str(k);folder.mkdir();(folder/'bench.cir').write_text(fixture(out,identity,v))
        tasks.append(dict(id=str(k),variant=v,deck_sha256=sha(folder/'bench.cir')))
    atomic(out/'manifest.json',dict(identity=identity,libraries=libraries,tasks=tasks,qualified_phy=False))
    return out


def bound(out,full=True):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION
            or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
            or i['spec']!=source.specifications()[1] or i['scope']!=SCOPE
            or (i['max_workers'],i['priority'])!=(1,1) or i['guards']!=source.guard_inputs(i['inputs'])
            or i['parity_limits']!=dict(maximum_crossing_error_ps=TIME_TOLERANCE_PS,maximum_terminal_voltage_error_v=VOLTAGE_TOLERANCE_V)
            or any(sha(ROOT/n)!=h for n,h in (i['inputs'] if full else i['guards']).items())
            or any(sha(Path(n))!=h for n,h in {**i['pdk_files'],**i['external_files']}.items())
            or any(sha(out/n)!=h for n,h in m['libraries'].items())
            or sha(out/'selected.spice')!=i['wave_sha256'] or engine()!='ngspice' or provenance()!=i['simulator']):
        raise ValueError('Recorded-waveform fine-recovery experiment changed')
    expected=[]
    for k,v in enumerate(MODELS):
        folder=out/str(k)
        if (folder/'bench.cir').read_text()!=fixture(out,i,v):raise ValueError('Full native diagnostic fixture changed')
        expected.append(dict(id=str(k),variant=v,deck_sha256=sha(folder/'bench.cir')))
        pins={p:'0' if p=='VGND' else 'VDD' if p=='VPWR' else p
              for p in source.source.native.definitions((out/v/'bank.spice').read_text())[TOP][0]}
        if source.source.native.mapped_mos((out/v/'bank.spice').read_text(),TOP,pins,'XD')!=i['observations'][v]['devices']:
            raise ValueError('Native retained diagnostic terminal map changed')
    if m['tasks']!=expected:raise ValueError('Require original baseline and one P24 hypothesis')
    return m


def parity(folder,identity):
    original=ROOT/identity['parent']/'1'
    columns={'v(in)','v(out)','v(xd.selected)','v(xd.fine_node)'}
    columns.update('v('+n.replace(':','.').lower()+')' for d in identity['observations']['baseline']['devices']
                   for n in d['terminals'] if n!='0')
    old_names,old=validate(original/'bench.raw',columns,25e-9)
    names,data=validate(folder/'bench.raw',columns,25e-9)
    ot=old[:,old_names.index('time')]*1e12;t=data[:,names.index('time')]*1e12
    voltage=max(float(np.max(np.abs(np.interp(ot,t,data[:,names.index(n)])-old[:,old_names.index(n)]))) for n in columns)
    errors=[]
    for n in ('v(in)','v(out)','v(xd.selected)','v(xd.fine_node)'):
        for up in (True,False):
            a=crossings(ot,old[:,old_names.index(n)],.9,up);b=crossings(t,data[:,names.index(n)],.9,up)
            if len(a)!=8 or len(b)!=8:raise ValueError('Baseline parity requires all eight native events')
            errors.extend(abs(x-y) for x,y in zip(a,b))
    return dict(maximum_crossing_error_ps=max(errors),maximum_terminal_voltage_error_v=voltage,
        all_eight_startup_events_compared=True,all_413_native_mos_terminals_compared=True,
        parity_passed=bool(max(errors)<=TIME_TOLERANCE_PS and voltage<=VOLTAGE_TOLERANCE_V))


def baseline_usable(result):
    return bool(result and result.get('baseline_parity',{}).get('parity_passed') is True
        and all(result.get(k) is True for k in ('all_input_output_pulses_present','input_timing_stimulus_passed',
            'full_swing_pulses_passed','unwrapped_native_epoch_passed','pulse_order_and_widths_passed',
            'terminal_screen_passed','control_settling_passed')))


def measure(folder,identity,variant):
    result=source.source.source.periodic.measure(folder,dict(identity,spec=identity['spec'],observations=identity['observations'][variant]))
    public=('v(in)','v(out)','v(xd.selected)','v(xd.fine_node)')
    names,data=validate(folder/'bench.raw',set(public),25e-9)
    t=data[:,names.index('time')]*1e12
    values={n:data[:,names.index(n)] for n in public}
    stages={};snapshots={}
    for up,edge,threshold in ((True,'rise',.18),(False,'fall',1.62)):
        selected=crossings(t,values['v(xd.selected)'],.9,up)
        fine=crossings(t,values['v(xd.fine_node)'],.9,not up)
        output=crossings(t,values['v(out)'],.9,up)
        samples=crossings(t,values['v(in)'],threshold,up)
        if any(len(v)!=8 for v in (selected,fine,output,samples)):
            raise ValueError('Require all eight native events in the retained fine stage')
        loaded=[b-a for a,b in zip(selected,fine)]
        final=[b-a for a,b in zip(fine,output)]
        stages[edge]=dict(loaded_delays_ps=loaded,final_delays_ps=final,
            loaded_first_minus_last_ps=loaded[0]-loaded[-1],
            maximum_sum_residual_ps=max(abs(a+b-(out-start)) for a,b,out,start in zip(loaded,final,output,selected)))
        snapshots[edge]=dict(source_times_ps=samples,
            fine_node_v=np.interp(samples,t,values['v(xd.fine_node)']).tolist())
    result.update(whole_bank_rc_retained=False,qualified_phy=False,scope=SCOPE,
                  stage_history=stages,source_edge_state=snapshots)
    return result


def run(out):
    m=bound(out);i=m['identity'];rows=[]
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain previous or partial recovery experiment')
        atomic(out/'state.json',dict(status='running',qualified_phy=False))
        for task in m['tasks']:
            folder=out/task['id'];result=error=None
            guarded=task['variant']!='baseline' and not baseline_usable(rows[0]['result'])
            if not guarded:
                try:
                    with lease(ROOT,priority=1,label=CONTEXT+'_'+task['id']):
                        bound(out,full=False)
                        p=subprocess.run([sys.executable,str(ROOT/'scripts/run_native_binary_v2.py'),'-l',str(folder/'ngspice.log'),str(folder/'bench.cir')],capture_output=True,text=True)
                    (folder/'console.log').write_text(p.stdout+p.stderr);p.check_returncode()
                    result=measure(folder,i,task['variant'])
                    if task['variant']=='baseline':result['baseline_parity']=parity(folder,i)
                except Exception as exc:error=str(exc)
            row=dict(task=task,result=result,error=error,guarded=guarded,
                files={p.name:sha(p) for p in folder.iterdir() if p.is_file()})
            atomic(folder/'summary.json',row);rows.append(row)
        bound(out)
        atomic(out/'summary.json',dict(rows=rows,baseline_usable=baseline_usable(rows[0]['result']),
            full_bank_qualified=False,qualified_phy=False,scope=SCOPE))
        atomic(out/'state.json',dict(status='complete',cases=2,errors=sum(r['error'] is not None for r in rows),
            guarded=sum(r['guarded'] for r in rows),qualified_phy=False))
    return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='action',required=True)
    q=sub.add_parser('prepare');q.add_argument('parent',type=Path);q.add_argument('materials',type=Path)
    q=sub.add_parser('run');q.add_argument('artifact',type=Path);a=p.parse_args()
    print(prepare(a.parent.resolve(),a.materials.resolve()) if a.action=='prepare' else run(a.artifact.resolve()),flush=True)
