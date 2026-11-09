#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Run the pinned ngspice engine and validate raw data without ASCII export.

Same pinned engine and deck translation, using default SMP instead of KLU.
No model, tolerance, initial-condition or transient-duration change.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from native_binary_raw_v2 import validate

ROOT=Path(__file__).resolve().parents[1]


def translate(text):
    from run_native_binary_v2 import translate as original
    if re.search(r'(?im)^\.options?\b[^\n]*\bklu\b',text):
        raise ValueError('SMP diagnostic refuses explicit source KLU selection')
    translated,names=original(text)
    first,rest=translated.split('\n',1)
    if not rest.startswith('.options klu\n'):
        raise ValueError('Pinned native KLU translation changed')
    return first+'\n'+rest.removeprefix('.options klu\n'),names


def run(deck,log):
    deck=deck.resolve();log=log.resolve();text=deck.read_text();translated,names=translate(text)
    path=deck.with_suffix('.ngspice.cir');raw=deck.with_suffix('.raw')
    if any(p.exists() for p in [path,raw,log]):raise ValueError('Retain prior native simulation evidence')
    runtime=ROOT/'build/tools/ngspice-runtime';binary=ROOT/'build/tools/ngspice-root/usr/bin/ngspice'
    loader=runtime/'ld-linux-x86-64.so.2'
    manifest=json.loads((ROOT/'build/tools/ngspice.json').read_text())
    for name,digest in manifest['files'].items():
        if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=digest:raise ValueError('Changed native simulator runtime: '+name)
    path.write_text(translated)
    p=subprocess.run([str(loader),'--library-path',str(runtime),str(binary),'-n','-b','-r',str(raw),'-o',str(log),str(path)],
                     cwd=deck.parent,capture_output=True,text=True)
    sys.stdout.write(p.stdout);sys.stderr.write(p.stderr)
    if p.returncode:return p.returncode
    from reduce_rc import number
    stops=re.findall(r'(?im)^\.tran\s+\S+\s+(\S+)',text)
    if len(stops)!=1:raise ValueError('Require one native transient')
    validate(raw,names,number(stops[0]));return 0


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('-l',type=Path,required=True);p.add_argument('deck',type=Path)
    a=p.parse_args();sys.exit(run(a.deck,a.l))
