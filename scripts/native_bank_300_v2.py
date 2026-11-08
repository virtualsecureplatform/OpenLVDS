#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Fresh profile-bound 300MHz bank pilots; historical producers stay immutable."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib,json,re,subprocess,sys
from pathlib import Path
import numpy as np
import clocking_profile_300 as policy
import single_fine_driver_300 as intervention
from copy import deepcopy
import probe_pullup_restored_bank_v360 as restored
import probe_direct_balanced_bank_v365 as direct
import probe_supply_current_centering_v362 as numerical
from native_binary_raw_v2 import validate
from regenerated_bank_periodic_measure_v67 import crossings
from spice_dispatch import lease
ROOT=policy.ROOT
VERSION='300mhz-single-driver-pilot-v2'
PARENTS={'restored':(restored,ROOT/'build/diagnostics/pullup_restored_bank_v360/8dba212d4f9eafd5'),
         'direct':(direct,ROOT/'build/diagnostics/direct_balanced_bank_v365/7a6d5e1732c144c3')}
NUMERICAL=ROOT/'build/diagnostics/supply_current_centering_v362/508e395be9fbc556'
sha=restored.sha
atomic=restored.atomic
KEYS=('all_input_output_pulses_present','input_timing_stimulus_passed','full_swing_pulses_passed',
      'unwrapped_native_epoch_passed','pulse_order_and_widths_passed','period_screen_passed',
      'repeated_delay_screen_passed','zero_code_quarter_passed','terminal_screen_passed','control_settling_passed')

def specifications(kind):
    base=PARENTS[kind][0].specifications()
    specs=[dict(s,frequency_mhz=310,stop_ns=40) for s in base]
    # An unshifted/centered active pair precedes the other three screen points.
    return [(specs[1],False),(specs[1],True),*[(specs[k],True) for k in (0,2,3)]]

def contract(result,spec):
    if spec['frequency_mhz'] not in policy.load()['requirements']['clock_test_mhz']:
        raise ValueError('Legacy frequency cannot qualify the 300MHz profile')
    result=dict(result)
    if spec['coarse']==spec['fine']==0:
        delays=[v for edge in ('rise','fall') for v in result['edge_delays_ps'][edge]]
        complete=len(delays)==16 and all(np.isfinite(v) and v>0 for v in delays)
        room=policy.budgets()['minimum_quarter_ps']-max(delays) if complete else None
        result.update(zero_code_fast_quarter_headroom_ps=room,zero_code_quarter_passed=bool(room is not None and room>=0))
    result['periodic_transport_screen_passed']=all(result.get(k) is True for k in KEYS)
    result['current_clock_interface_screen_passed']=bool(result['periodic_transport_screen_passed'] and result['current_downstream_250ps_slew_domain_passed'])
    result.update(qualified_phy=False,electrical_qualification_passed=False,whole_bank_rc_retained=False,
                  all_pvt_covered=False,scope='Fresh 310MHz SS40 eight-event 40ns pilot, native component RC and original 20fF screen only; next-bank load, routed bank RC and full clock qualification remain open')
    return result

def fixture(out,i,spec,centered):
    producer,_=PARENTS[i['kind']]
    text=producer.fixture(out,i['source_identity'],spec).replace(producer.TOP,i['macro_top'])
    if text.count('.tran 2p 40n 0 2p')!=1 or text.count('VDD VDD 0 1.8\n')!=1:
        raise ValueError('Require complete fresh 40ns stimulus and ideal fixed supply')
    if centered:
        if re.search(r'(?i)\bi\s*\(\s*vdd\s*\)',text) or any(w and w[0].upper() in ('F','H') for w in text.splitlines()):
            raise ValueError('Current feedback prevents invariant centering')
        text=text.replace('VDD VDD 0 1.8\n','VDD VDD 0 1.8\n'+numerical.CARD+'\n',1)
    return text

def prepare(kind):
    if kind!='restored':raise ValueError('Single-driver intervention requires the restored baseline')
    profile=policy.load();producer,parent=PARENTS[kind];m=producer.bound(parent,full=False)
    numerical.bound(NUMERICAL,full=False)
    report=json.loads((NUMERICAL/'summary.json').read_text())
    if any(r['error'] is not None or r['guarded'] for r in report['rows']) or report['rows'][2]['result']['parity_passed'] is not True:
        raise ValueError('Full quiet/observer/active numerical parity must pass first')
    text=(parent/'bank.spice').read_text()
    if re.search(r'(?i)\bi\s*\(\s*vdd\s*\)',text) or any(w and w[0].upper() in ('F','H') for w in text.splitlines()):
        raise ValueError('Macro supply-current feedback prevents invariant centering')
    text,observations=intervention.transform(text,m['identity']['observations'])
    top=intervention.TOP
    source_identity=deepcopy(m['identity']);source_identity['observations']=observations
    paths=[Path(__file__),ROOT/'scripts/clocking_profile_300.py',ROOT/'clocking_300mhz.json',parent/'manifest.json',parent/'bank.spice',NUMERICAL/'manifest.json',NUMERICAL/'summary.json']
    paths+=sorted({Path(mod.__file__).resolve() for mod in list(sys.modules.values()) if getattr(mod,'__file__',None) and Path(mod.__file__).resolve().parent==ROOT/'scripts'})
    inputs={**m['identity']['guards'],**{str(p.relative_to(ROOT)):sha(p) for p in paths}}
    i=dict(version=VERSION,kind=kind,parent=str(parent.relative_to(ROOT)),source_identity=source_identity,macro_top=top,
           profile_sha256=sha(ROOT/'clocking_300mhz.json'),inputs=inputs,max_workers=2,priority=1,
           bench_current_offset_a=.001,power_excludes_external_bench_load=True)
    out=ROOT/'build/diagnostics/native_bank_300_v2'/hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);(out/'bank.spice').write_text(text);tasks=[]
    for k,(s,centered) in enumerate(specifications(kind)):
        folder=out/str(k);folder.mkdir();(folder/'bench.cir').write_text(fixture(out,i,s,centered))
        tasks.append(dict(id=str(k),spec=s,centered=centered,deck_sha256=sha(folder/'bench.cir')))
    atomic(out/'manifest.json',dict(identity=i,tasks=tasks,bank_sha256=sha(out/'bank.spice'),qualified_phy=False));bound(out)
    return out

