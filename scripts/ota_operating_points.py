#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Characterize OTA gm, offset and terminal stress around observed native loop points."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import itertools
import json
import math
from pathlib import Path
import re
import subprocess

import numpy as np
from dll_campaign import atomic,closure,bias_reference_count
from dll_design import native_block
from dll_measurements import read_wave,average,loop
from layout import circuits
from qualify_dll_candidate import evaluate
from qualify_dll_recovery import inputs
from run_ngspice import read_raw
from screen_dll import stimulus
from spice_engine import command,provenance
from spice_probes import ProbeNetwork
from spice_slots import slot

ROOT=Path(__file__).resolve().parents[1]
CM_GUARD_V=.02
CTRL_GUARD_V=.01
DELTA_V=.005
SLOT_NS=10


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def native_points(qualification,stability):
    q,model=inputs(qualification,stability)
    if not q['identity']['variant'].startswith('ota_'):raise ValueError('Expected an OTA candidate')
    points=[];sources={}
    def remember(path):sources[str(path.relative_to(ROOT))]=digest(path)
    for task in q['tasks']:
        spec=task['spec']
        if task['fast_rc'] or spec['kind']!='loop':continue
        folder=qualification/task['id'];report=json.loads((folder/'summary.json').read_text())
        if (not report['passed'] or report['deck_sha256']!=digest(folder/'bench.cir') or
            task['deck_sha256']!=report['deck_sha256'] or report['waveform_sha256']!=digest(folder/'bench.cir.prn')):
            raise ValueError('Native OTA operating-point source changed')
        metrics=evaluate(qualification,task)
        if not metrics['passed'] or metrics!=report['metrics']:raise ValueError('Native OTA operating point no longer passes')
        points.append(dict(id=task['id'],process=spec['process'],temperature=spec['temperature'],
            cm_v=(metrics['uf_mean_v']+metrics['df_mean_v'])/2,
            ctrl_v=metrics['control_mean_v'],diff_v=metrics['uf_mean_v']-metrics['df_mean_v']))
        for name in ['bench.cir','bench.cir.prn','summary.json']:remember(folder/name)
    for result in model['results']:
        corner=result['corner'];process,temp=corner.rsplit('_',1)
        task=next(t for t in q['tasks'] if t['id']=='loop_'+corner)
        for target in [390,410]:
            folder=stability.parent/corner/f'step_{target}';wave,header=read_wave(folder/'bench.cir.prn')
            for alias,node in task['aliases'].items():header['V('+alias.upper()+')']=header['V('+node.upper()+')']
            metrics=loop(wave,header,target,'averaged_pfd_ota',3100,3300)
            if not metrics['passed']:raise ValueError('Native endpoint is not settled for OTA characterization')
            points.append(dict(id=f'step_{corner}_{target}',process=process,temperature=int(temp),
                cm_v=(metrics['uf_mean_v']+metrics['df_mean_v'])/2,
                ctrl_v=metrics['control_mean_v'],diff_v=metrics['uf_mean_v']-metrics['df_mean_v']))
            for name in ['bench.cir','bench.cir.prn','evidence.json']:remember(folder/name)
    return q,points,sources


def grid(points):
    groups=[];rows=[]
    for point in points:
        for cm_delta,ctrl_delta in itertools.product([-CM_GUARD_V,0,CM_GUARD_V],[-CTRL_GUARD_V,0,CTRL_GUARD_V]):
            cm=point['cm_v']+cm_delta;ctrl=point['ctrl_v']+ctrl_delta
            values=[cm,ctrl,point['diff_v']]
            if not all(math.isfinite(v) for v in values) or not 0<ctrl<1.95:
                raise ValueError('Invalid guarded OTA operating range')
            start=len(rows)
            for center in [0,point['diff_v']]:
                for delta in [-DELTA_V,0,DELTA_V]:
                    differential=center+delta
                    if not (0<cm+differential/2<1.8 and 0<cm-differential/2<1.8):
                        raise ValueError('Guarded OTA inputs exceed their signal domain')
                    rows.append(dict(cm_v=cm,ctrl_v=ctrl,diff_v=differential))
            groups.append(dict(source=point['id'],cm_v=cm,ctrl_v=ctrl,operating_diff_v=point['diff_v'],start=start))
    if not groups:raise ValueError('No observed native operating points')
    return groups,rows


