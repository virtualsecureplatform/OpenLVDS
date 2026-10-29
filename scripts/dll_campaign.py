#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Prepare, execute and resume isolated DLL experiments with a durable four-job queue."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import numpy as np
import dll_design as design
import dll_measurements as measure
from layout import circuits,flatten,schematic_text
from screen_dll import stimulus
from spice_library import library,replace
from spice_engine import command,engine,provenance
from run_ngspice import read_raw

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'build/diagnostics/dll_architecture'
CODE=['scripts/dll_campaign.py','scripts/dll_design.py','scripts/dll_measurements.py',
      'scripts/screen_dll.py','scripts/layout.py','scripts/lvs_utils.py','scripts/spice_library.py',
      'scripts/spice_scope.py','scripts/verify_phase_detector.py']

def digest(data):return hashlib.sha256(data).hexdigest()
def atomic(path,value):
    temp=path.with_name(path.name+'.tmp');temp.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n');temp.replace(path)
def dependencies():return {p:digest((ROOT/p).read_bytes()) for p in CODE}
def text_block(text,name):
    m=re.search(r'(?ims)^\.subckt '+re.escape(name)+r'\s.*?^\.ends[^\n]*',text)
    if not m:raise ValueError('Missing '+name)
    return m[0]
def closure(text,tops):
    blocks={m[1].lower():m[0] for m in re.finditer(r'(?ims)^\.subckt\s+(\S+)\s.*?^\.ends[^\n]*',text)}
    selected={}
    def visit(name):
        name=name.lower()
        if name in selected:return
        if name not in blocks:raise ValueError('Missing experiment root '+name)
        selected[name]=blocks[name]
        for line in blocks[name].splitlines():
            words=line.split()
            if words and words[0].lower().startswith('x'):
                end=next((i for i,x in enumerate(words) if '=' in x),len(words));child=words[end-1].lower()
                if child in blocks:visit(child)
    for top in tops:visit(top)
    return '\n\n'.join(selected.values())+'\n'

def bias_reference_count(deck,lib):
    definitions={m[1].lower():m[0] for m in re.finditer(r'(?ims)^\.subckt\s+(\S+)\s.*?^\.ends[^\n]*',lib)}
    def count(text,stack=()):
        total=0
        for line in text.splitlines():
            words=line.split()
            if not words or not words[0].lower().startswith('x'):continue
            end=next((i for i,w in enumerate(words) if '=' in w),len(words));child=words[end-1].lower()
            if child=='lvds_bias':total+=1
            elif child in definitions:
                if child in stack:raise ValueError('Recursive circuit hierarchy')
                total+=count(definitions[child],stack+(child,))
        return total
    return count(deck)


