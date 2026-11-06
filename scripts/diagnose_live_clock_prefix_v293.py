#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Diagnose observed clock crossings from a retained live native prefix.

Only IN/OUT/time are copied. Native terminal safety and complete transport
qualification require the original completed campaign; this cannot admit it.
"""
import argparse
import json
import os
from pathlib import Path
import re
from datetime import datetime,timezone
import numpy as np
import capture_native_live_tail_v290 as live
import regenerated_bank_periodic_measure_v67 as periodic

ROOT=live.ROOT


def analyze(values,spec):
    if values.ndim!=2 or values.shape[1]!=3 or len(values)<2 or not np.isfinite(values).all():raise ValueError('Require finite time/IN/OUT prefix')
    t=values[:,0]*1e12
    if t[0]<0 or t[0]>1e-6 or np.any(np.diff(t)<=0):raise ValueError('Missing startup or nonmonotonic prefix')
    result=periodic.timing(t,values[:,1],values[:,2],spec)
    quarter=result['zero_code_fast_quarter_headroom_ps']
    return dict(observed_timing=result,observed_zero_quarter_budget_violation=bool(result['all_input_output_pulses_present'] and quarter is not None and quarter<0),
        observed_prefix_stop_ns=float(t[-1]/1000),complete_native_terminal_safety_checked=False,
        completed_transport_admitted=False,source_waveform_complete=False,electrical_qualification_passed=False,qualified_phy=False)


def capture(pid,out):
    binding=live.process(pid);raw=ROOT/binding['raw'];case=raw.parent;parent=case.parent
    manifest_path=parent/'manifest.json';manifest_bytes=manifest_path.read_bytes();manifest=json.loads(manifest_bytes)
    tasks=[task for task in manifest['tasks'] if task['id']==case.name]
    if len(tasks)!=1 or live.sha((case/'bench.cir').read_bytes())!=tasks[0]['deck_sha256']:raise ValueError('Explicit native task/deck binding changed')
    spec=tasks[0]['spec']
    if spec.get('cycles')!=8 or spec.get('stop_ns')!=25 or spec.get('frequency_mhz') not in (390,400,410) or spec.get('duty') not in (.4,.5,.6):
        raise ValueError('Require original eight-cycle native clock screen')
    header,_,tail=live.tail(raw);names=[m[1].lower() for m in re.finditer(r'^\s*\d+\s+(\S+)\s+\S+\s*$',header.decode(),re.M)]
    columns=[names.index(name) for name in ('time','v(in)','v(out)')]
    with raw.open('rb') as stream:
        stat=os.fstat(stream.fileno())
        if (stat.st_dev,stat.st_ino)!=(tail['source_device'],tail['source_inode']):raise ValueError('Native waveform replaced')
        mapped=np.memmap(stream,dtype='<f8',mode='r',offset=len(header),shape=(tail['complete_frames_observed'],len(names)))
        values=np.array(mapped[:,columns],copy=True)
        if os.fstat(stream.fileno()).st_size<tail['source_size_observed']:raise ValueError('Native waveform shrank')
        del mapped
    report=analyze(values,spec)
    if live.process(pid)!=binding or manifest_path.read_bytes()!=manifest_bytes or live.sha((case/'bench.cir').read_bytes())!=tasks[0]['deck_sha256']:
        raise ValueError('Native process/task/deck changed during observation')
    out.mkdir(parents=True,exist_ok=False);copied=out/'time_in_out.tsv'
    np.savetxt(copied,values,fmt='%.18e',delimiter='\t',header='time_s\tin_v\tout_v',comments='# ')
    (out/'header.bin').write_bytes(header)
    report=dict(observed_utc=datetime.now(timezone.utc).isoformat(),process=binding,source_prefix=tail,task=tasks[0],
        manifest=str(manifest_path.relative_to(ROOT)),manifest_sha256=live.sha(manifest_bytes),
        capture_script_sha256=live.sha(Path(__file__).read_bytes()),selected_vectors_sha256=live.sha(copied.read_bytes()),
        numpy_version=np.__version__,timing_reader_sha256=live.sha(Path(periodic.__file__).read_bytes()),
        scope='Observed incomplete clock-prefix crossing diagnosis only; original campaign and complete native safety/transport gates remain required',**report)
    (out/'observation.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n');return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--pid',type=int,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();r=capture(a.pid,a.output.resolve());print(json.dumps(dict(pid=a.pid,observed_prefix_stop_ns=r['observed_prefix_stop_ns'],
        observed_zero_quarter_budget_violation=r['observed_zero_quarter_budget_violation'],headroom_ps=r['observed_timing']['zero_code_fast_quarter_headroom_ps'],qualified_phy=False)))
