#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Compare stronger PMOS loads with a completed unclamped original-tail static control."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import re
import subprocess

import numpy as np
from dll_campaign import atomic
from dll_measurements import read_wave
from qualify_receiver_components import static_metrics,rebind
from receiver_decision_load_experiment import source_variant,strengthen_loads,CODE as FACTORY_CODE,TOP
from receiver_static_diagnosis import capture_manifest,samples
from rx_candidate_aperture import lease
from spice_engine import command,engine,provenance
from spice_probes import ProbeNetwork
from spice_scope import closure_hash

ROOT=Path(__file__).resolve().parents[1]
CODE=sorted(set(FACTORY_CODE)|{'receiver_decision_load_static.py','receiver_static_diagnosis.py',
    'qualify_receiver_components.py','dll_measurements.py','spice_probes.py','spice_scope.py',
    'rx_candidate_aperture.py','spice_slots.py','spice_engine.py','run_ngspice.py'})


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def observed(deck,parent,root):
    deck=rebind(deck,parent,root);matches=list(re.finditer(r'(?im)^\.print tran[^\n]*$',deck))
    if len(matches)!=1:raise ValueError('Expected the original static observation command')
    nodes=['XR:XCORE:'+leaf for leaf in ['CL','CT','NBC']]
    ProbeNetwork((parent/'source.spice').read_text()).validate(deck,nodes)
    at=matches[0].end()
    return deck[:at]+' '+' '.join('V('+n+')' for n in nodes)+deck[at:]


def measured(wave,headers,headroom=False):
    if (wave.ndim!=2 or wave.shape[1]<5 or len(wave)<2 or
            any(headers.get(name)!=column for name,column in [('TIME',1),('V(P)',2),('V(N)',3),('V(Q)',4)]) or
            not np.isfinite(wave).all() or wave[0,1]>1e-15 or wave[-1,1]<144e-9-1e-12 or
            np.any(np.diff(wave[:,1])<=0)):
        raise ValueError('Incomplete original 144 ns static waveform')
    if headroom and any('V(XR:XCORE:'+n+')' not in headers for n in ['CL','CT','NBC']):
        raise ValueError('Missing declared headroom observations')
    return dict(metrics=static_metrics(wave),samples=samples(wave,headers))


def prepare(parent):
    if engine()!='ngspice' or not parent.is_relative_to(ROOT/'build/diagnostics/receiver_static_diagnosis'):
        raise ValueError('Use a completed standard unclamped static control')
    manifest=json.loads((parent/'manifest.json').read_text());control=json.loads((parent/'summary.json').read_text())
    if (control.get('diagnostic_complete') is not True or control['manifest_sha256']!=digest(parent/'manifest.json') or
            control['waveform_sha256']!=digest(parent/'bench.cir.prn')):
        raise ValueError('Static control is incomplete or changed')
    if provenance()!=manifest['identity']['simulator_provenance']:raise ValueError('Static runtime changed')
    for name,sha in manifest['files'].items():
        if digest(parent/name)!=sha:raise ValueError('Static control fixture changed')
    for name,sha in manifest['identity']['inputs'].items():
        if digest(ROOT/name)!=sha:raise ValueError('Static control inputs changed')
    for name,sha in manifest['identity']['code'].items():
        if digest(ROOT/'scripts'/name)!=sha:raise ValueError('Static control producer changed')
    expected=source_variant((ROOT/'analog/openlvds.spice').read_text(),False)
    if closure_hash((parent/'source.spice').read_text(),TOP)!=closure_hash(expected,TOP):
        raise ValueError('Static control is not the exact original-tail unclamped factory')
    wave,headers=read_wave(parent/'bench.cir.prn');remeasured=measured(wave,headers)
    if remeasured!=control['clamp_removed']:
        raise ValueError('Static control measurements differ from actual waveform')
    paths=[parent/n for n in ['manifest.json','source.spice','bench.cir','bench.cir.prn','summary.json']]+[ROOT/'analog/openlvds.spice',ROOT/'requirements.json']
    identity=dict(parent=str(parent.relative_to(ROOT)),operation='Only XCD/XCM PMOS W8 to W32; original tail W64 and input pair W8 unchanged',
        simulator_provenance=provenance(),code={n:digest(ROOT/'scripts'/n) for n in sorted(set(CODE)|set(manifest['identity']['code']))},
        inputs=dict(manifest['identity']['inputs'],**{str(p.relative_to(ROOT)):digest(p) for p in paths}))
    root=ROOT/'build/diagnostics/receiver_decision_load_static'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    root.mkdir(parents=True,exist_ok=True)
    for name,text in [('source.spice',strengthen_loads((parent/'source.spice').read_text())),('bench.cir',observed((parent/'bench.cir').read_text(),parent,root))]:
        path=root/name
        if path.exists() and path.read_text()!=text:raise ValueError('Static candidate fixture changed')
        if not path.exists():path.write_text(text)
    capture_manifest(root/'manifest.json',dict(identity=identity,qualified_phy=False,
        files={n:digest(root/n) for n in ['source.spice','bench.cir']}))
    return root


