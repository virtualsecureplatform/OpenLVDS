#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Change only the audited bias macro in the native core's six output pilots."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path

import assemble_driver_compact_native as assembly
import observe_compact_driver_loop as observation
import probe_driver_compact_native as pilot
from dll_campaign import text_block
from receiver_static_diagnosis import capture_manifest
from spice_library import replace

ROOT=Path(__file__).resolve().parents[1]
sha=assembly.sha


def native_bias_only(original,native):
    result=replace(original,'lvds_bias',text_block(native,'lvds_bias'))
    if result!=native or text_block(original,assembly.TOP)!=text_block(native,assembly.TOP):
        raise ValueError('Native bias control changed a block other than lvds_bias')
    if text_block(original,'lvds_bias')==text_block(native,'lvds_bias'):
        raise ValueError('Bias control must compare distinct source/native bias models')
    return result


def prepare(observer):
    om=observation.bound(observer);oi=om['identity']
    parent=ROOT/oi['parent'];m=pilot.bound(parent)
    assembled=ROOT/oi['assembly'];a=json.loads((assembled/'summary.json').read_text())
    if assembly.assemble(ROOT/a['identity']['extraction'])!=assembled:
        raise ValueError('Native core/bias assembly changed')
    rows=[];paths=[]
    for op in pilot.reference.shape.CASES:
        old=parent/('tt_25_'+op);r=json.loads((old/'summary.json').read_text())
        if (r.get('returncode')!=0 or r.get('error') is not None or
                r.get('manifest_sha256')!=sha(parent/'manifest.json') or
                any(sha(old/n)!=h for n,h in r['files'].items()) or
                pilot.measure(old)!=(r['metrics'],r['initial_dc']) or
                r['metrics']['rising_output_edges']!=22 or r['metrics']['common_mode_pp_v']<=.150):
            raise ValueError('Require both completed source-bias TT25 common-mode failures')
        paths += [old/n for n in [*r['files'],'summary.json']]
        rows.append(r)
    model=native_bias_only((parent/'tt_25_negative_op/source.spice').read_text(),(assembled/'native.spice').read_text())
    if len({(parent/t['id']/'source.spice').read_text() for t in m['tasks']})!=1:
        raise ValueError('Original pilot models differ across cases')
    inputs=dict(oi['inputs'])
    inputs.update({str((observer/n).relative_to(ROOT)):h for n,h in om['files'].items()})
    inputs.update({str((assembled/n).relative_to(ROOT)):h for n,h in a['files'].items()})
    paths += [parent/'manifest.json',observer/'manifest.json',assembled/'summary.json']
    paths += [parent/t['id']/n for t in m['tasks'] for n in t['files']]
    inputs.update({str(p.relative_to(ROOT)):sha(p) for p in paths})
    code=dict(oi['code'])
    code['prepare_driver_native_bias_pilot.py']=sha(Path(__file__))
    identity=dict(parent=str(parent.relative_to(ROOT)),extraction=m['identity']['extraction'],source=m['identity']['source'],
        native_bias_assembly=str(assembled.relative_to(ROOT)),inputs=inputs,code=code,simulator=pilot.provenance(),
        points=[list(p) for p in pilot.POINTS],view='native_core_and_native_bias',
        scope='Six actual native core-plus-native-bias output pilots at TT25/SS25/FF40, '
              'both initial polarities. Relative to the completed source-bias TT25 '
              'failures, only lvds_bias changes to its independently audited native '
              'network. Exact same native driver core, all original stimulus/rails/'
              'reference/load and 80 ns/1 ps accuracy. All 305 MOS terminal voltages '
              'and internal feedback/bias observations recorded. Generic pilot runner '
              'remeasures public outputs; internal stress remains separate sampled '
              'evidence, with no reliability or PHY admission. Passing this complete '
              'actual-native pilot may seed full native output and long-component '
              'qualification; a failing hybrid source-bias control does not substitute '
              'for measuring the actual final bias implementation.')
    out=ROOT/'build/diagnostics/driver_compact_native_pilot'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=True);tasks=[]
    with (out/'.preparation.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        for task in m['tasks']:
            old=parent/task['id'];folder=out/task['id'];folder.mkdir(exist_ok=True)
            deck,probes,mos=observation.fixture((old/'bench.cir').read_text(),old,folder,model,oi['observations'])
            for name,body in [('source.spice',model),('bench.cir',deck),('probes.json',json.dumps(probes,sort_keys=True,indent=2)+'\n'),
                              ('mos_observations.json',json.dumps(mos,sort_keys=True,indent=2)+'\n')]:
                path=folder/name
                if path.exists() and path.read_text()!=body: raise ValueError('Prepared native bias pilot changed')
                if not path.exists():path.write_text(body)
            row={k:v for k,v in task.items() if k!='files'}
            row['files']={n:sha(folder/n) for n in ['source.spice','bench.cir','probes.json','mos_observations.json']}
            tasks.append(row)
        capture_manifest(out/'manifest.json',dict(identity=identity,tasks=tasks,qualified_phy=False))
        capture_manifest(out/'source_bias_reference.json',dict(results=rows,source=str(parent.relative_to(ROOT)),qualified_phy=False))
    return out


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('observer',type=Path);args=parser.parse_args()
    print(prepare(args.observer.resolve()),flush=True)
