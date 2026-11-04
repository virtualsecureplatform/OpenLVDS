#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Preserve a bounded raw-waveform diagnosis while the native pilot continues."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import probe_dcc_native_rc_v3 as native
from probe_digital_dcc_v2 import sha,crossings
from run_ngspice import read_raw

ROOT=native.ROOT


def inspect(parent,selected):
    manifest=native.bound(parent);tasks={t['id']:t for t in manifest['tasks']};files=[parent/'manifest.json',Path(__file__),Path(native.__file__),ROOT/'scripts/run_ngspice.py']
    rows=[]
    for task_id in selected:
        task=tasks[task_id];folder=parent/task_id;receipt=json.loads((folder/'summary.json').read_text())
        if receipt['task']!=task or receipt['error'] is not None:raise ValueError('Require exact successfully exported task')
        for name in ['bench.cir','bench.raw']:
            if sha(folder/name)!=receipt['files'][name]:raise ValueError('Changed native DCC witness')
        files += [folder/n for n in ['summary.json','bench.cir','bench.raw']]
        names,w=read_raw(folder/'bench.raw');t=w[:,names.index('time')]*1e12
        period=1e6/task['spec']['mhz'];start=2000+8*period;end=2000+21*period
        def get(n):return w[:,names.index('v('+n.replace(':','.').lower()+')')]
        def edges(n,up=True):return crossings(t,get(n),up)
        def selected_edges(n,up=True):
            a=edges(n,up);return a[(a>=start)&(a<end)]
        widths={}
        for key,node in [('pulse0','XD:first_ff.Q'),('pulse180','XD:second_ff.Q'),('events','XD:combine.X')]:
            rises=selected_edges(node);falls=edges(node,False);values=[]
            for a in rises:
                b=falls[falls>a]
                if len(b):values.append(float(b[0]-a))
            widths[key]=dict(rising_edges=len(rises),falling_edges=len(selected_edges(node,False)),
                high_width_range_ps=[min(values),max(values)] if values else None)
        mask=(t>=start)&(t<end);event_voltage=get('XD:combine.X')[mask]
        source_count=len(selected_edges('P0'))+len(selected_edges('P180'))
        rows.append(dict(task=task,steady_window_ps=[start,end],source_rising_edges=source_count,
            pulse_widths=widths,output_transitions=len(selected_edges('Q'))+len(selected_edges('Q',False)),
            events_voltage_range_v=[float(np.min(event_voltage)),float(np.max(event_voltage))],
            events_stuck_high=bool(np.min(event_voltage)>1.62),
            pulse_longer_than_half_cycle=any(v['high_width_range_ps'] and v['high_width_range_ps'][1]>period/2 for k,v in widths.items() if k!='events'),
            qualified_phy=False))
    identity=dict(parent=str(parent.relative_to(ROOT)),selected=selected,witnesses={str(p.relative_to(ROOT)):sha(p) for p in files})
    out=ROOT/'build/diagnostics/dcc_native_failure_v2'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False)
    result=dict(identity=identity,rows=rows,qualified_phy=False,
        scope='Independent steady-window pulse widths, event counts and stuck-OR diagnosis for immutable completed cases only')
    if any(sha(ROOT/n)!=h for n,h in identity['witnesses'].items()):raise ValueError('Witness changed during diagnosis')
    (out/'summary.json').write_text(json.dumps(result,indent=2)+'\n');return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('artifact',type=Path);p.add_argument('cases',nargs='+')
    a=p.parse_args();print(inspect(a.artifact.resolve(),a.cases),flush=True)
