#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Return the independently verified P80/N32 recovery intervention to a full bank."""
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
import probe_restored_balanced_bank_v352 as source
import probe_restored_fine_recovery_v355 as recovery
from spice_dispatch import lease
from spice_engine import engine,provenance

ROOT=source.ROOT
VERSION='full-staged-bank-verified-p80n32-fine-recovery-v359.1'
CONTEXT='pullup_restored_bank_v359'
TOP='openlvds_pullup_restored_bank_v359'
FINE=recovery.STRONG
sha=source.sha
atomic=source.atomic
SCOPE=('Full original zero/fine60/fine40/coarse1 eight-startup-event SS40/410MHz '
       '25ns screen after independently verified local P80/N32 recovery; only '
       'two fine P20/N16 cells become two qualified P40/N16, with actual upstream '
       'loading and unchanged P10/N8 pre-driver, other cells and all original '
       'quarter/history/period/slew/control/voltage/overlap gates. Original 20fF '
       'screen only, no actual next-bank load/new shared RC/dense/update/PVT/DLL/PHY admission')


def specifications():
    return [dict(s,architecture='staged_restoration_pullup_recovery',loaded_driver='two_parallel_p40n16')
            for s in source.specifications()]


def transform(text,previous,wrapper):
    defs=source.native.definitions(text);extra=source.native.definitions(wrapper)
    expected=[['Xa','A','Y','VGND','VPWR',recovery.PULLUP],['Xb','A','Y','VGND','VPWR',recovery.PULLUP]]
    if (set(extra)!={FINE} or extra[FINE]!=(['A','Y','VGND','VPWR'],expected)
            or FINE in defs or defs[recovery.PULLUP][0]!=['A','Y','VGND','VPWR']):
        raise ValueError('Require exact verified two-P40/N16 native wrapper')
    ports,body=defs[source.TOP]
    old=['Xfine_isolate','pre_out','fine_node','VGND','VPWR',source.FINE]
    if sum(w==old for w in body)!=1 or len(previous['devices'])!=2086:
        raise ValueError('Original restored full bank changed')
    new=[w[:-1]+[FINE] if w==old else w for w in body]
    block='\n'.join(['.subckt '+TOP+' '+' '.join(ports),*[' '.join(w) for w in new],'.ends '+TOP,''])
    result=text.replace(source.definition(text,source.TOP),block,1)+'\n'+wrapper
    if any(source.definition(result,n)!=source.definition(text,n) for n in defs if n!=source.TOP):
        raise ValueError('Unrelated qualified component definition changed')
    devices=source.native.mapped_mos(result,TOP,{p:'0' if p=='VGND' else 'VDD' if p=='VPWR' else p for p in ports},'XD')
    before={d['name']:d for d in previous['devices']};after={d['name']:d for d in devices};prefix='XD:Xfine_isolate:'
    if (len(after)!=2126 or len(devices)!=2126
            or sum(n.startswith(prefix) for n in before)!=72 or sum(n.startswith(prefix) for n in after)!=112
            or any(after.get(n)!=d for n,d in before.items() if not n.startswith(prefix))
            or len(previous['controls'])!=86 or len(previous['programming_gates'])!=266):
        raise ValueError('Actual full native inventory or retained terminal map changed')
    for gate in previous['programming_gates']:
        if after[gate['device']]['terminals'][1]!=gate['gate_node']:raise ValueError('Original programming gate changed')
    _,leaves=source.inventory.native_leaves(source.collapse(result),TOP)
    if sum('fet_' in d['model'] for d in leaves)!=2126 or sum('cap_mim' in d['model'] for d in leaves)!=139:
        raise ValueError('Actual full MOS/MIM inventory changed')
    return result,dict(devices=devices,controls=deepcopy(previous['controls']),programming_gates=deepcopy(previous['programming_gates']))


def fixture(out,identity,spec):
    text=source.fixture(out,identity,spec)
    if text.count(source.TOP)!=1:raise ValueError('Original full-bank fixture changed')
    return text.replace('OpenLVDS '+source.VERSION,'OpenLVDS '+VERSION,1).replace(source.TOP,TOP,1)


