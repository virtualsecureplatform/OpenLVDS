#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Test a regular-P/N inverter pair after measured native BUF8 latency failure."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import numpy as np
import probe_discharge_isolated_fine_bank_v220 as source
import analyze_isolated_stage_latency_v262 as diagnosis
import native_clock_components_v2 as native
import native_bank_inventory_v51 as inventory
from build_compound_drivers_v3 import cell_definition
from audit_rc_comments_v2 import collapse
from probe_digital_dcc_v2 import atomic
from spice_dispatch import lease
from spice_engine import engine,provenance

ROOT=source.ROOT
sha=diagnosis.sha
VERSION='qualified-regular-p20n16-pair-output-regeneration-native-pilot-v263.1'
CONTEXT='regular_regenerated_bank_v263'
TOP='openlvds_regular_regenerated_fine_v263'
MODEL=source.DRIVERS['p20n16']
SCOPE='New regular-P/N pair output regeneration using qualified P20/N16 local RC, unchanged isolation/bank/controls, SS40 four-point native feasibility; new shared wires ideal, no routed/dense/update/full-frequency-duty/all-PVT/PHY admission'


def specifications():
    sample=source.specifications()[0]
    return [dict(sample,coarse=c,fine=f,duty=d,regenerator='p20n16_pair') for c,f,d in ((0,0,.5),(0,31,.6),(0,31,.4),(1,0,.5))]


def transform(bank,old_observations):
    defs=native.definitions(bank);ports=defs[MODEL][0]
    if ports!=['A','Y','VGND','VPWR']:raise ValueError('Qualified regular driver pin order changed')
    original=['Xfine_regenerate','fine_node','OUT','VGND','VPWR',source.BUF]
    if [w for w in defs[source.TOP][1] if w[0]=='Xfine_regenerate']!=[original]:raise ValueError('Original native BUF8 output stage changed')
    before=cell_definition(bank,source.TOP);after=before
    calls=[]
    for name,a,y in [('fine_regenerate0','fine_node','restored_b'),('fine_regenerate1','restored_b','OUT')]:
        pins=dict(A=a,Y=y,VGND='VGND',VPWR='VPWR')
        calls.append('X'+name+' '+' '.join(pins[p] for p in ports)+' '+MODEL)
    after=after.replace(' '.join(original)+'\n','\n'.join(calls)+'\n',1)
    after=after.replace('.subckt '+source.TOP+' ','.subckt '+TOP+' ',1).replace('.ends '+source.TOP+'\n','.ends '+TOP+'\n',1)
    result=bank.replace(before,after,1)
    for model in defs:
        if model!=source.TOP and cell_definition(result,model)!=cell_definition(bank,model):raise ValueError('Unrelated native macro definition changed')
    pins={p:'0' if p=='VGND' else 'VDD' if p=='VPWR' else p for p in native.definitions(result)[TOP][0]}
    devices=native.mapped_mos(result,TOP,pins,'XD');old={d['name']:d for d in old_observations['devices']};new={d['name']:d for d in devices}
    removed={name for name in old if name.startswith('XD:Xfine_regenerate:')}
    if len(removed)!=22 or len(devices)!=1529 or len(new)!=1529:raise ValueError('Regular pair native MOS census changed')
    if any(new.get(name)!=d for name,d in old.items() if name not in removed):raise ValueError('Non-regenerator native MOS terminals changed')
    gates=[dict(g,gate_node=new[g['device']]['terminals'][1]) for g in old_observations['programming_gates']]
    if gates!=old_observations['programming_gates'] or len(gates)!=173:raise ValueError('Original typed programming gates changed')
    if any(c['node'].startswith('XD:Xfine_regenerate:') for c in old_observations['controls']):raise ValueError('Stale output-stage control probe')
    flat=''.join(collapse(cell_definition(result,m)) for m in native.definitions(result))
    _,leaves=inventory.native_leaves(flat,TOP)
    counts={k:sum(1 for d in leaves if ('fet_' in d['model'])==k) for k in (True,False)}
    if counts!={True:1529,False:43}:raise ValueError('Regular pair native 1529-MOS/43-MIM inventory changed')
    obs=dict(devices=devices,controls=old_observations['controls'],programming_gates=gates)
    proof=dict(native_mos=1529,native_mims=43,removed_native_buf_mos=22,added_qualified_regular_driver_mos=72,
        all_nonregenerator_native_terminal_maps_preserved=True,all_programming_gate_maps_preserved=True,
        all_unrelated_native_macro_definitions_preserved=True,new_shared_wire_rc_qualified=False,qualified_phy=False)
    return result,obs,proof


