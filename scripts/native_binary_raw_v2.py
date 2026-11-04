# SPDX-License-Identifier: GPL-3.0-only
"""Memory-map complete real ngspice traces without duplicating large arrays."""
from pathlib import Path
import re
import numpy as np


def read(path):
    path=Path(path)
    with path.open('rb') as f:
        header=b''
        while b'Binary:\n' not in header:
            chunk=f.read(65536)
            if not chunk or len(header)>64*1024*1024:raise ValueError('Missing binary raw header')
            header+=chunk
    end=header.index(b'Binary:\n')+8;text=header[:end].decode()
    if 'complex' in text.lower():raise ValueError('Require real native transient')
    count=int(re.search(r'No\. Points:\s*(\d+)',text)[1])
    n=int(re.search(r'No\. Variables:\s*(\d+)',text)[1])
    names=[m[1].lower() for m in re.finditer(r'^\s*\d+\s+(\S+)\s+\S+\s*$',text,re.M)]
    if count<2 or n!=len(names) or len(set(names))!=n or path.stat().st_size!=end+count*n*8:
        raise ValueError('Incomplete or ambiguous native raw')
    return names,np.memmap(path,dtype='<f8',mode='r',offset=end,shape=(count,n))


def validate(path,requested,stop):
    names,w=read(path)
    if not {'time',*requested}<=set(names):raise ValueError('Missing requested native vectors')
    time=w[:,names.index('time')]
    if time[0]<0 or time[-1]<stop*(1-1e-8) or np.any(np.diff(time)<=0):raise ValueError('Incomplete/nonmonotonic native transient')
    for start in range(0,len(w),1024):
        if not np.isfinite(w[start:start+1024]).all():raise ValueError('Nonfinite native transient')
    return names,w
