#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Compare original and regular-P/N CLK/REQUEST buffers on the same counter.

Every master retains qualified component RC. Both assemblies use ideal shared
wires; neither represents a new routed counter or grants electrical admission.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import probe_fast_clear_counter_shared_rc_v269 as source
import probe_regular_regenerated_bank_v263 as regular
import analyze_counter_low_windows_v305 as diagnosis
from build_compound_drivers_v3 import cell_definition
from probe_digital_dcc_v2 import atomic
from native_binary_raw_v2 import validate
from spice_dispatch import lease

ROOT=source.ROOT
sha=source.sha
VERSION='paired-component-rc-counter-matched-clk-request-regular-buffers-v306.1'
CONTEXT='counter_matched_buffers_v306'
OLD='openlvds_buf_8_o4_shunted_v2'
BUFFER='openlvds_regular_buffer_p20n16_v306'
ROLES={'clock_driver','clock_driver_parallel','request_driver','request_driver_parallel'}
CORE=source.rc.NAME
PN=regular.MODEL
STORAGE=source.rc.physical.source.STORAGE
SCOPE='Paired original/regular-PN positive CLK and REQUEST buffers on unchanged fast-clear counter logic and original DCC loads; qualified component RC and ideal shared wires only, no routed-counter/PVT/DCC/PHY admission'


def specifications():
    base=source.specifications()[0]
    return [dict(base,temperature=t,duty=d,stop_level=level,buffer_variant=v)
        for t in (0,40) for d in (.6,.5,.4) for level in (0,1) for v in ('baseline','matched')]


def assemble(cells,module,logical,storage_text,pn_text,variant):
    native=source.native
    if variant not in ('baseline','matched') or len(logical)!=22 or len({c['name'] for c in logical})!=22:
        raise ValueError('Require one declared variant and the exact 22-macro fast-clear topology')
    roles=[c for c in logical if c['name'] in ROLES]
    if len(roles)!=4 or any(c['model']!=OLD for c in roles):raise ValueError('Original two CLK and two REQUEST buffer roles changed')
    defs=native.definitions(cells)
    for text,model,ports in ((storage_text,STORAGE,['A','B','Y','VGND','VPWR']),(pn_text,PN,['A','Y','VGND','VPWR'])):
        extra=native.definitions(text)
        if set(extra)!={model} or extra[model][0]!=ports or model in defs:raise ValueError('Qualified native component namespace or ports changed')
    if BUFFER in defs or CORE in defs:raise ValueError('Counter hypothesis namespace collision')
    wrapper='\n'.join(['.subckt '+BUFFER+' A X VGND VPWR',
        'Xrestore0 A internal_b VGND VPWR '+PN,'Xrestore1 internal_b X VGND VPWR '+PN,'.ends '+BUFFER,''])
    library=cells+'\n'+storage_text+'\n'+pn_text+'\n'+wrapper;definitions=native.definitions(library)
    calls=[]
    for cell in logical:
        model=BUFFER if variant=='matched' and cell['name'] in ROLES else cell['model']
        ports=definitions[model][0]
        if set(ports)!=set(cell['pins']):raise ValueError('Native component pin mapping changed')
        calls.append('X'+cell['name']+' '+' '.join(cell['pins'][p] for p in ports)+' '+model)
    block='\n'.join(['.subckt '+CORE+' '+' '.join(source.PORTS),*calls,'.ends '+CORE,''])
    return source.libraries(library,module,block)


def observations(cells,module):
    devices=source.native.mapped_mos(cells+module,source.HARNESS,
        {p:'0' if p=='VGND' else 'VDD' if p=='VPWR' else p for p in source.PORTS},'XD')
    if len({d['name'] for d in devices})!=len(devices):raise ValueError('Duplicate native counter observations')
    return devices


def preservation(baseline,matched,original_loads):
    def buffer(d):return any(d['name'].startswith('XD:XR:X'+role+':') for role in ROLES)
    def load(d):return any(d['name'].startswith('XD:'+role+':') for role in source.LOADS)
    if (len(baseline)!=644 or len(matched)!=844 or len([d for d in baseline if buffer(d)])!=88
        or len([d for d in matched if buffer(d)])!=288
        or [d for d in baseline if not buffer(d)]!=[d for d in matched if not buffer(d)]
        or [d for d in baseline if load(d)]!=[d for d in original_loads if load(d)]):
        raise ValueError('Native census, unchanged counter logic or original 64 load MOS not preserved')
    return dict(baseline_native_mos=644,matched_native_mos=844,removed_buffer_mos=88,added_regular_pair_mos=288,
        unchanged_nonbuffer_native_observations=True,original_downstream_64_mos_preserved=True,
        same_positive_buffer_ports=True,new_shared_wire_rc_qualified=False,qualified_phy=False)


