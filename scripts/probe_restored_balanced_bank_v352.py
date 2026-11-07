#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Test staged restoration, balanced coarse/fine drive and doubled fine units."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import numpy as np
import probe_pullup_two_stage_bank_v342 as baseline
import probe_tapered_regenerated_bank_v310 as tapered
import analyze_bank_latency_v348 as latency
from spice_dispatch import lease
from spice_engine import engine,provenance
from probe_digital_dcc_v2 import atomic

ROOT=baseline.ROOT
VERSION='restoration-before-balanced-fine-two-copy-fine-balanced-coarse-bank-v352.1'
CONTEXT='restored_balanced_bank_v352'
TOP='openlvds_restored_balanced_bank_v352'
PARENT=ROOT/'build/diagnostics/pullup_two_stage_bank_v342/6fb0494678a32ddc'
DRIVERS=ROOT/'build/diagnostics/tapered_fine_driver_rc_v309/4cf2d31774fd60cd'
ANALYSIS=ROOT/'build/diagnostics/bank_latency_analysis_v348/b595ea5eba2a50e6'
REPLAYS=('20261107T095305Z','20261107T090609Z','20261107T093733Z','20261107T102955Z')
GROUP=baseline.source.GROUP
SMALL=tapered.MODELS['p10n8']
REGULAR=baseline.source.source.MODEL
OLD_COARSE='openlvds_parallel_coarse_b2_v120'
COARSE='openlvds_balanced_coarse_v352'
FINE='openlvds_parallel_regular_fine_v352'
native=baseline.source.source.native
inventory=baseline.source.source.inventory
definition=baseline.source.source.cell_definition
collapse=baseline.source.collapse
SCOPE=('Four-point SS40/410MHz full eight-startup-event component-RC hypothesis: '
       'qualified INV16 group restoration, P10/N8 pre-fine restoration, two parallel '
       'qualified P20/N16 fine drivers, retained final P20/N16, two fine units per '
       'enable, two INV16 per coarse unit; four inversions/noninverting sections; '
       'ideal new shared wires and original 20fF screen only, no actual next-bank '
       'input loading, routed/dense/update/all-PVT/DLL/PHY admission')


def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        while block:=stream.read(1024*1024):h.update(block)
    return h.hexdigest()


def specifications():
    return [dict(s,architecture='staged_restoration_balanced_coarse_fine',fine_copies=2,
        pre_driver='p10n8',loaded_driver='two_parallel_p20n16',coarse_unit='two_inv16',
        regenerator='p10n8_before_fine_and_p20n16_after') for s in baseline.specifications()]


