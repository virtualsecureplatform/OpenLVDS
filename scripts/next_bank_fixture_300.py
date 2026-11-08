#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Connect a complete native next bank, retaining every actual observation."""
from copy import deepcopy
import re
import native_clock_components_v2 as native
from dcdl_uniform_tree_v3 import encode
from dcdl_tg_tree_v5 import control_targets

PORTS=['IN','OUT',*[f'S{k}' for k in range(4)],*[f'E{k}' for k in range(31)],'VPWR','VGND']


def harness(library,top,identity,next_coarse,next_fine):
    """Native static load, not a fitted capacitor or an input-stage proxy."""
    defs=native.definitions(library)
    if identity['ports']!=PORTS or defs[top][0]!=PORTS:
        raise ValueError('Require exact original 16-coarse/32-fine bank interface')
    pins=encode(next_coarse,next_fine)
    original_pins={p:'0' if p=='VGND' else 'VDD' if p=='VPWR' else p for p in PORTS}
    first=native.mapped_mos(library,top,original_pins,'XD')
    if first!=identity['observations']['devices']:
        raise ValueError('Original full native transistor observation map changed')
    mapping={**{p:'NEXT_'+p for p in pins},'IN':'OUT','OUT':'NEXT_OUT','VPWR':'VDD','VGND':'0'}
    loaded=native.mapped_mos(library,top,mapping,'XL')
    def rename(node):
        if node.startswith('XD:'):return 'XL:'+node[3:]
        if node in mapping:return mapping[node]
        if node=='VDD':return 'VDD'
        if node=='0':return '0'
        raise ValueError('Unresolved next-bank observation node: '+node)
    controls=[dict(c,node=rename(c['node'])) for c in identity['observations']['controls']]
    gates=[dict(g,device=rename(g['device']),gate_node=rename(g['gate_node']))
           for g in identity['observations']['programming_gates']]
    actual={d['name']:d for d in loaded}
    if (len(loaded)!=len(first) or len(actual)!=len(loaded)
            or {d['name'] for d in first}&actual.keys()
            or any(actual[g['device']]['terminals'][1]!=g['gate_node'] for g in gates)):
        raise ValueError('Incomplete or colliding actual next-bank native maps')
    # Every leaf differs only by the explicit instance/public-terminal map.
    for before,after in zip(first,loaded):
        expected=deepcopy(before);expected['name']=rename(before['name'])
        expected['terminals']=[rename(n) for n in before['terminals']]
        if after!=expected:raise ValueError('Next-bank transistor model, limits, order or connections changed')
    targets=control_targets(next_coarse,next_fine)
    if any(c['control'] not in targets for c in controls+gates):raise ValueError('Unresolved logical next-bank control')
    lines=[f'VNEXT_{p} NEXT_{p} 0 {1.8*v:g}' for p,v in pins.items()]
    lines += ['XL '+' '.join(mapping[p] for p in PORTS)+' '+top,'CNEXT_LOAD NEXT_OUT 0 20f']
    probes={'NEXT_OUT',*['NEXT_'+p for p in pins]}
    probes.update(n for d in loaded for n in d['terminals'] if n!='0')
    probes.update(c['node'] for c in controls);probes.update(g['gate_node'] for g in gates)
    return lines,probes,dict(devices=loaded,controls=controls,programming_gates=gates,
        next_coarse=next_coarse,next_fine=next_fine,native_mos=len(loaded),
        far_output_load_ff=20,first_output_fixed_capacitor_removed=True,
        full_next_bank_native_input_load=True,whole_clock_rc_qualified=False,qualified_phy=False)


def fixture(original,library,top,identity,*,next_coarse=0,next_fine=0):
    if (original.count('CLOAD OUT 0 20f\n')!=1 or original.count('.tran 2p 40n 0 2p')!=1
            or len(re.findall(r'(?m)^XD .* '+re.escape(top)+r'$',original))!=1
            or len(re.findall(r'(?m)^\.print tran ',original))!=1
            or re.search(r'(?im)^XL\s|^VNEXT_|^CNEXT_LOAD\s',original)):
        raise ValueError('Require untouched fresh 40 ns, 20 fF single-bank fixture')
    lines,probes,observations=harness(library,top,identity,next_coarse,next_fine)
    result=original.replace('CLOAD OUT 0 20f\n','\n'.join(lines)+'\n',1)
    result=re.sub(r'(?m)^(\.print tran [^\n]*)$',lambda m:m[1]+' '+' '.join('V('+n+')' for n in sorted(probes)),result,count=1)
    if ('CLOAD OUT 0' in result or result.count('CNEXT_LOAD NEXT_OUT 0 20f')!=1
            or len(re.findall(r'(?m)^XL ',result))!=1):
        raise ValueError('Require a real native next-bank input at the original output')
    return result,observations


def captured(parent):
    import json
    import native_bank_300_v1 as first
    import native_bank_300_v2 as single
    import native_bank_mim4_300_v1 as mim
    m=json.loads((parent/'manifest.json').read_text())
    producer={p.VERSION:p for p in (first,single,mim)}.get(m['identity']['version'])
    if producer is None:raise ValueError('Require fresh captured 300 MHz native bank')
    m=producer.bound(parent,full=False) if producer is mim else producer.bound(parent)
    task=m['tasks'][2];s=task['spec']
    if (task['id']!='2' or task['centered'] is not True
            or any(s[k]!=v for k,v in dict(coarse=0,fine=0,duty=.5,frequency_mhz=310,stop_ns=40,cycles=8,load_ff=20,process='ss',temperature=40).items())):
        raise ValueError('Require original complete zero-code/50% SS40 fastest-clock fixture')
    return producer,m


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
    identity=dict(version='actual-native-next-bank-zero-load-materials-300-v1',parent=str(parent.relative_to(root)),
        inputs=inputs,source_case='2',shared_interbank_wires='ideal',qualified_phy=False,
        active_loaded_numerical_parity_pending=True,
        scope='Prepared zero-code native next-bank loading diagnostics only; no simulations, DLL/detector fanout RC, all-PVT or PHY admission')
    out=root/'build/diagnostics/next_bank_zero_materials_300'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
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
    if (out.parent!=root/'build/diagnostics/next_bank_zero_materials_300'
            or i['version']!='actual-native-next-bank-zero-load-materials-300-v1'
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
