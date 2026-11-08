#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Test DC-zero transient-ramped bench current with complete native parity."""
import argparse,fcntl,hashlib,json,re,subprocess,sys,time
from pathlib import Path
import native_bank_300_v2 as reference
from native_binary_raw_v2 import validate
from regenerated_bank_periodic_measure_v67 import crossings
from run_native_binary_v2 import translate
from spice_dispatch import lease
ROOT=reference.ROOT
PARENT=ROOT/'build/diagnostics/native_bank_300_v2/2d31edbabe113146'
VERSION='dc-zero-transient-current-origin-full-native-parity-300-v1'
CONTEXT='ramped_current_center_300_v1'
OFFSETS=(.001,)
CARD='I_BENCH_CURRENT_CENTER VDD 0 DC 0 PWL(0 0 2p 0 4p 1m 40n 1m)'
sha=reference.sha
atomic=reference.atomic


def deck(original,library,parent_library,offset):
    if offset not in OFFSETS:raise ValueError('Only the fixed 1mA DC-zero transient bench origin')
    if (original.count('VDD VDD 0 1.8\n')!=1 or original.count('.tran 2p 40n 0 2p')!=1
            or 'I_BENCH_CURRENT_CENTER' in original
            or re.search(r'(?i)\bi\s*\(\s*vdd\s*\)',original)
            or any(w and w[0].upper() in ('F','H') for w in original.splitlines())):
        raise ValueError('Require unshifted fixed ideal supply without current feedback')
    include=f'.include "{parent_library}"'
    if original.count(include)!=1:raise ValueError('Captured native library path changed')
    text=original.replace(include,f'.include "{library}"',1)
    text=text.replace('VDD VDD 0 1.8\n','VDD VDD 0 1.8\n'+CARD+'\n',1)
    translate(text);return text


def prepare():
    m=reference.bound(PARENT);i=m['identity'];row=json.loads((PARENT/'0/summary.json').read_text());summary=json.loads((PARENT/'summary.json').read_text())
    if (json.loads((PARENT/'state.json').read_text())!=dict(status='complete',cases=5,errors=0,qualified_phy=False)
            or row['task']!=m['tasks'][0] or row['task']['centered'] is not False or row['error'] is not None
            or summary['active_numerical_parity']['passed'] is not False
            or summary['active_numerical_parity']['reference_difference']['maximum_all_vector_error_v']<=.002
            or summary['active_numerical_parity']['all_gate_classifications_preserved'] is not True):
        raise ValueError('Require exact complete unshifted reference and observed old-offset vector failure')
    original=(PARENT/'0/bench.cir').read_text();native=(PARENT/'bank.spice').read_text()
    if re.search(r'(?i)\bi\s*\(\s*vdd\s*\)',native) or any(w and w[0].upper() in ('F','H') for w in native.splitlines()):
        raise ValueError('Native macro current feedback prevents invariant bench origin')
    inputs={**i['inputs'],**i['source_identity']['pdk_files'],**i['source_identity']['external_files']}
    paths=[PARENT/n for n in ('manifest.json','summary.json','state.json','bank.spice')]
    paths += [PARENT/'0/summary.json',*[PARENT/'0'/n for n in row['files']]]
    paths += sorted({Path(mod.__file__).resolve() for mod in list(sys.modules.values())
        if getattr(mod,'__file__',None) and Path(mod.__file__).resolve().parent==ROOT/'scripts'})
    inputs.update({str(p.relative_to(ROOT)):sha(p) for p in paths})
    if any(sha(ROOT/n)!=h for n,h in inputs.items()):raise ValueError('Numerical reference changed')
    identity=dict(version=VERSION,parent=str(PARENT.relative_to(ROOT)),inputs=inputs,offsets_a=list(OFFSETS),
        max_workers=1,priority=2,current_source_card=CARD,dc_voltage_limit_v=1e-9,voltage_limit_v=.002,crossing_limit_ps=.25,external_power_excluded=True,
        stop_after_first_admissible_offset=True,qualified_phy=False)
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);(out/'bank.spice').write_text(native)
    tasks=[]
    for k,offset in enumerate(OFFSETS):
        folder=out/str(k);folder.mkdir();(folder/'bench.cir').write_text(deck(original,out/'bank.spice',PARENT/'bank.spice',offset))
        tasks.append(dict(id=str(k),offset_a=offset,external_bench_power_ceiling_w=1.8*offset,deck_sha256=sha(folder/'bench.cir')))
    atomic(out/'manifest.json',dict(identity=identity,tasks=tasks,bank_sha256=sha(out/'bank.spice'),qualified_phy=False));bound(out)
    return out


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION
            or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
            or i['parent']!=str(PARENT.relative_to(ROOT)) or i['offsets_a']!=list(OFFSETS)
            or (i['max_workers'],i['priority'],i['voltage_limit_v'],i['crossing_limit_ps'])!=(1,2,.002,.25)
            or i['external_power_excluded'] is not True or i['stop_after_first_admissible_offset'] is not True
            or i['current_source_card']!=CARD or i['dc_voltage_limit_v']!=1e-9
            or i['qualified_phy'] is not False or m['qualified_phy'] is not False):raise ValueError('DC-zero transient-origin numerical context changed')
    reference.bound(PARENT)
    if any(sha(ROOT/n)!=h for n,h in i['inputs'].items()):raise ValueError('Captured numerical reference/model/runtime changed')
    if sha(out/'bank.spice')!=m['bank_sha256'] or (out/'bank.spice').read_bytes()!=(PARENT/'bank.spice').read_bytes():raise ValueError('Native macro changed')
    expected=[]
    for k,offset in enumerate(OFFSETS):
        path=out/str(k)/'bench.cir'
        if path.read_text()!=deck((PARENT/'0/bench.cir').read_text(),out/'bank.spice',PARENT/'bank.spice',offset):raise ValueError('Numerical stimulus changed')
        expected.append(dict(id=str(k),offset_a=offset,external_bench_power_ceiling_w=1.8*offset,deck_sha256=sha(path)))
    if m['tasks']!=expected:raise ValueError('Bounded numerical controls changed')
    return m


