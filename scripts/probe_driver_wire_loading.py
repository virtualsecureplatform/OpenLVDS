#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Diagnostic ideal-wire control retaining every extracted PDK device parameter."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path

from audit_rc import collapse
import observe_compact_driver_loop as observer
import probe_driver_compact_native as pilot
from dll_campaign import atomic,text_block
from receiver_static_diagnosis import capture_manifest
from spice_dispatch import lease
from spice_engine import command,provenance
from spice_library import replace
from spice_probes import ProbeNetwork
import subprocess

ROOT=Path(__file__).resolve().parents[1]
sha=observer.sha


def ideal_wire_core(native,audited):
    expected=collapse(text_block(native,observer.assembly.TOP)).strip()
    body=text_block(audited,observer.assembly.TOP)
    if expected!=body.strip(): raise ValueError('Ideal-wire model differs from audited native collapse')
    if any(line.split() and line.split()[0][0].lower() in ['r','c'] for line in body.splitlines()):
        raise ValueError('Unexpected remaining numeric wire R/C')
    return replace(native,observer.assembly.TOP,body)


def prepare(observation):
    om=observer.bound(observation);oi=om['identity'];parent=ROOT/oi['parent'];m=pilot.bound(parent)
    extraction=ROOT/m['identity']['extraction'];r=json.loads((extraction/'summary.json').read_text())
    audited=extraction/'wire_collapsed.spice'
    if r.get('passed') is not True or r['rc_audit']['passed'] is not True or sha(audited)!=r['files'][str(audited.relative_to(ROOT))]:
        raise ValueError('Require original independently audited wire-collapsed device network')
    model=ideal_wire_core((parent/'tt_25_negative_op/source.spice').read_text(),audited.read_text())
    rows=[];paths=[parent/'manifest.json',observation/'manifest.json',extraction/'summary.json',audited]
    for op in pilot.reference.shape.CASES:
        folder=parent/('tt_25_'+op);row=json.loads((folder/'summary.json').read_text())
        if (row['returncode']!=0 or row['error'] is not None or row['manifest_sha256']!=sha(parent/'manifest.json') or
                any(sha(folder/n)!=h for n,h in row['files'].items()) or
                pilot.measure(folder)!=(row['metrics'],row['initial_dc'])):
            raise ValueError('Require completed native TT25 control traces')
        rows.append(row);paths += [folder/n for n in [*row['files'],'summary.json','source.spice','bench.cir']]
    inputs=dict(oi['inputs']);inputs.update({str(p.relative_to(ROOT)):sha(p) for p in paths})
    code=dict(oi['code']);code.update({n:sha(ROOT/'scripts'/n) for n in ['probe_driver_wire_loading.py','audit_rc.py']})
    identity=dict(observation=str(observation.relative_to(ROOT)),parent=str(parent.relative_to(ROOT)),inputs=inputs,
        code=code,simulator=provenance(),scope='Two TT25 ideal-wire diagnostics, both initial polarities. '
        'Only extracted numeric interconnect resistors are shorted and numeric parasitic '
        'capacitors removed, using the already audited wire-collapsed network. Every '
        'extracted MOS, physical finger W/L/junction parameter and intentional PDK '
        'resistor/MIM device retained. Original source bias, rails, reference, load and '
        'complete 80 ns/1 ps stimulus unchanged. Separates routing loading from native '
        'device geometry. The ideal wires are not hardware, an RC approximation for '
        'selection, native qualification or PHY admission.')
    out=ROOT/'build/diagnostics/driver_wire_loading_control'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=True);tasks=[]
    with (out/'.preparation.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        for op in pilot.reference.shape.CASES:
            old=parent/('tt_25_'+op);folder=out/op;folder.mkdir(exist_ok=True)
            deck=pilot.fixture((old/'bench.cir').read_text(),old,folder)
            ProbeNetwork(model).validate(deck,['D','P','N'])
            for name,body in [('source.spice',model),('bench.cir',deck)]:
                path=folder/name
                if path.exists() and path.read_text()!=body: raise ValueError('Prepared ideal-wire control changed')
                if not path.exists():path.write_text(body)
            tasks.append(dict(id=op,files={n:sha(folder/n) for n in ['source.spice','bench.cir']}))
        capture_manifest(out/'manifest.json',dict(identity=identity,tasks=tasks,qualified_phy=False))
        capture_manifest(out/'native_reference.json',dict(results=rows,qualified_phy=False))
    return out


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    if (not out.is_relative_to(ROOT/'build/diagnostics/driver_wire_loading_control') or
            out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16] or
            [t['id'] for t in m['tasks']]!=pilot.reference.shape.CASES or provenance()!=i['simulator'] or
            any(sha(ROOT/n)!=h for n,h in i['inputs'].items()) or
            any(sha(ROOT/'scripts'/n)!=h for n,h in i['code'].items()) or
            any(sha(out/t['id']/n)!=h for t in m['tasks'] for n,h in t['files'].items())):
        raise ValueError('Ideal-wire diagnostic context changed')
    return m


def run(out):
    m=bound(out);stamp=sha(out/'manifest.json')
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists() or any((out/t['id']/'bench.raw').exists() for t in m['tasks']):
            raise ValueError('Prior or partial ideal-wire diagnostic retained')
        rows=[]
        for task in m['tasks']:
            folder=out/task['id'];metrics=dc=None;error=None
            atomic(out/'state.json',dict(status='waiting_'+task['id'],qualified_phy=False))
            with lease(ROOT,priority=2,label='driver_ideal_wire_'+task['id']):
                bound(out);atomic(out/'state.json',dict(status='running_'+task['id'],qualified_phy=False))
                result=subprocess.run(command(folder/'ngspice.log',folder/'bench.cir'),cwd=folder,capture_output=True,text=True)
            (folder/'console.log').write_text(result.stdout+result.stderr);bound(out)
            try:result.check_returncode();metrics,dc=pilot.measure(folder)
            except Exception as caught:error=str(caught)
            row=dict(case=task['id'],task=task['id'],returncode=result.returncode,metrics=metrics,initial_dc=dc,
                error=error,manifest_sha256=stamp,qualified_phy=False,files={n:sha(folder/n) for n in
                ['bench.raw','bench.cir.prn','ngspice.log','console.log'] if (folder/n).exists()})
            capture_manifest(folder/'summary.json',row);rows.append(row)
        calibrated={};calibration_error=None
        try:
            if any(r['error'] is not None for r in rows):raise ValueError('Ideal-wire pair incomplete')
            low,high=[r['initial_dc']['differential_v'] for r in rows]
            calibrated={r['task']:pilot.reference.shape.transitions(*pilot.read_wave(out/r['case']/'bench.cir.prn'),low,high) for r in rows}
        except (ValueError,KeyError,OSError) as caught:calibration_error=str(caught)
        capture_manifest(out/'summary.json',dict(results=rows,calibrated_transitions=calibrated,error=calibration_error,
            diagnostic_complete=calibration_error is None,manifest_sha256=stamp,qualified_phy=False,scope=m['identity']['scope']))
        atomic(out/'state.json',dict(status='completed_ideal_wire_diagnostic' if calibration_error is None else 'held_ideal_wire_diagnostic',qualified_phy=False))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run']);p.add_argument('artifact',type=Path);a=p.parse_args()
    if a.action=='prepare':print(prepare(a.artifact.resolve()),flush=True)
    else:run(a.artifact.resolve())
