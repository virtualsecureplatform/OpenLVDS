#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Capture and classify actual ngspice observer log records without changing it."""
import argparse
from collections import Counter
from datetime import datetime,timezone
import hashlib
import json
import math
import os
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OBSERVER=ROOT/'build/reports/step_observer_prefix_diagnostic/20261107T130431Z'


def analyze(text):
    counts=Counter();all_counts=Counter();nodes=Counter();devices=Counter();flags=Counter();iterations=Counter()
    last=0.;trunc_rejections=0;statuses=Counter()
    for line in text.splitlines():
        if not line.startswith('OLVDS_STEP '):continue
        r=dict(piece.split('=',1) for piece in line.split()[1:]);kind=r['kind'];t=float(r['t'])
        if not math.isfinite(t) or t<0:raise ValueError('Nonfinite/negative observer time')
        all_counts[kind]+=1
        if t==0:continue
        if t>200e-12*(1+1e-12):raise ValueError('Outside bounded observer interval')
        last=max(last,t);counts[kind]+=1
        if kind=='ni_limit':
            nodes[r['node']]+=1;devices[r['device']]+=1;flags[int(r['noncon'])]+=1;iterations[int(r['iter'])]+=1
        elif kind=='trunc_decision':trunc_rejections+=int(r['reject'])
        elif kind=='noncon_reject':statuses[int(r['status'])]+=1
    capped=bool(all_counts['ni_success']+all_counts['ni_limit']>=50000
        or all_counts['noncon_reject']+all_counts['trunc_decision']>=50000
        or all_counts['charge_trunc']>=50000 or all_counts['device_type']>=50000)
    count=counts['ni_limit']
    observed=bool(count>=50 and counts['noncon_reject']==count and flags=={0:count}
        and nodes=={'vdd#branch':count} and devices=={'-':count}
        and not counts['charge_trunc'] and not trunc_rejections and not capped)
    return dict(positive_time_counts=dict(counts),all_logged_counts=dict(all_counts),last_observed_ps=last*1e12,
        last_failed_nodes=dict(nodes),last_failed_devices=dict(devices),model_nonconvergence_flags=dict(flags),
        iteration_limit_histogram=dict(iterations),rejection_status_histogram=dict(statuses),
        truncation_rejections=trunc_rejections,possible_trace_cap_reached=capped,
        supply_current_iteration_bottleneck_observed=observed,
        scope='Bounded positive-time observer records; operating point excluded; cached trouble fields interpreted with zero model nonconvergence flags',qualified_phy=False)


def capture(pid):
    proc=Path('/proc')/str(pid)
    def identity():
        stat=(proc/'stat').read_text();parts=stat[stat.rindex(')')+2:].split()
        args=[w.decode() for w in (proc/'cmdline').read_bytes().split(b'\0') if w]
        if parts[0]=='Z' or not any(Path(w).name=='ngspice' for w in args):raise ValueError('Require actual live observer engine')
        if '-o' not in args or args[args.index('-o')+1]!='/work/OpenLVDS/'+str((OBSERVER/'on/ngspice.log').relative_to(ROOT)):
            raise ValueError('Require explicit current logging-on observer output')
        return dict(pid=pid,start_ticks=int(parts[19]),command=args)
    before=identity();log=OBSERVER/'on/ngspice.log'
    with log.open('rb') as stream:
        stat=os.fstat(stream.fileno());data=stream.read(stat.st_size)
        if os.fstat(stream.fileno()).st_size<stat.st_size:raise ValueError('Observer log shrank')
    data=data[:data.rfind(b'\n')+1]
    if identity()!=before:raise ValueError('Observer process changed during log capture')
    report=analyze(data.decode())
    off=json.loads((OBSERVER/'off/summary.json').read_text())
    if (off['error'] is not None or off['result']['reference_difference']['all_native_prefix_voltages_within_2mv'] is not True
            or off['result']['steps']['minimum_step_ps']>=.01):
        raise ValueError('Require completed matching slow-step observer control')
    out=ROOT/'build/reports/step_trace_analysis_v361'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out.mkdir(parents=True,exist_ok=False);(out/'events.log').write_bytes(data)
    inputs={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (Path(__file__),OBSERVER/'manifest.json',OBSERVER/'off/summary.json')}
    report.update(process=before,source_log=str(log.relative_to(ROOT)),source_device=stat.st_dev,source_inode=stat.st_ino,
        source_size_observed=stat.st_size,captured_complete_line_bytes=len(data),captured_log_sha256=hashlib.sha256(data).hexdigest(),
        inputs=inputs,source_waveform_complete=False,parameters_changed=False)
    (out/'summary.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n');print(out,flush=True)
    return out


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--pid',type=int,required=True)
    capture(parser.parse_args().pid)