def thin_devices(native):
    ports,devices=circuits(native)['lvds_phase_ota']
    if ports!='UF DF OUT PB VDDIO VDDD VSS'.split():raise ValueError('Unsupported OTA signal interface')
    mapping=dict(zip(ports,['U','D','OUT','PB','VDDIO','VDDD','0']))
    result=[]
    for name,nodes,model,_ in devices:
        if re.match(r'^sky130_fd_pr__(?:nfet|pfet)_01v8(?:_|$)',model.lower()):
            if len(nodes)!=4:raise ValueError('Unexpected thin MOS terminal count')
            result.append(dict(name=name,nodes=[mapping.get(n,'XO:'+n) for n in nodes]))
    if not result:raise ValueError('OTA has no recognized thin devices')
    return result


def analyze(raw,groups,rows,devices):
    names,wave=read_raw(raw);index={n.lower():i for i,n in enumerate(names)};t=wave[:,index['time']]
    if (not np.isfinite(wave).all() or not np.all(np.diff(t)>0) or t[0]>1e-15 or
        t[-1]<len(rows)*SLOT_NS*1e-9-1e-12):raise ValueError('Incomplete OTA operating-point trace')
    def voltage(name):
        return np.zeros(len(t)) if name=='0' else wave[:,index['v('+name.replace(':','.').lower()+')']]
    rails=bool(np.max(abs(voltage('VDDIO')-3.3))<1e-8 and np.max(abs(voltage('VDDD')-1.8))<1e-8)
    currents=[];forced=True
    for i,row in enumerate(rows):
        keep=(t>=(i*SLOT_NS+8)*1e-9)&(t<=(i*SLOT_NS+9.8)*1e-9)
        currents.append(average(t[keep],wave[keep,index['i(vforce)']]))
        for node,value in [('U',row['cm_v']+row['diff_v']/2),('D',row['cm_v']-row['diff_v']/2),('OUT',row['ctrl_v'])]:
            forced &= bool(np.max(abs(voltage(node)[keep]-value))<1e-7)
    stress=[]
    for device in devices:
        terminals=[voltage(n) for n in device['nodes']]
        maximum=max(float(np.max(abs(a-b))) for a,b in itertools.combinations(terminals,2))
        stress.append(dict(name=device['name'],terminal_difference_max_v=maximum,passed=maximum<=1.95))
    results=[]
    for group in groups:
        i=group['start'];gm0=(currents[i+2]-currents[i])/(2*DELTA_V)
        gm_actual=(currents[i+5]-currents[i+3])/(2*DELTA_V)
        offset=-currents[i+1]/gm0 if gm0 else None
        passed=bool(math.isfinite(gm0) and math.isfinite(gm_actual) and gm0>1e-6 and gm_actual>1e-6 and
            offset is not None and math.isfinite(offset) and abs(offset)<.01)
        results.append(dict(group,gm_zero_s=gm0,gm_operating_s=gm_actual,input_offset_v=offset,
            zero_error_current_a=currents[i+1],operating_current_a=currents[i+4],passed=passed))
    return dict(passed=bool(rails and forced and all(s['passed'] for s in stress) and all(r['passed'] for r in results)),
        fixed_rails_passed=rails,forced_signals_passed=forced,points=results,thin_device_stress=stress,
        limits=dict(gm_min_s=1e-6,input_offset_abs_max_v=.01,thin_terminal_difference_max_v=1.95))


def stamp(qualification,stability,source,sources):
    return dict(qualification_manifest_sha256=digest(qualification/'manifest.json'),
        stability=str(stability.relative_to(ROOT)),stability_sha256=digest(stability),
        candidate_sha256=digest(source),sources=sources,producer_sha256=digest(Path(__file__)),
        simulator_provenance=provenance(),cm_guard_v=CM_GUARD_V,ctrl_guard_v=CTRL_GUARD_V,
        helpers={name:digest(ROOT/'scripts'/name) for name in ['screen_dll.py','qualify_dll_recovery.py']})


def pdk_library(qualification):
    q=json.loads((qualification/'manifest.json').read_text())
    task=next(t for t in q['tasks'] if t['spec']['kind']=='loop' and not t['fast_rc'])
    deck=qualification/task['id']/'bench.cir'
    if digest(deck)!=task['deck_sha256']:raise ValueError('Captured PDK reference fixture changed')
    found=re.findall(r'(?m)^\.lib "([^"\n]+)" \w+\s*$',deck.read_text())
    if len(found)!=1:raise ValueError('Native PDK binding is ambiguous')
    return found[0]


