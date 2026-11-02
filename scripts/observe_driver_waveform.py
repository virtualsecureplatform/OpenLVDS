#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Remeasure dynamic TX behavior in completed loaded component traces, without admission."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from dll_measurements import read_wave,edges
from receiver_static_diagnosis import capture_manifest
import qualify_driver_restore_components as components

ROOT=Path(__file__).resolve().parents[1]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
REFERENCE='https://e2e.ti.com/cfs-file/__key/communityserver-discussions-components-files/138/7380.eia_5F00_tia_5F00_644_2D00_a_5F00_lvds.pdf'


def measure(w,h):
    t=w[:,1];p=w[:,h['V(P)']];n=w[:,h['V(N)']];d=p-n;cm=(p+n)/2
    if t[0]>1e-15 or t[-1]<2540e-9-1e-12:raise ValueError('Incomplete original driver trace')
    def plateau(start,end):
        keep=(t>start*1e-9)&(t<end*1e-9)
        if np.count_nonzero(keep)<2:raise ValueError('Missing static driver plateau')
        return float(np.median(d[keep]))
    low,high=plateau(1800,1890),plateau(1950,1990)
    if not low<0<high:raise ValueError('Original driver polarity changed')
    span=high-low;rows=[]
    for rising in [True,False]:
        start_level=low+(.2 if rising else .8)*span;end_level=low+(.8 if rising else .2)*span
        first=edges(t,d,level=start_level,rising=rising);last=edges(t,d,level=end_level,rising=rising)
        for a in first[(first>2010e-9)&(first<2500e-9)]:
            later=last[last>a]
            if not len(later) or later[0]-a>1.25e-9:raise ValueError('Missing paired 20/80 crossing')
            b=later[0];samples=np.r_[start_level,d[(t>a)&(t<b)],end_level]
            monotonic=bool(np.all(np.diff(samples)*(1 if rising else -1)>=-1e-6))
            rows.append(dict(rising=rising,start_ns=float(a*1e9),duration_ps=float((b-a)*1e12),monotonic=monotonic))
    if len(rows)<4 or not {r['rising'] for r in rows}=={True,False}:raise ValueError('Insufficient alternating driver transitions')
    keep=(t>2010e-9)&(t<2500e-9);durations=[r['duration_ps'] for r in rows]
    # This original 800 Mb/s bench has a 1250 ps UI. The coupled 390/400/410
    # MHz cases have their own actual UIs and cannot inherit this comparison.
    return dict(edges=len(rows),static_low_v=low,static_high_v=high,
        transition_min_ps=min(durations),transition_max_ps=max(durations),
        monotonic_20_80=all(r['monotonic'] for r in rows),
        common_mode_min_v=float(cm[keep].min()),common_mode_max_v=float(cm[keep].max()),
        common_mode_pp_v=float(np.ptp(cm[keep])),
        transition_reference_limits_ps=[260,375],common_mode_reference_limit_v=.150,
        transition_within_reference_limits=bool(min(durations)>=260 and max(durations)<=375),
        common_mode_within_reference_limit=bool(np.ptp(cm[keep])<=.150),transitions=rows)


def observe(campaign):
    if not campaign.is_relative_to(ROOT/'build/diagnostics/driver_components'):raise ValueError('Use completed driver components')
    m=json.loads((campaign/'manifest.json').read_text());r=json.loads((campaign/'summary.json').read_text())
    req=json.loads((ROOT/'requirements.json').read_text());components.check_coverage(m['tasks'],req)
    if r.get('passed') is not True or r.get('passed_cases')!=30 or r.get('required')!=30 or r.get('manifest_sha256')!=sha(campaign/'manifest.json'):raise ValueError('Require all thirty completed driver components')
    paths=[campaign/'manifest.json',campaign/'summary.json',ROOT/'requirements.json'];results=[]
    for task in m['tasks']:
        folder=campaign/task['id'];row=json.loads((folder/'summary.json').read_text())
        if (row.get('passed') is not True or row.get('manifest_sha256')!=sha(campaign/'manifest.json') or
                row.get('waveform_sha256')!=sha(folder/'bench.cir.prn') or
                any(sha(folder/n)!=v for n,v in task['files'].items())):raise ValueError('Completed driver fixture/output changed')
        paths += [folder/n for n in ['summary.json','bench.cir.prn',*task['files']]]
    identity=dict(campaign=str(campaign.relative_to(ROOT)),inputs={str(p.relative_to(ROOT)):sha(p) for p in paths},
        code={n:sha(ROOT/'scripts'/n) for n in ['observe_driver_waveform.py','dll_measurements.py','qualify_driver_restore_components.py']},
        reference=REFERENCE,scope='Read-only dynamic observation of original 100 ohm plus 2 pF per pin component fixtures at 800 Mb/s. These differ from TIA-644-A generator fixtures; reference comparisons identify follow-up work, not compliance or PHY admission. Existing component verdicts retained.')
    for task in m['tasks']:
        w,h=read_wave(campaign/task['id']/'bench.cir.prn');results.append(dict(task=task['id'],**measure(w,h)))
    if any(sha(ROOT/n)!=v for n,v in identity['inputs'].items()):raise ValueError('Driver evidence changed during observation')
    out=ROOT/'build/diagnostics/driver_waveform_observation'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16];out.mkdir(parents=True,exist_ok=True)
    capture_manifest(out/'manifest.json',dict(identity=identity,qualified_phy=False))
    capture_manifest(out/'summary.json',dict(results=results,required=30,observed=len(results),qualified_phy=False,
        standard_generator_fixture=False,manifest_sha256=sha(out/'manifest.json'),scope=identity['scope']))
    return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('campaign',type=Path);a=p.parse_args()
    print(observe(a.campaign.resolve()),flush=True)
