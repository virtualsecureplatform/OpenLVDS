#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Pair the compact native core with audited native bias and real RC observations."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import re

import extract_driver_compact as physical
from dll_campaign import bias_reference_count, text_block
from layout import circuits, flatten, invoke_magic
from receiver_static_diagnosis import capture_manifest
from spice_library import checked_netlist, library, replace

ROOT=Path(__file__).resolve().parents[1]
sha=physical.sha
TOP=physical.TOP
OBSERVATIONS={
    'DP':('__XLS__XB0_S2_0__XP_',0), 'DN':('__XLS__XB1_S2_0__XP_',0),
    'TOP':('__XIT0_',0), 'BOT':('__XIB0_',0), 'SINK':('__XIB0_',1),
    'XLS__AD':('__XLS__XIN1__XP_',0), 'XLS__AB':('__XLS__XI__XP_',0),
    'XLS__L':('__XLS__XNA0_',0), 'XLS__R':('__XLS__XNB0_',0),
    'XLS__G0_0':('__XLS__XB0_S0_0__XP_',0), 'XLS__G0_1':('__XLS__XB0_S1_0__XP_',0),
    'XLS__G1_0':('__XLS__XB1_S0_0__XP_',0), 'XLS__G1_1':('__XLS__XB1_S1_0__XP_',0)}


def observation_targets(source,placements):
    devices=flatten(circuits(source),TOP)[1]
    by_name={d['name']:d for d in devices}
    result={}
    for leaf,(fragment,terminal) in OBSERVATIONS.items():
        matching=[p for p in placements if any(fragment in n for n in p['members'])]
        if len(matching)!=1: raise ValueError('Ambiguous physical observation '+leaf)
        p=matching[0]
        members=[by_name[n] for n in p['members'] if fragment in n]
        if {d['nodes'][terminal] for d in members}!={TOP+'__'+leaf}:
            raise ValueError('Physical member does not carry original observation '+leaf)
        pin=('Y' if terminal==0 else 'A') if p['cell'].startswith('inv_') else ('D' if terminal==0 else 'G')
        result[leaf]=dict(physical_pin=p['instance']+'.'+pin,cell=p['cell'],members=[d['name'] for d in members])
    return result


def native_nodes(model):
    result=set()
    for line in model.splitlines():
        w=line.split()
        if not w: continue
        if w[0][0].lower() in ['r','c']: result.update(w[1:3])
        elif w[0][0].lower()=='x':
            end=next((i for i,v in enumerate(w) if '=' in v),len(w))
            result.update(w[1:end-1])
    return result


def observations(ext,model,targets):
    """Resolve fresh GDS conductor equivalences to retained bare RC labels."""
    parents={};anchors={}
    def root(n):
        parents.setdefault(n,n)
        if parents[n]!=n: parents[n]=root(parents[n])
        return parents[n]
    for line in ext.splitlines():
        match=re.fullmatch(r'equiv "([^"]+)" "([^"]+)"',line)
        if match: parents[root(match[2])]=root(match[1])
        elif line.startswith('node '):
            w=line.split()
            name=w[1].strip('"')
            root(name);anchors[name]=dict(x_grid=int(w[4]),y_grid=int(w[5]),layer=w[6])
    retained=native_nodes(model)
    result={}
    for leaf,target in targets.items():
        pin=target['physical_pin']
        if pin not in parents: raise ValueError('Fresh GDS lacks physical observation '+pin)
        candidates=[n for n in anchors if root(n)==root(pin) and n in retained]
        if len(candidates)!=1: raise ValueError('Require one retained named GDS conductor for '+pin)
        node=candidates[0]
        result[leaf]=dict(target,native_node=node,gds_anchor=anchors[node],
            scope='Existing RC conductor label; no ideal alias, short or .tN terminal substitution.')
    if len({v['native_node'] for v in result.values()})!=len(result):
        raise ValueError('Distinct source observation nets merged physically')
    return result