def fixture(root,process,temp,rows,devices,pdk):
    probes=sorted({'U','D','OUT','PB','VDDIO','VDDD'}|{n for d in devices for n in d['nodes'] if n!='0'})
    ramps=[]
    for col in range(3):
        values=[(row['cm_v']+row['diff_v']/2,row['cm_v']-row['diff_v']/2,row['ctrl_v'])[col] for row in rows]
        sequence=[(at,value) for i,value in enumerate(values) for at in [i*SLOT_NS,i*SLOT_NS+9.9]]
        sequence.append((len(rows)*SLOT_NS,values[-1]));ramps.append(stimulus(*zip(*sequence)))
    return (f'OpenLVDS observed OTA operating points {process}_{temp}\n.lib "{pdk}" {process}\n.include "{root}/library.spice"\n'
        f'.options device temp={temp}\n.options timeint method=gear reltol=1e-4 abstol=1e-12\n'
        'VA VDDIO 0 3.3\nVD VDDD 0 1.8\nIB PB 0 35u\nXB PB NB VDDIO 0 lvds_bias\n'
        f'VU U 0 {ramps[0]}\nVDIFF D 0 {ramps[1]}\nVFORCE OUT 0 {ramps[2]}\n'
        'XO U D OUT PB VDDIO VDDD 0 lvds_phase_ota\n.save i(VFORCE)\n'+
        f'.tran 5p {len(rows)*SLOT_NS}n 0 20p\n.print tran '+' '.join('V('+n+')' for n in probes)+'\n.end\n')


def prepare(qualification,stability):
    q,points,sources=native_points(qualification,stability)
    source=ROOT/q['identity']['full_models']['layout']/'candidate.spice'
    if digest(source)!=q['identity']['full_models']['source_sha256']:raise ValueError('OTA physical source changed')
    native=native_block(source.read_text(),'lvds_phase_ota');devices=thin_devices(native)
    library=native+'\n'+closure((qualification/'full.spice').read_text(),['lvds_bias'])
    identity=stamp(qualification,stability,source,sources)
    root=qualification/'ota_operating_points'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    root.mkdir(parents=True,exist_ok=True)
    if (root/'manifest.json').exists():
        saved=json.loads((root/'manifest.json').read_text())
        if saved['identity']!=identity or (root/'library.spice').read_text()!=library or saved['devices']!=devices:
            raise ValueError('Captured OTA operating-point inputs changed')
        return root
    (root/'library.spice').write_text(library);tasks=[]
    req=json.loads((qualification/'requirements.json').read_text())
    pdk=pdk_library(qualification)
    for process,temp in itertools.product(req['process_corners'],req['temperatures_c']):
        selected=[p for p in points if p['process']==process and p['temperature']==temp]
        groups,rows=grid(selected);name=f'{process}_{temp}';folder=root/name;folder.mkdir()
        text=fixture(root,process,temp,rows,devices,pdk)
        if bias_reference_count(text,library)!=1:raise ValueError('OTA operating fixture duplicates bias reference')
        ProbeNetwork(library).validate(text,{'U','D','OUT','PB','VDDIO','VDDD'}|{n for d in devices for n in d['nodes'] if n!='0'})
        (folder/'bench.cir').write_text(text)
        tasks.append(dict(id=name,groups=groups,rows=rows,deck_sha256=digest(folder/'bench.cir')))
    atomic(root/'manifest.json',dict(identity=identity,tasks=tasks,devices=devices,observed_points=points,
        library_sha256=digest(root/'library.spice'),qualified_phy=False,
        scope='Native-finger schematic OTA with audited extracted bias; correlated points from complete native loop evidence'))
    return root


