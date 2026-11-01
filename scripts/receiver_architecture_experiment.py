#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Screen bounded receiver bias and 3.3 V decision-stage architectures."""
from receiver_architectures import transform, VARIANTS
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import re
import subprocess

from dll_campaign import atomic,text_block
from dll_measurements import read_wave
from layout import circuits
from qualify_receiver_components import rebind
from receiver_decision_load_static import measured
from receiver_static_diagnosis import capture_manifest
from receiver_tail_headroom_experiment import source_variant as reduced_source
import receiver_tail_headroom_static as control
from rx_candidate_aperture import lease
from spice_engine import command,engine,provenance
from spice_library import replace
from spice_scope import closure_hash

ROOT=Path(__file__).resolve().parents[1]
TOP='openlvds_receiver_core'

CODE=['receiver_architecture_experiment.py','receiver_architectures.py','receiver_lvt_pair_experiment.py','receiver_decision_load_static.py',
    'receiver_decision_load_experiment.py','receiver_tail_headroom_experiment.py','receiver_tail_headroom_static.py',
    'receiver_static_diagnosis.py','rx_candidate_aperture.py','spice_slots.py','spice_engine.py','run_ngspice.py',
    'spice_scope.py','spice_library.py','layout.py','dll_measurements.py','dll_campaign.py','qualify_receiver_components.py']


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def source_variant(source,modified=True,variant='lvt'):
    base=reduced_source(source,True)
    return transform(base,variant) if modified else base


def prepare(parent,variant):
    if variant not in VARIANTS:raise ValueError('Unknown receiver architecture')
    if engine()!='ngspice' or not parent.is_relative_to(ROOT/'build/diagnostics/receiver_tail_headroom_static'):
        raise ValueError('Use a completed reduced-tail source static control')
    if not (parent/'summary.json').exists():raise ValueError('Complete the reduced-tail control before preparation')
    control.run(parent)  # Cached only: checks all scientific context and actual measurements.
    manifest=json.loads((parent/'manifest.json').read_text());report=json.loads((parent/'summary.json').read_text())
    wave,headers=read_wave(parent/'bench.cir.prn');base=measured(wave,headers,True)
    if (report['manifest_sha256']!=digest(parent/'manifest.json') or report['waveform_sha256']!=digest(parent/'bench.cir.prn') or
            base!=report['reduced_decision_tail'] or base['metrics']['passed'] is not True or
            closure_hash((parent/'source.spice').read_text(),TOP)!=closure_hash(source_variant((ROOT/'analog/openlvds.spice').read_text(),False),TOP)):
        raise ValueError('Reduced-tail control is changed, failed or a different source')
    paths=[parent/n for n in ['manifest.json','summary.json','source.spice','bench.cir','bench.cir.prn']]+[ROOT/'analog/openlvds.spice',ROOT/'requirements.json']
    identity=dict(parent=str(parent.relative_to(ROOT)),architecture_variant=variant,
        operation='Bounded receiver architecture experiment; fixed input frontend and public interface',
        simulator_provenance=provenance(),
        code={n:digest(ROOT/'scripts'/n) for n in sorted(set(CODE)|set(manifest['identity']['code']))},
        inputs=dict(manifest['identity']['inputs'],**{str(p.relative_to(ROOT)):digest(p) for p in paths}))
    root=ROOT/'build/diagnostics/receiver_architecture_static'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    root.mkdir(parents=True,exist_ok=True)
    for name,text in [('source.spice',transform((parent/'source.spice').read_text(),variant)),('bench.cir',rebind((parent/'bench.cir').read_text(),parent,root))]:
        path=root/name
        if path.exists() and path.read_text()!=text:raise ValueError('Low-threshold decision pair fixture changed')
        if not path.exists():path.write_text(text)
    capture_manifest(root/'manifest.json',dict(identity=identity,qualified_phy=False,files={n:digest(root/n) for n in ['source.spice','bench.cir']}))
    return root


