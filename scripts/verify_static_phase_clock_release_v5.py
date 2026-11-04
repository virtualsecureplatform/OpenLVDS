#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Regenerate static-phase libraries and remeasure all declared waveforms."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import time
import probe_static_phase_clock_release_v5 as pilot
from native_binary_raw_v2 import validate

ROOT=pilot.ROOT
sha=pilot.sha
VERSION='independent-stack-guard-native-nand2b-static-phase-release-verification-v2.4'


def regenerate(out,m):
    i=m['identity'];rc={}
    for name in i['families']:
        group,_=pilot.families.witnesses(ROOT/name)
        if set(group)&set(rc):raise ValueError('Duplicate static-phase RC family')
        rc.update(group)
    cells='\n'.join(rc[n]['text'].rstrip() for n in sorted(rc))+'\n'
    if cells!=(out/'cells.spice').read_text():raise ValueError('Static-phase component library changed')
    devices={}
    for size in ['o1','o2']:
        text=pilot.circuit.source(rc,size)+pilot.harness(rc)
        if text!=(out/f'{size}.spice').read_text():raise ValueError('Native static-phase topology changed')
        devices[str(size)]=pilot.circuit.components.mapped_mos(cells+text,pilot.HARNESS,
            dict(RCLK='RCLK',REQUEST='REQUEST',PREPARE='PREPARE',RESET_N='RESET_N',CLK='CLK',VPWR='VDD',VGND='0'),'XD')
    if devices!=i['devices']:raise ValueError('Static-phase MOS coverage changed')
    return devices


def assess(rows):
    if [r['task']['spec'] for r in rows]!=pilot.specifications():raise ValueError('Incomplete static-phase coverage')
    groups=[]
    for size in ['o1','o2']:
        selected=[r for r in rows if r['task']['spec']['variant']==size]
        valid=[r['result'] for r in selected if r['error'] is None]
        groups.append(dict(variant=size,cases=len(selected),measurement_errors=[r['error'] for r in selected if r['error'] is not None],
            source_counter_feasibility_passed=bool(len(valid)==4 and all(r['counter_feasibility_passed'] for r in valid)),
            maximum_terminal_difference_v=max((d['max_terminal_difference_v'] for r in valid for d in r['terminal_stress']),default=None),
            minimum_prepare_margin_ps=min((r['margin_to_next_half_phase_ps']['prepare'] for r in valid),default=None),
            minimum_public_release_margin_ps=min((r['margin_to_next_half_phase_ps']['public_release'] for r in valid),default=None)))
    return groups


def verify(out):
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        m=pilot.bound(out);i=m['identity'];devices=regenerate(out,m);state=json.loads((out/'state.json').read_text())
        if (state['status']!='static_phase_pilot_complete' or state['cases']!=len(pilot.specifications())
            or len(m['tasks'])!=len(pilot.specifications()) or i['specs']!=pilot.specifications()):raise ValueError('Require the full terminal static-phase campaign')
        aggregate=json.loads((out/'summary.json').read_text())['rows']
        if len(aggregate)!=len(m['tasks']) or state['errors']!=sum(r['error'] is not None for r in aggregate):raise ValueError('Static-phase aggregate changed')
        paths=[out/n for n in ['manifest.json','summary.json','state.json',*m['libraries']]];rows=[]
        for n,task in enumerate(m['tasks']):
            folder=out/str(n);r=json.loads((folder/'summary.json').read_text());spec=task['spec'];ds=devices[str(spec['variant'])]
            if (r!=aggregate[n] or r['task']!=task or task['id']!=str(n)
                or (folder/'bench.cir').read_text()!=pilot.fixture(out,spec,ds)):raise ValueError('Static-phase task/deck changed')
            if (not {'bench.cir','bench.ngspice.cir','bench.raw','ngspice.log','console.log'}<=set(r['files'])
                or any(sha(folder/name)!=h for name,h in r['files'].items())):raise ValueError('Static-phase raw witness changed')
            # A complete waveform with a reproducible event-count failure is
            # negative evidence for that geometry, not missing coverage.
            requested={('v('+node.replace(':','.').lower()+')') for d in ds for node in d['terminals'] if node!='0'}
            validate(folder/'bench.raw',requested,26e-9)
            measured=error=None
            try:measured=pilot.measure(folder,spec,ds)
            except ValueError as exception:error=str(exception)
            if error!=r['error'] or measured!=r['result']:raise ValueError('Static-phase independent measurement changed')
            rows.append(dict(task=task,result=measured,error=error));paths += [folder/name for name in ['summary.json',*sorted(r['files'])]]
        groups=assess(rows);pilot.bound(out);files={str(p.relative_to(ROOT)):sha(p) for p in paths}
        code=[Path(__file__),Path(pilot.__file__),Path(pilot.circuit.__file__),Path(pilot.families.__file__),Path(pilot.families.base.__file__),Path(pilot.circuit.previous.__file__),Path(pilot.previous.__file__),ROOT/'scripts/native_binary_raw_v2.py']
        identity=dict(version=VERSION,parent=str(out.relative_to(ROOT)),witnesses=files,code={str(p.relative_to(ROOT)):sha(p) for p in code})
        if any(sha(ROOT/n)!=h for n,h in files.items()):raise ValueError('Static-phase witnesses changed during verification')
        receipt=ROOT/'build/diagnostics/static_phase_release_verification_v5'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
        receipt.mkdir(parents=True,exist_ok=False);pilot.atomic(receipt/'summary.json',dict(identity=identity,groups=groups,
            all_declared_raw_waveforms_verified=True,all_profiles_passed=all(g['source_counter_feasibility_passed'] for g in groups),qualified_phy=False,
            scope='All eight regenerated all-native component-RC alternating-phase counter waveforms, including retained event failures; no actual DCC first event, whole-controller RC, full-PVT or PHY admission'))
        return receipt


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('artifact',type=Path);p.add_argument('--watch',action='store_true');a=p.parse_args();out=a.artifact.resolve()
    if a.watch:
        while json.loads((out/'state.json').read_text())['status']=='running':time.sleep(10)
    print(verify(out),flush=True)