def transform(bank,previous,small):
    defs=native.definitions(bank);body=defs[baseline.TOP][1]
    extra=native.definitions(small)
    if (set(extra)!={SMALL} or extra[SMALL][0]!=['A','Y','VGND','VPWR']
            or SMALL in defs or FINE in defs or COARSE in defs
            or defs[GROUP][0]!=['IN','OUT','VPWR','VGND']
            or defs[REGULAR][0]!=['A','Y','VGND','VPWR']):
        raise ValueError('Require unchanged qualified native component interfaces')
    expected_isolate=['Xfine_isolate','selected','fine_node','VGND','VPWR',baseline.MODEL]
    expected_final=['Xfine_regenerate1','fine_node','OUT','VGND','VPWR',REGULAR]
    if (sum(w==expected_isolate for w in body)!=1 or sum(w==expected_final for w in body)!=1
            or len(previous['devices'])!=1385 or len(previous['controls'])!=86
            or len(previous['programming_gates'])!=173):
        raise ValueError('Require the actual P40 two-stage bank and complete original observations')
    new=[];coarse_calls=roots=0
    for w in body:
        if w[-1]==OLD_COARSE:
            coarse_calls+=1;new.append(w[:-1]+[COARSE])
        elif w==expected_isolate:
            new += [['Xfine_pre','selected','pre_out','VGND','VPWR',SMALL],
                    ['Xfine_isolate','pre_out','fine_node','VGND','VPWR',FINE]]
        elif w[0] in {f'Xswitch1_0_{k}' for k in range(4)}|{f'Xroot_parallel{k}' for k in range(4)}:
            k=int(w[0][-1]);expected=[w[0],f'tree0_{k}','selected',f'en1_{k}',f'en_b1_{k}',
                                     'VPWR','VGND',baseline.source.TG]
            if w!=expected:raise ValueError('Original parallel-root mux changed')
            roots+=1;new.append([w[0],f'regenerated{k}',*w[2:]])
        else:new.append(w)
    if coarse_calls!=16 or roots!=8:raise ValueError('Require all sixteen coarse units and eight root TGs')
    new += [[f'Xgroup_compound{k}',f'tree0_{k}',f'regenerated{k}','VPWR','VGND',GROUP] for k in range(4)]
    for k in range(31):
        old=[f'Xfine_unit{k}','fine_node',f'fine{k}',f'fine_b{k}','VPWR','VGND','openlvds_measured_gangs_b2_v125_unit']
        if sum(w==old for w in body)!=1:raise ValueError('Original 31 native fine units changed')
        new.append([f'Xfine_copy{k}',*old[1:]])
    ports=defs[baseline.TOP][0]
    block='\n'.join(['.subckt '+TOP+' '+' '.join(ports),*[' '.join(w) for w in new],'.ends '+TOP,''])
    result=bank.replace(definition(bank,baseline.TOP),block,1)+'\n'+small+'\n'
    result+='\n'.join(['.subckt '+COARSE+' IN OUT VPWR VGND',
        'Xa IN mid VPWR VGND '+GROUP,'Xb mid OUT VPWR VGND '+GROUP,'.ends '+COARSE,'',
        '.subckt '+FINE+' A Y VGND VPWR','Xa A Y VGND VPWR '+REGULAR,
        'Xb A Y VGND VPWR '+REGULAR,'.ends '+FINE,''])
    if any(definition(result,n)!=definition(bank,n) for n in defs if n!=baseline.TOP):
        raise ValueError('Unrelated qualified native component definition changed')
    devices=native.mapped_mos(result,TOP,
        {p:'0' if p=='VGND' else 'VDD' if p=='VPWR' else p for p in ports},'XD')
    lookup={d['name']:d for d in devices};old={d['name']:d for d in previous['devices']}
    changed=('XD:Xdelay','XD:Xtail_load:','XD:Xfine_isolate:',
        *[f'XD:Xswitch1_0_{k}:' for k in range(4)],*[f'XD:Xroot_parallel{k}:' for k in range(4)])
    if (len(devices)!=2086 or len(lookup)!=2086
            or any(lookup.get(n)!=d for n,d in old.items() if not n.startswith(changed))):
        raise ValueError('Unexpected native bank census or unrelated terminal-map change')
    gates=deepcopy(previous['programming_gates'])
    if any(lookup[g['device']]['terminals'][1]!=g['gate_node'] for g in gates):
        raise ValueError('Original programming gate map changed')
    for k in range(31):
        prefix=f'XD:Xfine_unit{k}:';group=[g for g in previous['programming_gates'] if g['device'].startswith(prefix)]
        if len(group)!=3:raise ValueError('Require all three real fine-cell programming gates')
        for g in group:
            name=g['device'].replace(prefix,f'XD:Xfine_copy{k}:',1)
            gates.append(dict(g,device=name,gate_node=lookup[name]['terminals'][1]))
    _,leaves=inventory.native_leaves(collapse(result),TOP)
    if (sum('fet_' in d['model'] for d in leaves)!=2086
            or sum('cap_mim' in d['model'] for d in leaves)!=139
            or len(gates)!=266 or len({g['device'] for g in gates})!=266):
        raise ValueError('Complete new native/capacitor/programming-gate inventory changed')
    observations=dict(devices=devices,controls=deepcopy(previous['controls']),programming_gates=gates)
    revision=dict(native_mos=2086,native_mims=139,controls=86,programming_gates=266,
        group_restorers=4,pre_fine_driver=SMALL,parallel_fine_driver_copies=2,fine_unit_copies=2,
        coarse_inverter_stages=2,input_to_output_polarity='noninverting',path_inversions=4,
        node_polarities=dict(selected='inverting',pre_out='noninverting',fine_node='inverting'),
        unchanged_component_definitions_preserved=True,new_shared_wire_rc_qualified=False)
    return result,observations,revision


def fixture(out,identity,spec):
    text=baseline.fixture(out,identity,spec)
    if text.count(baseline.TOP)!=1:raise ValueError('Original full native bank fixture changed')
    return text.replace('OpenLVDS '+baseline.VERSION,'OpenLVDS '+VERSION,1).replace(baseline.TOP,TOP,1).replace(
        '.print tran ','.print tran V(XD:pre_out) ',1)