def run(root,wait_slot=None):
    if not root.is_relative_to(ROOT/'build/diagnostics/receiver_architecture_static'):
        raise ValueError('Use a prepared low-threshold decision pair experiment')
    manifest=json.loads((root/'manifest.json').read_text());identity=manifest['identity'];variant=identity['architecture_variant'];stamp=digest(root/'manifest.json')
    def unchanged():
        if (digest(root/'manifest.json')!=stamp or provenance()!=identity['simulator_provenance'] or identity['architecture_variant'] not in VARIANTS or
                any(digest(ROOT/n)!=sha for n,sha in identity['inputs'].items()) or
                any(digest(ROOT/'scripts'/n)!=sha for n,sha in identity['code'].items()) or
                any(digest(root/n)!=sha for n,sha in manifest['files'].items())):
            raise ValueError('Low-threshold decision pair context changed')
        parent=ROOT/identity['parent']
        if ((root/'source.spice').read_text()!=transform((parent/'source.spice').read_text(),variant) or
                (root/'bench.cir').read_text()!=rebind((parent/'bench.cir').read_text(),parent,root)):
            raise ValueError('Low-threshold decision pair differs from the two-model intervention')
    with (root/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);unchanged()
        cached=json.loads((root/'summary.json').read_text()) if (root/'summary.json').exists() else None
        try:
            if cached is None:
                if any((root/n).exists() for n in ['bench.raw','ngspice.log','bench.cir.prn']):
                    raise ValueError('Incomplete prior execution retained; use a fresh retry context')
                policy=dict(manifest_sha256=stamp,wait_slot=wait_slot,global_slot_budget=6,producer_sha256=digest(Path(__file__)))
                folder=root/'execution_scheduling'/hashlib.sha256(json.dumps(policy,sort_keys=True).encode()).hexdigest()[:16]
                folder.mkdir(parents=True,exist_ok=True);capture_manifest(folder/'manifest.json',policy)
                atomic(root/'execution.json',dict(status='waiting_for_slot',qualified_phy=False))
                with lease(wait_slot):
                    unchanged();atomic(root/'execution.json',dict(status='running',qualified_phy=False))
                    process=subprocess.run(command(root/'ngspice.log',root/'bench.cir'),cwd=root,capture_output=True,text=True)
                (root/'console.log').write_text(process.stdout+process.stderr);process.check_returncode()
            elif digest(root/'bench.cir.prn')!=cached['waveform_sha256']:raise ValueError('Low-threshold decision pair waveform changed')
            unchanged();wave,headers=read_wave(root/'bench.cir.prn');candidate=measured(wave,headers,True)
            parent=ROOT/identity['parent'];base=json.loads((parent/'summary.json').read_text())['reduced_decision_tail']
            result=dict(diagnostic_complete=True,qualified_phy=False,manifest_sha256=stamp,waveform_sha256=digest(root/'bench.cir.prn'),
                reduced_tail_control=base,architecture=candidate,
                scope='Receiver architecture source DC only; original twelve fixed-supply samples; no dynamic, stress, native or PHY admission')
            if cached is not None and cached!=result:raise ValueError('Low-threshold decision pair measurements differ from actual waveform')
            atomic(root/'summary.json',result);atomic(root/'execution.json',dict(status='completed',qualified_phy=False,passed=candidate['metrics']['passed']))
        except Exception as error:
            atomic(root/'execution.json',dict(status='held_for_diagnosis',qualified_phy=False,error=str(error)));raise
    print(root/'summary.json',flush=True)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=['prepare','run']);parser.add_argument('artifact',type=Path)
    parser.add_argument('--variant',choices=VARIANTS);parser.add_argument('--wait-slot',type=int,choices=range(6));args=parser.parse_args()
    if args.action=='prepare':print(prepare(args.artifact.resolve(),args.variant),flush=True)
    else:run(args.artifact.resolve(),args.wait_slot)
