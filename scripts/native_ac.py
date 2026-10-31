# SPDX-License-Identifier: GPL-3.0-only
"""AC measurements with the pinned native engine; no transient-runner changes."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import numpy as np
from spice_engine import engine,provenance
from spice_slots import slot

ROOT=Path(__file__).resolve().parents[1]


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def read_complex(path):
    data=path.read_bytes();start=data.index(b'Binary:\n')+len(b'Binary:\n');header=data[:start].decode()
    if 'complex' not in header:raise ValueError('Expected complex AC data')
    n=int(re.search(r'No. Variables:\s*(\d+)',header)[1]);count=int(re.search(r'No. Points:\s*(\d+)',header)[1])
    names=[m[1].lower() for m in re.finditer(r'^\s*\d+\s+(\S+)\s+\S+[^\n]*$',header,re.M)]
    values=np.frombuffer(data[start:],dtype='<c16')
    if len(names)!=n or len(values)!=n*count or count<2 or not np.isfinite(values).all():
        raise ValueError('Incomplete AC data')
    wave=values.reshape(count,n)
    frequency=wave[:,names.index('frequency')].real
    if np.any(frequency<=0) or np.any(np.diff(frequency)<=0):raise ValueError('Invalid AC frequencies')
    return names,wave


def run(deck):
    if engine()!='ngspice':raise ValueError('Use the pinned ngspice environment')
    runtime=ROOT/'build/tools/ngspice-runtime';binary=ROOT/'build/tools/ngspice-root/usr/bin/ngspice'
    manifest=json.loads((ROOT/'build/tools/ngspice.json').read_text())
    for name,value in manifest['files'].items():
        if digest(ROOT/name)!=value:raise ValueError('Changed engine runtime')
    raw=deck.with_suffix('.raw');log=deck.with_suffix('.log')
    with slot():
        result=subprocess.run([str(runtime/'ld-linux-x86-64.so.2'),'--library-path',str(runtime),str(binary),
            '-n','-b','-r',str(raw),'-o',str(log),str(deck)],cwd=deck.parent,capture_output=True,text=True)
    deck.with_suffix('.console.log').write_text(result.stdout+result.stderr)
    result.check_returncode();read_complex(raw)
    record=dict(passed=True,simulator_provenance=provenance(),producer_sha256=digest(Path(__file__)),
                deck_sha256=digest(deck),raw_sha256=digest(raw))
    deck.with_suffix('.evidence.json').write_text(json.dumps(record,indent=2)+'\n')
    return raw