def require_diagnosis(folder):
    m=json.loads((folder/'manifest.json').read_text());i=m['identity'];r=json.loads((folder/'summary.json').read_text())
    if (folder.parent!=ROOT/'build/diagnostics'/diagnosis.CONTEXT or i['version']!=diagnosis.VERSION
        or folder.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or json.loads((folder/'state.json').read_text())!=dict(status='complete',analysis_completed=True,qualified_phy=False)
        or r.get('analysis_completed') is not True or r.get('parameters_changed') is not False
        or any(sha(ROOT/n)!=h for n,h in i['inputs'].items())):
        raise ValueError('Require unchanged complete fixed-epoch native low-window diagnosis')
    old=[row for row in r['rows'] if row['native_mos_observed']==612 and row['task']['spec']['duty']==.6]
    passing=[row for row in r['rows'] if row['native_mos_observed']==644 and row['task']['spec']['duty']==.5]
    if (len(old)!=1 or not old[0]['original_clear']['original_async_clear_gate_reproduced']
        or old[0]['low_windows']['all_three_assertions_in_original_low_windows'] is not False
        or old[0]['low_windows']['minimum_remaining_low_window_ps']>=0 or len(passing)!=2
        or any(not row['low_windows']['all_three_assertions_in_original_low_windows'] for row in passing)):
        raise ValueError('Require distinct original 60% arming failure and both completed fast-clear 50% controls')
    return i


def fixture(out,s,devices):
    spec={k:v for k,v in s.items() if k!='buffer_variant'}
    text=source.baseline.fixture(out,spec,devices);first,rest=text.split('\n',1)
    if first!='OpenLVDS '+source.baseline.VERSION:raise ValueError('Original 26ns native protocol changed')
    return 'OpenLVDS '+VERSION+'\n'+rest


def prepare(counter,bank,evidence):
    di=require_diagnosis(evidence);cm=source.bound(counter);ci=cm['identity'];bm=regular.bound(bank);bi=bm['identity']
    pilot=ROOT/ci['source'];pm=source.pilot.bound(pilot)
    rc=ROOT/ci['parent'];rm=source.rc.bound(rc);physical=ROOT/rm['identity']['parent']
    physical_m=source.rc.physical.bound(physical);logical=physical_m['identity']['cells']
    storage=ROOT/physical_m['identity']['component']
    record=source.rc.physical.source.storage_evidence(storage)
    storage_path=ROOT/record['report']['extraction']['netlist'];storage_text=storage_path.read_text()
    pn_text=cell_definition((bank/'bank.spice').read_text(),PN)
    original_cells=(pilot/'cells.spice').read_text();original_module=(pilot/'pair.spice').read_text()
    libraries={v:assemble(original_cells,original_module,logical,storage_text,pn_text,v) for v in ('baseline','matched')}
    devices={v:observations(*libraries[v]) for v in libraries}
    proof=preservation(devices['baseline'],devices['matched'],ci['devices'])
    paths=[counter/'manifest.json',bank/'manifest.json',bank/'bank.spice',physical/'manifest.json',storage_path,
        pilot/'manifest.json',pilot/'cells.spice',pilot/'pair.spice',*[evidence/n for n in ('manifest.json','summary.json','state.json')]]
    paths += [ROOT/n for n in {*ci['inputs'],*bi['inputs'],*pm['identity']['inputs'],*di['inputs'],*record['files']}]
    paths += sorted({Path(mod.__file__).resolve() for mod in list(sys.modules.values()) if getattr(mod,'__file__',None)
        and Path(mod.__file__).resolve().parent==ROOT/'scripts'})
    i=dict(version=VERSION,counter=str(counter.relative_to(ROOT)),bank=str(bank.relative_to(ROOT)),diagnosis=str(evidence.relative_to(ROOT)),
        logical_cells=logical,devices=devices,preservation=proof,specs=specifications(),
        pdk_files={**ci['pdk_files'],**bi['pdk_files'],**bi.get('external_files',{})},simulator=ci['simulator'],
        inputs={str(p.relative_to(ROOT)):sha(p) for p in sorted(set(paths))},max_workers=2,priority=0,scope=SCOPE)
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);hashes={}
    for v,(cells,module) in libraries.items():
        folder=out/v;folder.mkdir()
        for name,text in (('cells.spice',cells),('pair.spice',module)):
            p=folder/name;p.write_text(text);hashes[str(p.relative_to(out))]=sha(p)
    tasks=[]
    for k,s in enumerate(i['specs']):
        folder=out/str(k);folder.mkdir();(folder/'bench.cir').write_text(fixture(out/s['buffer_variant'],s,devices[s['buffer_variant']]))
        tasks.append(dict(id=str(k),spec=s,deck_sha256=sha(folder/'bench.cir')))
    atomic(out/'manifest.json',dict(identity=i,tasks=tasks,libraries=hashes,qualified_phy=False));return out


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION
        or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or i['specs']!=specifications() or i['max_workers']!=2 or i['priority']!=0 or len(m['tasks'])!=24
        or source.engine()!='ngspice' or source.provenance()!=i['simulator']
        or any(sha(ROOT/n)!=h for n,h in i['inputs'].items()) or any(sha(Path(n))!=h for n,h in i['pdk_files'].items())
        or any(sha(out/n)!=h for n,h in m['libraries'].items())):
        raise ValueError('Matched clock/REQUEST native hypothesis context changed')
    current={v:observations((out/v/'cells.spice').read_text(),(out/v/'pair.spice').read_text()) for v in ('baseline','matched')}
    if current!=i['devices'] or preservation(current['baseline'],current['matched'],i['devices']['baseline'])!=i['preservation']:
        raise ValueError('Matched buffer native terminal census or preservation changed')
    for k,t in enumerate(m['tasks']):
        s=i['specs'][k];path=out/str(k)/'bench.cir'
        if t!=dict(id=str(k),spec=s,deck_sha256=sha(path)) or path.read_text()!=fixture(out/s['buffer_variant'],s,i['devices'][s['buffer_variant']]):
            raise ValueError('Original matched-buffer native fixture changed')
    return m