def fixture(out,i,s):
    width=s['input_slew_ps']/1e12/(2*np.arctanh(.8));period=1e-6/s['frequency_mhz']
    wave='+'.join(f'0.9*(tanh((time-{2.1e-9+k*period:.17g})/{width:.17g})-tanh((time-{2.1e-9+(k+s["duty"])*period:.17g})/{width:.17g}))' for k in range(s['cycles']))
    pins=source.periodic.baseline.circuit.encode(s['coarse'],s['fine']);o=i['observations']
    rows=['OpenLVDS '+VERSION,f'.lib "{i["model"]}" {s["process"]}',f'.include "{out}/bank.spice"',
        f'.options device temp={s["temperature"]}', '.options timeint method=gear reltol=1e-4 abstol=1e-12','VDD VDD 0 1.8','BIN IN 0 V={'+wave+'}']
    rows += [f'V{p} {p} 0 {1.8*v:g}' for p,v in pins.items()]
    rows += ['XD '+' '.join('0' if p=='VGND' else 'VDD' if p=='VPWR' else p for p in i['ports'])+' '+TOP,
        f'CLOAD OUT 0 {s["load_ff"]}f',f'.tran 2p {s["stop_ns"]}n 0 2p']
    probes={'IN','OUT','VDD','XD:selected','XD:fine_node','XD:restored_b',*pins}
    probes.update(n for d in o['devices'] for n in d['terminals'] if n!='0');probes.update(c['node'] for c in o['controls'])
    return '\n'.join(rows+['.print tran '+' '.join('V('+n+')' for n in sorted(probes)),'.end',''])


def require_diagnosis(parent):
    m=json.loads((parent/'manifest.json').read_text());i=m['identity'];r=json.loads((parent/'summary.json').read_text())
    if (parent.parent!=ROOT/'build/diagnostics'/diagnosis.CONTEXT or i['version']!=diagnosis.VERSION
        or parent.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or any(sha(ROOT/n)!=h for n,h in i['inputs'].items()) or r.get('analysis_completed') is not True):
        raise ValueError('Require unchanged complete native stage-latency diagnosis')
    old=[row for row in r['rows'] if row['source_version']=='strong-native-fine-isolation-after-inv1-pulse-loss-v190.1'
         and row['task']['spec']['driver']=='inv' and (row['task']['spec']['coarse'],row['task']['spec']['fine'])==(0,0)]
    if len(old)!=1:raise ValueError('Require the completed INV8 zero-quarter failure')
    row=old[0];g=row['recorded_gates']
    if g.get('zero_code_quarter_passed') is not False or any(g.get(k) is not True for k in ('terminal_screen_passed','control_settling_passed','period_screen_passed','repeated_delay_screen_passed','current_downstream_250ps_slew_domain_passed')):
        raise ValueError('Require isolated zero-quarter latency failure with passing other native gates')
    if diagnosis.analyze(ROOT/row['case'])!=row:raise ValueError('Native failing-zero stage diagnosis does not reproduce')
    return i,r


def prepare(parent,evidence):
    di,dr=require_diagnosis(evidence);m=source.bound(parent);pi=m['identity']
    if engine()!='ngspice' or provenance()!=pi['simulator']:raise ValueError('Require unchanged native ngspice environment')
    refs=[];paths=[parent/'manifest.json',parent/'p20n16_c1/bank.spice']
    for k in (0,1):
        case=parent/str(k);row=json.loads((case/'summary.json').read_text())
        if row['task']!=m['tasks'][k] or row['error'] is not None or not row['result']['current_clock_interface_screen_passed'] or any(sha(case/n)!=h for n,h in row['files'].items()):
            raise ValueError('Require both complete passing P20/N16 fine endpoint references')
        if source.measure(case,pi,row['spec'])!=row['result']:raise ValueError('Existing P20/N16 native metrics do not reproduce')
        refs.append(row);paths += [case/'summary.json',*[case/n for n in row['files']]]
    bank,obs,proof=transform((parent/'p20n16_c1/bank.spice').read_text(),pi['observations']['p20n16_c1'])
    paths += [evidence/n for n in ('manifest.json','summary.json','state.json')]+[ROOT/n for n in {*pi['inputs'],*di['inputs']}]
    paths += sorted({Path(mod.__file__).resolve() for mod in list(sys.modules.values()) if getattr(mod,'__file__',None) and Path(mod.__file__).resolve().parent==ROOT/'scripts'})
    i=dict(pi,version=VERSION,parent=str(parent.relative_to(ROOT)),diagnosis=str(evidence.relative_to(ROOT)),specs=specifications(),
        ports=native.definitions(bank)[TOP][0],observations=obs,native_revision=proof,source_fine_endpoints=refs,
        inputs={str(p.relative_to(ROOT)):sha(p) for p in sorted(set(paths))},max_workers=2,priority=0,scope=SCOPE)
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16];out.mkdir(parents=True,exist_ok=False)
    (out/'bank.spice').write_text(bank);tasks=[]
    for k,s in enumerate(i['specs']):
        f=out/str(k);f.mkdir();(f/'bench.cir').write_text(fixture(out,i,s));tasks.append(dict(id=str(k),spec=s,deck_sha256=sha(f/'bench.cir')))
    atomic(out/'manifest.json',dict(identity=i,tasks=tasks,bank_sha256=sha(out/'bank.spice'),qualified_phy=False));return out


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or i['specs']!=specifications() or i['max_workers']!=2 or i['priority']!=0 or engine()!='ngspice' or provenance()!=i['simulator']
        or any(sha(ROOT/n)!=h for n,h in i['inputs'].items()) or any(sha(Path(n))!=h for n,h in {**i['pdk_files'],**i['external_files']}.items())
        or len(i['observations']['devices'])!=1529 or len(i['observations']['programming_gates'])!=173
        or sha(out/'bank.spice')!=m['bank_sha256'] or len(m['tasks'])!=4):raise ValueError('Regular regeneration native pilot context changed')
    for k,t in enumerate(m['tasks']):
        f=out/str(k)/'bench.cir'
        if t!=dict(id=str(k),spec=i['specs'][k],deck_sha256=sha(f)) or f.read_text()!=fixture(out,i,t['spec']):raise ValueError('Regular regeneration native fixture changed')
    return m


