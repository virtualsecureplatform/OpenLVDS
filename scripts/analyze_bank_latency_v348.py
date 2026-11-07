#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Measure internal slew and recovery state in six fully replayed bank cases."""
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
from native_binary_raw_v2 import validate
from regenerated_bank_periodic_measure_v67 import crossings
from probe_digital_dcc_v2 import atomic
from audit_rc_comments_v2 import collapse
from native_bank_inventory_v51 import native_leaves

ROOT=Path(__file__).resolve().parents[1]
VERSION='full-native-bank-stage-slew-and-zero-latency-analysis-v348.1'
CONTEXT='bank_latency_analysis_v348'
SOURCES=(('p20_zero','two_stage_bank_native_replay/20261107T030617Z',1365),
         ('p40_zero','pullup_bank_native_replay/20261107T095305Z',1385),
         ('p20_fine60','two_stage_bank_native_replay/20261107T035323Z',1365),
         ('p40_fine60','pullup_bank_native_replay/20261107T090609Z',1385),
         ('p20_fine40','two_stage_bank_native_replay/20261107T045805Z',1365),
         ('p40_fine40','pullup_bank_native_replay/20261107T093733Z',1385))
NODES=dict(input='v(in)',selected='v(xd.selected)',fine_node='v(xd.fine_node)',output='v(out)')
SCOPE=('Read-only internal slew/recovery analysis of exact six completed full native '
       'bank traces bound to independently reproduced original metric receipts; '
       'no parameter/circuit/solver change, new simulation, alternate-load timing, '
       'range, PVT, routed-bank, DLL or PHY admission')


def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        while block:=stream.read(1024*1024):h.update(block)
    return h.hexdigest()


def edge_slews(t,v,up):
    """Never borrow a missing threshold crossing from an adjacent pulse."""
    half=np.asarray(crossings(t,v,.9,up))
    opposite=np.asarray(crossings(t,v,.9,not up))
    early=np.asarray(crossings(t,v,.18 if up else 1.62,up))
    late=np.asarray(crossings(t,v,1.62 if up else .18,up))
    rows=[]
    for mid in half:
        before=opposite[opposite<mid];after=opposite[opposite>mid]
        lo=float(before[-1]) if len(before) else float(t[0])
        hi=float(after[0]) if len(after) else float(t[-1])
        a=early[(early>=lo)&(early<=mid)];b=late[(late>=mid)&(late<=hi)]
        start=float(a[-1]) if len(a) else None
        end=float(b[0]) if len(b) else None
        rows.append(dict(half_crossing_ps=float(mid),interval_ps=[lo,hi],
            early_crossing_ps=start,late_crossing_ps=end,
            slew_ps=end-start if start is not None and end is not None else None,
            full_10_90_swing=start is not None and end is not None))
    return rows


def native_inventory(bank,model,input_pin):
    ports,devices=native_leaves(collapse(bank),model)
    if input_pin not in ports:raise ValueError('Native component input port changed')
    groups={}
    for d in devices:
        if 'fet_' not in d['model']:continue
        group='input_gate' if d['nodes'][1]==input_pin else 'other_gate'
        key=group+'/'+d['model'];entry=groups.setdefault(key,dict(mos=0,total_width_um=0.))
        entry['mos']+=1;entry['total_width_um']+=float(d['params']['w'])
    return dict(model=model,ports=ports,primitive_count=len(devices),gate_groups=groups)


def observe(case):
    names,data=validate(case/'bench.raw',set(NODES.values()),25e-9)
    t=data[:,names.index('time')]*1e12
    wave={n:data[:,names.index(column)] for n,column in NODES.items()}
    stages={n:{edge:edge_slews(t,v,up) for edge,up in (('rise',True),('fall',False))}
            for n,v in wave.items()}
    if any(len(rows)!=8 for stage in stages.values() for rows in stage.values()):
        raise ValueError('Require all eight half-supply events of each polarity at every stage')
    launch=crossings(t,wave['input'],.18,True)
    if len(launch)!=8:raise ValueError('Require all eight original source launch events')
    return dict(stages=stages,summary={n:{edge:dict(
        full_swing_edges=sum(e['full_10_90_swing'] for e in rows),
        maximum_slew_ps=max((e['slew_ps'] for e in rows if e['slew_ps'] is not None),default=None))
        for edge,rows in stage.items()} for n,stage in stages.items()},
        fine_node_before_source_rise_v=[float(np.interp(event,t,wave['fine_node'])) for event in launch])