def measure(case,i,s):
    spec={k:v for k,v in s.items() if k!='buffer_variant'};r=source.baseline.measure(case,spec,i['devices'][s['buffer_variant']])
    names,w=validate(case/'bench.raw',{'v(clk)',*[f'v(xd.xr.{n})' for n in diagnosis.STAGES]},26e-9)
    signals={'CLK':w[:,names.index('v(clk)')],**{n:w[:,names.index(f'v(xd.xr.{n})')] for n in diagnosis.STAGES}}
    window=diagnosis.windows(w[:,names.index('time')]*1e12,signals)
    passed=bool(r['counter_feasibility_passed'] and math.isfinite(r['minimum_clock_low_voltage_margin_v'])
        and r['minimum_clock_low_voltage_margin_v']>=0 and window['all_three_assertions_in_original_low_windows'])
    return dict(r,low_windows=window,hypothesis_point_checks_passed=passed,component_rc_only=True,
        counter_shared_wire_rc_qualified=False,whole_clock_rc_qualified=False,all_pvt_covered=False,
        electrical_qualification_passed=False,qualified_phy=False,scope=SCOPE)


def assess(rows):
    if len(rows)!=24 or any(r['error'] is not None or r['result'] is None for r in rows):return None
    if [r['task']['spec'] for r in rows]!=specifications():raise ValueError('Require complete paired 24-case SS0/40 clock-duty/stopped-level coverage')
    pairs=[]
    for a,b in zip(rows[::2],rows[1::2]):
        x=a['result'];y=b['result']
        pairs.append(dict(spec={k:v for k,v in a['task']['spec'].items() if k!='buffer_variant'},
            baseline_point_passed=x['hypothesis_point_checks_passed'],matched_point_passed=y['hypothesis_point_checks_passed'],
            baseline_low_window_ps=x['low_windows']['minimum_remaining_low_window_ps'],
            matched_low_window_ps=y['low_windows']['minimum_remaining_low_window_ps'],
            baseline_voltage_margin_v=x['minimum_clock_low_voltage_margin_v'],matched_voltage_margin_v=y['minimum_clock_low_voltage_margin_v']))
    return dict(paired_native_component_cases_complete=True,pairs=pairs,matched_component_hypothesis_passed=all(p['matched_point_passed'] for p in pairs),
        baseline_component_hypothesis_passed=all(p['baseline_point_passed'] for p in pairs),
        actual_shared_counter_timing_pilot_passed=False,all_pvt_covered=False,whole_clock_rc_qualified=False,
        hardware_warmup_qualified=False,electrical_qualification_passed=False,qualified_phy=False)


def run(out):
    m=bound(out);i=m['identity']
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain previous or partial native matched-buffer hypothesis')
        atomic(out/'state.json',dict(status='running',qualified_phy=False))
        def execute(task):
            case=out/task['id'];result=error=None
            try:
                with lease(ROOT,priority=i['priority'],label=CONTEXT+'_'+task['id']):
                    bound(out);p=subprocess.run([sys.executable,str(ROOT/'scripts/run_native_binary_v2.py'),'-l',str(case/'ngspice.log'),str(case/'bench.cir')],capture_output=True,text=True)
                (case/'console.log').write_text(p.stdout+p.stderr);p.check_returncode();result=measure(case,i,task['spec'])
            except Exception as e:error=str(e)
            row=dict(task=task,result=result,error=error,files={p.name:sha(p) for p in case.iterdir() if p.is_file()});atomic(case/'summary.json',row);return row
        with ThreadPoolExecutor(max_workers=2) as pool:rows=list(pool.map(execute,m['tasks']))
        bound(out);atomic(out/'summary.json',dict(rows=rows,comparison=assess(rows),scope=SCOPE,qualified_phy=False))
        atomic(out/'state.json',dict(status='complete',cases=24,errors=sum(r['error'] is not None for r in rows),qualified_phy=False));return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='action',required=True)
    q=sub.add_parser('prepare');q.add_argument('counter',type=Path);q.add_argument('bank',type=Path);q.add_argument('diagnosis',type=Path)
    q=sub.add_parser('run');q.add_argument('artifact',type=Path);a=p.parse_args()
    print(prepare(a.counter.resolve(),a.bank.resolve(),a.diagnosis.resolve()) if a.action=='prepare' else run(a.artifact.resolve()),flush=True)
