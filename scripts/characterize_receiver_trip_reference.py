#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Measure unloaded restoring-inverter trip replicas at one captured fixed-supply PVT."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import re
import subprocess
import numpy as np

from dll_campaign import text_block
from dll_measurements import read_wave
from layout import circuits,flatten,schematic_text
from receiver_static_diagnosis import capture_manifest
from spice_dispatch import lease
from spice_engine import command,provenance

ROOT=Path(__file__).resolve().parents[1]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()


def characterize(parent):
    if not parent.is_relative_to(ROOT/'build/diagnostics/receiver_differential_restore_static'):
        raise ValueError('Use a completed differential-restoration source case')
    source=parent/'candidate.spice'; report=parent/'summary.json'; wave=parent/'bench.cir.prn'; deck=parent/'bench.cir'
    saved=json.loads(report.read_text())
    if saved['waveform_sha256']!=sha(wave):raise ValueError('Parent waveform changed')
    definitions=circuits(source.read_text()); rows={r[0]:r for r in definitions['openlvds_receiver_core'][1]}
    small=rows['XIB0'][2];large=rows['XTRACK'][2]
    if small!='lvds_inv18_drive' or large!='lvds_rx_track_strong':raise ValueError('Require the measured standard-inverter restoration family')
    parent_deck=deck.read_text(); libs=re.findall(r'(?im)^\.lib[^\n]+',parent_deck)
    temps=re.findall(r'(?im)^\.options device temp=[^\n]+',parent_deck)
    if len(libs)!=1 or len(temps)!=1 or 'VDIG VDDD 0 1.8' not in parent_deck:raise ValueError('Unexpected captured supply/model/temperature fixture')
    identity=dict(parent=str(parent.relative_to(ROOT)),inputs={str(p.relative_to(ROOT)):sha(p) for p in [source,report,wave,deck,parent.parent/'manifest.json']},
        code={n:sha(ROOT/'scripts'/n) for n in [Path(__file__).name,'layout.py','dll_campaign.py','dll_measurements.py','spice_dispatch.py','spice_engine.py','receiver_static_diagnosis.py']},
        simulator_provenance=provenance(),scope='Isolated unloaded diode-connected trip measurements at the captured fixed 1.8 V supply and one PVT. Original whole-width helpers and their exact physical finger equivalents. One ns transient starts from the DC operating point. No supply sweep, amplifier, source sensitivity, native transport or PHY admission.')
    out=ROOT/'build/diagnostics/receiver_trip_reference'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16];out.mkdir(parents=True,exist_ok=True)
    text='* Exact whole-width and physical-finger helper definitions\n'+text_block(source.read_text(),small)+'\n'+text_block(source.read_text(),large)+'\n'
    for helper in [small,large]:
        ports,devices=flatten(definitions,helper)
        text+=schematic_text(helper+'_fingers',ports,devices)+'\n'
    bench='OpenLVDS isolated trip-reference diagnosis\n'+libs[0]+'\n'+temps[0]+'\n.options method=gear reltol=1e-4 abstol=1e-12\n'
    bench+=f'.include "{out}/source.spice"\nVDIG VDDD 0 1.8\n'
    names=['first_whole','reference_whole','first_fingers','reference_fingers']
    for name,helper in zip(names,[small,large,small+'_fingers',large+'_fingers'],strict=True):bench+=f'X{name} {name} {name} VDDD 0 {helper}\n'
    bench+='.tran 10p 1n 0 1p\n.print tran '+' '.join('V('+n+')' for n in names)+'\n.end\n'
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        for name,value in [('source.spice',text),('bench.cir',bench)]:
            p=out/name
            if p.exists() and p.read_text()!=value:raise ValueError('Retain changed trip diagnostic')
            if not p.exists():p.write_text(value)
        capture_manifest(out/'manifest.json',dict(identity=identity,files={n:sha(out/n) for n in ['source.spice','bench.cir']},qualified_phy=False))
        def unchanged():
            if provenance()!=identity['simulator_provenance'] or any(sha(ROOT/n)!=h for n,h in identity['inputs'].items()) or any(sha(ROOT/'scripts'/n)!=h for n,h in identity['code'].items()):raise ValueError('Trip diagnostic context changed')
        unchanged()
        if not (out/'summary.json').exists():
            if any((out/n).exists() for n in ['bench.raw','bench.cir.prn','ngspice.log']):raise ValueError('Retain partial trip measurement')
            with lease(ROOT,priority=0,label='receiver_trip_reference_diagnosis'):
                unchanged();p=subprocess.run(command(out/'ngspice.log',out/'bench.cir'),cwd=out,capture_output=True,text=True)
            (out/'console.log').write_text(p.stdout+p.stderr);p.check_returncode()
        w,h=read_wave(out/'bench.cir.prn')
        if not np.isfinite(w).all() or np.any(np.diff(w[:,1])<=0) or w[-1,1]<1e-9-1e-12:raise ValueError('Incomplete trip diagnostic trace')
        values={n:float(w[-1,h['V('+n.upper()+')']]) for n in names}
        result=dict(identity=identity,trip_v=values,whole_reference_minus_first_v=values['reference_whole']-values['first_whole'],finger_reference_minus_first_v=values['reference_fingers']-values['first_fingers'],waveform_sha256=sha(out/'bench.cir.prn'),manifest_sha256=sha(out/'manifest.json'),qualified_phy=False)
        unchanged();capture_manifest(out/'summary.json',result)
    return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('parent',type=Path);a=p.parse_args()
    print(characterize(a.parent.resolve())/'summary.json',flush=True)
