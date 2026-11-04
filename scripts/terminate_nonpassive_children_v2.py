#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Terminate only owned solver leaves of frozen, proven-nonpassive campaigns.

Preserve adapters, original artifacts, partial raws, and dispatcher lock inodes.
The existing drain finisher inventories all files after adapters have exited.
"""
import argparse
import json
import os
from pathlib import Path
import re
import signal
import struct
import drain_superseded_clocking_v4 as drain

ROOT=drain.ROOT


def host(path):
    if path.startswith('/work/OpenLVDS/'):return ROOT/path[len('/work/OpenLVDS/'):]
    return Path(path)


def sample(path):
    if not path.exists():return None
    with path.open('rb') as f:
        header=f.read(1024*1024);end=header.find(b'Binary:\n')
        if end<0:return dict(bytes=path.stat().st_size)
        start=end+8;variables=int(re.search(rb'No\. Variables:\s*(\d+)',header[:start])[1]);size=path.stat().st_size
        points=max(0,(size-start)//(variables*8));times=[]
        for n in sorted({max(0,points-20),max(0,points-10),points-1}):
            if n<0:continue
            f.seek(start+n*variables*8);value=f.read(8)
            if len(value)==8:times.append(struct.unpack('<d',value)[0])
        return dict(bytes=size,complete_records=points,last_sample_times_s=times)


def terminate(receipt):
    identity=json.loads((receipt/'identity.json').read_text());expected=identity['coordinator'];artifact=ROOT/identity['artifact']
    if artifact.parent.name not in ['nand_shunt_native_v2','native_clock_components_v2']:raise ValueError('Not a nonpassive component campaign')
    current=drain.proc(expected['pid'])
    if current is None or current['start']!=expected['start'] or current['argv']!=expected['argv'] or current['uid']!=os.getuid() or current['state']!='T':
        raise ValueError('Exact coordinator must already be frozen')
    if drain.digest(Path(drain.__file__))!=identity['producer_sha256'] or drain.digest(artifact/'manifest.json')!=identity['manifest_sha256']:
        raise ValueError('Drain producer or campaign changed')
    m=json.loads((artifact/'manifest.json').read_text());libraries={str((artifact/n).relative_to(ROOT)):h for n,h in m['libraries'].items()}
    if any(drain.digest(ROOT/n)!=h for n,h in libraries.items()):raise ValueError('Component library changed')
    proofs=[]
    for name,digest in identity['evidence_files'].items():
        path=ROOT/name
        if drain.digest(path)!=digest:raise ValueError('Passivity evidence changed')
        evidence=json.loads(path.read_text())
        if not evidence.get('negative_energy_witness'):continue
        inputs=evidence['identity']['inputs']
        if any(n in inputs and inputs[n]==h for n,h in libraries.items()):proofs.append(name)
    if not proofs:raise ValueError('Require negative-energy proof bound to this exact component library')
    recorded={r['pid']:r for r in json.loads((receipt/'children.json').read_text())};children=drain.descendants(expected['pid']);solvers=[]
    for child in children:
        argv=child['argv']
        if not any(v.endswith('/ngspice-root/usr/bin/ngspice') for v in argv):continue
        old=recorded.get(child['pid'])
        if old is None or child['start']!=old['start'] or argv!=old['argv'] or child['uid']!=os.getuid():raise ValueError('Solver identity changed')
        raw=host(argv[argv.index('-r')+1]);deck=host(argv[-1])
        if raw.name!='bench.raw' or deck.name!='bench.ngspice.cir' or raw.parent!=deck.parent or not raw.is_relative_to(artifact):
            raise ValueError('Solver does not belong to this frozen artifact')
        solvers.append(dict(process=child,raw=str(raw.relative_to(ROOT)),partial_raw_sample=sample(raw)))
    path=receipt/'nonpassive_children_termination.json'
    if path.exists():raise ValueError('Retain previous termination receipt')
    drain.save(path,dict(reason='Exact library has a negative capacitor-matrix energy witness; its transients cannot qualify hardware',
        passivity_proofs=proofs,solvers=solvers,signal='SIGTERM',original_artifact_unchanged=True,qualified_phy=False))
    for row in solvers:
        old=row['process'];now=drain.proc(old['pid'])
        if now is None:continue
        if now['start']!=old['start'] or now['argv']!=old['argv'] or now['uid']!=old['uid']:raise ValueError('Solver changed before termination')
        os.kill(old['pid'],signal.SIGTERM)
    return dict(terminated_solver_leaves=len(solvers),receipt=str(path))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('receipt',type=Path);a=p.parse_args();print(json.dumps(terminate(a.receipt.resolve()),indent=2))