def run(root,wait_slot=None):
    if not root.is_relative_to(ROOT/'build/diagnostics/receiver_decision_load_static'):
        raise ValueError('Use a prepared decision-load static experiment')
    manifest=json.loads((root/'manifest.json').read_text());identity=manifest['identity'];manifest_sha=digest(root/'manifest.json')
    def unchanged():
        if digest(root/'manifest.json')!=manifest_sha or provenance()!=identity['simulator_provenance']:
            raise ValueError('Static candidate manifest/runtime changed')
        if any(digest(ROOT/n)!=sha for n,sha in identity['inputs'].items()) or any(
                digest(ROOT/'scripts'/n)!=sha for n,sha in identity['code'].items()):
            raise ValueError('Static candidate input or producer changed')
        if any(digest(root/n)!=sha for n,sha in manifest['files'].items()):raise ValueError('Static candidate fixture changed')
        parent=ROOT/identity['parent']
        if ((root/'source.spice').read_text()!=strengthen_loads((parent/'source.spice').read_text()) or
                (root/'bench.cir').read_text()!=observed((parent/'bench.cir').read_text(),parent,root)):
            raise ValueError('Static candidate differs from its one-factor intervention')
    with (root/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        unchanged();report=root/'summary.json';cached=json.loads(report.read_text()) if report.exists() else None
        try:
            if cached is None:
                if any((root/name).exists() for name in ['bench.raw','bench.cir.prn','ngspice.log']):
                    raise ValueError('Incomplete prior execution retained; prepare a fresh experiment before retrying')
                policy=dict(manifest_sha256=manifest_sha,wait_slot=wait_slot,global_slot_budget=6,producer_sha256=digest(Path(__file__)))
                key=hashlib.sha256(json.dumps(policy,sort_keys=True).encode()).hexdigest()[:16]
                folder=root/'execution_scheduling'/key;folder.mkdir(parents=True,exist_ok=True)
                capture_manifest(folder/'manifest.json',policy)
                atomic(root/'execution.json',dict(status='waiting_for_slot',qualified_phy=False))
                with lease(wait_slot):
                    unchanged();atomic(root/'execution.json',dict(status='running',qualified_phy=False))
                    process=subprocess.run(command(root/'ngspice.log',root/'bench.cir'),cwd=root,capture_output=True,text=True)
                (root/'console.log').write_text(process.stdout+process.stderr);process.check_returncode()
            elif digest(root/'bench.cir.prn')!=cached['waveform_sha256']:
                raise ValueError('Static candidate waveform changed')
            wave,headers=read_wave(root/'bench.cir.prn');candidate=measured(wave,headers,True)
            parent=ROOT/identity['parent'];base=json.loads((parent/'summary.json').read_text())['clamp_removed']
            result=dict(diagnostic_complete=True,qualified_phy=False,manifest_sha256=manifest_sha,
                waveform_sha256=digest(root/'bench.cir.prn'),standard_tail_control=base,
                stronger_pmos_load=candidate,
                scope='One-factor PMOS load change versus completed standard unclamped W64-tail control; original 12 static samples only; no native or PHY qualification')
            unchanged()
            if cached is not None and cached!=result:raise ValueError('Static candidate analysis differs from actual waveform')
            atomic(report,result);atomic(root/'execution.json',dict(status='completed',qualified_phy=False,passed=result['stronger_pmos_load']['metrics']['passed']))
        except Exception as error:
            atomic(root/'execution.json',dict(status='held_for_diagnosis',qualified_phy=False,error=str(error)));raise
    print(root/'summary.json',flush=True)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=['prepare','run']);parser.add_argument('artifact',type=Path)
    parser.add_argument('--wait-slot',type=int,choices=range(6));args=parser.parse_args()
    if args.action=='prepare':print(prepare(args.artifact.resolve()),flush=True)
    else:run(args.artifact.resolve(),args.wait_slot)
