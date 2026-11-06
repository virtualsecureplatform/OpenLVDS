#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Test the fresh native storage body-contact row in the complete counter."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import probe_counter_output_guard_margin_v168 as source
from probe_digital_dcc_v2 import sha,write,atomic
from spice_dispatch import lease
from spice_engine import engine,provenance

ROOT=source.ROOT
CAD='/nix/store/nah36l3f04m5gsi98a7civz9n8szraml-devshell-dir/bin/python3'
VERSION='native-storage-body-contact-row-three-ss-temperatures-counter-v179.1'
CONTEXT='counter_storage_bodytap_v179'
OLD='openlvds_nand2_4_o3_shunted_v2'
NEW='openlvds_nand2_4_o3_bodytap_v178'
SCOPE='Fresh native body-contact-row storage NAND with 3um setter-guard hypothesis, SS0/25/40 50% duty both stopped levels; complete original counter timing/stress checks, ideal shared wires and unqualified setter geometry, no whole-clock/PVT/PHY admission'


def evidence(component):
    code='''import sys,json
from pathlib import Path
sys.path.insert(0,'scripts')
import build_counter_storage_bodytap_v178 as p
out=Path(sys.argv[1]);i=p.bound(out);r=json.loads((out/'summary.json').read_text())
if json.loads((out/'state.json').read_text())!=dict(status='complete',passed=True,qualified_phy=False) or not r['component_physical_rc_passed'] or any(p.sha(out/n)!=h for n,h in r['files'].items()) or any(p.sha(p.ROOT/n)!=h for n,h in r['extracted_files'].items()):raise ValueError('Require complete unchanged native storage body-contact-row component RC')
files=[out/'manifest.json',out/'summary.json',out/'state.json',*[out/n for n in r['files']],*[p.ROOT/n for n in r['extracted_files']],*[p.ROOT/n for n in i['inputs']]]
print(json.dumps(dict(identity=i,report=r,files={str(f.relative_to(p.ROOT)):p.sha(f) for f in files})))
'''
    p=subprocess.run([CAD,'-c',code,str(component)],cwd=ROOT,capture_output=True,text=True)
    if p.returncode:raise ValueError('Native storage component admission refused:\n'+p.stderr[-2500:])
    return json.loads(p.stdout)


def libraries(parent,component_text):
    cells=(parent/'guard_3/cells.spice').read_text();module=(parent/'guard_3/pair.spice').read_text()
    defs=source.guards.native.definitions(component_text)
    if set(defs)!={NEW} or defs[NEW][0]!=['A','B','Y','VGND','VPWR'] or NEW in source.guards.native.definitions(cells):raise ValueError('Native storage component namespace/ports changed')
    rows=re.findall(r'(?m)^Xlow0_q [^\n]+$',module)
    if len(rows)!=1 or rows[0].split()!=['Xlow0_q','low0_sn','low0_qb','low0','VGND','VPWR',OLD]:raise ValueError('Require exactly the original low0 storage NAND')
    altered=module.replace(rows[0],rows[0][:-len(OLD)]+NEW,1)
    return cells+'\n'+component_text,altered


def devices(cells,module,baseline):
    original=source.source.original.original
    mapped=original.circuit.components.mapped_mos(cells+module,original.HARNESS,
        dict(RCLK='RCLK',REQUEST='REQUEST',PREPARE='PREPARE',RESET_N='RESET_N',CLK='CLK',VPWR='VDD',VGND='0'),'XD')
    prefix='XD:XR:Xlow0_q:'
    if len(mapped)!=len(baseline) or [d for d in mapped if not d['name'].startswith(prefix)]!=[d for d in baseline if not d['name'].startswith(prefix)]:
        raise ValueError('Counter MOS coverage or non-storage native observations changed')
    if len([d for d in mapped if d['name'].startswith(prefix)])!=16:raise ValueError('Require all sixteen actual storage MOS observations')
    return mapped


def fixture(out,spec,observations):
    first,rest=source.fixture(out,spec,observations).split('\n',1)
    if first!='OpenLVDS '+source.VERSION:raise ValueError('Original complete native fixture changed')
    return 'OpenLVDS '+VERSION+'\n'+rest


