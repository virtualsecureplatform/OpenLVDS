#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Run an ngspice transient and export ordered columns for the shared analyzers."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import numpy as np

ROOT=Path(__file__).resolve().parents[1]

def read_raw(path):
    data=path.read_bytes();position=data.index(b'Binary:\n')+len(b'Binary:\n')
    header=data[:position].decode();n=int(re.search(r'No\. Variables:\s*(\d+)',header)[1])
    count=int(re.search(r'No\. Points:\s*(\d+)',header)[1])
    if 'complex' in header:raise ValueError('Expected real transient data')
    names=[m[1].lower() for m in re.finditer(r'^\s*\d+\s+(\S+)\s+\S+\s*$',header,re.M)]
    if len(names)!=n:raise ValueError('Raw variable count mismatch')
    values=np.frombuffer(data[position:],dtype='<f8')
    if len(values)!=n*count:raise ValueError('Incomplete raw data')
    return names,values.reshape(count,n)

def delay_ramps(text):
    """Hold a from-zero supply ramp at zero for its first 0.1 ns.

    ngspice 42 cannot take its first transient step on the SKY130 driver when
    every source starts moving at t=0 ("timestep too small" at 1e-14 s). The
    ramp still ends at the same time and level."""
    return re.sub(r'(?i)PWL\(0 0 1n ',' PWL(0 0 0.1n 0 1n '[1:],text)

def trapezoidal(text):
    """The deck with ngspice's default trapezoidal integration instead of Gear."""
    return re.sub(r'(?im)^(\.options\b.*?)\s+method=gear\b',r'\1',text)

def main():
    p=argparse.ArgumentParser();p.add_argument('-l',type=Path,required=True);p.add_argument('deck',type=Path)
    a=p.parse_args();deck=a.deck.resolve();text=deck.read_text()
    match=re.search(r'(?im)^\.print\s+tran\s+(.+)$',text)
    if not match:raise ValueError('Expected one transient voltage print statement')
    original=re.findall(r'V\(([^)]+)\)',match[1],re.I)
    names=['v('+n.replace(':','.').lower()+')' for n in original]
    translated=text.replace(match[0],'.save '+' '.join(names))
    translated=re.sub(r'(?i)V\(([^)]+)\)',lambda m:'V('+m[1].replace(':','.')+')',translated)
    translated=re.sub(r'(?im)^\.options\s+device\s+temp=(\S+)',r'.temp \1',translated)
    translated=re.sub(r'(?im)^\.options\s+timeint\s+',r'.options ',translated)
    translated=delay_ramps(translated)
    first,rest=translated.split('\n',1)
    translated=first+'\n.options klu\n'+rest
    path=deck.with_suffix('.ngspice.cir');path.write_text(translated)
    runtime=ROOT/'build/tools/ngspice-runtime';binary=ROOT/'build/tools/ngspice-root/usr/bin/ngspice'
    loader=runtime/'ld-linux-x86-64.so.2'
    if not binary.exists() or not loader.exists():raise ValueError('Run python3 scripts/setup_ngspice.py on the host first')
    manifest=json.loads((ROOT/'build/tools/ngspice.json').read_text())
    for name,digest in manifest['files'].items():
        if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=digest:
            raise ValueError('Changed ngspice runtime file: '+name)
    raw=deck.with_suffix('.raw');raw.unlink(missing_ok=True)
    output=Path(str(deck)+'.prn');output.unlink(missing_ok=True)
    command=[str(loader),'--library-path',str(runtime),str(binary),'-n','-b','-r',str(raw),'-o',str(a.l.resolve()),str(path)]
    result=subprocess.run(command,cwd=deck.parent,capture_output=True,text=True)
    note=deck.with_name('numerics_retry.txt');note.unlink(missing_ok=True)
    if result.returncode and 'Timestep too small' in a.l.read_text(errors='replace') and trapezoidal(translated)!=translated:
        # Gear occasionally collapses the step on a 5 V device body node. The
        # same deck (same mismatch seed) is retried once with trapezoidal
        # integration, and the retry is recorded beside the result.
        path.write_text(trapezoidal(translated));note.write_text('Gear: timestep too small. Rerun with trapezoidal integration.\n')
        result=subprocess.run(command,cwd=deck.parent,capture_output=True,text=True)
    sys.stdout.write(result.stdout);sys.stderr.write(result.stderr)
    if result.returncode:return result.returncode
    variables,wave=read_raw(raw);index={n:i for i,n in enumerate(variables)}
    missing=set(names)-set(index)
    if missing:raise ValueError('Missing requested ngspice vectors: '+str(missing))
    columns=np.column_stack([np.arange(len(wave)),wave[:,index['time']],*[wave[:,index[n]] for n in names]])
    np.savetxt(output,columns,header='Index TIME '+' '.join('V('+n+')' for n in original),comments='',fmt='%.17g')
    stop=re.search(r'(?im)^\.tran\s+\S+\s+(\S+)',text)
    if stop:
        from reduce_rc import number
        if columns[-1,1]<number(stop[1])*(1-1e-8):raise ValueError('Incomplete ngspice transient')
    return 0

if __name__=='__main__':sys.exit(main())
