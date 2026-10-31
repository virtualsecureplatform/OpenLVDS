#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Screen an exact OTA candidate source before building its native qualification.

The analog DLL, including its delay line, uses native-finger schematic devices.
PFD and bias retain the audited extracted networks. This is diagnostic evidence;
all physical and native electrical gates remain mandatory.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import json
from pathlib import Path

from benchmark_exact_dll import candidate
import dll_campaign as campaign
from dll_design import native_block
from dll_measurements import loop, read_wave
from ota_operating_points import pdk_library
from qualify_dll_candidate import CODE, loop_fixture
from spice_engine import engine, provenance
from spice_library import replace
from spice_probes import ProbeNetwork
from spice_slots import slot

ROOT=Path(__file__).resolve().parents[1]
VARIANT='ota_w8_c4'


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def producer_code():
    return {name:digest(ROOT/'scripts'/name) for name in set(CODE)|{
        Path(__file__).name,'benchmark_exact_dll.py','ota_operating_points.py','exact_rc_candidate.py'}}


def source_library(source, full):
    # Use the submitted source as a whole: do not silently restore an old monitor.
    result=replace(full,'openlvds_dll_analog',native_block(source,'openlvds_dll_analog'))
    for name in ['openlvds_dll_core','openlvds_dll']:
        result=replace(result,name,campaign.text_block(source,name))
    return result


def prepare(source_path, reference, layout):
    if engine()!='ngspice':raise ValueError('Use the pinned --ngspice environment')
    if not all(p.is_relative_to(ROOT) for p in [source_path,reference,layout]):
        raise ValueError('All inputs must reside in OpenLVDS')
    manifest=json.loads((reference/'manifest.json').read_text())
    full,_=candidate(layout,reference,manifest)
    source=source_path.read_text();library=source_library(source,full)
    identity=dict(code=campaign.dependencies(),producer_code=producer_code(),simulator_provenance=provenance(),
        source_sha256=digest(source_path),full_library_sha256=hashlib.sha256(library.encode()).hexdigest(),
        reference=str(reference.relative_to(ROOT)),reference_manifest_sha256=digest(reference/'manifest.json'),
        layout=str(layout.relative_to(ROOT)),layout_manifest_sha256=digest(layout/'manifest.json'),
        requirements_sha256=digest(reference/'requirements.json'))
    root=ROOT/'build/diagnostics/dll_architecture'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    if (root/'manifest.json').exists():return root
    root.mkdir(parents=True,exist_ok=True);inputs=root/'inputs';inputs.mkdir(exist_ok=True)
    (inputs/(VARIANT+'.spice')).write_text(source)
    (inputs/'requirements.json').write_bytes((reference/'requirements.json').read_bytes())
    for name in identity['producer_code']:
        destination=inputs/'scripts'/name;destination.parent.mkdir(exist_ok=True);destination.write_bytes((ROOT/'scripts'/name).read_bytes())
    pdk=pdk_library(reference);tasks=[]
    for corner,temp in [('ss',0),('tt',25),('ff',0)]:
        name=f'{VARIANT}_loop_{corner}_{temp}';folder=root/name;folder.mkdir(exist_ok=True)
        fixture=dict(kind='loop',architecture='averaged_pfd_ota',mhz=400,duty=.5)
        body,probes,_,_=loop_fixture(fixture)
        # Stop before the native stage's later marker; retain its startup/loads.
        deck=(f'OpenLVDS source-specific OTA architecture screen {name}\n.lib "{pdk}" {corner}\n'
            f'.include "{folder}/library.spice"\n.options device temp={temp}\n'
            '.options timeint method=gear reltol=1e-4 abstol=1e-12\n'
            'VA VDDIO 0 3.3\nVD VDDD 0 1.8\nIB PB 0 35u\n'+body+
            '\n.save i(VA) i(VD)\n.tran 5p 1500n 0 20p\n.print tran '+
            ' '.join('V('+n+')' for n in probes.values())+'\n.end\n')
        if campaign.bias_reference_count(deck,library)!=1:raise ValueError('Duplicate bias reference')
        ProbeNetwork(library).validate(deck,probes.values())
        (folder/'library.spice').write_text(library);(folder/'bench.cir').write_text(deck)
        spec=dict(kind='loop',variant=VARIANT,architecture='averaged_pfd_ota',corner=corner,temp=temp,
                  mhz=400,stop_ns=1500,tops=['openlvds_dll'])
        tasks.append(dict(id=name,spec=spec,aliases=probes,needs=[],
            files={n:digest(folder/n) for n in ['library.spice','bench.cir']}))
    campaign.atomic(root/'manifest.json',dict(identity=identity,tasks=tasks,diagnostic=True,qualified=False,
        analog_view='Native-finger schematic DLL and delay; extracted PFD and bias'))
    campaign.atomic(root/'state.json',dict(status='prepared',tasks={t['id']:dict(status='pending') for t in tasks}))
    return root


def validate(root,manifest):
    identity=manifest['identity']
    if identity['producer_code']!=producer_code():raise ValueError('Screen producer changed')
    if digest(root/'inputs'/(VARIANT+'.spice'))!=identity['source_sha256']:
        raise ValueError('Screen source changed')
    for task in manifest['tasks']:
        campaign.validate(root,manifest,task)
        if digest(root/task['id']/'library.spice')!=identity['full_library_sha256']:
            raise ValueError('Screen library changed')


def run(root,jobs):
    with (root/'.source_screen.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        manifest=json.loads((root/'manifest.json').read_text());validate(root,manifest)
        state=dict(status='running',tasks={t['id']:dict(status='pending') for t in manifest['tasks']})
        campaign.atomic(root/'state.json',state)
        def execute(task):
            folder=root/task['id'];path=folder/'summary.json'
            if path.exists():
                result=json.loads(path.read_text())
                if result.get('input_files')!=task['files'] or digest(folder/'bench.cir.prn')!=result.get('waveform_sha256'):
                    raise ValueError('Captured screen evidence changed')
                wave,header=read_wave(folder/'bench.cir.prn')
                for alias,node in task['aliases'].items():header['V('+alias.upper()+')']=header['V('+node.upper()+')']
                return dict(result,**loop(wave,header,400,'averaged_pfd_ota'))
            campaign.atomic(folder/'execution.json',dict(status='waiting_for_slot'))
            with slot():
                campaign.atomic(folder/'execution.json',dict(status='running'))
                return campaign.execute(root,task)
        with ThreadPoolExecutor(max_workers=jobs) as pool:
            futures={t['id']:pool.submit(execute,t) for t in manifest['tasks']}
            for name,future in futures.items():
                result=future.result();state['tasks'][name]=dict(status='passed' if result['passed'] else 'failed')
                campaign.atomic(root/'state.json',state)
        validate(root,manifest)
        passed=all(t['status']=='passed' for t in state['tasks'].values())
        state['status']='completed' if passed else 'completed_with_failures'
        campaign.atomic(root/'state.json',state)
        campaign.atomic(root/'summary.json',dict(passed=passed,diagnostic=True,qualified_phy=False,tasks=state['tasks']))
    return root


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run'])
    p.add_argument('path',type=Path);p.add_argument('--reference',type=Path);p.add_argument('--layout',type=Path)
    p.add_argument('--jobs',type=int,choices=range(1,7),default=2);a=p.parse_args()
    if a.action=='prepare':
        if not a.reference or not a.layout:p.error('prepare requires --reference and --layout')
        root=prepare(a.path.resolve(),a.reference.resolve(),a.layout.resolve())
    else:root=run(a.path.resolve(),a.jobs)
    print(root,flush=True)


if __name__=='__main__':main()