def prepare(parent,component):
    m=source.bound(parent);i=m['identity'];r=json.loads((parent/'summary.json').read_text())
    if json.loads((parent/'state.json').read_text())!=dict(status='complete',cases=12,errors=0,qualified_phy=False) or len(r['rows'])!=12:raise ValueError('Require completed larger-guard comparison')
    inherited=[row for row in r['rows'] if row['task']['variant']=='3']
    if len(inherited)!=6 or any(row['error'] is not None for row in inherited):raise ValueError('Require all six complete 3um setter-guard cases')
    paths=[parent/'manifest.json',parent/'summary.json',parent/'state.json',parent/'guard_3/cells.spice',parent/'guard_3/pair.spice']
    for row in inherited:
        folder=parent/row['task']['id']
        if row!=json.loads((folder/'summary.json').read_text()) or any(sha(folder/n)!=h for n,h in row['files'].items()):raise ValueError('Completed source trace changed')
        remeasured=source.source.measure(folder,row['task']['spec'],i['devices'])
        if any(row['result'].get(k)!=v for k,v in remeasured.items() if k!='scope'):raise ValueError('Consumed native source waveform does not reproduce')
        paths += [folder/'summary.json',*[folder/n for n in row['files']]]
    if inherited[0]['result']['terminal_screen_passed'] or not all(row['result']['counter_feasibility_passed'] for row in inherited[1:]):raise ValueError('Require the measured cold stopped-low failure and five passing source conditions')
    record=evidence(component);rc=ROOT/record['report']['extraction']['netlist'];cells,module=libraries(parent,rc.read_text());mapped=devices(cells,module,i['devices'])
    paths += [ROOT/n for n in i['inputs']]
    paths += sorted({Path(mod.__file__).resolve() for mod in list(sys.modules.values()) if getattr(mod,'__file__',None) and Path(mod.__file__).resolve().parent==ROOT/'scripts'})
    specs=[row['task']['spec'] for row in inherited]
    identity=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),component=str(component.relative_to(ROOT)),component_netlist=str(rc.relative_to(ROOT)),
        inputs={**record['files'],**{str(p.relative_to(ROOT)):sha(p) for p in paths}},pdk_files=i['pdk_files'],simulator=provenance(),
        baseline_devices=i['devices'],devices=mapped,specs=specs,max_workers=2,cad=dict(path=CAD,sha256=sha(Path(CAD))),scope=SCOPE)
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);write(out/'cells.spice',cells);write(out/'pair.spice',module);tasks=[]
    for k,spec in enumerate(specs):
        folder=out/str(k);folder.mkdir();write(folder/'bench.cir',fixture(out,spec,mapped));tasks.append(dict(id=str(k),spec=spec,deck_sha256=sha(folder/'bench.cir')))
    atomic(out/'manifest.json',dict(identity=identity,tasks=tasks,qualified_phy=False));return out


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION
        or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or any(sha(ROOT/n)!=h for n,h in i['inputs'].items()) or any(sha(Path(n))!=h for n,h in i['pdk_files'].items())
        or engine()!='ngspice' or provenance()!=i['simulator'] or sha(Path(CAD))!=i['cad']['sha256'] or i['max_workers']!=2):raise ValueError('Native storage repair context changed')
    cells,module=libraries(ROOT/i['parent'],(ROOT/i['component_netlist']).read_text())
    if cells!=(out/'cells.spice').read_text() or module!=(out/'pair.spice').read_text() or devices(cells,module,i['baseline_devices'])!=i['devices']:
        raise ValueError('Native storage repair libraries/observations changed')
    if len(m['tasks'])!=6 or len(i['specs'])!=6:raise ValueError('Require all six SS temperature/stopped-level cases')
    for k,t in enumerate(m['tasks']):
        file=out/str(k)/'bench.cir'
        if t!=dict(id=str(k),spec=i['specs'][k],deck_sha256=sha(file)) or file.read_text()!=fixture(out,t['spec'],i['devices']):raise ValueError('Native counter fixture changed')
    return m


def run(out):
    m=bound(out);i=m['identity']
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain existing or partial native storage repair')
        atomic(out/'state.json',dict(status='running',qualified_phy=False))
        def execute(task):
            folder=out/task['id'];result=error=None
            try:
                with lease(ROOT,priority=0,label=CONTEXT+'_'+task['id']):
                    bound(out);p=subprocess.run([sys.executable,str(ROOT/'scripts/run_native_binary_v2.py'),'-l',str(folder/'ngspice.log'),str(folder/'bench.cir')],capture_output=True,text=True)
                write(folder/'console.log',p.stdout+p.stderr);p.check_returncode();r=source.source.measure(folder,task['spec'],i['devices'])
                result=dict(r,hypothesis_point_checks_passed=r['counter_feasibility_passed'] and r['minimum_clock_low_voltage_margin_v']>=0,
                    storage_component_physical_rc_qualified=True,setter_guard_geometry_qualified=False,whole_clock_rc_qualified=False,
                    all_pvt_covered=False,electrical_qualification_passed=False,qualified_phy=False,scope=SCOPE)
            except Exception as e:error=str(e)
            row=dict(task=task,result=result,error=error,files={p.name:sha(p) for p in folder.iterdir() if p.is_file()});atomic(folder/'summary.json',row);return row
        with ThreadPoolExecutor(max_workers=2) as pool:rows=list(pool.map(execute,m['tasks']))
        bound(out);atomic(out/'summary.json',dict(rows=rows,scope=SCOPE,qualified_phy=False))
        atomic(out/'state.json',dict(status='complete',cases=6,errors=sum(r['error'] is not None for r in rows),qualified_phy=False))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','campaign']);p.add_argument('artifact',type=Path);p.add_argument('--component',type=Path)
    a=p.parse_args();out=a.artifact.resolve()
    if a.action in ('prepare','campaign'):
        if a.component is None:p.error('--component required')
        out=prepare(out,a.component.resolve());print(out,flush=True)
    if a.action in ('run','campaign'):run(out);print(out,flush=True)