def prepare(local,receipts):
    rm=recovery.bound(local,full=False);ri=rm['identity'];report=json.loads((local/'summary.json').read_text())
    if (json.loads((local/'state.json').read_text())!=dict(status='complete',cases=2,errors=0,guarded=0,qualified_phy=False)
            or report['baseline_usable'] is not True or not recovery.recorded.baseline_usable(report['rows'][0]['result'])
            or report['rows'][1]['result']['current_clock_interface_screen_passed'] is not True
            or len(receipts)!=2):raise ValueError('Require complete parity-gated passing local recovery')
    paths=[local/n for n in ('manifest.json','summary.json','state.json','selected.spice',*rm['libraries'])]
    for k,path in enumerate(receipts):
        proof=json.loads(path.read_text());rows=proof['rows']
        if (proof.get('all_original_native_metrics_reproduced') is not True
                or proof.get('all_original_selected_source_points_preserved') is not True
                or proof.get('parameters_changed') is not False or len(rows)!=1
                or rows[0]['case']!=str((local/str(k)).relative_to(ROOT))
                or rows[0]['native_mos']!=(622 if k==0 else 662) or rows[0]['programming_gates']!=186
                or rows[0]['all_original_native_metrics_reproduced'] is not True
                or (k==0 and rows[0]['baseline_parity']['parity_passed'] is not True)
                or (k==1 and rows[0]['recorded_gates']['current_clock_interface_screen_passed'] is not True)
                or any(sha(ROOT/n)!=h for n,h in proof['inputs'].items())):
            raise ValueError('Require exact independent baseline and successful pull-up replays')
        folder=local/str(k);row=json.loads((folder/'summary.json').read_text())
        if row!=report['rows'][k] or any(sha(folder/n)!=h for n,h in row['files'].items()):
            raise ValueError('Complete local native recovery evidence changed')
        paths += [path,folder/'summary.json',*[folder/n for n in row['files']],*[ROOT/n for n in proof['inputs']]]
    parent=ROOT/ri['parent'];m=source.bound(parent,full=False);i=m['identity']
    original=(parent/'bank.spice').read_text();local_text=(local/'pullup/bank.spice').read_text()
    if source.definition(original,recovery.PULLUP)!=source.definition(local_text,recovery.PULLUP):
        raise ValueError('Qualified P40 numerical component differs from successful local intervention')
    wrapper=source.definition(local_text,FINE);text,observations=transform(original,i['observations'],wrapper)
    paths += [parent/'manifest.json',parent/'bank.spice',*[ROOT/n for n in i['guards']]]
    paths += sorted({Path(module.__file__).resolve() for module in list(sys.modules.values())
        if getattr(module,'__file__',None) and Path(module.__file__).resolve().parent==ROOT/'scripts'})
    inputs={str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p):sha(p) for p in sorted(set(paths))}
    identity=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),local_recovery=str(local.relative_to(ROOT)),
        receipts=[str(p.relative_to(ROOT)) for p in receipts],specs=specifications(),model=TOP,ports=i['ports'],
        observations=observations,inputs=inputs,guards={n:h for n,h in inputs.items() if not n.endswith('.raw')},
        pdk_files=i['pdk_files'],external_files=i['external_files'],simulator=i['simulator'],
        native_revision=dict(native_mos=2126,native_mims=139,controls=86,programming_gates=266,
            fine_wrapper=FINE,fine_cells=2,pre_driver=source.SMALL,all_unrelated_calls_and_definitions_preserved=True),
        max_workers=2,priority=1,scope=SCOPE)
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);(out/'bank.spice').write_text(text);tasks=[]
    for k,spec in enumerate(specifications()):
        (out/str(k)).mkdir();(out/str(k)/'bench.cir').write_text(fixture(out,identity,spec))
        tasks.append(dict(id=str(k),spec=spec,deck_sha256=sha(out/str(k)/'bench.cir')))
    atomic(out/'manifest.json',dict(identity=identity,tasks=tasks,bank_sha256=sha(out/'bank.spice'),qualified_phy=False))
    return out