def evidence(parent):
    manifest=json.loads((parent/'manifest.json').read_text());i=manifest['identity']
    report=json.loads((parent/'summary.json').read_text())
    if (parent!=PARENT or i['version']!=baseline.VERSION
            or parent.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
            or json.loads((parent/'state.json').read_text())!=dict(status='complete',cases=4,errors=0,qualified_phy=False)
            or report['comparison']!=baseline.compare(report['rows'])
            or report['comparison']['component_hypothesis_passed'] is not False
            or report['rows'][0]['result']['zero_code_quarter_passed'] is not False
            or any(v>=0 for v in report['comparison']['conservative_coarse_overlap_ps'].values())
            or sha(parent/'bank.spice')!=manifest['bank_sha256']):
        raise ValueError('Require complete failed P40 zero/range screen before changing architecture')
    paths=[parent/n for n in ('manifest.json','summary.json','state.json','bank.spice')];expected={}
    for k,stamp in enumerate(REPLAYS):
        proof_file=ROOT/'build/reports/pullup_bank_native_replay'/stamp/'summary.json'
        proof=json.loads(proof_file.read_text());row=json.loads((parent/str(k)/'summary.json').read_text())
        if (row!=report['rows'][k] or row['task']!=manifest['tasks'][k] or row['error'] is not None
                or proof['case']!=str((parent/str(k)).relative_to(ROOT))
                or proof.get('all_original_native_metrics_reproduced') is not True
                or proof.get('native_mos')!=1385 or proof.get('programming_gates')!=173):
            raise ValueError('Require all four exact independently replayed native cases')
        for n,h in proof['inputs'].items():
            if n in expected and expected[n]!=h:raise ValueError('Conflicting frozen baseline inputs')
            expected[n]=h
        paths += [proof_file,parent/str(k)/'summary.json']
    am=json.loads((ANALYSIS/'manifest.json').read_text());ar=json.loads((ANALYSIS/'summary.json').read_text())
    if (am['identity']['version']!=latency.VERSION
            or json.loads((ANALYSIS/'state.json').read_text())!=dict(status='complete',analysis_completed=True,qualified_phy=False)
            or ar.get('analysis_completed') is not True or ar.get('parameters_changed') is not False
            or ar.get('no_new_simulation') is not True):
        raise ValueError('Require completed slew/recovery analysis before selecting staged restoration')
    for n,h in am['identity']['inputs'].items():
        if n in expected and expected[n]!=h:raise ValueError('Conflicting native slew-analysis inputs')
        expected[n]=h
    paths += [ANALYSIS/n for n in ('manifest.json','summary.json','state.json')]
    return i,paths,expected,report['comparison']


def prepare(parent):
    old,paths,expected,comparison=evidence(parent)
    if engine()!='ngspice' or provenance()!=old['simulator']:raise ValueError('Require pinned native ngspice')
    cells,driver_paths,driver_i=tapered.driver_materials(DRIVERS)
    bank,observations,revision=transform((parent/'bank.spice').read_text(),old['observations'],cells['p10n8'])
    paths += driver_paths+[ROOT/n for n in expected]
    paths += sorted({Path(m.__file__).resolve() for m in list(sys.modules.values())
        if getattr(m,'__file__',None) and Path(m.__file__).resolve().parent==ROOT/'scripts'})
    inputs={str(p.relative_to(ROOT)):sha(p) for p in sorted(set(paths))}
    if any(inputs.get(n)!=h for n,h in expected.items()):raise ValueError('Baseline science or component bytes changed')
    identity=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),specs=specifications(),
        model=old['model'],ports=old['ports'],pdk_files=old['pdk_files'],simulator=old['simulator'],
        observations=observations,native_revision=revision,baseline_comparison=comparison,
        inputs=inputs,guards={n:h for n,h in inputs.items() if not n.endswith('.raw')},
        external_files={**old['external_files'],**driver_i['external_files']},drivers=str(DRIVERS.relative_to(ROOT)),
        architecture_analysis=str(ANALYSIS.relative_to(ROOT)),max_workers=2,priority=1,scope=SCOPE)
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);(out/'bank.spice').write_text(bank)
    tasks=[]
    for k,spec in enumerate(identity['specs']):
        folder=out/str(k);folder.mkdir();text=fixture(out,identity,spec);(folder/'bench.cir').write_text(text)
        tasks.append(dict(id=str(k),spec=spec,deck_sha256=hashlib.sha256(text.encode()).hexdigest()))
    atomic(out/'manifest.json',dict(identity=identity,tasks=tasks,bank_sha256=sha(out/'bank.spice'),qualified_phy=False))
    return out


