#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Test pull-up recovery behind the completed v352 selected-node waveform.

Baseline parity must pass before two qualified P40/N16 inverters replace
the two P20/N16 fine drivers. Native pre/final stages and both fine banks stay.
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
import probe_restored_balanced_bank_v352 as source
import probe_loaded_fine_recovery_v333 as recorded
import regenerated_bank_periodic_measure_v67 as periodic
from native_binary_raw_v2 import validate
from spice_dispatch import lease
from spice_engine import engine,provenance

ROOT=source.ROOT
VERSION='recorded-restored-fine-pullup-p40n32-to-p80n32-v355.1'
CONTEXT='restored_fine_recovery_v355'
TOP='openlvds_recorded_restored_fine_v355'
STRONG='openlvds_parallel_pullup_fine_v355'
PULLUP=source.baseline.MODEL
VARIANTS=('baseline','pullup')
COUNTS={'baseline':622,'pullup':662}
sha=source.sha
atomic=source.atomic
SCOPE=('All-sample actual v352 selected-node PWL drives retained native P10/N8 '
       'pre-stage, doubled fine units/controls and final P20/N16. Baseline native '
       'parity gates replacing only two loaded P20/N16 with two qualified '
       'P40/N16 cells. No upstream loading, zero-code quarter, coarse overlap, '
       'new shared RC, PVT, DLL or PHY admission')


def transform(text,previous,variant):
    if variant not in VARIANTS:raise ValueError('Unknown recovery variant')
    defs=source.native.definitions(text);ports,body=defs[source.TOP]
    if any(w[0][0].upper()!='X' for w in body):raise ValueError('Require explicit analysis of shared passives')
    wanted={f'Xfine_{kind}{k}' for k in range(31) for kind in ('buffer','inverse','unit','copy')}
    wanted.update(('Xfine_pre','Xfine_isolate','Xfine_regenerate1'))
    keep=[w for w in body if w[0] in wanted]
    if len(keep)!=127 or {w[0] for w in keep}!=wanted:raise ValueError('Incomplete original fine controls/copies/stages')
    expected=[['Xfine_pre','selected','pre_out','VGND','VPWR',source.SMALL],
              ['Xfine_isolate','pre_out','fine_node','VGND','VPWR',source.FINE],
              ['Xfine_regenerate1','fine_node','OUT','VGND','VPWR',source.REGULAR]]
    if any(w not in keep for w in expected):raise ValueError('Original three-inverter fine path changed')
    if (defs[source.FINE][1]!=[['Xa','A','Y','VGND','VPWR',source.REGULAR],
                                ['Xb','A','Y','VGND','VPWR',source.REGULAR]]
            or defs[PULLUP][0]!=['A','Y','VGND','VPWR'] or STRONG in defs):
        raise ValueError('Require unchanged two-P20 driver and included qualified P40 model')
    if variant=='pullup':keep=[w[:-1]+[STRONG] if w==expected[1] else w for w in keep]
    top='\n'.join(['.subckt '+TOP+' '+' '.join(ports+['REPLAY']),
        *[' '.join(w) for w in keep],'Rboundary selected REPLAY 1m','.ends '+TOP,''])
    result=text.replace(source.definition(text,source.TOP),top,1)
    if variant=='pullup':
        result+='\n'.join(['','.subckt '+STRONG+' A Y VGND VPWR',
            'Xa A Y VGND VPWR '+PULLUP,'Xb A Y VGND VPWR '+PULLUP,'.ends '+STRONG,''])
    if any(source.definition(result,n)!=source.definition(text,n) for n in defs if n!=source.TOP):
        raise ValueError('Existing native component definition changed')
    pins={p:'0' if p=='VGND' else 'VDD' if p=='VPWR' else p for p in ports+['REPLAY']}
    devices=source.native.mapped_mos(result,TOP,pins,'XD')
    prefixes=tuple('XD:'+w[0]+':' for w in keep)
    old={d['name']:d for d in previous['devices'] if d['name'].startswith(prefixes)}
    new={d['name']:d for d in devices}
    if (len(old)!=622 or len(new)!=COUNTS[variant]
            or any(new.get(n)!=d for n,d in old.items()
                   if variant=='baseline' or not n.startswith('XD:Xfine_isolate:'))):
        raise ValueError('Native retained maps or census changed')
    controls=[c for c in previous['controls'] if re.fullmatch(r'XD:fine(?:_b)?\d+',c['node'])]
    gates=[g for g in previous['programming_gates'] if g['device'] in new]
    if len(controls)!=62 or len(gates)!=186:raise ValueError('Incomplete doubled fine programming observations')
    return result,dict(devices=devices,controls=controls,programming_gates=gates)


