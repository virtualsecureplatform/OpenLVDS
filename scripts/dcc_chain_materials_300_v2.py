#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Capture actual source-DCC/four-section loading decks, without simulation."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import probe_tg2_four_bank_300_v1 as chain
import dcc_source_300 as dcc
import dcc_chain_fanout_300_v2 as fanout

ROOT=chain.ROOT
PARENT=ROOT/'build/diagnostics/tg2_four_section_zero_pilot_300_v1/4bf88d17231064da'
DCC=ROOT/'build/diagnostics/dcc_source_300_v1/1a4f4e8eabb896e4'
VERSION='actual-source-dcc-complete-phase-observations-materials-300-v2'
CONTEXT='dcc_four_section_materials_300_v2'
sha=chain.sha
atomic=chain.atomic


def tasks(out,parent_manifest,dcc_library):
    bank=(PARENT/'bank.spice').read_text()
    for task in parent_manifest['tasks']:
        folder=PARENT/task['id'];text=(folder/'bench.cir').read_text()
        include=f'.include "{PARENT}/bank.spice"'
        if text.count(include)!=1:raise ValueError('Original chain library include changed')
        text=text.replace(include,f'.include "{out}/bank.spice"',1)
        text,obs=fanout.fixture(text,bank,dcc_library,out/'dcc.spice')
        observations=dict(sections=json.loads((folder/'observations.json').read_text()),dcc=obs)
        yield dict(id=task['id'],centered=task['centered'],spec=task['spec']),text,observations


def prepare():
    pm=chain.bound(PARENT);dm=dcc.bound(DCC,full=False)
    library=fanout.namespace((DCC/'cells.spice').read_text()+'\n'+(DCC/'hold1.spice').read_text())
    inputs={}
    def retain(path,digest=None):
        path=path.resolve();key=str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)
        value=sha(path)
        if (digest is not None and value!=digest) or (key in inputs and inputs[key]!=value):
            raise ValueError('Conflicting or changed captured input')
        inputs[key]=value
    for original in (pm['identity']['inputs'],dm['identity']['inputs'],dm['identity']['pdk_files']):
        for n,h in original.items():retain(ROOT/n,h)
    for path in (PARENT/'manifest.json',PARENT/'bank.spice',DCC/'manifest.json',DCC/'cells.spice',DCC/'hold1.spice'):
        retain(path)
    for task in pm['tasks']:
        for n in ('bench.cir','observations.json'):retain(PARENT/task['id']/n)
    for mod in list(sys.modules.values()):
        n=getattr(mod,'__file__',None)
        if n and Path(n).resolve().parent==ROOT/'scripts':retain(Path(n))
    identity=dict(version=VERSION,parent=str(PARENT.relative_to(ROOT)),dcc_parent=str(DCC.relative_to(ROOT)),
        inputs=inputs,guards={n:h for n,h in inputs.items() if Path(n).suffix!='.raw'},
        source_dcc_qualified=False,source_chain_qualified=False,detector_fanout_present=False,
        shared_wire_rc_qualified=False,qualified_phy=False,
        scope='Prepared source-DCC/four-section loading diagnostic only; no simulations or phase/PHY admission')
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False)
    (out/'bank.spice').write_bytes((PARENT/'bank.spice').read_bytes());(out/'dcc.spice').write_text(library)
    records=[]
    for task,text,obs in tasks(out,pm,library):
        folder=out/task['id'];folder.mkdir();(folder/'bench.cir').write_text(text);atomic(folder/'observations.json',obs)
        records.append(dict(task,files={n:sha(folder/n) for n in ('bench.cir','observations.json')}))
    atomic(out/'manifest.json',dict(identity=identity,tasks=records,
        libraries={n:sha(out/n) for n in ('bank.spice','dcc.spice')},qualified_phy=False))
    check(out)
    atomic(out/'state.json',dict(status='prepared_unqualified',simulations=0,qualified_phy=False))
    return out


def check(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION
            or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
            or i['parent']!=str(PARENT.relative_to(ROOT)) or i['dcc_parent']!=str(DCC.relative_to(ROOT))
            or any(i[n] is not False for n in ('source_dcc_qualified','source_chain_qualified',
                'detector_fanout_present','shared_wire_rc_qualified','qualified_phy'))
            or i['guards']!={n:h for n,h in i['inputs'].items() if Path(n).suffix!='.raw'}
            or m['qualified_phy'] is not False):raise ValueError('Combined loading material identity changed')
    if any(sha(ROOT/n)!=h for n,h in i['inputs'].items()):raise ValueError('Captured combined loading input changed')
    pm=chain.bound(PARENT,full=False);dcc.bound(DCC,full=False)
    library=fanout.namespace((DCC/'cells.spice').read_text()+'\n'+(DCC/'hold1.spice').read_text())
    if ((out/'bank.spice').read_bytes()!=(PARENT/'bank.spice').read_bytes()
            or (out/'dcc.spice').read_text()!=library
            or m['libraries']!={n:sha(out/n) for n in ('bank.spice','dcc.spice')}):
        raise ValueError('Combined actual native libraries changed')
    expected=[]
    for task,text,obs in tasks(out,pm,library):
        folder=out/task['id']
        if (folder/'bench.cir').read_text()!=text or json.loads((folder/'observations.json').read_text())!=obs:
            raise ValueError('Combined source-DCC/chain wiring changed')
        expected.append(dict(task,files={n:sha(folder/n) for n in ('bench.cir','observations.json')}))
    if m['tasks']!=expected:raise ValueError('Combined fresh reference coverage changed')
    return m


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('prepare','check'));p.add_argument('artifact',nargs='?',type=Path)
    a=p.parse_args()
    if a.action=='prepare':print(prepare(),flush=True)
    else:
        if a.artifact is None:p.error('Supply captured material directory')
        check(a.artifact.resolve());print('Actual combined loading materials verified; no simulations',flush=True)
