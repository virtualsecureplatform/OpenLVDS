#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Dense all-PVT source curves and bulk-update health for a native node shunt.

Characterize TX coarse-count 16 at coarse codes 0/1 and all 32 fine codes.
Each coarse/PVT also repeats the worst bidirectional bulk code sequence. The
4x4 r0 shunt is explored first for its SS40 source stress headroom; this is no
minimum-area selection or transfer of source proof to physical admission.
"""
import argparse
from contextlib import contextmanager
import hashlib
import itertools
import json
from pathlib import Path
import probe_dcdl_charge_kick_v2 as pilot
import verify_dcdl_charge_kick_v2 as evidence

h=pilot.h
ROOT=pilot.ROOT
batch=pilot.parent_source.original
VERSION='dcdl-node-shunt-dense-pvt-v2.1'


def specifications(req,geometry):
    if geometry not in (2,4):raise ValueError('Undeclared node-shunt geometry')
    patterns=[('dense_'+str(n),list(range(n,n+8))) for n in range(0,32,8)]
    patterns.append(('bulk',pilot.parent_source.CODES))
    return [dict(process=p,temperature=t,coarse=c,codes=codes,pattern=pattern,
                 node_geometry_um=geometry,restore='mim2x2',control_slew_ps=20)
        for p,t,c,(pattern,codes) in itertools.product(req['process_corners'],req['temperatures_c'],[0,1],patterns)]


def circuit(coarse,geometry):
    text,devices=batch.policy.circuit(coarse)
    return pilot.circuit(text,'node_mim'+str(geometry)+'x'+str(geometry)),devices


def fixture(out,spec):
    return pilot.parent_source.fixture(out,spec)


def prepare(parent,geometry):
    proof=evidence.report(parent);m=pilot.bound(parent)
    repair=f'node_mim{geometry}x{geometry}'
    candidates=[c for c in proof['candidates'] if c['repair']==repair and c['source_stress_passed']]
    if proof['cases']!=4 or proof['numerical_errors'] or len(candidates)!=1:
        raise ValueError('Require independently passing node-shunt pilot')
    text,_=circuit(0,geometry)
    if text!=(parent/f'coarse0_{repair}.spice').read_text():raise ValueError('Passing node-shunt topology differs')
    files=[Path(__file__),Path(pilot.__file__),Path(evidence.__file__),
        ROOT/'scripts/probe_dcdl_control_margin_v2.py',ROOT/'scripts/probe_dcdl_control_restore_v2.py',
        ROOT/'scripts/analyze_dcdl_batch_v2.py',ROOT/'scripts/probe_digital_dcdl_batch_v2.py',
        ROOT/'scripts/dcdl_cap_strong_v2.py',ROOT/'scripts/dcdl_cap_bank_v2.py',
        ROOT/'scripts/probe_digital_dcdl_v2.py',ROOT/'scripts/probe_digital_dcc_v2.py',
        ROOT/'scripts/verify_digital_clocking_v2.py',ROOT/'scripts/run_ngspice.py',
        ROOT/'scripts/spice_dispatch.py',ROOT/'scripts/spice_engine.py',ROOT/'scripts/env.sh',
        ROOT/'requirements.json',ROOT/'clocking_v2.json',ROOT/'build/apptainer/openlvds.sif.sha256']
    specs=specifications(json.loads((ROOT/'requirements.json').read_text()),geometry)
    identity=dict(version=VERSION,code={str(p.relative_to(ROOT)):h.sha(p) for p in files},
        parent=str(parent.relative_to(ROOT)),
        parent_inputs={str((parent/n).relative_to(ROOT)):h.sha(parent/n) for n in ['manifest.json','summary.json','state.json']},
        pdk=m['identity']['pdk'],pdk_sha256=m['identity']['pdk_sha256'],model_library=m['identity']['model_library'],
        model_library_sha256=m['identity']['model_library_sha256'],simulator=h.provenance(),specs=specs,
        coarse_count=16,node_geometry_um=geometry,coarse_codes=[0,1],fine_codes=list(range(32)),
        control_slew_ps=20,maximum_step_ps=2,load_ff=20)
    out=ROOT/'build/diagnostics/dcdl_node_bank_pvt_v2'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);h.write(out/'cells.spice',(parent/'cells.spice').read_text())
    for c in [0,1]:h.write(out/f'coarse{c}.spice',circuit(c,geometry)[0])
    tasks=[]
    for n,spec in enumerate(specs):
        folder=out/str(n);folder.mkdir();h.write(folder/'bench.cir',fixture(out,spec))
        tasks.append(dict(id=str(n),spec=spec,devices=circuit(spec['coarse'],geometry)[1],deck_sha256=h.sha(folder/'bench.cir')))
    h.atomic(out/'manifest.json',dict(identity=identity,tasks=tasks,
        libraries={p.name:h.sha(p) for p in out.glob('*.spice')},qualified_phy=False))
    return out


def bound(out):
    if not out.is_relative_to(ROOT/'build/diagnostics/dcdl_node_bank_pvt_v2'):
        raise ValueError('Wrong node-bank PVT context')
    m=h.bound(out);i=m['identity']
    if (i['version']!=VERSION or h.sha(Path(i['model_library']))!=i['model_library_sha256']
        or any(h.sha(ROOT/n)!=v for n,v in i['parent_inputs'].items())):
        raise ValueError('Node-bank PVT inputs changed')
    if [t['spec'] for t in m['tasks']]!=specifications(json.loads((ROOT/'requirements.json').read_text()),i['node_geometry_um']):
        raise ValueError('Node-bank PVT coverage changed')
    return m


def measure(folder,task):
    return dict(pilot.parent_source.restore.analysis.measure(folder,task),version=VERSION,
        node_geometry_um=task['spec']['node_geometry_um'],
        scope='Dense source code curves and bulk-update stress only; no legal ROM, RX range, physical or PHY admission')


@contextmanager
def profile():
    previous=batch.bound,batch.measure;batch.bound=bound;batch.measure=measure
    try:yield
    finally:batch.bound,batch.measure=previous


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','bound'])
    p.add_argument('artifact',type=Path);p.add_argument('--geometry',type=int,choices=[2,4],default=4);a=p.parse_args()
    if a.action=='prepare':print(prepare(a.artifact.resolve(),a.geometry),flush=True)
    elif a.action=='bound':print(json.dumps(bound(a.artifact.resolve()),indent=2))
    else:
        with profile():batch.run(a.artifact.resolve())