def fixture(out,identity,variant):
    original=identity['original_fixture'].splitlines()
    lines=['OpenLVDS '+VERSION,next(v for v in original if v.startswith('.lib ')),
        '.include "'+str(out/variant/'bank.spice')+'"',
        '.include "'+str(out/'selected.spice')+'"']
    lines += [v for v in original if v.startswith('.options ')]
    lines += [v for v in original if v.startswith(('VDD ','BIN ','VS','VE'))]
    call=next(v for v in original if v.startswith('XD ')).split()
    if call[-1]!=source.TOP:raise ValueError('Original full native fixture changed')
    lines += [' '.join([*call[:-1],'REPLAY',TOP])]
    lines += [next(v for v in original if v.startswith(prefix)) for prefix in ('CLOAD ','.tran ')]
    o=identity['observations'][variant]
    nodes={'IN','OUT','VDD','REPLAY','XD:selected','XD:pre_out','XD:fine_node',
           *('S'+str(k) for k in range(4)),*('E'+str(k) for k in range(31))}
    nodes.update(n for d in o['devices'] for n in d['terminals'] if n!='0')
    nodes.update(c['node'] for c in o['controls']);nodes.update(g['gate_node'] for g in o['programming_gates'])
    return '\n'.join([*lines,'.print tran '+' '.join('V('+n+')' for n in sorted(nodes)),'.end',''])


def prepare(parent,evidence):
    m=source.bound(parent,full=False);i=m['identity'];case=parent/'1'
    row=json.loads((case/'summary.json').read_text());proof=json.loads(evidence.read_text())
    if (row['task']!=m['tasks'][1] or row['spec']!=source.specifications()[1] or row['error'] is not None
            or row['result']['period_screen_passed'] is not False
            or row['result']['repeated_delay_screen_passed'] is not False
            or proof['case']!=str(case.relative_to(ROOT)) or proof['spec']!=row['spec']
            or proof['all_original_native_metrics_reproduced'] is not True
            or proof.get('prepared_architecture_regenerated') is not True
            or proof['native_mos']!=2086 or proof['programming_gates']!=266
            or any(sha(ROOT/n)!=h for n,h in proof['inputs'].items())
            or any(sha(case/n)!=h for n,h in row['files'].items())):
        raise ValueError('Require naturally complete, independently replayed v352 fine60 failure')
    text=(parent/'bank.spice').read_text()
    variants={v:transform(text,i['observations'],v) for v in VARIANTS}
    names,data=validate(case/'bench.raw',{'v(xd.selected)'},25e-9)
    wave=recorded.waveform(data[:,names.index('time')],data[:,names.index('v(xd.selected)')])
    paths=[parent/'manifest.json',parent/'bank.spice',case/'summary.json',evidence,
           *[case/n for n in row['files']],*[ROOT/n for n in i['guards']],
           *[ROOT/n for n in proof['inputs']]]
    paths += sorted({Path(module.__file__).resolve() for module in list(sys.modules.values())
        if getattr(module,'__file__',None) and Path(module.__file__).resolve().parent==ROOT/'scripts'})
    inputs={str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p):sha(p) for p in sorted(set(paths))}
    identity=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),evidence=str(evidence.relative_to(ROOT)),
        spec=row['spec'],original_fixture=(case/'bench.cir').read_text(),inputs=inputs,
        guards={n:h for n,h in inputs.items() if not n.endswith('.raw')},
        observations={v:variants[v][1] for v in VARIANTS},pdk_files=i['pdk_files'],external_files=i['external_files'],
        simulator=i['simulator'],wave_sha256=hashlib.sha256(wave.encode()).hexdigest(),
        native_source_points=len(data),parity_limits=dict(crossing_ps=.25,voltage_v=.002),
        max_workers=1,priority=2,scope=SCOPE)
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);(out/'selected.spice').write_text(wave)
    tasks=[];libraries={}
    for k,v in enumerate(VARIANTS):
        (out/v).mkdir();(out/v/'bank.spice').write_text(variants[v][0]);libraries[v+'/bank.spice']=sha(out/v/'bank.spice')
        (out/str(k)).mkdir();(out/str(k)/'bench.cir').write_text(fixture(out,identity,v))
        tasks.append(dict(id=str(k),variant=v,deck_sha256=sha(out/str(k)/'bench.cir')))
    atomic(out/'manifest.json',dict(identity=identity,tasks=tasks,libraries=libraries,qualified_phy=False))
    return out


