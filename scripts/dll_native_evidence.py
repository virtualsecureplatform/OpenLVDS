# SPDX-License-Identifier: GPL-3.0-only
"""Recheck complete native OTA DLL coverage and every captured measurement."""
import hashlib
import itertools
import json
from pathlib import Path
import re

from dll_campaign import bias_reference_count
from dll_measurements import read_wave
from dll_qualification_measurements import compare
from qualify_dll_candidate import validate, evaluate, phase_fixture, loop_fixture, screen_status
from verify_phase_detector import response_cases

ROOT=Path(__file__).resolve().parents[1]
FIELDS=('kind','process','temperature','mhz','duty','offset_ps','reference_slew_ps',
        'feedback_slew_ps','up','dn','step_mhz')


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def signature(spec,fast=False):
    return (fast,)+tuple(spec.get(k) for k in FIELDS)+(bool(spec.get('interruption')),)


def required_cases(requirements,captures=()):
    expected=set()
    def add(kind,process,temp,fast=False,**kw):
        expected.add(signature(dict(kind=kind,process=process,temperature=temp,**kw),fast))
    for p,t,o,sr,sf in response_cases(corners=True)+response_cases(slew_corners=True):
        add('phase',p,t,mhz=400,offset_ps=o,reference_slew_ps=sr,feedback_slew_ps=sf)
    for (p,t),mhz,o in itertools.product([('ss',0),('tt',25),('ff',0)],[390,410],[0,50,-50,150,-150,300,-300]):
        add('phase',p,t,mhz=mhz,offset_ps=o,reference_slew_ps=100,feedback_slew_ps=100)
    for p,t,up,dn in itertools.product(requirements['process_corners'],requirements['temperatures_c'],[0,1.8],[0,1.8]):
        add('logic',p,t,up=up,dn=dn)
    for p,t in itertools.product(requirements['process_corners'],requirements['temperatures_c']):
        add('loop',p,t,mhz=400,duty=.5)
    for (p,t),mhz,duty in itertools.product([('ss',0),('tt',25),('ff',0)],requirements['clock_test_mhz'],requirements['clock_duty']):
        add('loop',p,t,mhz=mhz,duty=duty)
    for capture in captures:add('loop','tt',25,mhz=400,duty=capture['duty'])
    for (p,t),target in itertools.product([('ss',0),('tt',25),('ff',0)],[390,410,None]):
        add('loop',p,t,mhz=400,duty=.5,step_mhz=target,interruption=target is None)
    add('loop','tt',25,fast=True,mhz=400,duty=.5)
    for (p,t),o in itertools.product([('ss',0),('tt',25),('ff',0)],[0,150,-150]):
        add('phase',p,t,fast=True,mhz=400,offset_ps=o,reference_slew_ps=100,feedback_slew_ps=100)
    return expected


def check_coverage(manifest,requirements):
    tasks=manifest['tasks'];actual=[signature(t['spec'],t['fast_rc']) for t in tasks]
    expected=required_cases(requirements,manifest['identity'].get('captured_clocks',[]))
    if len(set(actual))!=len(actual) or set(actual)!=expected:
        raise ValueError('Native DLL case coverage is incomplete, duplicated or unexpected')
    names={t['id'] for t in tasks}
    if len(names)!=len(tasks):raise ValueError('Duplicate native DLL task id')
    for task in tasks:
        spec=task['spec']
        if spec['kind']=='loop' and spec.get('architecture')!='averaged_pfd_ota':
            raise ValueError('Native DLL release requires the OTA architecture')
        if spec['kind']=='logic' and spec.get('expected') is not True:
            raise ValueError('Stuck detector fixture must require a fault')
    return {t['id']:t for t in tasks}


