#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""All fifteen native driver output points, gated by the complete six-case pilot."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import itertools
import json
from pathlib import Path
import subprocess

import probe_driver_compact_native as pilot
from dll_campaign import atomic
from receiver_static_diagnosis import capture_manifest
from spice_dispatch import lease
from spice_engine import command, provenance

ROOT=Path(__file__).resolve().parents[1]
sha=pilot.sha
NAME=Path(__file__).name


def tasks(req):
    points=list(itertools.product(req['process_corners'],req['temperatures_c']))
    result=[dict(id=f'{p}_{t}_{op}',process=p,temperature=t,op=op)
            for p,t in points for op in pilot.reference.shape.CASES]
    if len(points)!=15 or len(set(points))!=15 or len({t['id'] for t in result})!=30:
        raise ValueError('Require five processes and three temperatures, both polarities')
    return points,result


def pilot_ready(parent):
    if not (parent/'summary.json').exists(): raise ValueError('Complete the native pilot first')
    report=pilot.verify(parent)
    if report.get('native_output_pilot_passed') is not True or report.get('passed_pvt')!=3:
        raise ValueError('Every native pilot point must pass before full qualification')
    return report


def prepare(parent):
    pilot_ready(parent)
    pm=pilot.bound(parent);pi=pm['identity']
    req=json.loads((ROOT/'requirements.json').read_text());points,rows=tasks(req)
    inputs=dict(pi['inputs'])
    inputs.update({str((parent/n).relative_to(ROOT)):sha(parent/n) for n in ['manifest.json','summary.json']})
    for task in pm['tasks']:
        folder=parent/task['id'];report=json.loads((folder/'summary.json').read_text())
        inputs.update({str((folder/n).relative_to(ROOT)):h for n,h in dict(task['files'],**report['files']).items()})
        inputs[str((folder/'summary.json').relative_to(ROOT))]=sha(folder/'summary.json')
    code=dict(pi['code']);code[NAME]=sha(Path(__file__))
    identity=dict(pilot=str(parent.relative_to(ROOT)),inputs=inputs,code=code,
        simulator=provenance(),points=[list(p) for p in points],
        scope='Thirty full native GDS output cases, five processes x 0/25/40 C x '
              'two initial polarities. Original fixed rails/reference, 100 ohm '
              'plus 2 pF/pin, full 80 ns/1 ps fixtures, fresh DC calibration and '
              'output-waveform reference checks. Six-case pilot independently '
              'remeasured before preparation. Internal MOS stress, original '
              'long component fixtures, coupled PHY and generator certification '
              'remain separate gates.')
    out=ROOT/'build/diagnostics/driver_compact_native'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=True)
    model=(parent/'tt_25_negative_op/source.spice').read_text()
    source=ROOT/pi['source']
    with (out/'.preparation.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        for task in rows:
            folder=out/task['id'];folder.mkdir(exist_ok=True);old=source/task['id']
            deck=pilot.fixture((old/'bench.cir').read_text(),old,folder)
            pilot.ProbeNetwork(model).validate(deck,['D','P','N'])
            for name,text in [('source.spice',model),('bench.cir',deck)]:
                path=folder/name
                if path.exists() and path.read_text()!=text: raise ValueError('Native full fixture changed')
                if not path.exists(): path.write_text(text)
            task['files']={n:sha(folder/n) for n in ['source.spice','bench.cir']}
        capture_manifest(out/'manifest.json',dict(identity=identity,tasks=rows,qualified_phy=False))
    return out


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    points,expected=tasks(json.loads((ROOT/'requirements.json').read_text()))
    if (not out.is_relative_to(ROOT/'build/diagnostics/driver_compact_native') or
            out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16] or
            i['points']!=[list(p) for p in points] or provenance()!=i['simulator'] or
            [{k:v for k,v in t.items() if k!='files'} for t in m['tasks']]!=expected or
            any(sha(ROOT/n)!=h for n,h in i['inputs'].items()) or
            any(sha(ROOT/'scripts'/n)!=h for n,h in i['code'].items()) or
            any(sha(out/t['id']/n)!=h for t in m['tasks'] for n,h in t['files'].items())):
        raise ValueError('Native full context or coverage changed')
    return m