def assemble(parent):
    if not parent.is_relative_to(ROOT/'build/diagnostics/driver_compact_extraction'):
        raise ValueError('Use compact-driver GDS extraction evidence')
    r=json.loads((parent/'summary.json').read_text())
    if r.get('passed') is not True or r['rc_audit']['passed'] is not True:
        raise ValueError('Require native driver RC audit')
    layout=ROOT/r['identity']['parent']
    if physical.run(layout)!=parent: raise ValueError('Driver extraction context changed')
    p=json.loads((layout/'summary.json').read_text());source=(layout/'candidate.spice').read_text()
    core=checked_netlist(r['extraction'])
    baseline,bias_inputs,_=library(extracted=True,designs={'lvds_bias'})
    bias_audit=json.loads((ROOT/'build/rc_audit/summary.json').read_text())['designs']['lvds_bias']
    if (bias_audit.get('passed') is not True or bias_audit['netlist_sha256']!=bias_inputs['lvds_bias'] or
            sha(ROOT/bias_audit['report'])!=bias_audit['report_sha256']):
        raise ValueError('Native bias lacks current independent RC LVS')
    native=replace(replace(source,TOP,core),'lvds_bias',text_block(baseline.decode(),'lvds_bias'))
    component='XD D P N VR PB VA VD 0 openlvds_driver'
    endpoint='''XB PB NB VA 0 lvds_bias
XCT CLK CP CN VR PB NB VA VD 0 openlvds_driver_core
XDT DATA DP DN VR PB NB VA VD 0 openlvds_driver_core'''
    if bias_reference_count(component,native)!=1 or bias_reference_count(endpoint,native)!=1:
        raise ValueError('Require exactly one shared bias reference per endpoint')
    paths=[parent/'summary.json',layout/'summary.json',ROOT/'build/extracted/current.json',
        ROOT/'build/layout/current.json',ROOT/'build/rc_audit/summary.json',ROOT/bias_audit['report']]
    bias_info=json.loads((ROOT/'build/extracted/current.json').read_text())['designs']['lvds_bias']
    bias_physical=json.loads((ROOT/'build/layout/current.json').read_text())['designs']['lvds_bias']
    paths += [ROOT/bias_info['netlist'],ROOT/bias_physical['gds']]
    inputs=dict(p['identity']['inputs'],**r['files'])
    inputs.update({str((layout/n).relative_to(ROOT)):h for n,h in p['files'].items()})
    inputs.update({str(n.relative_to(ROOT)):sha(n) for n in paths})
    code=dict(p['identity']['code'],**r['identity']['code'])
    code.update({n:sha(ROOT/'scripts'/n) for n in ['assemble_driver_compact_native.py','spice_library.py','spice_probes.py']})
    identity=dict(extraction=str(parent.relative_to(ROOT)),inputs=inputs,code=code,
        technology=p['identity']['technology'],native_bias_sha256=bias_inputs['lvds_bias'],
        scope='Preparation only: audited native driver core plus audited native shared '
              'bias and retained diagnostic RC labels. One reference per endpoint. '
              'No native electrical, MOS-stress, long-component or PHY admission.')
    out=ROOT/'build/diagnostics/driver_compact_native_library'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=True)
    def unchanged():
        if (any(sha(ROOT/n)!=h for n,h in inputs.items()) or any(sha(ROOT/'scripts'/n)!=h for n,h in code.items()) or
                any(sha(Path(n))!=h for n,h in identity['technology'].items())):
            raise ValueError('Native driver/bias assembly context changed')
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);unchanged()
        if (out/'summary.json').exists():
            old=json.loads((out/'summary.json').read_text())
            if old['identity']!=identity or any(sha(out/n)!=h for n,h in old['files'].items()):
                raise ValueError('Native driver/bias assembly outputs changed')
            return out
        if (out/'manifest.json').exists(): raise ValueError('Partial native library assembly retained')
        capture_manifest(out/'manifest.json',dict(identity=identity,qualified_phy=False))
        (out/'schematic.spice').write_text(source);(out/'native.spice').write_text(native)
        gds=ROOT/p['designs'][TOP]['gds']
        invoke_magic(out,f'''gds read {gds}
load {TOP}
flatten observation_flat
load observation_flat
extract style ngspice()
extract all''','observe_gds')
        observed=observations((out/'observation_flat.ext').read_text(),core,
                              observation_targets(source,p['designs'][TOP]['placements']))
        capture_manifest(out/'observations.json',observed)
        unchanged()
        files={n.name:sha(n) for n in out.iterdir() if n.is_file() and n.name not in ['.execution.lock','summary.json']}
        capture_manifest(out/'summary.json',dict(identity=identity,assembly_complete=True,
            observations=observed,component_reference_count=1,two_core_endpoint_reference_count=1,
            files=files,qualified_phy=False,physical_admission=False,electrical_admission=False))
    return out


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('parent',type=Path);args=parser.parse_args()
    print(assemble(args.parent.resolve()),flush=True)