def bound(out,full=True):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION or i['scope']!=SCOPE
            or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
            or i['spec']!=source.specifications()[1] or i['parity_limits']!=dict(crossing_ps=.25,voltage_v=.002)
            or (i['max_workers'],i['priority'])!=(1,2)
            or i['guards']!={n:h for n,h in i['inputs'].items() if not n.endswith('.raw')}
            or engine()!='ngspice' or provenance()!=i['simulator']
            or any(sha(ROOT/n)!=h for n,h in (i['inputs'] if full else i['guards']).items())
            or any(sha(ROOT/n)!=h for n,h in {**i['pdk_files'],**i['external_files']}.items())
            or sha(out/'selected.spice')!=i['wave_sha256']
            or any(sha(out/n)!=h for n,h in m['libraries'].items())):
        raise ValueError('Unchanged native recovery diagnostic context changed')
    parent=ROOT/i['parent'];old=json.loads((parent/'manifest.json').read_text())['identity'];tasks=[]
    for k,v in enumerate(VARIANTS):
        text,observations=transform((parent/'bank.spice').read_text(),old['observations'],v)
        if ((out/v/'bank.spice').read_text()!=text or observations!=i['observations'][v]
                or (out/str(k)/'bench.cir').read_text()!=fixture(out,i,v)):
            raise ValueError('Native recovery circuit or full fixture cannot regenerate')
        tasks.append(dict(id=str(k),variant=v,deck_sha256=sha(out/str(k)/'bench.cir')))
    if tasks!=m['tasks']:raise ValueError('Require parity baseline then pull-up intervention')
    return m


def parity(folder,i):
    nodes={'v(in)','v(out)','v(xd.selected)','v(xd.pre_out)','v(xd.fine_node)'}
    nodes.update('v('+n.replace(':','.').lower()+')' for d in i['observations']['baseline']['devices'] for n in d['terminals'] if n!='0')
    names,old=validate(ROOT/i['parent']/'1/bench.raw',nodes,25e-9)
    cols,new=validate(folder/'bench.raw',nodes,25e-9)
    ot=old[:,names.index('time')]*1e12;t=new[:,cols.index('time')]*1e12
    voltage=max(float(np.max(np.abs(np.interp(ot,t,new[:,cols.index(n)])-old[:,names.index(n)]))) for n in nodes)
    errors=[]
    for n in ('v(in)','v(out)','v(xd.selected)','v(xd.pre_out)','v(xd.fine_node)'):
        for up in (True,False):
            a=periodic.crossings(ot,old[:,names.index(n)],.9,up);b=periodic.crossings(t,new[:,cols.index(n)],.9,up)
            if len(a)!=8 or len(b)!=8:raise ValueError('Require all eight native stage events in baseline parity')
            errors.extend(abs(x-y) for x,y in zip(a,b))
    return dict(maximum_crossing_error_ps=max(errors),maximum_terminal_voltage_error_v=voltage,
        all_622_native_mos_terminals_compared=True,all_eight_startup_events_compared=True,
        parity_passed=bool(max(errors)<=.25 and voltage<=.002))


