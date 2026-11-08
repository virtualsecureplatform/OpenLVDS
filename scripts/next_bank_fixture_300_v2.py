#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Native next-bank load materials with runner-validated unique saved vectors."""
import re
import next_bank_fixture_300 as previous
from run_native_binary_v2 import translate
harness=previous.harness
captured=previous.captured
PORTS=previous.PORTS


def fixture(original,library,top,identity,*,next_coarse=0,next_fine=0):
    text,observations=previous.fixture(original,library,top,identity,next_coarse=next_coarse,next_fine=next_fine)
    match=re.search(r'(?m)^\.print tran (.*)$',text)
    if match is None:raise ValueError('Missing complete native observation statement')
    kept=[];seen=set()
    for token in match[1].split():
        key=token.lower().replace(':','.')
        if key not in seen:kept.append(token);seen.add(key)
    text=text[:match.start()]+'.print tran '+' '.join(kept)+text[match.end():]
    translate(text)  # Actual runner preflight; does not invoke SPICE.
    return text,observations


def material_tasks(parent,out):
    import json
    producer,m=captured(parent);i=m['identity'];old=(parent/'2/bench.cir').read_text()
    include=f'.include "{parent}/bank.spice"'
    if old.count(include)!=1 or old.count(producer.numerical.CARD+'\n')!=1:
        raise ValueError('Require exact captured native library and declared bench-current offset')
    base=old.replace(include,f'.include "{out}/bank.spice"',1);library=(parent/'bank.spice').read_text()
    records=[]
    for number,(next_fine,centered) in enumerate(((0,False),(0,True),(31,True))):
        deck=base if centered else base.replace(producer.numerical.CARD+'\n','',1)
        deck,obs=fixture(deck,library,i['macro_top'],i['source_identity'],next_fine=next_fine)
        records.append(dict(id=str(number),next_fine=next_fine,centered=centered,deck=deck,observations=obs,
            first_native_mos=len(i['source_identity']['observations']['devices']),
            total_native_mos=2*len(i['source_identity']['observations']['devices'])))
    return records


def prepare(parent):
    import hashlib,json,sys
    from pathlib import Path
    producer,m=captured(parent);i=m['identity'];root=producer.ROOT
    paths=[parent/'manifest.json',parent/'bank.spice',parent/'2/bench.cir']
    paths += sorted({Path(mod.__file__).resolve() for mod in list(sys.modules.values())
        if getattr(mod,'__file__',None) and Path(mod.__file__).resolve().parent==root/'scripts'})
    inputs={**i.get('guards',i['inputs']),**i['source_identity']['pdk_files'],**i['source_identity']['external_files'],
            **{str(p.relative_to(root)):producer.sha(p) for p in paths}}
    identity=dict(version='actual-native-next-bank-zero-load-materials-300-v2',parent=str(parent.relative_to(root)),
        inputs=inputs,source_case='2',shared_interbank_wires='ideal',qualified_phy=False,
        active_loaded_numerical_parity_pending=True,
        scope='Prepared zero-code native next-bank loading diagnostics only; no simulations, DLL/detector fanout RC, all-PVT or PHY admission')
    out=root/'build/diagnostics/next_bank_zero_materials_300_v2'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);(out/'bank.spice').write_bytes((parent/'bank.spice').read_bytes());tasks=[]
    for task in material_tasks(parent,out):
        folder=out/task['id'];folder.mkdir();(folder/'bench.cir').write_text(task['deck'])
        producer.atomic(folder/'observations.json',task['observations'])
        tasks.append({**{k:v for k,v in task.items() if k not in ('deck','observations')},
                      'files':{n:producer.sha(folder/n) for n in ('bench.cir','observations.json')}})
    producer.atomic(out/'manifest.json',dict(identity=identity,tasks=tasks,bank_sha256=producer.sha(out/'bank.spice'),qualified_phy=False))
    check(out);producer.atomic(out/'state.json',dict(status='prepared_unqualified',simulations=0,qualified_phy=False))
    return out


def check(out):
    import hashlib,json
    from pathlib import Path
    import clocking_profile_300 as policy
    root=policy.ROOT;m=json.loads((out/'manifest.json').read_text());i=m['identity'];parent=root/i['parent']
    if (out.parent!=root/'build/diagnostics/next_bank_zero_materials_300_v2'
            or i['version']!='actual-native-next-bank-zero-load-materials-300-v2'
            or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
            or i['qualified_phy'] is not False or i['active_loaded_numerical_parity_pending'] is not True
            or m['qualified_phy'] is not False):raise ValueError('Native next-bank material identity changed')
    producer,_=captured(parent)
    if any(producer.sha(root/n)!=h for n,h in i['inputs'].items()):raise ValueError('Captured next-bank input changed')
    if (producer.sha(out/'bank.spice')!=m['bank_sha256']
            or (out/'bank.spice').read_bytes()!=(parent/'bank.spice').read_bytes()):raise ValueError('Original native library changed')
    expected=[]
    for task in material_tasks(parent,out):
        folder=out/task['id']
        if ((folder/'bench.cir').read_text()!=task['deck']
                or json.loads((folder/'observations.json').read_text())!=task['observations']):
            raise ValueError('Native next-bank fixture or observation map changed')
        expected.append({**{k:v for k,v in task.items() if k not in ('deck','observations')},
                         'files':{n:producer.sha(folder/n) for n in ('bench.cir','observations.json')}})
    if m['tasks']!=expected:raise ValueError('Actual next-bank coverage changed')
    return m


if __name__=='__main__':
    import argparse
    from pathlib import Path
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=('prepare','check'));parser.add_argument('artifact',type=Path)
    args=parser.parse_args();target=args.artifact.resolve()
    if args.action=='prepare':print(prepare(target),flush=True)
    else:check(target);print('Actual native next-bank materials verified; no electrical admission',flush=True)
