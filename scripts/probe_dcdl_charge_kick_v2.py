#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Compare shared-node capacitance and serialized control updates.

Both EB shunt geometries fail a simultaneous 31-bit falling update at 20 ps:
r0 drops below -0.16 V, exceeding the unchanged 1.95 V PMOS terminal limit.
Keep the 2x2 EB shunts and compare a native r0 MIM against single-bit updates.
This is bounded source diagnosis, not a delay ROM or physical admission.
"""
import argparse
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import probe_dcdl_control_margin_v2 as parent_source
import verify_dcdl_control_margin_v2 as evidence

h=parent_source.h
ROOT=parent_source.ROOT
VERSION='dcdl-control-shared-node-charge-kick-v2.1'
REPAIRS=['single_low','single_high','node_mim2x2','node_mim4x4']


def specification(repair):
    if repair not in REPAIRS:raise ValueError('Undeclared charge-kick repair')
    codes=([0,1]*4 if repair=='single_low' else
           [31,30]*4 if repair=='single_high' else parent_source.CODES)
    return dict(process='ss',temperature=40,coarse=0,codes=codes,
                restore='mim2x2',control_slew_ps=20,repair=repair)


def circuit(parent_text,repair):
    if repair not in REPAIRS:raise ValueError('Undeclared charge-kick repair')
    if repair.startswith('node_mim'):
        dimension=2 if repair=='node_mim2x2' else 4
        if parent_text.count('.ends dcdl_source')!=1:raise ValueError('Parent source closure changed')
        parent_text=parent_text.replace('.ends dcdl_source',
            f'XCKICK r0 VSS sky130_fd_pr__cap_mim_m3_1 w={dimension} l={dimension}\n.ends dcdl_source')
    return parent_text


def fixture(out,spec):
    text=parent_source.fixture(out,spec)
    name=f'coarse0_{spec["repair"]}.spice'
    if text.count('/coarse0.spice"')!=1:raise ValueError('Parent fixture source include changed')
    return text.replace('/coarse0.spice"','/'+name+'"')


def prepare(parent):
    proof=evidence.report(parent);m=parent_source.bound(parent)
    if proof['cases']!=6 or proof['numerical_errors']:
        raise ValueError('Require the complete independently remeasured margin matrix')
    rows=json.loads((parent/'summary.json').read_text())['rows']
    fast=[r for r in rows if r['task']['spec']['control_slew_ps']==20]
    if len(fast)!=2 or not all(r['result']['custom_mos_stress_passed'] is False for r in fast):
        raise ValueError('Missing reproduced fast-update failures')
    files=[Path(__file__),Path(parent_source.__file__),Path(evidence.__file__),
        ROOT/'scripts/probe_dcdl_control_restore_v2.py',ROOT/'scripts/analyze_dcdl_batch_v2.py',
        ROOT/'scripts/probe_digital_dcdl_batch_v2.py',ROOT/'scripts/dcdl_cap_strong_v2.py',
        ROOT/'scripts/dcdl_cap_bank_v2.py',ROOT/'scripts/probe_digital_dcdl_v2.py',
        ROOT/'scripts/probe_digital_dcc_v2.py',ROOT/'scripts/verify_digital_clocking_v2.py',
        ROOT/'scripts/run_ngspice.py',ROOT/'scripts/spice_dispatch.py',ROOT/'scripts/spice_engine.py',
        ROOT/'scripts/env.sh',ROOT/'requirements.json',ROOT/'clocking_v2.json',ROOT/'build/apptainer/openlvds.sif.sha256']
    specs=[specification(r) for r in REPAIRS]
    identity=dict(version=VERSION,code={str(p.relative_to(ROOT)):h.sha(p) for p in files},
        parent=str(parent.relative_to(ROOT)),
        parent_inputs={str((parent/n).relative_to(ROOT)):h.sha(parent/n) for n in ['manifest.json','summary.json','state.json']},
        pdk=m['identity']['pdk'],pdk_sha256=m['identity']['pdk_sha256'],model_library=m['identity']['model_library'],
        model_library_sha256=m['identity']['model_library_sha256'],simulator=h.provenance(),specs=specs)
    out=ROOT/'build/diagnostics/dcdl_charge_kick_v2'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);h.write(out/'cells.spice',(parent/'cells.spice').read_text())
    source=(parent/'coarse0.spice').read_text();tasks=[]
    for n,spec in enumerate(specs):
        h.write(out/f'coarse0_{spec["repair"]}.spice',circuit(source,spec['repair']))
        folder=out/str(n);folder.mkdir();h.write(folder/'bench.cir',fixture(out,spec))
        tasks.append(dict(id=str(n),spec=spec,devices=m['tasks'][0]['devices'],deck_sha256=h.sha(folder/'bench.cir')))
    h.atomic(out/'manifest.json',dict(identity=identity,tasks=tasks,
        libraries={p.name:h.sha(p) for p in out.glob('*.spice')},qualified_phy=False))
    return out


def bound(out):
    if not out.is_relative_to(ROOT/'build/diagnostics/dcdl_charge_kick_v2'):
        raise ValueError('Wrong charge-kick context')
    m=h.bound(out);i=m['identity']
    if (i['version']!=VERSION or h.sha(Path(i['model_library']))!=i['model_library_sha256']
        or any(h.sha(ROOT/n)!=v for n,v in i['parent_inputs'].items())):
        raise ValueError('Charge-kick inputs changed')
    for task in m['tasks']:
        if (out/task['id']/'bench.cir').read_text()!=fixture(out,task['spec']):
            raise ValueError('Charge-kick fixture changed')
    return m


def measure(folder,task):
    return dict(parent_source.restore.analysis.measure(folder,task),version=VERSION,
        repair=task['spec']['repair'],scope='SS40 shared-node source repair only; no PVT, ROM or physical admission')


@contextmanager
def profile():
    original=parent_source.original;previous=original.bound,original.measure
    original.bound=bound;original.measure=measure
    try:yield
    finally:original.bound,original.measure=previous


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','bound']);p.add_argument('artifact',type=Path);a=p.parse_args()
    if a.action=='prepare':print(prepare(a.artifact.resolve()),flush=True)
    elif a.action=='bound':print(json.dumps(bound(a.artifact.resolve()),indent=2))
    else:
        with profile():parent_source.original.run(a.artifact.resolve())
