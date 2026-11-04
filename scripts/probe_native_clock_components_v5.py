#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Joint clock pilot using actual component RC, before whole-backend routing."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import itertools
import json
from pathlib import Path
import subprocess
import native_clock_components_v3 as components
import clocking_duty_profile_v2 as duty_profile
import probe_conditioned_dcc_v3 as joint
from verify_conditioned_clock_v2 import regenerated_front
from measure_conditioned_dcc_v2 import measure
from probe_digital_dcc_v2 import sha,write,atomic
from spice_library import checked_netlist
from spice_dispatch import lease
from spice_engine import command,provenance

ROOT=joint.ROOT
VERSION='joint-strong-native-clock-approved-40-60-duty-rc-pilot-v2.4'
VERSIONS={'passive_clock_rc_verification_v2':('passivity-gated-flat-RC-independent-topology-v2.1',None)}


def witnesses(parent):
    if parent.parent.name not in VERSIONS:raise ValueError('Unknown component extraction context')
    version,count=VERSIONS[parent.parent.name];m=json.loads((parent/'manifest.json').read_text());i=m['identity']
    if i['version']!=version or parent.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]:raise ValueError('Changed component extraction identity')
    paths=[parent/n for n in ['manifest.json','summary.json','state.json']]
    for n,h in {**i['code'],**i['inputs']}.items():
        if sha(ROOT/n)!=h:raise ValueError('Changed extraction witness '+n)
        paths.append(ROOT/n)
    physical=ROOT/i['parent']
    if count is None:count=6 if physical.parent.name=='clock_cell_shunts_physical_v2' else 2
    pm=json.loads((physical/'manifest.json').read_text())['identity']
    for n,h in {**pm['code'],**pm['inputs']}.items():
        if sha(ROOT/n)!=h:raise ValueError('Changed physical input '+n)
        paths.append(ROOT/n)
    if any(sha(Path(n))!=h for n,h in pm['pdk_files'].items()):raise ValueError('Changed physical PDK')
    report=json.loads((parent/'summary.json').read_text());pr=json.loads((physical/'summary.json').read_text())
    if not report['passed'] or not pr['passed'] or len(report['rows'])!=count:raise ValueError('Require complete clean component family')
    cells={}
    for row in report['rows']:
        name=row['macro'];info=row['extraction'];text=checked_netlist(info);folder=physical/name
        if not info.get('passivity',{}).get('elementwise_passive_passed'):raise ValueError('Require sign-gated passive extraction')
        p=next(r for r in pr['rows'] if r['macro']==name)
        if not row['rc_topology_passed'] or p['drc_count']!='0' or not p['lvs_passed'] or not p['passed']:raise ValueError('Failed component topology/geometry')
        if (sha(folder/(name+'.gds'))!=info['gds_sha256'] or p['gds_sha256']!=info['gds_sha256']
            or sha(folder/(name+'.sch.spice'))!=info['source_scope_sha256']):raise ValueError('Component GDS/source identity mismatch')
        paths += [ROOT/info['netlist'],ROOT/info['raw_netlist'],parent/name/'extraction.json',parent/name/'lvs.log',parent/name/'summary.json']
        paths += [folder/(name+n) for n in ['.gds','.lef','.sch.spice','.drc_count.txt','.lvs.log']]
        cells[name]=dict(info=info,text=text)
    return cells,paths


def fixture(out,spec,devices):
    deck=joint.fixture(out,spec,devices);marker=f'.include "{out}/frontend.spice"\n'
    if deck.count(marker)!=1:raise ValueError('Require exact front-end include')
    return deck.replace(marker,f'.include "{out}/cells.spice"\n'+marker).replace('OpenLVDS '+joint.VERSION,'OpenLVDS '+VERSION)