def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity'];producer,parent=PARENTS[i['kind']]
    if (out.parent!=ROOT/'build/diagnostics/native_bank_300_v2' or i['version']!=VERSION
        or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or i['profile_sha256']!=sha(ROOT/'clocking_300mhz.json') or (i['max_workers'],i['priority'])!=(2,1)):
        raise ValueError('300MHz native context changed')
    original=producer.bound(parent,full=False)['identity']
    if i['kind']!='restored' or i['bench_current_offset_a']!=.001 or i['power_excludes_external_bench_load'] is not True:raise ValueError('Intervention metadata changed')
    if any(sha(ROOT/n)!=v for n,v in i['inputs'].items()):raise ValueError('Captured source/profile changed')
    expected,observations=intervention.transform((parent/'bank.spice').read_text(),original['observations'])
    source_identity=deepcopy(original);source_identity['observations']=observations
    if i['source_identity']!=source_identity or i['macro_top']!=intervention.TOP:raise ValueError('Source identity or native observation map changed')
    if (out/'bank.spice').read_text()!=expected or sha(out/'bank.spice')!=m['bank_sha256']:raise ValueError('Native library changed')
    tasks=[]
    for k,(s,c) in enumerate(specifications(i['kind'])):
        f=out/str(k)/'bench.cir'
        if f.read_text()!=fixture(out,i,s,c):raise ValueError('Native stimulus changed')
        tasks.append(dict(id=str(k),spec=s,centered=c,deck_sha256=sha(f)))
    if tasks!=m['tasks']:raise ValueError('Required native points changed')
    return m

def parity(out,rows):
    if any(r['error'] is not None for r in rows[:2]):return dict(passed=False,reason='Active control incomplete')
    names,a=validate(out/'0/bench.raw',set(),40e-9);other,b=validate(out/'1/bench.raw',set(names),40e-9)
    diff=numerical.wave_difference(names,a,other,b);errors=[]
    for node in ('v(in)','v(out)'):
        for up in (True,False):
            x=crossings(a[:,0]*1e12,a[:,names.index(node)],.9,up);y=crossings(b[:,0]*1e12,b[:,other.index(node)],.9,up)
            if len(x)!=8 or len(y)!=8:return dict(passed=False,reason='Missing active control events')
            errors.extend(abs(v-w) for v,w in zip(x,y))
    flags=all(rows[0]['result'][k]==rows[1]['result'][k] for k in (*KEYS,'current_downstream_250ps_slew_domain_passed'))
    for category in ('terminal_stress','controls','programming_gates'):
        flags=flags and [v['passed'] for v in rows[0]['result'][category]]==[v['passed'] for v in rows[1]['result'][category]]
    return dict(passed=bool(diff['maximum_all_vector_error_v']<=.002 and max(errors)<=.25 and flags),reference_difference=diff,maximum_crossing_error_ps=max(errors),all_gate_classifications_preserved=flags)

def run(out):
    import fcntl
    m=bound(out);i=m['identity'];producer,_=PARENTS[i['kind']]
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain prior or partial native campaign')
        atomic(out/'state.json',dict(status='running',qualified_phy=False))
        def execute(task):
            f=out/task['id'];error=result=None
            try:
                with lease(ROOT,priority=1,label='native_bank_300_v2_'+i['kind']+'_'+task['id']):
                    bound(out)
                    p=subprocess.run([sys.executable,str(ROOT/'scripts/run_native_binary_v2.py'),'-l',str(f/'ngspice.log'),str(f/'bench.cir')],capture_output=True,text=True)
                (f/'console.log').write_text(p.stdout+p.stderr);p.check_returncode()
                result=contract(producer.measure(f,i['source_identity'],task['spec']),task['spec'])
            except Exception as exc:error=str(exc)
            row=dict(task=task,result=result,error=error,files={p.name:sha(p) for p in f.iterdir() if p.is_file()});atomic(f/'summary.json',row);return row
        with ThreadPoolExecutor(max_workers=2) as pool:rows=list(pool.map(execute,m['tasks']))
        check=parity(out,rows)
        screen=[rows[k] for k in (2,1,3,4)]
        overlap={e:min(v for k in (1,3) for v in rows[k]['result']['edge_delays_ps'][e])-max(rows[4]['result']['edge_delays_ps'][e]) for e in ('rise','fall')} if all(r['result'] is not None for r in rows) else None
        passed=bool(check['passed'] and overlap and all(v>0 for v in overlap.values()) and all(r['result']['current_clock_interface_screen_passed'] for r in screen))
        bound(out);atomic(out/'summary.json',dict(rows=rows,active_numerical_parity=check,conservative_overlap_ps=overlap,component_pilot_passed=passed,qualified_phy=False))
        atomic(out/'state.json',dict(status='complete',cases=5,errors=sum(r['error'] is not None for r in rows),qualified_phy=False))
    return out

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('action',choices=['prepare','run']);a.add_argument('target');args=a.parse_args()
    out=prepare(args.target) if args.action=='prepare' else Path(args.target).resolve()
    print(out,flush=True)
    if args.action=='run':run(out)