def prepare():
    if engine()!='ngspice':raise ValueError('Use env.sh --ngspice for the pinned diagnostic campaign')
    source=(ROOT/'analog/openlvds.spice').read_text();monitor=(ROOT/'analog/experiments/phase_area.spice').read_text()
    captured,inputs,_=library(extracted=True,designs={'openlvds_dll_analog','openlvds_delay_line','lvds_bias'})
    captured=captured.decode();pdports=re.search(r'(?im)^\.subckt lvds_pfd ([^\n]+)',captured)[1].split()
    req=(ROOT/'requirements.json').read_bytes();code=dependencies();stamp=provenance()
    capture=ROOT/'build/analog_extracted/dll_ss_0/bench.cir.prn';capture_bytes=capture.read_bytes()
    identity=dict(code=code,simulator=engine(),simulator_provenance=stamp,source_sha256=digest(source.encode()),
        monitor_sha256=digest(monitor.encode()),requirements_sha256=digest(req),extraction_inputs=inputs,
        captured_library_sha256=digest(captured.encode()),follower_capture_sha256=digest(capture_bytes))
    root=BASE/digest(json.dumps(identity,sort_keys=True).encode())[:16]
    if (root/'manifest.json').exists():return root
    root.mkdir(parents=True,exist_ok=True);snap=root/'inputs';snap.mkdir(exist_ok=True)
    for name in CODE:
        path=snap/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes((ROOT/name).read_bytes())
    (snap/'original.spice').write_text(source);(snap/'phase_area.spice').write_text(monitor)
    (snap/'requirements.json').write_bytes(req);(snap/'follower_capture.prn').write_bytes(capture_bytes)
    pdk=Path(os.environ['PDK_ROOT'])/'sky130A/libs.tech/ngspice/sky130.lib.spice'
    tasks=[]
    def add(name,spec,lib,body,probes,needs=()):
        out=root/name;out.mkdir(exist_ok=True)
        lib=closure(lib,spec['tops']);(out/'library.spice').write_text(lib)
        prefix=f'''OpenLVDS {name} DIAGNOSTIC ONLY
.lib "{pdk}" {spec.get('corner','tt')}
.include "{out}/library.spice"
.options device temp={spec.get('temp',25)}
.options timeint method=gear reltol=1e-4 abstol=1e-12
VA VDDIO 0 3.3
VD VDDD 0 1.8
IB PB 0 35u
'''
        if spec['kind']!='loop':prefix+='XB PB NB VDDIO 0 lvds_bias\n'
        if spec['kind'] in ['phase','logic']:prefix+='XBI PB PC NC VDDIO VDDD 0 screen_bias\n'
        deck=prefix+body+f'\n.save i(VA) i(VD)\n.tran 5p {spec["stop_ns"]}n 0 20p\n.print tran '+ ' '.join('V('+n+')' for n in probes.values())+'\n.end\n'
        if bias_reference_count(deck,lib)!=1:raise ValueError('Fixture must contain exactly one reference diode generator')
        (out/'bench.cir').write_text(deck)
        task=dict(id=name,spec=spec,aliases=probes,needs=list(needs),files={n:digest((out/n).read_bytes()) for n in ['bench.cir','library.spice']})
        tasks.append(task)
    # The native monitor is independent of the old inertial XOR network.
    monitor_source=source+'\n'+monitor+'\n'+design.bias_block(source)
    monitor_lib=captured+'\n'+design.native_block(monitor_source,'lvds_phase_area')+'\n'+design.native_block(monitor_source,'screen_bias')
    for corner,temp in [('ss',0),('tt',25),('ff',0)]:
        for offset in [0,50,-50,150,-150,300,-300]:
            body=f'''VRST RST 0 PWL(0 0 2n 0 2.1n 1.8)
VR REF 0 PULSE(0 1.8 5n 100p 100p 1.15n 2.5n)
VF FDB 0 PULSE(0 1.8 {5+offset/1000:.9g}n 100p 100p 1.15n 2.5n)
XP REF FDB RST VDDD UP DN ERR VDDD 0 0 0 0 lvds_pfd
XMON UP DN UF DF BAD PC VDDD 0 lvds_phase_area
CB BAD 0 20f
'''
            add(f'monitor_{corner}_{temp}_{offset}ps',dict(kind='phase',corner=corner,temp=temp,offset=offset,stop_ns=160,
                tops=['lvds_phase_area','lvds_pfd','lvds_bias','screen_bias']),monitor_lib,body,{n:n for n in ['REF','FDB','UP','DN','UF','DF','BAD']})
        for value in [0,1.8]:
            body=f'''VU UP 0 {value}\nVN DN 0 {value}\nXMON UP DN UF DF BAD PC VDDD 0 lvds_phase_area\nCB BAD 0 20f\n'''
            add(f'stuck_{corner}_{temp}_{value:g}',dict(kind='logic',expected=True,corner=corner,temp=temp,stop_ns=160,
                tops=['lvds_phase_area','lvds_bias','screen_bias']),monitor_lib,body,{n:n for n in ['UP','DN','UF','DF','BAD']})
    monitor_needs=[t['id'] for t in tasks]
    wave,head=measure.read_wave(snap/'follower_capture.prn')
    chosen=wave[(wave[:,1]>=1200e-9)&(wave[:,1]<1250e-9)];times=(chosen[:,1]-chosen[0,1])*1e9
    replay_time=np.concatenate([times,times+50,[100]])
    def replay(name):
        values=measure.column(chosen,head,name)
        return stimulus(replay_time,np.concatenate([values,values,[values[0]]]))
    variants={**design.CP_VARIANTS,**design.OTA_VARIANTS}
    for variant in variants:
        candidate=design.candidate_source(source,variant,monitor)
        (snap/(variant+'.spice')).write_text(candidate)
        if variant in design.CP_VARIANTS:
            for load in ['loaded','unloaded']:
                defs=circuits(candidate);ports,rows=defs['openlvds_dll_analog']
                if load=='unloaded':rows=[r for r in rows if r[0] not in {'XCUDUMP','XADDUDN','XCDDUMP','XADDDDP'}]
                defs['openlvds_dll_analog']=(ports,rows)
                _,devices=flatten(defs,'openlvds_dll_analog');flat=schematic_text('openlvds_dll_analog',ports+['openlvds_dll_analog__CTRL'],devices)
                lib=replace(candidate,'openlvds_dll_analog',flat)
                nodes=dict(CLK='0',PD_ENABLE='VDDD',PH0='PH0',PH90='PH90',PH180='PH180',PH270='PH270',FB='FB',PD_REF='PD_REF',
                           PHASE_BAD='BAD',UP='UP',DN='DN',PB='PB',VDDIO='VDDIO',VDDD='VDDD',VSS='0')
                body=f'''VC CTRL 0 {replay('XL:XCORE:XA:openlvds_dll_analog__CTRL')}
VU UP 0 {replay('UP')}
VN DN 0 {replay('DN')}
XA {' '.join(nodes[p] for p in ports)} CTRL openlvds_dll_analog
'''
                probes=dict(CTRL='CTRL',COPY='XA:openlvds_dll_analog__VCOPY',UP='UP',DN='DN')
                add(variant+'_'+load,dict(kind='follower',load=load,corner='ss',temp=0,stop_ns=100,
                    tops=['openlvds_dll_analog','lvds_bias','screen_bias']),lib,body,probes)
        hybrid=design.hybrid_library(candidate,captured,pdports)
        for corner,temp in [('ss',0),('tt',25),('ff',0)]:
            body='''VREF VREF 0 1.2
VCLK CLK 0 PULSE(0 1.8 5n 100p 100p 1.15n 2.5n)
VRST RST 0 PWL(0 0 2n 0 2.02n 1.8)
VEN ENABLE 0 PWL(0 0 85.2n 0 85.22n 1.8)
XL CLK RST ENABLE PH0 PH90 PH180 PH270 FB BAD UP DN VREF PB VDDIO VDDD 0 openlvds_dll
C0 PH0 0 40f
C90 PH90 0 40f
C180 PH180 0 20f
C270 PH270 0 20f
CFB FB 0 20f
'''
            probes={n:n for n in ['PH0','PH90','PH180','PH270','FB','BAD','UP','DN']}
            probes['PD_REF']='XL:XCORE:PD_REF'
            for n in ['CTRL','UF','DF']:probes[n]='XL:XCORE:XA:openlvds_dll_analog__'+n
            architecture='charge_pump' if variant in design.CP_VARIANTS else 'averaged_pfd_ota'
            if architecture=='charge_pump':probes['COPY']='XL:XCORE:XA:openlvds_dll_analog__VCOPY'
            needs=monitor_needs+([variant+'_loaded'] if architecture=='charge_pump' else [])
            add(f'{variant}_loop_{corner}_{temp}',dict(kind='loop',variant=variant,architecture=architecture,corner=corner,temp=temp,mhz=400,
                stop_ns=1500,tops=['openlvds_dll']),hybrid,body,probes,needs)
    manifest=dict(identity=identity,tasks=tasks,diagnostic=True,qualified=False)
    atomic(root/'manifest.json',manifest)
    atomic(root/'state.json',dict(status='prepared',tasks={t['id']:dict(status='pending') for t in tasks}))
    return root

