#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Retain a bounded native waveform tail bound to one live solver process.

This is incomplete diagnostic data. It cannot admit timing, parity or a PHY.
The solver, waveform and producer files are never modified.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import statistics
import struct
from datetime import datetime,timezone

ROOT=Path(__file__).resolve().parents[1]


def sha(data):return hashlib.sha256(data).hexdigest()


def process(pid):
    base=Path('/proc')/str(pid)
    stat=(base/'stat').read_text();fields=stat[stat.rindex(')')+2:].split()
    args=[v.decode() for v in (base/'cmdline').read_bytes().split(b'\0') if v]
    if fields[0]=='Z' or not any(Path(v).name=='ngspice' for v in args) or args.count('-r')!=1:
        raise ValueError('Require one live native ngspice process with explicit raw output')
    raw=args[args.index('-r')+1]
    if raw.startswith('/work/OpenLVDS/'):raw=str(ROOT/raw.removeprefix('/work/OpenLVDS/'))
    path=Path(raw)
    if not path.is_absolute():path=Path(os.readlink(base/'cwd'))/path
    path=path.resolve();path.relative_to(ROOT/'build/diagnostics')
    return dict(pid=pid,start_ticks=int(fields[19]),command=args,raw=str(path.relative_to(ROOT)))


def tail(path,frames=64):
    if type(frames) is not int or not 2<=frames<=1024:raise ValueError('Require bounded two-to-1024-frame window')
    with path.open('rb') as stream:
        before=os.fstat(stream.fileno());header=b''
        while b'Binary:\n' not in header:
            chunk=stream.read(65536)
            if not chunk or len(header)>64*1024*1024:raise ValueError('Missing bounded binary header')
            header+=chunk
        offset=header.index(b'Binary:\n')+8;header=header[:offset];text=header.decode()
        if 'complex' in text.lower():raise ValueError('Require real native waveform')
        match=re.search(r'No\. Variables:\s*(\d+)',text)
        if match is None:raise ValueError('Missing native variable count')
        count=int(match[1]);names=[m[1].lower() for m in re.finditer(r'^\s*\d+\s+(\S+)\s+\S+\s*$',text,re.M)]
        if count<1 or count!=len(names) or len(set(names))!=count or names[0]!='time':raise ValueError('Ambiguous native vectors')
        frame_bytes=count*8;available=(before.st_size-offset)//frame_bytes
        if available<2:raise ValueError('Fewer than two complete native frames')
        used=min(frames,available);start=available-used
        stream.seek(offset+start*frame_bytes);window=stream.read(used*frame_bytes)
        after=os.fstat(stream.fileno())
        if len(window)!=used*frame_bytes or after.st_size<before.st_size:raise ValueError('Native waveform shrank during capture')
    values=list(struct.iter_unpack('<'+'d'*count,window));times=[v[0] for v in values]
    import math
    if any(not math.isfinite(v) for row in values for v in row) or times[0]<0 or any(b<=a for a,b in zip(times,times[1:])):
        raise ValueError('Nonfinite or nonmonotonic native tail')
    ranges=[]
    for k,name in enumerate(names):
        if not name.startswith('v('):continue
        vs=[v[k] for v in values];lo=min(vs);hi=max(vs)
        ranges.append(dict(vector=name,min_v=lo,max_v=hi,peak_to_peak_v=hi-lo))
    ranges.sort(key=lambda r:(-r['peak_to_peak_v'],r['vector']))
    return header,window,dict(source_device=before.st_dev,source_inode=before.st_ino,source_size_observed=before.st_size,
        variables=count,complete_frames_observed=available,first_copied_frame=start,copied_frames=used,
        ignored_partial_frame_bytes=(before.st_size-offset)%frame_bytes,first_copied_ns=times[0]*1e9,last_accepted_ns=times[-1]*1e9,
        median_window_step_ps=statistics.median((b-a)*1e12 for a,b in zip(times,times[1:])),
        largest_voltage_ranges=ranges[:20],input_output_ranges=[r for r in ranges if r['vector'] in ('v(in)','v(out)')],
        header_sha256=sha(header),window_sha256=sha(window),source_waveform_complete=False,qualified_phy=False)


def capture(pid,out):
    binding=process(pid);path=ROOT/binding['raw'];header,window,report=tail(path)
    if process(pid)!=binding:raise ValueError('Solver identity changed during observation')
    out.mkdir(parents=True,exist_ok=False)
    (out/'header.bin').write_bytes(header);(out/'window.bin').write_bytes(window)
    report=dict(observed_utc=datetime.now(timezone.utc).isoformat(),process=binding,**report,
        scope='Bounded live diagnostic tail only; no completed waveform, electrical, parity or PHY qualification')
    (out/'observation.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n');return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--pid',type=int,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();report=capture(args.pid,args.output.resolve());print(json.dumps(dict(pid=args.pid,last_accepted_ns=report['last_accepted_ns'],median_window_step_ps=report['median_window_step_ps'],qualified_phy=False)))
