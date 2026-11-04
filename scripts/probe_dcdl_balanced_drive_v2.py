#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Measure balanced coarse-core drive with the exact extracted fine units.

Uniform parallel copies preserve every stage's logical topology and internal
fanout ratio. The same hardware is used at coarse 0 and 1. An extra output
drive variant checks whether the 20 fF receiver load limits the first edge.
These are native feasibility probes, not physically proven compound cells.
"""
import argparse
from contextlib import contextmanager
import hashlib
import itertools
import json
from pathlib import Path
import re
import probe_dcdl_rc_drive_v2 as previous
import probe_dcdl_node_bank_pvt_v2 as source_core

parent_source=previous.parent_source
h=previous.h
ROOT=previous.ROOT
batch=previous.batch
VERSION='hybrid-dcdl-balanced-core-drive-v2.1'
VARIANTS={'core2':2,'core2_output4':4}


def circuit(text,variant):
    if variant not in VARIANTS:raise ValueError('Unknown balanced drive')
    result=[];count=0
    for line in text.splitlines():
        words=line.split();result.append(line)
        if not words or not words[-1].startswith('sky130_fd_sc_hd__'):continue
        if not re.fullmatch(r'X(?:in|out|[ftpm]\d+)',words[0]):raise ValueError('Unexpected coarse-core cell')
        count+=1
        copies=VARIANTS[variant] if words[0]=='Xout' else 2
        result.extend(line.replace(words[0]+' ',words[0]+f'_parallel{i} ',1) for i in range(1,copies))
    if count!=64:raise ValueError('Expected the complete 16-stage coarse core')
    return '\n'.join(result)+'\n'


def specifications():
    return [dict(process='ss',temperature=40,coarse=c,codes=[0,1,16,31,0],restore='mim2x2',
        control_slew_ps=20,variant=v) for v,c in itertools.product(VARIANTS,[0,1])]


def fixture(out,spec,devices):
    # Parent adds the extracted-unit library alongside the original coarse0
    # include. Normalize coarse1 through that same checked path, then select it.
    text=parent_source.fixture(out,dict(spec,coarse=0),devices)
    return text.replace('/coarse0.spice"',f'/coarse{spec["coarse"]}_{spec["variant"]}.spice"')


def prepare(receipt):
    if not receipt.is_relative_to(ROOT/'build/diagnostics/dcdl_rc_drive_verification_v2'):
        raise ValueError('Require independent prior drive proof')
    proof=json.loads((receipt/'summary.json').read_text());parent=ROOT/proof['identity']['artifact'];m=previous.bound(parent)
    if (h.sha(parent/'manifest.json')!=proof['identity']['manifest_sha256']
        or h.sha(parent/'summary.json')!=proof['identity']['summary_sha256']
        or any(h.sha(ROOT/n)!=v for n,v in proof['witness_files'].items())):
        raise ValueError('Prior drive witnesses changed')
    if len(proof['candidates'])!=3 or any(c['error'] is not None for c in proof['candidates']):
        raise ValueError('Require complete three-variant drive evidence')
    # Preserve source node shunt and all exact extracted unit bytes.
    baseline=parent_source.bank(source_core.circuit(0,4)[0])
    original=ROOT/m['identity']['parent']
    if baseline!=(original/'coarse0.spice').read_text():raise ValueError('Source core differs from the exact-unit baseline')
    code=[Path(__file__),Path(previous.__file__),Path(parent_source.__file__),Path(source_core.__file__),
        ROOT/'scripts/probe_dcdl_charge_kick_v2.py',ROOT/'scripts/probe_dcdl_control_margin_v2.py',
        ROOT/'scripts/probe_dcdl_control_restore_v2.py',ROOT/'scripts/analyze_dcdl_batch_v2.py',
        ROOT/'scripts/probe_digital_dcdl_batch_v2.py',ROOT/'scripts/dcdl_cap_strong_v2.py',
        ROOT/'scripts/dcdl_cap_bank_v2.py',ROOT/'scripts/probe_digital_dcdl_v2.py',ROOT/'scripts/probe_digital_dcc_v2.py',
        ROOT/'scripts/run_ngspice.py',ROOT/'scripts/spice_dispatch.py',ROOT/'scripts/spice_engine.py',
        ROOT/'scripts/env.sh',ROOT/'requirements.json',ROOT/'clocking_v2.json',ROOT/'build/apptainer/openlvds.sif.sha256']
    inputs=dict(proof['witness_files'])
    inputs.update({str((receipt/'summary.json').relative_to(ROOT)):h.sha(receipt/'summary.json')})
    inputs.update({str((parent/n).relative_to(ROOT)):h.sha(parent/n) for n in ['manifest.json','summary.json','cells.spice','unit_rc.spice']})
    specs=specifications()
    identity=dict(version=VERSION,code={str(p.relative_to(ROOT)):h.sha(p) for p in code},inputs=inputs,
        pdk=m['identity']['pdk'],pdk_sha256=m['identity']['pdk_sha256'],model_library=m['identity']['model_library'],
        model_library_sha256=m['identity']['model_library_sha256'],simulator=h.provenance(),specs=specs,
        parent=str(parent.relative_to(ROOT)))
    out=ROOT/'build/diagnostics/dcdl_balanced_drive_v2'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False)
    for n in ['cells.spice','unit_rc.spice']:h.write(out/n,(parent/n).read_text())
    tasks=[];devices=m['tasks'][0]['devices']
    for n,spec in enumerate(specs):
        text=parent_source.bank(source_core.circuit(spec['coarse'],4)[0])
        h.write(out/f'coarse{spec["coarse"]}_{spec["variant"]}.spice',circuit(text,spec['variant']))
        folder=out/str(n);folder.mkdir();h.write(folder/'bench.cir',fixture(out,spec,devices))
        tasks.append(dict(id=str(n),spec=spec,devices=devices,deck_sha256=h.sha(folder/'bench.cir')))
    h.atomic(out/'manifest.json',dict(identity=identity,tasks=tasks,libraries={p.name:h.sha(p) for p in out.glob('*.spice')},qualified_phy=False))
    return out


def bound(out):
    if not out.is_relative_to(ROOT/'build/diagnostics/dcdl_balanced_drive_v2'):raise ValueError('Wrong balanced-drive context')
    m=h.bound(out);i=m['identity']
    if (i['version']!=VERSION or h.sha(Path(i['model_library']))!=i['model_library_sha256']
        or any(h.sha(ROOT/n)!=v for n,v in i['inputs'].items()) or [t['spec'] for t in m['tasks']]!=specifications()):
        raise ValueError('Balanced-drive coverage or inputs changed')
    return m


def measure(folder,task):
    return dict(parent_source.measure(folder,task),version=VERSION,variant=task['spec']['variant'],
        scope='SS40 balanced source core/exact unit RC; no compound-cell, full-bank, PVT, ROM or PHY admission')


@contextmanager
def profile():
    before=batch.bound,batch.measure;batch.bound=bound;batch.measure=measure
    try:yield
    finally:batch.bound,batch.measure=before


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','bound']);p.add_argument('artifact',type=Path);a=p.parse_args()
    if a.action=='prepare':print(prepare(a.artifact.resolve()),flush=True)
    elif a.action=='bound':print(json.dumps(bound(a.artifact.resolve()),indent=2))
    else:
        with profile():batch.run(a.artifact.resolve())
