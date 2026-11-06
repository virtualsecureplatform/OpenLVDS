# SPDX-License-Identifier: GPL-3.0-only
"""Normalize only RAW voltage-vector aliases, preserving binary sample bytes."""
import hashlib
from pathlib import Path
import re


def digest(path):
    result=hashlib.sha256()
    with path.open('rb') as stream:
        while chunk:=stream.read(8*1024*1024):result.update(chunk)
    return result.hexdigest()


def normalize(source,target):
    source=Path(source);target=Path(target)
    with source.open('rb') as src:
        lines=[];size=0
        while True:
            line=src.readline();size+=len(line)
            if not line or size>64*1024*1024:raise ValueError('Missing bounded binary RAW header')
            lines.append(line)
            if line==b'Binary:\n':break
        header=b''.join(lines).decode('ascii')
        flags=re.search(r'(?m)^Flags:\s*(.*)$',header)
        if flags is None or 'real' not in flags[1].split() or 'complex' in flags[1].split():raise ValueError('Require real RAW samples')
        n=int(re.search(r'No\. Variables:\s*(\d+)',header)[1]);points=int(re.search(r'No\. Points:\s*(\d+)',header)[1])
        variables=list(re.finditer(r'(?m)^(\s*\d+\s+)(\S+)(\s+\S+\s*)$',header))
        names=[m[2].replace(':','.').lower() for m in variables]
        if points<2 or [int(m[1].strip()) for m in variables]!=list(range(n)) or n!=len(names) or len(set(names))!=n or source.stat().st_size!=size+points*n*8:
            raise ValueError('Incomplete or ambiguous real RAW payload')
        if 'time' not in names:raise ValueError('RAW omits time')
        changed=header
        for m,name in reversed(list(zip(variables,names))):changed=changed[:m.start(2)]+name+changed[m.end(2):]
        payload=hashlib.sha256()
        with target.open('xb') as dst:
            dst.write(changed.encode('ascii'))
            while chunk:=src.read(8*1024*1024):payload.update(chunk);dst.write(chunk)
    with target.open('rb') as dst:
        dst.seek(len(changed.encode('ascii')));check=hashlib.sha256()
        while chunk:=dst.read(8*1024*1024):check.update(chunk)
    if check.digest()!=payload.digest():raise ValueError('RAW alias conversion altered binary samples')
    return dict(binary_samples_byte_identical=True,payload_sha256=payload.hexdigest(),samples=points,variables=n,
                vector_aliases_only=True,source_sha256=digest(source),
                normalized_sha256=digest(target))