def aggregate(out,m,rows):
    req=json.loads((ROOT/'requirements.json').read_text());points=[]
    for process,temp in m['identity']['points']:
        pair=[r for r in rows if r['case'].startswith(f'{process}_{temp}_')]
        waveforms={};error=None
        try:
            if len(pair)!=2 or any(r['error'] is not None or r['metrics'] is None for r in pair):
                raise ValueError('Native pair incomplete')
            low,high=[r['initial_dc']['differential_v'] for r in pair]
            waveforms={r['task']:pilot.reference.shape.transitions(*pilot.read_wave(out/r['case']/'bench.cir.prn'),low,high) for r in pair}
        except (ValueError,OSError,KeyError) as caught: error=str(caught)
        points.append(dict(process=process,temperature=temp,calibrated_transitions=waveforms,error=error,
            passed=error is None and pilot.reference.pair_checks(pair,waveforms,req)))
    return dict(results=rows,pvt=points,required_cases=30,required_pvt=15,
        passed_pvt=sum(p['passed'] for p in points),native_output_matrix_passed=all(p['passed'] for p in points),
        manifest_sha256=sha(out/'manifest.json'),qualified_phy=False,physical_admission=False,scope=m['identity']['scope'])


def verify(out):
    m=bound(out);rows=[]
    for task in m['tasks']:
        folder=out/task['id'];row=json.loads((folder/'summary.json').read_text())
        if (row['case']!=task['id'] or row['task']!=task['op'] or row['returncode']!=0 or row['error'] is not None or
                row['manifest_sha256']!=sha(out/'manifest.json') or
                set(row['files'])!={'bench.raw','bench.cir.prn','ngspice.log','console.log'} or
                any(sha(folder/n)!=h for n,h in row['files'].items()) or
                pilot.measure(folder)!=(row['metrics'],row['initial_dc'])):
            raise ValueError('Native full output or remeasurement changed')
        rows.append(row)
    report=aggregate(out,m,rows)
    if report!=json.loads((out/'summary.json').read_text()): raise ValueError('Native full aggregate changed')
    bound(out)
    return report


def run(out):
    m=bound(out);stamp=sha(out/'manifest.json')
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists() or any((out/t['id']/n).exists() for t in m['tasks'] for n in ['bench.raw','summary.json','ngspice.log']):
            raise ValueError('Prior or partial native full qualification retained')
        atomic(out/'state.json',dict(status='running_native_output_matrix',qualified_phy=False))
        def execute(task):
            folder=out/task['id'];metrics=dc=result=None;error=None
            atomic(folder/'state.json',dict(status='waiting_for_slot'))
            try:
                with lease(ROOT,priority=1,label='compact_driver_full_'+task['id']):
                    bound(out);atomic(folder/'state.json',dict(status='running'))
                    result=subprocess.run(command(folder/'ngspice.log',folder/'bench.cir'),cwd=folder,capture_output=True,text=True)
                (folder/'console.log').write_text(result.stdout+result.stderr)
                result.check_returncode();bound(out);metrics,dc=pilot.measure(folder)
            except Exception as caught: error=str(caught)
            row=dict(case=task['id'],task=task['op'],returncode=None if result is None else result.returncode,
                metrics=metrics,initial_dc=dc,error=error,manifest_sha256=stamp,qualified_phy=False,
                files={n:sha(folder/n) for n in ['bench.raw','bench.cir.prn','ngspice.log','console.log'] if (folder/n).exists()})
            capture_manifest(folder/'summary.json',row)
            atomic(folder/'state.json',dict(status='completed' if error is None else 'held_for_diagnosis'))
            return row
        with ThreadPoolExecutor(max_workers=2) as pool: rows=list(pool.map(execute,m['tasks']))
        bound(out);report=aggregate(out,m,rows);capture_manifest(out/'summary.json',report)
        atomic(out/'state.json',dict(status='completed_native_output_matrix' if report['native_output_matrix_passed'] else 'held_native_output_checks',qualified_phy=False))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','verify']);p.add_argument('artifact',type=Path);a=p.parse_args()
    if a.action=='prepare': print(prepare(a.artifact.resolve()),flush=True)
    elif a.action=='run': run(a.artifact.resolve())
    else: print(json.dumps(verify(a.artifact.resolve())),flush=True)