def validate(root,manifest,task):
    if dependencies()!=manifest['identity']['code'] or provenance()!=manifest['identity']['simulator_provenance']:
        raise ValueError('Producer or simulator changed; prepare a new campaign')
    for name,expected in task['files'].items():
        if digest((root/task['id']/name).read_bytes())!=expected:raise ValueError('Captured task input changed: '+name)

def execute(root,task,reuse_from=None):
    manifest=json.loads((root/'manifest.json').read_text());validate(root,manifest,task)
    out=root/task['id'];spec=task['spec'];start=time.time()
    if reuse_from is None:
        run=subprocess.run(command(out/(engine()+'.log'),out/'bench.cir'),cwd=out,capture_output=True,text=True)
        (out/'console.log').write_text(run.stdout+run.stderr)
        returncode=run.returncode
    else:returncode=0
    result=dict(diagnostic=True,qualified=False,task=task['id'],spec=spec,returncode=returncode,passed=False,
                wall_seconds=time.time()-start,input_files=task['files'])
    try:
        if returncode:raise ValueError('Simulator failed')
        wave,head=measure.read_wave(out/'bench.cir.prn')
        for alias,node in task['aliases'].items():head['V('+alias.upper()+')']=head['V('+node.upper()+')']
        kind=spec['kind']
        if kind=='phase':metrics=measure.phase(wave,head,spec['offset'])
        elif kind=='logic':metrics=measure.logic(wave,head,spec['expected'])
        elif kind=='loop':metrics=measure.loop(wave,head,spec['mhz'],spec['architecture'])
        else:
            keep=(wave[:,1]>=50e-9)&(wave[:,1]<100e-9)
            error=(measure.column(wave,head,'CTRL')-measure.column(wave,head,'COPY'))[keep]
            peak=float(np.max(abs(error))*1000)
            metrics=dict(passed=bool(measure.complete(wave,100) and peak<50),complete=measure.complete(wave,100),
                         screening_margin_passed=peak<40,peak_copy_error_mv=peak,
                         mean_copy_error_mv=measure.average(wave[keep,1],error)*1000)
        result.update(metrics)
        if reuse_from is None:
            variables,raw=read_raw(out/'bench.raw');index={n:i for i,n in enumerate(variables)}
            keep=raw[:,index['time']]>=max(0,spec['stop_ns']-300)*1e-9
            power=-3.3*raw[keep,index['i(va)']]-1.8*raw[keep,index['i(vd)']]
            result['mean_supply_power_mw']=measure.average(raw[keep,index['time']],power)*1000
            result['raw_sha256']=digest((out/'bench.raw').read_bytes())
        else:
            result.update(reanalysis_from=reuse_from,mean_supply_power_mw=None,power_applicability='Original raw current trace was not attested; not reused')
        result['waveform_sha256']=digest((out/'bench.cir.prn').read_bytes())
        validate(root,manifest,task)
    except (ValueError,KeyError,OSError,IndexError) as e:result.update(passed=False,error=str(e))
    atomic(out/'summary.json',result)
    return result

