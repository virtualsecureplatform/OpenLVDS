#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Prepare six actual native core/bias pilots from a qualified physical assembly."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path

import assemble_driver_compact_native as assembly
import observe_compact_driver_loop as observation
import probe_driver_compact_native as pilot
from prepare_driver_native_bias_pilot import native_bias_only
from layout import circuits,flatten
from receiver_static_diagnosis import capture_manifest

ROOT=Path(__file__).resolve().parents[1]
sha=assembly.sha


def analog_targets(source,placements):
    devices=flatten(circuits(source),assembly.TOP)[1];by_name={d['name']:d for d in devices}
    result={}
    for label,fragment,index,pin in [('CM','__XRCP',1,'R2'),('CMS','__XRCM0',1,'R2'),
            ('CMFB_L','__XCM__XNP_',0,'D'),('CMFB_T','__XCM__XNT_',0,'D')]:
        found=[p for p in placements if any((fragment in n if fragment.endswith('_') else n==assembly.TOP+fragment) for n in p['members'])]
        if len(found)!=1:raise ValueError('Ambiguous logical analog observation '+label)
        p=found[0]
        members=[by_name[n] for n in p['members'] if fragment in n]
        expected=assembly.TOP+'__'+(label if not label.startswith('CMFB_') else 'XCM__'+label[-1])
        if not members or {d['nodes'][index] for d in members}!={expected}:
            raise ValueError('Analog observation lost its original source net '+label)
        result[label]=dict(physical_pin=p['instance']+'.'+pin,source_net=expected,members=[d['name'] for d in members])
    return result


def prepare(assembled):
    a=json.loads((assembled/'summary.json').read_text());extraction=ROOT/a['identity']['extraction']
    if (a.get('assembly_complete') is not True or a.get('component_reference_count')!=1 or
            a.get('two_core_endpoint_reference_count')!=1 or assembly.assemble(extraction)!=assembled):
        raise ValueError('Require a complete audited native core/bias assembly')
    # Reuse the existing strict source-readiness/physical/fixture preparer,
    # but do not execute its hybrid source-bias model as the final candidate.
    base=pilot.prepare(extraction);m=pilot.bound(base)
    if any((base/t['id']/n).exists() for t in m['tasks'] for n in ['bench.raw','summary.json','ngspice.log']):
        raise ValueError('Expected an unexecuted source-bias preparation context')
    model=native_bias_only((base/'tt_25_negative_op/source.spice').read_text(),(assembled/'native.spice').read_text())
    r=json.loads((extraction/'summary.json').read_text());layout=ROOT/r['identity']['parent']
    p=json.loads((layout/'summary.json').read_text())
    extra=assembly.observations((assembled/'observation_flat.ext').read_text(),assembly.text_block(model,assembly.TOP),
        analog_targets((assembled/'schematic.spice').read_text(),p['designs'][assembly.TOP]['placements']))
    observations=dict(a['observations'],**extra)
    inputs=dict(m['identity']['inputs'],**a['identity']['inputs'])
    inputs.update({str((assembled/n).relative_to(ROOT)):h for n,h in a['files'].items()})
    paths=[base/'manifest.json',assembled/'summary.json']+[base/t['id']/n for t in m['tasks'] for n in t['files']]
    inputs.update({str(n.relative_to(ROOT)):sha(n) for n in paths})
    code=dict(m['identity']['code'],**a['identity']['code'])
    code.update({n:sha(ROOT/'scripts'/n) for n in ['prepare_driver_complete_native_pilot.py',
        'prepare_driver_native_bias_pilot.py','observe_compact_driver_loop.py','driver_native_stress.py']})
    identity=dict(extraction=str(extraction.relative_to(ROOT)),source=m['identity']['source'],
        assembly=str(assembled.relative_to(ROOT)),unexecuted_source_bias_preparation=str(base.relative_to(ROOT)),
        points=[list(p) for p in pilot.POINTS],inputs=inputs,code=code,simulator=pilot.provenance(),
        view='native_core_and_native_bias',scope='Six complete native core-plus-native-bias '
        'output pilots at TT25/SS25/FF40 and both initial polarities. Original full '
        '80 ns/1 ps stimulus, fixed rails/reference and 100 ohm plus 2 pF/pin. '
        'Core and bias each have source/GDS binding and strict independent RC LVS. '
        'Every actual MOS terminal and source-identified CMFB sensing/mirror/tail '
        'conductor recorded, with no ideal alias. Public outputs use the original '
        'calibrated pilot checks. No long-component, reliability, complete PVT or '
        'PHY admission from preparation or a partial pilot.')
    out=ROOT/'build/diagnostics/driver_compact_native_pilot'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=True);tasks=[]
    with (out/'.preparation.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        for task in m['tasks']:
            old=base/task['id'];folder=out/task['id'];folder.mkdir(exist_ok=True)
            deck,probes,mos=observation.fixture((old/'bench.cir').read_text(),old,folder,model,observations)
            for name,body in [('source.spice',model),('bench.cir',deck),('probes.json',json.dumps(probes,sort_keys=True,indent=2)+'\n'),
                              ('mos_observations.json',json.dumps(mos,sort_keys=True,indent=2)+'\n')]:
                path=folder/name
                if path.exists() and path.read_text()!=body:raise ValueError('Prepared complete native pilot changed')
                if not path.exists():path.write_text(body)
            row={k:v for k,v in task.items() if k!='files'}
            row['files']={n:sha(folder/n) for n in ['source.spice','bench.cir','probes.json','mos_observations.json']};tasks.append(row)
        capture_manifest(out/'manifest.json',dict(identity=identity,tasks=tasks,qualified_phy=False))
    return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('assembly',type=Path);a=p.parse_args()
    print(prepare(a.assembly.resolve()),flush=True)
