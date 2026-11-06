#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Inspect all native terminals even when counter event measurements fail."""
import argparse
import hashlib
import itertools
import json
from pathlib import Path
import numpy as np
from native_binary_raw_v2 import validate
from probe_digital_dcc_v2 import crossings

ROOT=Path(__file__).resolve().parents[1]
VERSION='shared-counter-failed-event-independent-native-stress-v200.1'
SOURCE_VERSION='actual-shared-wire-repaired-clock-counter-full-native-transient-v194.1'


def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        while block:=stream.read(1024*1024):h.update(block)
    return h.hexdigest()


def terminal_peak(values):
    worst=None
    for a,b in itertools.combinations(range(4),2):
        differences=np.abs(values[a]-values[b]);sample=int(np.argmax(differences));peak=float(differences[sample])
        if not np.isfinite(peak):raise ValueError('Nonfinite terminal difference')
        if worst is None or peak>worst[0]:worst=(peak,sample,a,b)
    return worst


def diagnose(folder):
    parent=folder.parent;manifest=parent/'manifest.json';summary=folder/'summary.json'
    m=json.loads(manifest.read_text());i=m['identity'];r=json.loads(summary.read_text());task=r['task']
    if (i['version']!=SOURCE_VERSION or parent.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or task not in m['tasks'] or task['id']!=folder.name or len(i['devices'])!=510
        or r['error'] not in (None,'Alternating phase-state event count')):
        raise ValueError('Require completed exact shared-counter case, including functional event failures')
    if not {'bench.raw','bench.cir','ngspice.log'}<=set(r['files']):raise ValueError('Missing completed counter waveform/deck/log')
    if any(sha(folder/n)!=h for n,h in r['files'].items()) or sha(folder/'bench.cir')!=task['deck_sha256'] or any(sha(parent/n)!=h for n,h in m['libraries'].items()):
        raise ValueError('Completed counter waveform, deck or libraries changed')
    paths=[manifest,summary,Path(__file__),*[folder/n for n in r['files']],*[parent/n for n in m['libraries']],Path(validate.__code__.co_filename),Path(crossings.__code__.co_filename)]
    inputs={str(p.relative_to(ROOT)):sha(p) for p in paths}
    monitors=['RCLK','CLK','REQUEST','PREPARE','RESET_N',*['XD:XR:'+n for n in ('request_i','low0','high1','low1','armed')]]
    devices=i['devices'];requested={'v('+n.replace(':','.').lower()+')' for n in monitors}
    requested.update('v('+n.replace(':','.').lower()+')' for d in devices for n in d['terminals'] if n!='0')
    names,w=validate(folder/'bench.raw',requested,26e-9);idx={n:k for k,n in enumerate(names)};t=w[:,idx['time']]*1e12;zero=np.zeros(len(t))
    def get(node):return zero if node=='0' else w[:,idx['v('+node.replace(':','.').lower()+')']]
    events={n:dict(min_v=float(np.min(get(n))),max_v=float(np.max(get(n))),rise_ps=crossings(t,get(n)).tolist(),fall_ps=crossings(t,get(n),False).tolist()) for n in monitors}
    stress=[]
    for d in devices:
        values=[get(n) for n in d['terminals']];peak,sample,a,b=terminal_peak(values)
        stress.append(dict(device=d['name'],model=d['model'],peak_v=peak,limit_v=d['limit_v'],passed=peak<=d['limit_v'],
            time_ps=float(t[sample]),worst_pair=[('D','G','S','B')[k] for k in (a,b)],
            terminals={label:dict(node=n,voltage_v=float(values[k][sample])) for k,(label,n) in enumerate(zip(('D','G','S','B'),d['terminals']))}))
    if any(sha(ROOT/n)!=h for n,h in inputs.items()):raise ValueError('Counter trace changed during diagnosis')
    return dict(version=VERSION,case=str(folder.relative_to(ROOT)),task=task,original_measurement_error=r['error'],inputs=inputs,
        events=events,native_mos_observed=len(stress),all_terminal_pairs_checked=True,terminal_screen_passed=all(d['passed'] for d in stress),
        maximum_terminal_difference_v=max(d['peak_v'] for d in stress),terminal_stress=stress,
        scope='Read-only complete failed-or-passing shared-counter trace diagnosis; no event filtering, circuit repair or counter timing/PHY admission',qualified_phy=False)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('case',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    r=diagnose(a.case.resolve());a.output.parent.mkdir(parents=True,exist_ok=True)
    with a.output.open('x') as f:f.write(json.dumps(r,indent=2)+'\n')
    print(json.dumps({k:r[k] for k in ('case','native_mos_observed','terminal_screen_passed','maximum_terminal_difference_v','original_measurement_error')}))