def bound(out,full=True):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION or i['scope']!=SCOPE
            or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
            or i['specs']!=specifications() or (i['max_workers'],i['priority'])!=(2,1)
            or i['guards']!={n:h for n,h in i['inputs'].items() if not n.endswith('.raw')}
            or engine()!='ngspice' or provenance()!=i['simulator']
            or any(sha(ROOT/n)!=h for n,h in (i['inputs'] if full else i['guards']).items())
            or any(sha(ROOT/n)!=h for n,h in {**i['pdk_files'],**i['external_files']}.items())
            or sha(out/'bank.spice')!=m['bank_sha256']):raise ValueError('Full restored pull-up bank context changed')
    parent=ROOT/i['parent'];old=json.loads((parent/'manifest.json').read_text())['identity']
    wrapper=source.definition((ROOT/i['local_recovery']/'pullup/bank.spice').read_text(),FINE)
    text,observations=transform((parent/'bank.spice').read_text(),old['observations'],wrapper)
    if text!=(out/'bank.spice').read_text() or observations!=i['observations']:
        raise ValueError('Verified local intervention cannot regenerate complete native bank')
    tasks=[]
    for k,spec in enumerate(specifications()):
        if (out/str(k)/'bench.cir').read_text()!=fixture(out,i,spec):raise ValueError('Original full eight-event fixture changed')
        tasks.append(dict(id=str(k),spec=spec,deck_sha256=sha(out/str(k)/'bench.cir')))
    if m['tasks']!=tasks:raise ValueError('Original zero/duty/coarse coverage changed')
    return m


def measure(folder,i,spec):return dict(source.measure(folder,i,spec),scope=SCOPE)


def compare(rows):
    if len(rows)!=4 or any(r['error'] is not None or r['result'] is None for r in rows):return None
    if [r['spec'] for r in rows]!=specifications():raise ValueError('Full native bank coverage changed')
    complete=all(len(r['result']['edge_delays_ps'][edge])==8
        and all(np.isfinite(v) and v>0 for v in r['result']['edge_delays_ps'][edge]) for r in rows for edge in ('rise','fall'))
    overlap={edge:min(min(rows[k]['result']['edge_delays_ps'][edge]) for k in (1,2))
        -max(rows[3]['result']['edge_delays_ps'][edge]) if complete else None for edge in ('rise','fall')}
    keys=('current_clock_interface_screen_passed','all_input_output_pulses_present','input_timing_stimulus_passed','full_swing_pulses_passed',
        'unwrapped_native_epoch_passed','pulse_order_and_widths_passed','current_downstream_250ps_slew_domain_passed',
        'period_screen_passed','repeated_delay_screen_passed','zero_code_quarter_passed','terminal_screen_passed',
        'control_settling_passed','periodic_transport_screen_passed')
    return dict(component_hypothesis_passed=bool(complete and all(r['result'].get(k) is True for r in rows for k in keys)
        and all(v>0 for v in overlap.values())),conservative_coarse_overlap_ps=overlap,
        complete_four_point_native_screen=True,shared_wire_rc_qualified=False,all_pvt_covered=False,
        electrical_qualification_passed=False,qualified_phy=False)


def run(out):
    m=bound(out);i=m['identity']
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain prior or partial full-bank run')
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
            row=dict(task=task,spec=task['spec'],result=result,error=error,files={p.name:sha(p) for p in folder.iterdir() if p.is_file()})
            atomic(folder/'summary.json',row);return row
        with ThreadPoolExecutor(max_workers=2) as pool:rows=list(pool.map(execute,m['tasks']))
        bound(out)
        atomic(out/'summary.json',dict(rows=rows,comparison=compare(rows),scope=SCOPE,qualified_phy=False))
        atomic(out/'state.json',dict(status='complete',cases=4,errors=sum(r['error'] is not None for r in rows),qualified_phy=False))
    return out


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('prepare','run','campaign'));parser.add_argument('artifact',type=Path)
    parser.add_argument('--baseline-replay',type=Path);parser.add_argument('--pullup-replay',type=Path);args=parser.parse_args()
    out=prepare(args.artifact.resolve(),[args.baseline_replay.resolve(),args.pullup_replay.resolve()]) if args.action in ('prepare','campaign') else args.artifact.resolve()
    print(out,flush=True)
    if args.action in ('run','campaign'):print(run(out),flush=True)