def import_monitor_results(root,previous):
    """Reanalyze only unchanged, hash-bound monitor stimuli; no loop reuse."""
    import shutil
    current=json.loads((root/'manifest.json').read_text());old=json.loads((previous/'manifest.json').read_text())
    for key,value in current['identity'].items():
        if key!='code' and old['identity'].get(key)!=value:raise ValueError('Changed input scope: '+key)
    for name,value in current['identity']['code'].items():
        if name=='scripts/dll_campaign.py' or old['identity']['code'].get(name)==value:continue
        if name=='scripts/dll_measurements.py':
            import ast
            def monitor_ast(text):
                tree=ast.parse(text);tree.body=[n for n in tree.body if not isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) or n.name!='loop']
                return ast.dump(tree,include_attributes=False)
            if monitor_ast((previous/'inputs'/name).read_text())==monitor_ast((ROOT/name).read_text()):continue
        raise ValueError('Changed monitor analyzer dependency')
    old_tasks={t['id']:t for t in old['tasks']};imported=0
    normalize=lambda text:re.sub(r'(?im)^\.include .*$', '.include "CAPTURED_LIBRARY"',text)
    for task in current['tasks']:
        if task['spec']['kind'] not in ['phase','logic']:continue
        prior=previous/task['id'];report=prior/'summary.json'
        if not report.exists():continue
        evidence=json.loads(report.read_text());old_task=old_tasks[task['id']]
        if evidence.get('returncode')!=0 or evidence.get('input_files')!=old_task['files']:continue
        if task['spec']!=old_task['spec'] or task['aliases']!=old_task['aliases']:raise ValueError('Changed monitor fixture')
        for name,sha in old_task['files'].items():
            if digest((prior/name).read_bytes())!=sha:raise ValueError('Changed captured monitor input')
        out=root/task['id']
        if (out/'library.spice').read_bytes()!=(prior/'library.spice').read_bytes():raise ValueError('Changed monitor library')
        if normalize((out/'bench.cir').read_text())!=normalize((prior/'bench.cir').read_text()):raise ValueError('Changed monitor stimulus')
        wave=prior/'bench.cir.prn'
        if digest(wave.read_bytes())!=evidence.get('waveform_sha256'):raise ValueError('Changed captured monitor waveform')
        shutil.copyfile(wave,out/'bench.cir.prn')
        origin=dict(campaign=str(previous),task=task['id'],manifest_sha256=digest((previous/'manifest.json').read_bytes()),
                    producer_code=old['identity']['code'],waveform_sha256=evidence['waveform_sha256'])
        atomic(out/'reanalysis_origin.json',origin);execute(root,task,reuse_from=origin);imported+=1
    return imported


