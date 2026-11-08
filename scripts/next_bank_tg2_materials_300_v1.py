#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Actual native next-bank loading decks for the captured double-TG bank.

Preparation only. A prepared deck is not a passing pilot or a SPICE result.
"""
from copy import deepcopy
import argparse
import hashlib
import json
from pathlib import Path
import sys
import next_bank_fixture_300_v2 as fixture_tools
import probe_tg2_p40n32_300 as producer

ROOT=producer.ROOT
VERSION='double-tg-actual-next-bank-zero-materials-300-v1'
CONTEXT='tg2_next_bank_zero_materials_300_v1'
PARENT=ROOT/'build/diagnostics/tg2_p40n32_pilot_300_v1/aae4b31d0e77445c'
SOURCE_CASE='0'
SETTINGS=((0,False),(0,True),(31,False),(31,True))
sha=producer.sha
atomic=producer.atomic


def captured(parent):
    if parent!=PARENT:
        raise ValueError('Require the explicitly captured double-TG pilot')
    m=producer.bound(parent,full=False)
    i=m['identity'];task=m['tasks'][int(SOURCE_CASE)];s=task['spec']
    expected=dict(coarse=0,fine=0,duty=.5,frequency_mhz=310,stop_ns=40,
                  cycles=8,load_ff=20,process='ss',temperature=40)
    if (task['id']!=SOURCE_CASE or task['variant']!=producer.VARIANT
            or task['centered'] is not True
            or any(s[k]!=v for k,v in expected.items())):
        raise ValueError('Require exact fastest-clock zero-code SS40 source fixture')
    return m


def material_tasks(parent,out,manifest=None):
    m=captured(parent) if manifest is None else manifest
    i=m['identity'];variant=producer.VARIANT
    source=deepcopy(i['source_identity'])
    source['observations']=deepcopy(i['observations'][variant])
    top=i['revisions'][variant]['macro_top']
    source_library=parent/variant/'bank.spice'
    library=source_library.read_text()
    old=(parent/SOURCE_CASE/'bench.cir').read_text()
    include=f'.include "{source_library}"'
    card=producer.numerical_trial.CARD+'\n'
    if old.count(include)!=1 or old.count(card)!=1:
        raise ValueError('Require exact original native library and DC-zero current card')
    base=old.replace(include,f'.include "{out}/bank.spice"',1)
    records=[]
    for number,(fine,centered) in enumerate(SETTINGS):
        deck=base if centered else base.replace(card,'',1)
        deck,loaded=fixture_tools.fixture(deck,library,top,source,next_fine=fine)
        if ('I_BENCH_CURRENT_CENTER' in deck)!=centered:
            raise ValueError('Native loaded current-control pair changed')
        observations=dict(first=deepcopy(source['observations']),next=loaded)
        records.append(dict(id=str(number),next_coarse=0,next_fine=fine,
            centered=centered,deck=deck,observations=observations,
            first_native_mos=len(source['observations']['devices']),
            total_native_mos=2*len(source['observations']['devices'])))
    return records


def record(task,folder):
    return dict(**{k:v for k,v in task.items() if k not in ('deck','observations')},
                files={n:sha(folder/n) for n in ('bench.cir','observations.json')})


def prepare():
    m=captured(PARENT);i=m['identity']
    paths=[PARENT/'manifest.json',PARENT/SOURCE_CASE/'bench.cir',
           PARENT/producer.VARIANT/'bank.spice',ROOT/'clocking_300mhz.json']
    paths+=sorted({Path(mod.__file__).resolve() for mod in list(sys.modules.values())
        if getattr(mod,'__file__',None) and Path(mod.__file__).resolve().parent==ROOT/'scripts'})
    inputs={**i['guards'],**{str(p.relative_to(ROOT)):sha(p) for p in paths}}
    identity=dict(version=VERSION,parent=str(PARENT.relative_to(ROOT)),source_case=SOURCE_CASE,
        inputs=inputs,settings=[list(v) for v in SETTINGS],shared_interbank_wires='ideal',
        active_loaded_numerical_parity_pending=True,qualified_phy=False,
        scope='Actual two-bank zero-code diagnostic materials; no simulations or bank/PHY admission')
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False)
    (out/'bank.spice').write_bytes((PARENT/producer.VARIANT/'bank.spice').read_bytes())
    tasks=[]
    for task in material_tasks(PARENT,out,m):
        folder=out/task['id'];folder.mkdir();(folder/'bench.cir').write_text(task['deck'])
        atomic(folder/'observations.json',task['observations']);tasks.append(record(task,folder))
    atomic(out/'manifest.json',dict(identity=identity,tasks=tasks,
        bank_sha256=sha(out/'bank.spice'),qualified_phy=False))
    check(out)
    atomic(out/'state.json',dict(status='prepared_unqualified',simulations=0,qualified_phy=False))
    return out


def check(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION
            or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
            or i['parent']!=str(PARENT.relative_to(ROOT)) or i['source_case']!=SOURCE_CASE
            or i['settings']!=[list(v) for v in SETTINGS]
            or i['shared_interbank_wires']!='ideal'
            or i['active_loaded_numerical_parity_pending'] is not True
            or i['qualified_phy'] is not False or m['qualified_phy'] is not False):
        raise ValueError('Actual next-bank material identity changed')
    if any(sha(ROOT/n)!=h for n,h in i['inputs'].items()):
        raise ValueError('Captured next-bank input changed')
    parent=captured(PARENT)
    if (sha(out/'bank.spice')!=m['bank_sha256']
            or (out/'bank.spice').read_bytes()!=(PARENT/producer.VARIANT/'bank.spice').read_bytes()):
        raise ValueError('Captured native bank library changed')
    expected=[]
    for task in material_tasks(PARENT,out,parent):
        folder=out/task['id']
        if ((folder/'bench.cir').read_text()!=task['deck']
                or json.loads((folder/'observations.json').read_text())!=task['observations']):
            raise ValueError('Actual native next-bank wiring or observations changed')
        expected.append(record(task,folder))
    if expected!=m['tasks']:
        raise ValueError('Actual next-bank material coverage changed')
    return m


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=('prepare','check'));p.add_argument('artifact',nargs='?',type=Path)
    a=p.parse_args()
    if a.action=='prepare':print(prepare(),flush=True)
    else:
        if a.artifact is None:p.error('Supply the captured material directory')
        check(a.artifact.resolve());print('Actual next-bank decks verified; no electrical admission',flush=True)