def run():
    expected={};records=[];paths=[Path(__file__)]
    for label,relative,count in SOURCES:
        file=ROOT/'build/reports'/relative/'summary.json';proof=json.loads(file.read_text())
        if (proof.get('all_original_native_metrics_reproduced') is not True
                or proof.get('parameters_changed') is not False
                or proof.get('native_mos')!=count or proof.get('programming_gates')!=173):
            raise ValueError('Require exact independently replayed full native bank metrics')
        case=ROOT/proof['case'];row=json.loads((case/'summary.json').read_text())
        if row['error'] is not None or row['spec']!=proof['spec']:
            raise ValueError('Complete native case/replay specification changed')
        wanted_fine=0 if label.endswith('_zero') else 31
        wanted_duty=.5 if wanted_fine==0 else .6 if label.endswith('60') else .4
        if any(row['spec'].get(k)!=v for k,v in dict(process='ss',temperature=40,coarse=0,
                fine=wanted_fine,duty=wanted_duty,frequency_mhz=410,cycles=8,stop_ns=25,
                input_slew_ps=100,load_ff=20).items()):
            raise ValueError('Require matching full native zero and fine-duty endpoint cases')
        for name,digest in proof['inputs'].items():
            if name in expected and expected[name]!=digest:
                raise ValueError('Conflicting frozen input bytes between native replay receipts')
            expected[name]=digest
        paths += [file,case/'summary.json',case.parent/'bank.spice']
        records.append(dict(label=label,case=str(case.relative_to(ROOT)),
            proof=str(file.relative_to(ROOT)),spec=row['spec'],native_mos=count))
    paths += [ROOT/n for n in expected]
    paths += sorted({Path(m.__file__).resolve() for m in list(sys.modules.values())
        if getattr(m,'__file__',None) and Path(m.__file__).resolve().parent==ROOT/'scripts'})
    inputs={str(p.relative_to(ROOT)):sha(p) for p in sorted(set(paths))}
    if any(inputs.get(n)!=h for n,h in expected.items()):
        raise ValueError('Completed native replay inputs changed')
    identity=dict(version=VERSION,records=records,inputs=inputs,scope=SCOPE)
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);atomic(out/'manifest.json',dict(identity=identity,qualified_phy=False))
    atomic(out/'state.json',dict(status='analyzing',qualified_phy=False))
    try:
        rows=[]
        for record in records:
            case=ROOT/record['case'];bank=(case.parent/'bank.spice').read_text()
            driver='openlvds_recovery_p40n16_v339' if record['label'].startswith('p40') else 'openlvds_discharge_p20n16_v218'
            inventory={name:native_inventory(bank,model,pin) for name,model,pin in (
                ('loaded_driver',driver,'A'),('coarse_unit','openlvds_parallel_coarse_b2_v120','IN'),
                ('tg','openlvds_tg_quad_stacked_nlvt_v27','A'))}
            rows.append(dict(record,**observe(case),native_inventory=inventory))
            atomic(out/(record['label']+'.json'),rows[-1])
        if any(sha(ROOT/n)!=h for n,h in inputs.items()):raise ValueError('Native analysis inputs changed')
        atomic(out/'summary.json',dict(rows=rows,analysis_completed=True,parameters_changed=False,
            no_new_simulation=True,qualified_phy=False,scope=SCOPE))
        atomic(out/'state.json',dict(status='complete',analysis_completed=True,qualified_phy=False))
    except Exception as error:
        atomic(out/'state.json',dict(status='failed',error=str(error),qualified_phy=False));raise
    return out


if __name__=='__main__':print(run(),flush=True)