def compare(original,new,old_result,new_result):
    names,a=validate(original/'bench.raw',set(),40e-9);other,b=validate(new/'bench.raw',set(names),40e-9)
    forward=reference.numerical.wave_difference(names,a,other,b);reverse=reference.numerical.wave_difference(other,b,names,a)
    errors=[]
    for node in ('v(in)','v(out)'):
        for up in (True,False):
            x=crossings(a[:,0]*1e12,a[:,names.index(node)],.9,up);y=crossings(b[:,0]*1e12,b[:,other.index(node)],.9,up)
            if len(x)!=8 or len(y)!=8:return dict(passed=False,reason='Missing native events')
            errors.extend(abs(v-w) for v,w in zip(x,y))
    flags=all(old_result[k]==new_result[k] for k in (*reference.KEYS,'current_downstream_250ps_slew_domain_passed'))
    for category in ('terminal_stress','controls','programming_gates'):
        flags=flags and [v['passed'] for v in old_result[category]]==[v['passed'] for v in new_result[category]]
    maximum=max(forward['maximum_all_vector_error_v'],reverse['maximum_all_vector_error_v'])
    if a[0,0]!=0 or b[0,0]!=0:raise ValueError('Require original DC sample at t=0')
    initial=max(abs(float(a[0,names.index(n)])-float(b[0,other.index(n)])) for n in names if n.startswith('v('))
    dc_preserved=bool(initial<=1e-9)
    return dict(passed=bool(maximum<=.002 and max(errors)<=.25 and flags and dc_preserved),maximum_all_vector_error_v=maximum,
        maximum_dc_voltage_error_v=initial,dc_operating_point_preserved=dc_preserved,
        maximum_crossing_error_ps=max(errors),all_gate_classifications_preserved=flags,forward=forward,reverse=reverse,
        original_failed_history_preserved=old_result['repeated_delay_screen_passed'] is False and new_result['repeated_delay_screen_passed'] is False)



def engine_elapsed(folder):
    log=folder/'ngspice.log'
    if not log.is_file():return None
    values=re.findall(r'(?m)^Total elapsed time \(seconds\) =\s*([0-9.eE+-]+)',log.read_text())
    return float(values[0]) if len(values)==1 else None

def run(out):
    m=bound(out);parent=reference.bound(PARENT);i=parent['identity'];old=json.loads((PARENT/'0/summary.json').read_text())
    producer=reference.PARENTS[i['kind']][0];spec=old['task']['spec']
    if reference.contract(producer.measure(PARENT/'0',i['source_identity'],spec),spec)!=old['result']:
        raise ValueError('Full original numerical reference does not reproduce')
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain prior or partial numerical controls')
        atomic(out/'state.json',dict(status='running',qualified_phy=False));rows=[];admitted=None
        for task in m['tasks']:
            folder=out/task['id'];start=time.monotonic();error=result=proof=None
            try:
                with lease(ROOT,priority=2,label=CONTEXT+'_'+task['id']):
                    bound(out)
                    process=subprocess.run([sys.executable,str(ROOT/'scripts/run_native_binary_v2.py'),'-l',str(folder/'ngspice.log'),str(folder/'bench.cir')],capture_output=True,text=True)
                (folder/'console.log').write_text(process.stdout+process.stderr);process.check_returncode()
                result=reference.contract(producer.measure(folder,i['source_identity'],spec),spec)
                proof=compare(PARENT/'0',folder,old['result'],result)
            except Exception as exc:error=str(exc)
            row=dict(task=task,error=error,result=result,parity=proof,observed_wall_seconds_including_lease_wait=time.monotonic()-start,ngspice_elapsed_seconds=engine_elapsed(folder),
                files={p.name:sha(p) for p in folder.iterdir() if p.is_file()})
            atomic(folder/'summary.json',row);rows.append(row)
            if error is None and proof['passed']:
                admitted=task['offset_a'];break
        bound(out);atomic(out/'summary.json',dict(rows=rows,admissible_offset_for_reference_case_a=admitted,
            skipped_after_success=[t['id'] for t in m['tasks'][len(rows):]],reference_ngspice_elapsed_seconds=engine_elapsed(PARENT/'0'),original_results_preserved=True,qualified_phy=False,
            scope='Numerical origin validation for one exact completed native case only; every new circuit still requires its own active parity; no physical timing failure repaired or PHY admitted'))
        atomic(out/'state.json',dict(status='complete',cases_executed=len(rows),errors=sum(r['error'] is not None for r in rows),qualified_phy=False))
    return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('prepare','run'));p.add_argument('artifact',type=Path,nargs='?');a=p.parse_args()
    print(prepare() if a.action=='prepare' else run(a.artifact.resolve()),flush=True)
