#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Test a freshly extracted 2x3 fine unit against the measured overlap gap.

Independently read the two terminal core2 cases while other parent variants may
remain live. Keep those files intact. Replace all 31 units with the distinct
DRC/LVS/RC-audited larger unit; never relabel the old 2x2 extracted geometry.
"""
import argparse
from contextlib import contextmanager
import hashlib
import itertools
import json
from pathlib import Path
import mim_switch_2x3_v2 as unit
import probe_dcdl_balanced_drive_v2 as parent_source
import verify_digital_clocking_v2 as reader
from spice_library import checked_netlist
from lvs_utils import clean_match

ROOT=parent_source.ROOT
h=parent_source.h
batch=parent_source.batch
VERSION='hybrid-balanced-core-larger-extracted-fine-unit-v2.1'


def specifications():
    return [dict(process=p,temperature=t,coarse=c,codes=[0,1,16,31,0],restore='mim2x2',
                 control_slew_ps=20,variant='core2') for (p,t),c in itertools.product([('ss',40),('fs',40),('ff',0)],[0,1])]


def replace_unit(text):
    old=parent_source.parent_source.UNIT
    lines=[line for line in text.splitlines() if line.startswith('XU')]
    if len(lines)!=31 or any(line.split()[-1]!=old for line in lines):raise ValueError('Original 31-unit bank changed')
    if text.count(old)!=31:raise ValueError('Unexpected original-unit references')
    return text.replace(old,unit.NAME)


def parent_failure(parent):
    m=parent_source.bound(parent);rows=[];files={str((parent/'manifest.json').relative_to(ROOT)):h.sha(parent/'manifest.json')}
    for case in ['0','1']:
        folder=parent/case;path=folder/'summary.json';stamp=h.sha(path);row=json.loads(path.read_text());task=m['tasks'][int(case)]
        if row['task']!=task or task['spec']['variant']!='core2' or task['spec']['coarse']!=int(case) or row['error'] is not None:
            raise ValueError('Require both terminal core2 coarse cases')
        if not reader.REQUIRED<=set(row['files']) or any(h.sha(folder/n)!=v for n,v in row['files'].items()):
            raise ValueError('Parent terminal witnesses changed')
        reader.export_matches_raw(folder)
        measured=parent_source.measure(folder,task)
        if measured!=row['result'] or not measured['custom_mos_stress_passed']:raise ValueError('Parent delay/stress did not reproduce')
        if h.sha(path)!=stamp or any(h.sha(folder/n)!=v for n,v in row['files'].items()):raise ValueError('Parent witnesses changed while read')
        files[str(path.relative_to(ROOT))]=stamp
        files.update({str((folder/n).relative_to(ROOT)):v for n,v in row['files'].items()});rows.append(row)
    first=rows[0]['result'];second=rows[1]['result']
    maximum_fine=max(s['rise_delay_ps'] for s in first['samples'] if s['code']==31)
    minimum_next=min(s['rise_delay_ps'] for s in second['samples'] if s['code']==0)
    if maximum_fine>=minimum_next:raise ValueError('Require reproduced rising coarse/fine overlap failure')
    if max(s['rise_delay_ps'] for s in first['samples'] if s['code']==0)>=first['required_quarter_range_ps'][0]:
        raise ValueError('Balanced source has no minimum-delay headroom')
    parent_source.bound(parent)
    return m,files,dict(rising_gap_ps=minimum_next-maximum_fine,rows=rows)


def prepare(receipt,parent):
    if not receipt.is_relative_to(ROOT/'build/diagnostics/mim_switch_2x3_verification_v2'):raise ValueError('Require independent larger-unit RC receipt')
    proof=json.loads((receipt/'summary.json').read_text());info=proof['verified_model']
    if proof['rc_topology_passed'] is not True or proof['qualified_phy'] is not False or not clean_match((receipt/'lvs.log').read_text()):
        raise ValueError('Larger-unit topology is not independently passing')
    if any(h.sha(ROOT/n)!=v for n,v in proof['identity']['witnesses'].items()):raise ValueError('Unit witnesses changed')
    text=checked_netlist(info)
    headers=[line.split() for line in text.splitlines() if line.lower().startswith('.subckt ')]
    if headers!=[['.subckt',unit.NAME,'NODE','EN','ENB','VDD','VSS']]:raise ValueError('Wrong larger-unit model')
    m,inputs,failure=parent_failure(parent)
    inputs.update(proof['identity']['witnesses'])
    inputs.update({str((receipt/n).relative_to(ROOT)):h.sha(receipt/n) for n in ['summary.json','lvs.log']})
    inputs.update({str((parent/n).relative_to(ROOT)):h.sha(parent/n) for n in ['cells.spice','coarse0_core2.spice','coarse1_core2.spice']})
    code=[Path(__file__),Path(unit.__file__),Path(parent_source.__file__),Path(reader.__file__),
        ROOT/'scripts/probe_dcdl_rc_drive_v2.py',ROOT/'scripts/probe_dcdl_unit_rc_v2.py',
        ROOT/'scripts/probe_dcdl_node_bank_pvt_v2.py',ROOT/'scripts/probe_dcdl_charge_kick_v2.py',
        ROOT/'scripts/probe_dcdl_control_margin_v2.py',ROOT/'scripts/probe_dcdl_control_restore_v2.py',
        ROOT/'scripts/analyze_dcdl_batch_v2.py',ROOT/'scripts/probe_digital_dcdl_batch_v2.py',
        ROOT/'scripts/probe_digital_dcdl_v2.py',ROOT/'scripts/probe_digital_dcc_v2.py',
        ROOT/'scripts/spice_library.py',ROOT/'scripts/lvs_utils.py',ROOT/'scripts/run_ngspice.py',
        ROOT/'scripts/spice_dispatch.py',ROOT/'scripts/spice_engine.py',ROOT/'scripts/env.sh',
        ROOT/'requirements.json',ROOT/'clocking_v2.json',ROOT/'build/apptainer/openlvds.sif.sha256']
    specs=specifications()
    identity=dict(version=VERSION,code={str(p.relative_to(ROOT)):h.sha(p) for p in code},inputs=inputs,
        parent=str(parent.relative_to(ROOT)),unit_model=info,pdk=m['identity']['pdk'],pdk_sha256=m['identity']['pdk_sha256'],
        model_library=m['identity']['model_library'],model_library_sha256=m['identity']['model_library_sha256'],
        simulator=h.provenance(),specs=specs,unit_geometry_um=[2,3])
    out=ROOT/'build/diagnostics/dcdl_larger_unit_v2'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);h.write(out/'cells.spice',(parent/'cells.spice').read_text());h.write(out/'unit_rc.spice',text)
    h.atomic(out/'parent_gap.json',failure)
    for coarse in [0,1]:h.write(out/f'coarse{coarse}_core2.spice',replace_unit((parent/f'coarse{coarse}_core2.spice').read_text()))
    tasks=[];devices=parent_source.parent_source.devices(text)
    for n,spec in enumerate(specs):
        folder=out/str(n);folder.mkdir();h.write(folder/'bench.cir',parent_source.fixture(out,spec,devices))
        tasks.append(dict(id=str(n),spec=spec,devices=devices,deck_sha256=h.sha(folder/'bench.cir')))
    h.atomic(out/'manifest.json',dict(identity=identity,tasks=tasks,libraries={p.name:h.sha(p) for p in out.glob('*.spice')},
        parent_gap_sha256=h.sha(out/'parent_gap.json'),qualified_phy=False))
    return out


def bound(out):
    if not out.is_relative_to(ROOT/'build/diagnostics/dcdl_larger_unit_v2'):raise ValueError('Wrong larger-unit hybrid context')
    m=h.bound(out);i=m['identity']
    if (i['version']!=VERSION or h.sha(Path(i['model_library']))!=i['model_library_sha256']
        or any(h.sha(ROOT/n)!=v for n,v in i['inputs'].items()) or [t['spec'] for t in m['tasks']]!=specifications()
        or h.sha(out/'parent_gap.json')!=m['parent_gap_sha256']):raise ValueError('Larger-unit context or witnesses changed')
    return m


def measure(folder,task):
    return dict(parent_source.parent_source.measure(folder,task),version=VERSION,
        variant='core2',unit_geometry_um=[2,3],
        scope='Sparse source core plus exact larger-unit RC only; no compound-cell, full-bank, dense ROM, all-PVT or PHY admission')


@contextmanager
def profile():
    before=batch.bound,batch.measure;batch.bound=bound;batch.measure=measure
    try:yield
    finally:batch.bound,batch.measure=before


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','bound']);p.add_argument('artifact',type=Path)
    p.add_argument('--parent',type=Path);a=p.parse_args()
    if a.action=='prepare':
        if a.parent is None:p.error('Provide --parent balanced-drive context')
        print(prepare(a.artifact.resolve(),a.parent.resolve()),flush=True)
    elif a.action=='bound':print(json.dumps(bound(a.artifact.resolve()),indent=2))
    else:
        with profile():batch.run(a.artifact.resolve())