def measure(folder,i,variant):
    result=periodic.measure(folder,dict(i,observations=i['observations'][variant]))
    public=('v(in)','v(xd.selected)','v(xd.pre_out)','v(xd.fine_node)','v(out)')
    names,data=validate(folder/'bench.raw',set(public),25e-9);t=data[:,names.index('time')]*1e12
    signals={n:data[:,names.index(n)] for n in public};stages={};snapshots={}
    for up,edge in ((True,'rise'),(False,'fall')):
        events={n:periodic.crossings(t,v,.9,not up if n in ('v(xd.selected)','v(xd.fine_node)') else up) for n,v in signals.items()}
        if any(len(v)!=8 for v in events.values()):raise ValueError('Require all eight correctly polarized native events')
        stages[edge]={a+'_to_'+b:[y-x for x,y in zip(events[a],events[b])] for a,b in zip(public,public[1:])}
        input_times=periodic.crossings(t,signals['v(in)'],.18 if up else 1.62,up)
        snapshots[edge]=dict(input_threshold_times_ps=input_times,fine_node_v=np.interp(input_times,t,signals['v(xd.fine_node)']).tolist())
    result.update(stage_delays_ps=stages,source_edge_state=snapshots,whole_bank_rc_retained=False,qualified_phy=False,scope=SCOPE)
    return result


def run(out):
    m=bound(out);i=m['identity'];rows=[]
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain prior or partial recovery diagnostic')
        atomic(out/'state.json',dict(status='running',qualified_phy=False))
        for task in m['tasks']:
            folder=out/task['id'];variant=task['variant'];result=error=None
            guarded=variant!='baseline' and not recorded.baseline_usable(rows[0]['result'])
            if not guarded:
                try:
                    with lease(ROOT,priority=2,label=CONTEXT+'_'+task['id']):
                        bound(out,full=False)
                        p=subprocess.run([sys.executable,str(ROOT/'scripts/run_native_binary_v2.py'),'-l',str(folder/'ngspice.log'),str(folder/'bench.cir')],capture_output=True,text=True)
                    (folder/'console.log').write_text(p.stdout+p.stderr);p.check_returncode()
                    result=measure(folder,i,variant)
                    if variant=='baseline':result['baseline_parity']=parity(folder,i)
                except Exception as exc:error=str(exc)
            row=dict(task=task,result=result,error=error,guarded=guarded,files={p.name:sha(p) for p in folder.iterdir() if p.is_file()})
            atomic(folder/'summary.json',row);rows.append(row)
        bound(out)
        atomic(out/'summary.json',dict(rows=rows,baseline_usable=recorded.baseline_usable(rows[0]['result']),qualified_phy=False,scope=SCOPE))
        atomic(out/'state.json',dict(status='complete',cases=2,errors=sum(r['error'] is not None for r in rows),guarded=sum(r['guarded'] for r in rows),qualified_phy=False))
    return out


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('prepare','run','campaign'));parser.add_argument('artifact',type=Path)
    parser.add_argument('--evidence',type=Path);args=parser.parse_args()
    out=prepare(args.artifact.resolve(),args.evidence.resolve()) if args.action in ('prepare','campaign') else args.artifact.resolve()
    print(out,flush=True)
    if args.action in ('run','campaign'):print(run(out),flush=True)