def check_fixture(root,manifest,task):
    spec=task['spec'];models=manifest['identity']['full_models']
    if spec['kind']=='loop':body,probes,stop,timing=loop_fixture(spec,models['observation_nodes'])
    else:body,probes,stop,timing=phase_fixture(spec,models['observation_nodes'])
    if task['aliases']!=probes or spec['stop_ns']!=stop or any(spec.get(k)!=v for k,v in timing.items()):
        raise ValueError('Native DLL probes or scoring windows changed')
    text=(root/task['id']/'bench.cir').read_text()
    pdk=re.search(r'(?m)^\.lib "([^"\n]+)" \S+$',text)
    if not pdk or '/'+json.loads((root/'requirements.json').read_text())['pdk_version']+'/' not in pdk[1]:
        raise ValueError('Native DLL PDK version changed')
    mode='fast' if task['fast_rc'] else 'full'
    expected=(f'OpenLVDS native DLL qualification {task["id"]}\n.lib "{pdk[1]}" {spec["process"]}\n'
        f'.include "{root}/{mode}.spice"\n.options device temp={spec["temperature"]}\n'
        '.options timeint method=gear reltol=1e-4 abstol=1e-12\n'
        'VA VDDIO 0 3.3\nVD VDDD 0 1.8\nIB PB 0 35u\n'+body+
        f'.save i(VA) i(VD)\n.tran 5p {stop}n 0 20p\n.print tran '+
        ' '.join('V('+node+')' for node in probes.values())+'\n.end\n')
    if text!=expected or digest(root/task['id']/'bench.cir')!=task['deck_sha256']:
        raise ValueError('Native DLL fixture changed')
    return mode


def verify(root):
    root=Path(root).resolve();manifest=json.loads((root/'manifest.json').read_text());validate(root,manifest)
    if not root.is_relative_to(ROOT/'build/diagnostics/dll_qualification'):
        raise ValueError('Native DLL evidence outside candidate directory')
    requirements=json.loads((root/'requirements.json').read_text())
    if digest(root/'requirements.json')!=digest(ROOT/'requirements.json'):
        raise ValueError('Native DLL requirements changed')
    tasks=check_coverage(manifest,requirements);summary=json.loads((root/'summary.json').read_text())
    if (not summary['passed'] or summary['manifest_sha256']!=digest(root/'manifest.json') or
        set(summary['tasks'])!=set(tasks) or any(v['status']!='passed' for v in summary['tasks'].values())):
        raise ValueError('Complete native DLL qualification has not passed')
    if screen_status(manifest)!='passed':raise ValueError('Native DLL architecture screen has not passed')
    checked=set();files={}
    for name,task in tasks.items():
        mode=check_fixture(root,manifest,task);signature_kind=(mode,task['spec']['kind'])
        if signature_kind not in checked:
            if bias_reference_count((root/name/'bench.cir').read_text(),(root/(mode+'.spice')).read_text())!=1:
                raise ValueError('Native DLL fixture duplicates bias reference')
            checked.add(signature_kind)
        folder=root/name;record=json.loads((folder/'summary.json').read_text())
        if (not record['passed'] or record['returncode']!=0 or record['task']!=name or
            record['deck_sha256']!=task['deck_sha256'] or
            digest(folder/'bench.cir.prn')!=record['waveform_sha256'] or digest(folder/'bench.raw')!=record['raw_sha256']):
            raise ValueError('Native DLL case failed or artifacts changed: '+name)
        measured=evaluate(root,task)
        if not measured['passed'] or measured!=record['metrics']:
            raise ValueError('Native DLL waveform reanalysis failed: '+name)
        files[name]=digest(folder/'summary.json')
    comparisons=[];pairs=manifest['comparisons']
    # Every approximate case needs exactly one corresponding full case.
    if {p['fast'] for p in pairs}!={t['id'] for t in tasks.values() if t['fast_rc']} or len(pairs)!=10:
        raise ValueError('Native DLL comparison coverage is incomplete')
    for pair in pairs:
        traces=[];a,b=(tasks[pair[n]] for n in ['full','fast'])
        if a['fast_rc'] or not b['fast_rc'] or signature(a['spec'])!=signature(b['spec']):
            raise ValueError('Native DLL comparison pairs differ')
        for task in [a,b]:
            wave,header=read_wave(root/task['id']/'bench.cir.prn')
            for alias,node in task['aliases'].items():header['V('+alias.upper()+')']=header['V('+node.upper()+')']
            traces.extend([wave,header])
        metrics=compare(*traces,list(a['aliases']),a['spec']['start_ns'],a['spec']['end_ns'])
        if not metrics['passed']:raise ValueError('Native DLL RC comparison failed')
        comparisons.append(dict(pair=pair,**metrics))
    if comparisons!=summary['dll_full_fast_comparisons']:
        raise ValueError('Native DLL comparison summary differs from waveforms')
    return dict(passed=True,manifest_sha256=digest(root/'manifest.json'),summary_sha256=digest(root/'summary.json'),
                case_reports=files,comparisons=comparisons)
