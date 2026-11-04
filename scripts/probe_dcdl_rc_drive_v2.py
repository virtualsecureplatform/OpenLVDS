#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Restore quarter-period headroom lost to measured fine-unit RC loading.

The independently verified SS40 hybrid minimum is 711.9 ps. Compare matched
parallel copies of the existing native turn/merge gates, keeping unit geometry,
node capacitance, input/output buffers and all device-stress limits intact.
Physical implementation of each compound gate remains an independent task.
"""
import argparse
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import probe_dcdl_unit_rc_v2 as parent_source
import verify_dcdl_unit_rc_v2 as evidence

h=parent_source.h
ROOT=parent_source.ROOT
batch=parent_source.batch
VERSION='hybrid-dcdl-rc-native-drive-repair-v2.1'
VARIANTS={'double_merge':(1,2),'double_turn_merge':(2,2),'triple_merge':(1,3)}


def circuit(text,variant):
    if variant not in VARIANTS:raise ValueError('Unknown native drive combination')
    turn,merge=VARIANTS[variant]
    for name,count,model in [('Xt0',turn,'sky130_fd_sc_hd__nand2b_4'),('Xm0',merge,'sky130_fd_sc_hd__nand2_8')]:
        rows=[line for line in text.splitlines() if line.startswith(name+' ')]
        if len(rows)!=1 or not rows[0].endswith(model):raise ValueError('Original native turn/merge gate changed')
        text=text.replace(rows[0],rows[0]+''.join('\n'+rows[0].replace(name+' ',name+f'_parallel{i} ',1) for i in range(1,count)))
    return text


def fixture(out,spec,devices):
    return parent_source.fixture(out,spec,devices).replace('/coarse0.spice"',f'/coarse0_{spec["variant"]}.spice"')


def prepare(parent):
    parent_source.bound(parent)
    # A complete consumer invocation verifies waveforms, not just summary bits.
    with evidence.profile():m,rows,files=evidence.reader.remeasure(parent)
    if (len(rows)!=1 or rows[0]['error'] is not None or not rows[0]['result']['custom_mos_stress_passed']
        or rows[0]['result']['hybrid_min_below_fast_quarter'] is not False):
        raise ValueError('Require independently remeasured stress-pass/quarter-range-failed unit RC')
    code=[Path(__file__),Path(parent_source.__file__),Path(evidence.__file__),Path(evidence.reader.__file__),
        ROOT/'scripts/probe_digital_dcdl_batch_v2.py',ROOT/'scripts/analyze_dcdl_batch_v2.py',
        ROOT/'scripts/probe_dcdl_control_margin_v2.py',ROOT/'scripts/probe_dcdl_control_restore_v2.py',
        ROOT/'scripts/probe_digital_dcdl_v2.py',ROOT/'scripts/probe_digital_dcc_v2.py',
        ROOT/'scripts/run_ngspice.py',ROOT/'scripts/spice_dispatch.py',ROOT/'scripts/spice_engine.py',
        ROOT/'scripts/env.sh',ROOT/'requirements.json',ROOT/'clocking_v2.json',ROOT/'build/apptainer/openlvds.sif.sha256']
    specs=[dict(rows[0]['task']['spec'],codes=[0,1,16,31,0],variant=v) for v in VARIANTS]
    identity=dict(version=VERSION,code={str(p.relative_to(ROOT)):h.sha(p) for p in code},
        inputs=files,parent=str(parent.relative_to(ROOT)),pdk=m['identity']['pdk'],pdk_sha256=m['identity']['pdk_sha256'],
        model_library=m['identity']['model_library'],model_library_sha256=m['identity']['model_library_sha256'],
        simulator=h.provenance(),specs=specs)
    out=ROOT/'build/diagnostics/dcdl_rc_drive_v2'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False)
    for n in ['cells.spice','unit_rc.spice']:h.write(out/n,(parent/n).read_text())
    text=(parent/'coarse0.spice').read_text();tasks=[]
    for n,spec in enumerate(specs):
        h.write(out/f'coarse0_{spec["variant"]}.spice',circuit(text,spec['variant']))
        folder=out/str(n);folder.mkdir();devices=rows[0]['task']['devices']
        h.write(folder/'bench.cir',fixture(out,spec,devices))
        tasks.append(dict(id=str(n),spec=spec,devices=devices,deck_sha256=h.sha(folder/'bench.cir')))
    h.atomic(out/'manifest.json',dict(identity=identity,tasks=tasks,libraries={p.name:h.sha(p) for p in out.glob('*.spice')},qualified_phy=False))
    return out


def bound(out):
    if not out.is_relative_to(ROOT/'build/diagnostics/dcdl_rc_drive_v2'):raise ValueError('Wrong RC drive-repair context')
    m=h.bound(out);i=m['identity']
    if (i['version']!=VERSION or h.sha(Path(i['model_library']))!=i['model_library_sha256']
        or any(h.sha(ROOT/n)!=v for n,v in i['inputs'].items())):raise ValueError('RC drive-repair inputs changed')
    return m


def measure(folder,task):
    return dict(parent_source.measure(folder,task),version=VERSION,variant=task['spec']['variant'],
        scope='SS40 source compound-gate/unit-RC feasibility only; no gate physical proof, full-bank, PVT or PHY admission')


@contextmanager
def profile():
    previous=batch.bound,batch.measure;batch.bound=bound;batch.measure=measure
    try:yield
    finally:batch.bound,batch.measure=previous


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','bound']);p.add_argument('artifact',type=Path);a=p.parse_args()
    if a.action=='prepare':print(prepare(a.artifact.resolve()),flush=True)
    elif a.action=='bound':print(json.dumps(bound(a.artifact.resolve()),indent=2))
    else:
        with profile():batch.run(a.artifact.resolve())
