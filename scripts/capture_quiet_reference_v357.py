#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Freeze all vectors of the live v352 zero-code prefix for observer comparison.

The original solver and raw remain untouched. The copied raw's point-count
header is normalized for ordinary readers; original header and payload hashes
are retained. This is a quiet prefix, never complete bank qualification.
"""
import argparse
from datetime import datetime,timezone
import hashlib
import json
import math
import mmap
import os
from pathlib import Path
import re
import struct
import capture_native_live_tail_v290 as live
process=live.process

ROOT=Path(__file__).resolve().parents[1]
SOURCE='build/diagnostics/restored_balanced_bank_v352/67d491be912b3621'
VERSION='all-vector-quiet-native-prefix-reference-v357.1'


def digest(data):return hashlib.sha256(data).hexdigest()


def read_prefix(path,stop=200e-12):
    if not 0<stop<=200e-12:raise ValueError('Require a quiet prefix of at most 200 ps')
    with Path(path).open('rb') as stream:
        before=os.fstat(stream.fileno());header=b''
        while b'Binary:\n' not in header:
            chunk=stream.read(65536)
            if not chunk or len(header)>64*1024*1024:raise ValueError('Missing native binary header')
            header+=chunk
        end=header.index(b'Binary:\n')+8;header=header[:end]
        text=header.decode();match=re.search(r'No\. Variables:\s*(\d+)',text)
        variables=list(re.finditer(r'^\s*(\d+)\s+(\S+)\s+\S+\s*$',text,re.M))
        if (not match or 'complex' in text.lower() or int(match[1])!=len(variables)
                or [int(m[1]) for m in variables]!=list(range(len(variables)))):
            raise ValueError('Ambiguous real native vector table')
        names=[m[2].lower() for m in variables];n=len(names)
        if not n or names[0]!='time' or len(set(names))!=n:raise ValueError('Missing time or duplicate native vector')
        if len(re.findall(r'(?m)^No\. Points:[^\n]*',text))!=1:raise ValueError('Ambiguous native point-count field')
        size=stream.seek(0,2);available=(size-end)//(8*n)
        if available<2:raise ValueError('Need complete native frames')
        with mmap.mmap(stream.fileno(),size,access=mmap.ACCESS_READ) as mapped:
            sample=lambda k:struct.unpack_from('<d',mapped,end+k*n*8)[0]
            if sample(0)!=0 or not math.isfinite(sample(available-1)) or sample(available-1)<stop:
                raise ValueError('Original trace does not span requested prefix from zero')
            lo,hi=0,available
            while lo<hi:
                mid=(lo+hi)//2
                if sample(mid)<=stop:lo=mid+1
                else:hi=mid
            count=lo;payload=bytes(mapped[end:end+count*n*8])
        after=os.fstat(stream.fileno());current=Path(path).stat()
        if (after.st_size<size or (before.st_dev,before.st_ino)!=(current.st_dev,current.st_ino)):
            raise ValueError('Original native waveform shrank or was replaced')
    times=[]
    for row in struct.iter_unpack('<'+str(n)+'d',payload):
        if not all(math.isfinite(v) for v in row):raise ValueError('Nonfinite native reference vector')
        times.append(row[0])
    if len(times)<2 or any(b<=a for a,b in zip(times,times[1:])):
        raise ValueError('Nonmonotonic native reference prefix')
    steps=[(b-a)*1e12 for a,b in zip(times,times[1:])]
    normalized=re.sub(rb'(?m)^No\. Points:[^\n]*',('No. Points: '+str(count)).encode(),header,count=1)
    metadata=dict(source_device=before.st_dev,source_inode=before.st_ino,
        source_size_observed=size,complete_source_frames_observed=available,
        ignored_partial_source_frame_bytes=(size-end)%(8*n),native_vectors=n,copied_frames=count,
        requested_cutoff_ps=stop*1e12,last_copied_ps=times[-1]*1e12,
        original_header_sha256=digest(header),unmodified_payload_sha256=digest(payload),
        steps_ps=dict(minimum=min(steps),maximum=max(steps),mean=sum(steps)/len(steps)),
        header_point_count_normalized=True,source_waveform_complete=False,qualified_phy=False)
    return header,normalized+payload,metadata


def capture(pid):
    binding=process(pid);raw=ROOT/binding['raw'];case=raw.parent;parent=case.parent
    if str(parent.relative_to(ROOT))!=SOURCE or case.name!='0':raise ValueError('Require explicit live v352 zero-code case')
    paths=[parent/'manifest.json',parent/'bank.spice',case/'bench.cir',Path(__file__),Path(live.__file__)]
    inputs={str(p.relative_to(ROOT)):digest(p.read_bytes()) for p in paths}
    m=json.loads((parent/'manifest.json').read_text());i=m['identity']
    if (parent.name!=digest(json.dumps(i,sort_keys=True).encode())[:16]
            or m['bank_sha256']!=inputs[str((parent/'bank.spice').relative_to(ROOT))]
            or m['tasks'][0]['id']!='0' or m['tasks'][0]['spec']['coarse']!=0 or m['tasks'][0]['spec']['fine']!=0
            or m['tasks'][0]['deck_sha256']!=inputs[str((case/'bench.cir').relative_to(ROOT))]):
        raise ValueError('Original prepared bank or native zero-code fixture changed')
    original,copied,metadata=read_prefix(raw)
    if process(pid)!=binding or any(digest((ROOT/n).read_bytes())!=h for n,h in inputs.items()):
        raise ValueError('Original native process or context changed during reference capture')
    out=ROOT/'build/reports/quiet_native_reference_v357'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out.mkdir(parents=True,exist_ok=False)
    (out/'original_header.bin').write_bytes(original);(out/'reference_prefix.raw').write_bytes(copied)
    report=dict(version=VERSION,process=binding,task=m['tasks'][0],inputs=inputs,**metadata,
        copied_files={n:digest((out/n).read_bytes()) for n in ('original_header.bin','reference_prefix.raw')},
        scope='All saved native vectors of original live quiet prefix only; point-count header normalized, payload unchanged; not full timing/stress/bank/PHY admission')
    (out/'summary.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    print(out,flush=True)
    return out


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--pid',type=int,required=True)
    capture(parser.parse_args().pid)
