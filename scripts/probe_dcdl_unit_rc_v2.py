#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Check actual unit RC loading before routing an entire DCDL bank.

Replicate the exact verified five-port unit RC model 31 times in the retained
coarse-count-16 source core. Preserve the 4x4 node shunt, native controls and all
MOS stress probes. No inter-unit/core routing or full physical admission is
claimed. The SS40 0/31/0 sequence exposes minimum/range and update stress.
"""
import argparse
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import re
import analyze_dcdl_batch_v2 as analysis
import probe_digital_dcdl_batch_v2 as batch
import probe_dcdl_control_margin_v2 as controls
import verify_digital_clocking_v2 as binary
from spice_library import checked_netlist
from lvs_utils import clean_match

h=batch.h
ROOT=batch.ROOT
VERSION='hybrid-dcdl-exact-unit-rc-v2.1'
UNIT='openlvds_mim_switch_unit_v2'


def bank(text):
    for i in range(31):
        for name in [f'XSWN{i}',f'XSWP{i}',f'XCLR{i}',f'XC{i}']:
            text,count=re.subn(r'(?m)^'+name+r' [^\n]+\n','',text)
            if count!=1:raise ValueError('Source fine unit changed: '+name)
    instances='\n'.join(f'XU{i} r0 E{i} EB{i} VDD VSS {UNIT}' for i in range(31))
    if text.count('.ends dcdl_source')!=1:raise ValueError('Source bank closure changed')
    return text.replace('.ends dcdl_source',instances+'\n.ends dcdl_source')


def devices(text):
    mos=[]
    for line in text.splitlines():
        words=line.split()
        if not words or not words[0].lower().startswith('x'):continue
        index=next((i for i,w in enumerate(words) if '=' in w),len(words))-1
        model=words[index]
        if model not in ['sky130_fd_pr__nfet_01v8','sky130_fd_pr__pfet_01v8']:continue
        if len(words[1:index])!=4:raise ValueError('Unit MOS terminal list changed')
        params=dict(w.split('=',1) for w in words[index+1:])
        for n in range(31):
            formal={'NODE':'XD:r0','EN':f'E{n}','ENB':f'EB{n}','VDD':'VDD','VSS':'VSS'}
            nodes=[formal.get(w,f'XD:XU{n}:'+w) for w in words[1:index]]
            mos.append(dict(name=f'XD:XU{n}:'+words[0],model=model,width_um=float(params['w']),length_um=float(params['l']),terminals=nodes))
    if len(mos)!=93:raise ValueError('Unit RC must contain exactly three MOS devices')
    return mos


def fixture(out,spec,mos):
    text=controls.fixture(out,spec)
    text=text.replace(f'.include "{out}/coarse0.spice"',f'.include "{out}/coarse0.spice"\n.include "{out}/unit_rc.spice"')
    text,count=re.subn(r'(?m)^XCEB\d+[^\n]+\n','',text)
    if count!=31:raise ValueError('External control shunts changed')
    # Old source-only cap nodes no longer exist; observe the actual extracted
    # device terminals inside each five-port unit instead.
    text=re.sub(r' V\(XD:cap\d+\)','',text)
    probes=sorted({n for d in mos for n in d['terminals'] if n not in ['VDD','VSS']})
    return text.replace('\n.end\n',' '+' '.join(f'V({n})' for n in probes)+'\n.end\n')


def prepare(receipt,parent):
    if not receipt.is_relative_to(ROOT/'build/diagnostics/mim_switch_unit_verification_v2'):
        raise ValueError('Require the independent unit RC receipt')
    proof=json.loads((receipt/'summary.json').read_text());info=proof['verified_model']
    if proof['rc_topology_passed'] is not True or proof['qualified_phy'] is not False:
        raise ValueError('Unit topology audit did not pass')
    if not clean_match((receipt/'lvs.log').read_text()):raise ValueError('Missing independent topology match')
    if any(h.sha(ROOT/n)!=v for n,v in proof['identity']['witnesses'].items()):raise ValueError('Unit witness changed')
    unit=checked_netlist(info)
    # Parent is the completed source repair pilot, never the running dense PVT
    # campaign. Its exact coarse library is a source baseline, not a certificate.
    if not parent.is_relative_to(ROOT/'build/diagnostics/dcdl_charge_kick_v2'):
        raise ValueError('Require the retained node-shunt source pilot')
    import probe_dcdl_charge_kick_v2 as pilot
    pilot.bound(parent)
    if json.loads((parent/'state.json').read_text())['status']!='source_screen_complete':raise ValueError('Source pilot incomplete')
    text=(parent/'coarse0_node_mim4x4.spice').read_text();spec=dict(process='ss',temperature=40,coarse=0,
        codes=[0,31,0],restore='mim2x2',control_slew_ps=20)
    files=[Path(__file__),ROOT/'scripts/probe_digital_dcdl_batch_v2.py',ROOT/'scripts/analyze_dcdl_batch_v2.py',
        ROOT/'scripts/probe_dcdl_control_margin_v2.py',ROOT/'scripts/probe_dcdl_control_restore_v2.py',
        ROOT/'scripts/probe_digital_dcdl_v2.py',ROOT/'scripts/probe_digital_dcc_v2.py',
        ROOT/'scripts/spice_library.py',ROOT/'scripts/lvs_utils.py',ROOT/'scripts/run_ngspice.py',
        ROOT/'scripts/spice_dispatch.py',ROOT/'scripts/spice_engine.py',ROOT/'scripts/env.sh',ROOT/'requirements.json',
        ROOT/'clocking_v2.json',ROOT/'build/apptainer/openlvds.sif.sha256']
    pm=json.loads((parent/'manifest.json').read_text())
    inputs={str((receipt/n).relative_to(ROOT)):h.sha(receipt/n) for n in ['summary.json','lvs.log']}
    inputs.update(proof['identity']['witnesses'])
    inputs.update({str((parent/n).relative_to(ROOT)):h.sha(parent/n) for n in ['manifest.json','summary.json','state.json','cells.spice','coarse0_node_mim4x4.spice']})
    identity=dict(version=VERSION,code={str(p.relative_to(ROOT)):h.sha(p) for p in files},inputs=inputs,
        pdk=pm['identity']['pdk'],pdk_sha256=pm['identity']['pdk_sha256'],model_library=pm['identity']['model_library'],
        model_library_sha256=pm['identity']['model_library_sha256'],simulator=h.provenance(),specs=[spec])
    out=ROOT/'build/diagnostics/dcdl_unit_rc_v2'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);h.write(out/'cells.spice',(parent/'cells.spice').read_text())
    h.write(out/'coarse0.spice',bank(text));h.write(out/'unit_rc.spice',unit);mos=devices(unit)
    folder=out/'0';folder.mkdir();h.write(folder/'bench.cir',fixture(out,spec,mos))
    task=dict(id='0',spec=spec,devices=mos,deck_sha256=h.sha(folder/'bench.cir'))
    h.atomic(out/'manifest.json',dict(identity=identity,tasks=[task],libraries={p.name:h.sha(p) for p in out.glob('*.spice')},qualified_phy=False))
    return out


def bound(out):
    if not out.is_relative_to(ROOT/'build/diagnostics/dcdl_unit_rc_v2'):raise ValueError('Wrong hybrid unit-RC context')
    m=h.bound(out);i=m['identity']
    if (i['version']!=VERSION or h.sha(Path(i['model_library']))!=i['model_library_sha256']
        or any(h.sha(ROOT/n)!=v for n,v in i['inputs'].items())):raise ValueError('Hybrid unit-RC inputs changed')
    return m


def measure(folder,task):
    # Existing analysis accepts direct ngspice node names. Normalize hierarchy
    # separators in the metadata, without changing any samples or time values.
    normalized=dict(task,devices=[dict(d,terminals=[n.replace(':','.') for n in d['terminals']]) for d in task['devices']])
    result=analysis.measure(folder,normalized)
    minimum=min(s['rise_delay_ps'] for s in result['samples'] if s['code']==0)
    frequencies=json.loads((ROOT/'requirements.json').read_text())['clock_test_mhz']
    quarter=[1e6/max(frequencies)/4,1e6/min(frequencies)/4]
    return dict(result,version=VERSION,minimum_hybrid_rise_ps=minimum,required_quarter_range_ps=quarter,
        hybrid_min_below_fast_quarter=minimum<=quarter[0],
        scope='Exact unit RC plus source coarse core/ideal common wiring only; no full-bank RC, legal ROM or PHY admission')


@contextmanager
def profile():
    previous=batch.bound,batch.measure;batch.bound=bound;batch.measure=measure
    try:yield
    finally:batch.bound,batch.measure=previous


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','bound']);p.add_argument('artifact',type=Path);p.add_argument('--source',type=Path);a=p.parse_args()
    if a.action=='prepare':
        if a.source is None:p.error('Provide --source source-pilot artifact')
        print(prepare(a.artifact.resolve(),a.source.resolve()),flush=True)
    elif a.action=='bound':print(json.dumps(bound(a.artifact.resolve()),indent=2))
    else:
        with profile():batch.run(a.artifact.resolve())