def supervise(root,jobs):
    if jobs<1 or jobs>4:raise ValueError('Concurrency must be 1..4')
    BASE.mkdir(parents=True,exist_ok=True)
    with (BASE/'.supervisor.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        manifest=json.loads((root/'manifest.json').read_text());tasks={t['id']:t for t in manifest['tasks']}
        state=json.loads((root/'state.json').read_text());state.update(status='running',supervisor_pid=os.getpid(),max_jobs=jobs)
        active={}
        # Recover only completed, hash-bound results; never silently rerun an active worker.
        for key,record in state['tasks'].items():
            out=root/key/'summary.json'
            if out.exists():
                r=json.loads(out.read_text());validate(root,manifest,tasks[key])
                if r.get('input_files')!=tasks[key]['files'] or r.get('task')!=key:raise ValueError('Stale result')
                record.update(status='passed' if r.get('passed') else 'failed',result=str(out))
            elif record['status']=='running':
                pid=record.get('pid')
                try:os.kill(pid,0)
                except (ProcessLookupError,TypeError):record.update(status='failed',error='Worker exited without a result')
                else:active[key]=None
        while True:
            for key,proc in list(active.items()):
                summary=root/key/'summary.json'
                if proc is not None and proc.poll() is None:continue
                if proc is None and not summary.exists():
                    try:os.kill(state['tasks'][key]['pid'],0)
                    except ProcessLookupError:pass
                    else:continue
                if summary.exists():
                    r=json.loads(summary.read_text());state['tasks'][key].update(status='passed' if r.get('passed') else 'failed',result=str(summary))
                else:state['tasks'][key].update(status='failed',error='Worker exited without result')
                active.pop(key)
            for key,task in tasks.items():
                record=state['tasks'][key]
                if record['status']!='pending':continue
                needed=[state['tasks'][n]['status'] for n in task['needs']]
                if any(s in ['failed','skipped'] for s in needed):record.update(status='skipped',error='Prerequisite failed');continue
                if any(s!='passed' for s in needed) or len(active)>=jobs:continue
                validate(root,manifest,task)
                log=(root/key/'worker.log').open('a')
                proc=subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'worker',str(root),'--task',key],stdout=log,stderr=subprocess.STDOUT)
                log.close();active[key]=proc;record.update(status='running',pid=proc.pid,started_unix=time.time())
            state['updated_unix']=time.time();atomic(root/'state.json',state)
            if not active and not any(r['status']=='pending' for r in state['tasks'].values()):break
            time.sleep(2)
        state['status']='completed' if all(r['status']=='passed' for r in state['tasks'].values()) else 'completed_with_failures'
        atomic(root/'state.json',state)
        print(json.dumps(dict(campaign=str(root),status=state['status'],counts={s:sum(r['status']==s for r in state['tasks'].values()) for s in ['passed','failed','skipped']})))

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','status','worker'])
    p.add_argument('campaign',nargs='?',type=Path);p.add_argument('--jobs',type=int,default=4);p.add_argument('--task');p.add_argument('--reuse-monitors',type=Path)
    a=p.parse_args();root=a.campaign.resolve() if a.campaign else None
    if a.action=='prepare':
        root=prepare()
        if a.reuse_monitors:print('Reanalyzed monitors:',import_monitor_results(root,a.reuse_monitors.resolve()))
        print(root);return
    if root is None:p.error('Campaign directory required')
    if a.action=='run':supervise(root,a.jobs)
    elif a.action=='worker':
        manifest=json.loads((root/'manifest.json').read_text());task=next(t for t in manifest['tasks'] if t['id']==a.task)
        r=execute(root,task);print(json.dumps(r));return 0 if r.get('passed') else 1
    else:
        state=json.loads((root/'state.json').read_text());counts={}
        for v in state['tasks'].values():counts[v['status']]=counts.get(v['status'],0)+1
        print(json.dumps(dict(campaign=str(root),status=state['status'],counts=counts,
            running=[k for k,v in state['tasks'].items() if v['status']=='running'],failed=[k for k,v in state['tasks'].items() if v['status']=='failed']),indent=2))

if __name__=='__main__':raise SystemExit(main())
