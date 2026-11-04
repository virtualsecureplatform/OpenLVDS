#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Localize every voltage failure in two completed phase-release cases.

The remaining producer cases may still run. Complete raw files, exact decks,
libraries, device coverage and bound producer inputs are required. This
diagnosis does not change, clip or waive any voltage measurement.
"""
import argparse
import hashlib
import itertools
import json
from pathlib import Path
import numpy as np
import verify_guarded_phase_clock_release_v2 as verification
from native_binary_raw_v2 import validate

ROOT=verification.ROOT
sha=verification.sha
VERSION='guarded-phase-release-stopped-reassertion-voltage-diagnosis-v2.1'


def diagnose(parent):
    m=verification.pilot.bound(parent);devices=verification.regenerate(parent,m)
    paths=[parent/'manifest.json',*[parent/n for n in m['libraries']]];rows=[]
    for case in [0,1]:
        folder=parent/str(case);s=json.loads((folder/'summary.json').read_text());task=m['tasks'][case]
        ds=devices[str(task['spec']['guard_um'])]
        if (s['task']!=task or s['error'] is not None or s['result']['terminal_screen_passed']
            or (folder/'bench.cir').read_text()!=verification.pilot.fixture(parent,task['spec'],ds)
            or any(sha(folder/n)!=h for n,h in s['files'].items())):
            raise ValueError('Require exact complete retained phase-release failures')
        requested={('v('+n.replace(':','.').lower()+')') for d in ds for n in d['terminals'] if n!='0'}
        names,w=validate(folder/'bench.raw',requested,26e-9);idx={n:i for i,n in enumerate(names)}
        t=w[:,idx['time']]*1e12;zero=np.zeros(len(t))
        def get(n):return zero if n=='0' else w[:,idx['v('+n.replace(':','.').lower()+')']]
        failed={d['device']:d['max_terminal_difference_v'] for d in s['result']['terminal_stress'] if not d['passed']}
        violations=[]
        for d in ds:
            if d['name'] not in failed:continue
            values=[get(n) for n in d['terminals']];worst=(0.,None,None)
            for a,b in itertools.combinations(range(4),2):
                delta=np.abs(values[a]-values[b]);j=int(np.argmax(delta));v=float(delta[j])
                if v>worst[0]:worst=(v,(a,b),j)
            v,pair,j=worst
            if v!=failed[d['name']]:raise ValueError('Stress remeasurement changed')
            violations.append(dict(device=d['name'],model=d['model'],peak_v=v,time_ps=float(t[j]),
                nodes=[d['terminals'][k] for k in pair],voltages_v=[float(values[k][j]) for k in pair],
                signals_v={n:float(get(n)[j]) for n in ['REQUEST','CLK','PREPARE','RESET_N','XD:XR:armed']}))
        if not violations or len(violations)!=len(failed):raise ValueError('Incomplete failure localization')
        rows.append(dict(case=case,spec=task['spec'],violations=violations))
        paths += [folder/n for n in ['summary.json',*s['files']]]
    verification.pilot.bound(parent)
    code=[Path(__file__),Path(verification.__file__),Path(verification.pilot.__file__),ROOT/'scripts/native_binary_raw_v2.py']
    identity=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),inputs={str(p.relative_to(ROOT)):sha(p) for p in paths+code})
    out=ROOT/'build/diagnostics/guarded_phase_release_failure_v2'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False)
    verification.pilot.atomic(out/'summary.json',dict(identity=identity,rows=rows,
        all_worst_excursions_during_stopped_reassertion=all(22990<=d['time_ps']<=23200 for r in rows for d in r['violations']),
        qualified_phy=False,scope='Two complete initial cases only; voltage-pair/time localization, no repaired-circuit, all-case or physical admission'))
    return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('artifact',type=Path);a=p.parse_args();print(diagnose(a.artifact.resolve()),flush=True)