def verify(path):
    path=path.resolve()
    root=path.parent;qualification=root.parent.parent;manifest=json.loads((root/'manifest.json').read_text())
    if not qualification.is_relative_to(ROOT/'build/diagnostics/dll_qualification'):raise ValueError('OTA evidence outside native qualification')
    identity=manifest['identity'];stability=ROOT/identity['stability']
    q,points,sources=native_points(qualification,stability);source=ROOT/q['identity']['full_models']['layout']/'candidate.spice'
    native=native_block(source.read_text(),'lvds_phase_ota')
    expected_library=native+'\n'+closure((qualification/'full.spice').read_text(),['lvds_bias'])
    report=json.loads(path.read_text())
    if (identity!=stamp(qualification,stability,source,sources) or manifest['observed_points']!=points or
        digest(root/'library.spice')!=manifest['library_sha256'] or (root/'library.spice').read_text()!=expected_library or
        manifest['devices']!=thin_devices(native) or not report['passed'] or
        report['manifest_sha256']!=digest(root/'manifest.json') or len(report['results'])!=len(manifest['tasks'])):
        raise ValueError('Failed or stale OTA operating evidence')
    expected={f'{p}_{t}' for p in json.loads((qualification/'requirements.json').read_text())['process_corners']
              for t in json.loads((qualification/'requirements.json').read_text())['temperatures_c']}
    if {t['id'] for t in manifest['tasks']}!=expected or len(manifest['tasks'])!=len(expected):raise ValueError('OTA PVT coverage incomplete')
    for task,result in zip(manifest['tasks'],report['results']):
        folder=root/task['id'];process,temp=task['id'].rsplit('_',1)
        groups,rows=grid([p for p in points if p['process']==process and p['temperature']==int(temp)])
        if task['groups']!=groups or task['rows']!=rows or task['deck_sha256']!=digest(folder/'bench.cir'):
            raise ValueError('OTA guarded input grid changed')
        if (folder/'bench.cir').read_text()!=fixture(root,process,int(temp),rows,manifest['devices'],pdk_library(qualification)):
            raise ValueError('OTA characterization PVT, rails or fixture changed')
        measured=analyze(folder/'bench.raw',groups,rows,manifest['devices'])
        if result['id']!=task['id'] or not result['passed'] or not measured['passed'] or result['measurement']!=measured:
            raise ValueError('OTA native-finger characterization failed reanalysis')
        if set(result['files'])!={'bench.cir','bench.raw','summary.json'}:raise ValueError('Missing OTA characterization artifacts')
        for name,value in result['files'].items():
            if digest(folder/name)!=value:raise ValueError('OTA characterization artifact changed')
    return report


def run(qualification,stability,jobs=6):
    qualification=qualification.resolve();stability=stability.resolve()
    if not qualification.is_relative_to(ROOT/'build/diagnostics/dll_qualification'):raise ValueError('Use an isolated native qualification')
    root=prepare(qualification,stability);manifest=json.loads((root/'manifest.json').read_text())
    if manifest['identity']['producer_sha256']!=digest(Path(__file__)) or digest(root/'library.spice')!=manifest['library_sha256']:
        raise ValueError('OTA operating producer or library changed')
    with (root/'.execution.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        def measure(task):
            folder=root/task['id'];deck=folder/'bench.cir';previous=folder/'summary.json'
            if digest(deck)!=task['deck_sha256']:raise ValueError('OTA fixture changed')
            if not previous.exists():
                with slot():
                    result=subprocess.run(command(folder/'ngspice.log',deck),cwd=folder,capture_output=True,text=True)
                (folder/'console.log').write_text(result.stdout+result.stderr);result.check_returncode()
                measurement=analyze(folder/'bench.raw',task['groups'],task['rows'],manifest['devices'])
                atomic(previous,dict(measurement=measurement,raw_sha256=digest(folder/'bench.raw'),deck_sha256=digest(deck)))
            recorded=json.loads(previous.read_text())
            if recorded['raw_sha256']!=digest(folder/'bench.raw') or recorded['deck_sha256']!=digest(deck):
                raise ValueError('OTA characterization waveform changed')
            measurement=analyze(folder/'bench.raw',task['groups'],task['rows'],manifest['devices'])
            if measurement!=recorded['measurement']:raise ValueError('OTA characterization analysis changed')
            print(task['id'],measurement['passed'],flush=True)
            return dict(id=task['id'],passed=measurement['passed'],measurement=measurement,
                files={name:digest(folder/name) for name in ['bench.cir','bench.raw','summary.json']})
        with ThreadPoolExecutor(max_workers=jobs) as pool:results=list(pool.map(measure,manifest['tasks']))
        atomic(root/'summary.json',dict(passed=all(r['passed'] for r in results),qualified_phy=False,
            manifest_sha256=digest(root/'manifest.json'),results=results))
        if all(r['passed'] for r in results):verify(root/'summary.json')
        print(root/'summary.json',flush=True);return 0 if all(r['passed'] for r in results) else 1


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('qualification',type=Path)
    p.add_argument('--stability',type=Path,required=True);p.add_argument('--jobs',type=int,choices=range(1,7),default=6)
    a=p.parse_args();return run(a.qualification,a.stability,a.jobs)


if __name__=='__main__':raise SystemExit(main())