def bound(out,full=True):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION or i['scope']!=SCOPE
            or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
            or i['specs']!=specifications() or (i['max_workers'],i['priority'])!=(2,1)
            or i['guards']!={n:h for n,h in i['inputs'].items() if not n.endswith('.raw')}
            or any(sha(ROOT/n)!=h for n,h in (i['inputs'] if full else i['guards']).items())
            or any(sha(Path(n))!=h for n,h in {**i['pdk_files'],**i['external_files']}.items())
            or engine()!='ngspice' or provenance()!=i['simulator'] or sha(out/'bank.spice')!=m['bank_sha256']):
        raise ValueError('Restored/balanced native bank context changed')
    old=json.loads((ROOT/i['parent']/'manifest.json').read_text())['identity']
    text=(out/'bank.spice').read_text();small=definition(text,SMALL)
    expected,observations,revision=transform((ROOT/i['parent']/'bank.spice').read_text(),old['observations'],small)
    if text!=expected or observations!=i['observations'] or revision!=i['native_revision']:
        raise ValueError('Staged restoration, balanced units or full native observations cannot regenerate')
    tasks=[]
    for k,spec in enumerate(specifications()):
        text=fixture(out,i,spec);deck=out/str(k)/'bench.cir'
        if deck.read_text()!=text:raise ValueError('Original full eight-event bank fixture changed')
        tasks.append(dict(id=str(k),spec=spec,deck_sha256=sha(deck)))
    if m['tasks']!=tasks:raise ValueError('Require exact four original zero/duty/coarse points')
    return m


def measure(folder,i,spec):
    return dict(baseline.measure(folder,i,spec),scope=SCOPE,new_common_routing_qualified=False,
        native_component_rc_hypothesis_only=True,electrical_qualification_passed=False,qualified_phy=False)


def compare(rows):
    if len(rows)!=4 or any(r['error'] is not None or r['result'] is None for r in rows):return None
    if [r['spec'] for r in rows]!=specifications():raise ValueError('Require full four-point restored-bank coverage')
    complete=all(len(r['result']['edge_delays_ps'][edge])==8
        and all(np.isfinite(v) and v>0 for v in r['result']['edge_delays_ps'][edge])
        for r in rows for edge in ('rise','fall'))
    overlap={edge:min(v for r in rows[1:3] for v in r['result']['edge_delays_ps'][edge])
        -max(rows[3]['result']['edge_delays_ps'][edge]) if complete else None for edge in ('rise','fall')}
    keys=('current_clock_interface_screen_passed','input_timing_stimulus_passed',
        'full_swing_pulses_passed','unwrapped_native_epoch_passed','pulse_order_and_widths_passed',
        'current_downstream_250ps_slew_domain_passed','period_screen_passed','repeated_delay_screen_passed',
        'zero_code_quarter_passed','terminal_screen_passed','control_settling_passed','periodic_transport_screen_passed')
    return dict(component_hypothesis_passed=bool(complete
        and all(r['result'].get(k) is True for r in rows for k in keys)
        and all(v>0 for v in overlap.values())),conservative_coarse_overlap_ps=overlap,
        complete_four_point_native_screen=True,shared_wire_rc_qualified=False,all_pvt_covered=False,
        electrical_qualification_passed=False,qualified_phy=False)


def run(out):
    m=bound(out);i=m['identity']
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain existing or partial restored/balanced bank run')
        atomic(out/'state.json',dict(status='running',qualified_phy=False))
        def execute(task):
            folder=out/task['id'];result=error=None
            try:
                with lease(ROOT,priority=1,label=CONTEXT+'_'+task['id']):
                    bound(out,full=False)
                    p=subprocess.run([sys.executable,str(ROOT/'scripts/run_native_binary_v2.py'),
                        '-l',str(folder/'ngspice.log'),str(folder/'bench.cir')],capture_output=True,text=True)
                (folder/'console.log').write_text(p.stdout+p.stderr);p.check_returncode()
                result=measure(folder,i,task['spec'])
            except Exception as exc:error=str(exc)
            row=dict(task=task,spec=task['spec'],result=result,error=error,
                files={p.name:sha(p) for p in folder.iterdir() if p.is_file()})
            atomic(folder/'summary.json',row);return row
        with ThreadPoolExecutor(max_workers=2) as pool:rows=list(pool.map(execute,m['tasks']))
        bound(out)
        atomic(out/'summary.json',dict(rows=rows,comparison=compare(rows),qualified_phy=False,scope=SCOPE))
        atomic(out/'state.json',dict(status='complete',cases=4,errors=sum(r['error'] is not None for r in rows),qualified_phy=False))
    return out


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('prepare','run','campaign'));parser.add_argument('artifact',type=Path)
    args=parser.parse_args();out=args.artifact.resolve()
    if args.action in ('prepare','campaign'):out=prepare(out);print(out,flush=True)
    if args.action in ('run','campaign'):print(run(out),flush=True)