def measure(folder,i,s):
    r=source.periodic.measure(folder,dict(i,spec=s));r.update(new_common_routing_qualified=False,native_component_rc_hypothesis_only=True,
        electrical_qualification_passed=False,qualified_phy=False,scope=SCOPE);return r


def compare(rows):
    if len(rows)!=4 or any(r['error'] is not None or r['result'] is None for r in rows):return None
    if [r['spec'] for r in rows]!=specifications():raise ValueError('Regular regeneration four-point coverage changed')
    by={(r['spec']['coarse'],r['spec']['fine'],r['spec']['duty']):r['result'] for r in rows}
    complete=all(len(r['result']['edge_delays_ps'][edge])==8 and all(np.isfinite(v) and v>0 for v in r['result']['edge_delays_ps'][edge]) for r in rows for edge in ('rise','fall'))
    overlap={edge:min(v for d in (.4,.6) for v in by[0,31,d]['edge_delays_ps'][edge])-max(by[1,0,.5]['edge_delays_ps'][edge]) if complete else None for edge in ('rise','fall')}
    return dict(component_hypothesis_passed=complete and all(r['result']['current_clock_interface_screen_passed'] for r in rows) and all(v>0 for v in overlap.values()),
        conservative_coarse_overlap_ps=overlap,complete_four_point_native_screen=True,new_common_routing_qualified=False,all_pvt_covered=False,electrical_qualification_passed=False,qualified_phy=False)


def run(out):
    m=bound(out);i=m['identity']
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain existing or partial regular-regenerator native pilot')
        atomic(out/'state.json',dict(status='running',qualified_phy=False))
        def execute(task):
            folder=out/task['id'];result=error=None
            try:
                with lease(ROOT,priority=i['priority'],label=CONTEXT+'_'+task['id']):
                    bound(out);p=subprocess.run([sys.executable,str(ROOT/'scripts/run_native_binary_v2.py'),'-l',str(folder/'ngspice.log'),str(folder/'bench.cir')],capture_output=True,text=True)
                (folder/'console.log').write_text(p.stdout+p.stderr);p.check_returncode();result=measure(folder,i,task['spec'])
            except Exception as e:error=str(e)
            row=dict(task=task,spec=task['spec'],result=result,error=error,files={p.name:sha(p) for p in folder.iterdir() if p.is_file()});atomic(folder/'summary.json',row);return row
        with ThreadPoolExecutor(max_workers=2) as pool:rows=list(pool.map(execute,m['tasks']))
        bound(out);atomic(out/'summary.json',dict(rows=rows,comparison=compare(rows),scope=SCOPE,qualified_phy=False))
        atomic(out/'state.json',dict(status='complete',cases=4,errors=sum(r['error'] is not None for r in rows),qualified_phy=False));return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','campaign']);p.add_argument('artifact',type=Path);p.add_argument('--diagnosis',type=Path);a=p.parse_args();out=a.artifact.resolve()
    if a.action in ('prepare','campaign'):
        if a.diagnosis is None:p.error('--diagnosis required')
        out=prepare(out,a.diagnosis.resolve());print(out,flush=True)
    if a.action in ('run','campaign'):print(run(out),flush=True)