def prepare(parent,nands,clock,tg):
    jm=joint.bound(parent);front_parent=ROOT/jm['identity']['parent'];sources,front_devices=regenerated_front(front_parent)
    cells={};paths=[parent/'manifest.json'];pdk_files=dict(jm['identity']['pdk_files'])
    for artifact in [nands,clock,tg]:
        group,files=witnesses(artifact)
        if set(cells)&set(group):raise ValueError('Duplicate physical component model')
        cells.update(group);paths+=files
        pm=json.loads((ROOT/json.loads((artifact/'manifest.json').read_text())['identity']['parent']/'manifest.json').read_text())['identity']
        pdk_files.update(pm['pdk_files'])
    modules=components.compose(cells);modules['frontend.spice']=sources['frontend.spice'];modules['bias.spice']=sources['bias.spice']
    devices={}
    for v in ['p3_c1','p3_c3']:
        text='\n'.join(modules[n] for n in ['cells.spice','clean.spice','release.spice',v+'.spice'])
        ds=[d for d in front_devices if d['name'].startswith(('XF:','XB:'))]
        ds+=components.mapped_mos(text,components.clean.NAME,dict(F0='F0',F180='F180',P0='P0',P180='P180',MON0='MON0',MON180='MON180',VPWR='VDD',VGND='0'),'XC')
        ds+=components.mapped_mos(text,components.dcc.NAME,dict(VGND='0',VPWR='VDD',clock_out='Q',phase0='P0',phase180='P180',reset_n='RESET_N'),'XD')
        for tag,clk,rst in [('XR0','P0','RESET_N'),('XR180','P180','RESET_180')]:
            ds+=components.mapped_mos(text,components.release.NAME,dict(CLK=clk,REQUEST='REQUEST',RESET_N=rst,VPWR='VDD',VGND='0'),tag)
        if len({d['name'] for d in ds})!=len(ds):raise ValueError('Duplicate native MOS witness')
        devices[v]=ds
    code=[Path(__file__),Path(components.__file__),Path(joint.__file__),ROOT/'scripts/verify_conditioned_clock_v2.py',
        ROOT/'scripts/measure_conditioned_dcc_v2.py',ROOT/'scripts/spice_dispatch.py',ROOT/'scripts/spice_engine.py',ROOT/'scripts/run_ngspice.py',ROOT/'scripts/probe_digital_dcc_v2.py',ROOT/'scripts/spice_library.py',ROOT/'scripts/native_clock_components_v2.py',Path(duty_profile.__file__),duty_profile.PROFILE,ROOT/'clocking_v2.json']
    paths+=code+[front_parent/'manifest.json',front_parent/'frontend.spice',front_parent/'bias.spice']
    # Keep inherited generator/library witnesses immutable even though the
    # source pilot can continue writing independent per-case results.
    paths += [ROOT/n for n in jm['identity']['inputs']]
    specs=[dict(variant=v,process=p,temperature=40,mhz=410,load_ff=20,slew0_ps=100,slew180_ps=100,duty=d,raw_start_ns=22)
        for v,p,d in itertools.product(['p3_c1','p3_c3'],['ss'],duty_profile.load()['timing']['rx_reference_duty_range'])]
    identity=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),components=[str(p.relative_to(ROOT)) for p in [nands,clock,tg]],
        inputs={str(p.relative_to(ROOT)):sha(p) for p in paths},pdk_files=pdk_files,simulator=provenance(),specs=specs,devices=devices,
        scope='Stronger native storage and one/three parallel real clock-driver RC experiments; ideal inter-component wires and analog conditioner source plus native bias RC; physical parallel-output assembly, full-PVT and PHY admission remain required')
    out=ROOT/'build/diagnostics/native_clock_components_v2'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False)
    for n,text in modules.items():write(out/n,text)
    tasks=[]
    for n,spec in enumerate(specs):
        folder=out/str(n);folder.mkdir();write(folder/'bench.cir',fixture(out,spec,devices[spec['variant']]))
        tasks.append(dict(id=str(n),spec=spec,deck_sha256=sha(folder/'bench.cir')))
    atomic(out/'manifest.json',dict(identity=identity,tasks=tasks,libraries={p.name:sha(p) for p in out.glob('*.spice')},qualified_phy=False));return out


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    if (out.parent!=ROOT/'build/diagnostics/native_clock_components_v2' or i['version']!=VERSION
        or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or any(sha(ROOT/n)!=h for n,h in i['inputs'].items()) or any(sha(Path(n))!=h for n,h in i['pdk_files'].items())
        or provenance()!=i['simulator'] or any(sha(out/n)!=h for n,h in m['libraries'].items()) or len(m['tasks'])!=len(i['specs'])):raise ValueError('Native component clock context changed')
    for n,task in enumerate(m['tasks']):
        if task['id']!=str(n) or task['spec']!=i['specs'][n] or sha(out/str(n)/'bench.cir')!=task['deck_sha256']:raise ValueError('Native component task/deck changed')
    return m


def run(out):
    m=bound(out)
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain prior native component run')
        atomic(out/'state.json',dict(status='running',qualified_phy=False))
        def execute(task):
            folder=out/task['id'];result=error=None
            try:
                with lease(ROOT,priority=0,label='native_clock_components_v2_'+task['id']):
                    bound(out);p=subprocess.run(command(folder/'ngspice.log',folder/'bench.cir'),capture_output=True,text=True)
                write(folder/'console.log',p.stdout+p.stderr);p.check_returncode()
                result=measure(folder,task['spec'],m['identity']['devices'][task['spec']['variant']],m['identity']['scope'])
            except Exception as e:error=str(e)
            row=dict(task=task,result=result,error=error,files={p.name:sha(p) for p in folder.iterdir() if p.is_file()});atomic(folder/'summary.json',row);return row
        with ThreadPoolExecutor(max_workers=2) as pool:rows=list(pool.map(execute,m['tasks']))
        bound(out);atomic(out/'summary.json',dict(rows=rows,qualified_phy=False));atomic(out/'state.json',dict(status='native_component_pilot_complete',cases=len(rows),errors=sum(r['error'] is not None for r in rows),qualified_phy=False))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run']);p.add_argument('artifact',type=Path)
    p.add_argument('--nands',type=Path);p.add_argument('--clock-cells',type=Path);p.add_argument('--tg',type=Path);a=p.parse_args();out=a.artifact.resolve()
    if a.action=='prepare':
        if any(v is None for v in [a.nands,a.clock_cells,a.tg]):p.error('Provide all three checked component RC families')
        print(prepare(out,a.nands.resolve(),a.clock_cells.resolve(),a.tg.resolve()),flush=True)
    else:run(out)
