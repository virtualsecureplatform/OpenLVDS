#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Gate a long genuine DCO capture on observed native KLU/SMP waveform parity."""
import argparse,fcntl,hashlib,json,os,subprocess,sys
from pathlib import Path
import numpy as np
import clocking_profile_300 as policy
import capture_openpll_physical_300 as source
from native_binary_raw_v2 import validate
from regenerated_bank_periodic_measure_v67 import crossings
from spice_dispatch import lease
ROOT=policy.ROOT
BASE=ROOT/'build/diagnostics/openpll_trace_300/20261108T013035Z'
PROOF=ROOT/'build/diagnostics/verified_clock_sources_300/b919a47f1f6cefea'
VERSION='parity-gated-klu-long-native-dco-300-v1'
CONTEXT='openpll_long_trace_300_v1'
sha=source.sha


def deck(original,stop_ns):
    if not 70<=stop_ns<=200000:raise ValueError('DCO duration outside bounded capture range')
    option='.option method=gear reltol=1e-3 abstol=1e-15 chgtol=1e-16 num_threads=2'
    reset='VRESET RESET_N 0 PULSE(0 {VDD} 5.0n 50p 50p 70.0n 140.0n)'
    tran='.tran 2.0p 70.0n 0 2.0p'
    if (original.count(option)!=1 or original.count(reset)!=1 or original.count(tran)!=1
            or '.option klu' in original.lower()):raise ValueError('Require exact unmodified pinned native baseline')
    result=original.replace(option,option+'\n.option klu',1)
    result=result.replace(reset,'VRESET RESET_N 0 PULSE(0 {VDD} 5.0n 50p 50p '+f'{stop_ns:.1f}n {2*stop_ns:.1f}n)',1)
    return result.replace(tran,f'.tran 2.0p {stop_ns:.1f}n 0 2.0p',1)


def parity(t,a,u,b):
    if (t[0]>1e-18 or u[0]>1e-18 or t[-1]<70e-9*(1-1e-8) or u[-1]<70e-9*(1-1e-8)
            or np.any(np.diff(t)<=0) or np.any(np.diff(u)<=0)
            or not all(np.isfinite(v).all() for v in (t,a,u,b))):
        raise ValueError('Require complete finite unshifted 70 ns native parity traces')
    errors=[]
    for up in (True,False):
        x=crossings(t*1e12,a,.9,up);y=crossings(u*1e12,b,.9,up)
        if len(x)!=len(y) or len(x)<8:return dict(passed=False,reason='Missing native observed clock events')
        errors.extend(abs(v-w) for v,w in zip(x,y))
    maximum=max(float(np.max(abs(a-np.interp(t,u,b)))),float(np.max(abs(b-np.interp(u,t,a)))))
    return dict(passed=bool(maximum<=.002 and max(errors)<=.25),maximum_observed_voltage_error_v=maximum,
                maximum_absolute_crossing_error_ps=max(errors),observed_node='PLLOUT',
                internal_voltage_parity_not_observed=True,phase_alignment_or_rescaling_applied=False)


def prepare(stop_ns=20000):
    p=policy.load()
    if type(stop_ns) is not int or not 20000<=stop_ns<=200000:raise ValueError('Long source must cover at least 20 us, bounded at 200 us')
    proof=json.loads((PROOF/'manifest.json').read_text());i=proof['identity'];report=json.loads((PROOF/'summary.json').read_text())
    if (i['version']!='verified-genuine-clock-sources-300-v1'
            or PROOF.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
            or report['all_source_contracts_passed'] is not True or report['qualified_phy'] is not False
            or i['openpll_commit']!=p['requirements']['openpll_commit']
            or not any(r['trace']==str((BASE/'clock.csv').relative_to(ROOT)) for r in report['rows'])):
        raise ValueError('Require independent genuine physical source verification')
    if json.loads((BASE/'state.json').read_text())!=dict(status='complete',qualified_phy=False):raise ValueError('Never replace or interrupt a live baseline')
    raw=json.loads((BASE/'summary.json').read_text());original=(BASE/'bench.cir').read_text()
    if sha(BASE/'bench.raw')!=raw['raw_sha256'] or raw['metrics']['passed'] is not True:raise ValueError('Original native clock changed')
    files=[PROOF/'manifest.json',PROOF/'summary.json',BASE/'bench.raw',BASE/'bench.cir',ROOT/'clocking_300mhz.json']
    files += sorted({Path(m.__file__).resolve() for m in list(sys.modules.values())
        if getattr(m,'__file__',None) and Path(m.__file__).resolve().parent==ROOT/'scripts'})
    inputs={**i['inputs'],**{str(f.relative_to(ROOT)):sha(f) for f in files}}
    if any(sha(ROOT/n)!=h for n,h in inputs.items()):raise ValueError('Clock capture input changed')
    identity=dict(version=VERSION,inputs=inputs,baseline=str(BASE.relative_to(ROOT)),verified_sources=str(PROOF.relative_to(ROOT)),
        stop_ns=stop_ns,pilot_stop_ns=70,max_workers=1,pilot_priority=1,long_priority=2,
        observed_voltage_parity_limit_v=.002,absolute_crossing_parity_limit_ps=.25,
        native_tolerances_unchanged=True,bench_current_offset_a=0,qualified_phy=False)
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False)
    for name,duration in (('pilot',70),('long',stop_ns)):
        folder=out/name;folder.mkdir();(folder/'bench.cir').write_text(deck(original,duration))
    atomic(out/'manifest.json',dict(identity=identity,decks={n:sha(out/n/'bench.cir') for n in ('pilot','long')},qualified_phy=False));bound(out)
    return out


def atomic(path,value):
    tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(value,indent=2)+'\n');tmp.replace(path)


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION
            or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
            or (i['max_workers'],i['pilot_priority'],i['long_priority'])!=(1,1,2)
            or i['baseline']!=str(BASE.relative_to(ROOT)) or i['verified_sources']!=str(PROOF.relative_to(ROOT))
            or (i['observed_voltage_parity_limit_v'],i['absolute_crossing_parity_limit_ps'])!=(.002,.25)
            or i['native_tolerances_unchanged'] is not True or i['bench_current_offset_a']!=0
            or i['qualified_phy'] is not False or m['qualified_phy'] is not False
            or i['pilot_stop_ns']!=70 or type(i['stop_ns']) is not int or not 20000<=i['stop_ns']<=200000):
        raise ValueError('Long native-clock context changed')
    if any(sha(ROOT/n)!=h for n,h in i['inputs'].items()):raise ValueError('Captured physical source/model/runtime changed')
    original=(BASE/'bench.cir').read_text()
    if set(m['decks'])!={'pilot','long'}:raise ValueError('Missing parity or long deck')
    for name,duration in (('pilot',70),('long',i['stop_ns'])):
        f=out/name/'bench.cir'
        if f.read_text()!=deck(original,duration) or sha(f)!=m['decks'][name]:raise ValueError('Native timing, reset or solver declaration changed')
    return m


def run(out):
    m=bound(out);i=m['identity'];p=policy.load()
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain existing or partial clock capture')
        atomic(out/'state.json',dict(status='running',stage='pilot',qualified_phy=False))
        try:
            def execute(name,duration,priority):
                folder=out/name
                with lease(ROOT,priority=priority,label=CONTEXT+'_'+name):
                    bound(out)
                    command=[str(ROOT/'build/tools/ngspice-runtime/ld-linux-x86-64.so.2'),'--library-path',str(ROOT/'build/tools/ngspice-runtime'),
                             str(ROOT/'build/tools/ngspice-root/usr/bin/ngspice'),'-n','-b','-r',str(folder/'bench.raw'),'-o',str(folder/'ngspice.log'),str(folder/'bench.cir')]
                    result=subprocess.run(command,cwd=Path(os.environ['PDK_ROOT'])/'sky130A/libs.tech/ngspice',capture_output=True,text=True)
                (folder/'console.log').write_text(result.stdout+result.stderr);result.check_returncode()
                names,w=validate(folder/'bench.raw',{'v(pllout)'},duration*1e-9)
                t=w[:,names.index('time')];v=w[:,names.index('v(pllout)')]
                clock=source.edges(t,v);measured=source.metrics(clock,p['requirements'])
                np.savetxt(folder/'clock.csv',clock,delimiter=',',header='time_ns,level',comments='',fmt=['%.9f','%d'])
                atomic(folder/'summary.json',dict(metrics=measured,raw_sha256=sha(folder/'bench.raw'),clock_sha256=sha(folder/'clock.csv'),qualified_phy=False))
                if not measured['passed']:raise ValueError('Fresh native clock outside frequency/duty/swing contract')
                return t,v,measured
            t,v,pilot=execute('pilot',70,1)
            names,w=validate(BASE/'bench.raw',{'v(pllout)'},70e-9)
            control=parity(w[:,names.index('time')],w[:,names.index('v(pllout)')],t,v)
            atomic(out/'observed_parity.json',control)
            if not control['passed']:
                atomic(out/'summary.json',dict(observed_parity=control,long_capture_launched=False,qualified_phy=False))
                atomic(out/'state.json',dict(status='rejected_numerical_parity',qualified_phy=False));return out
            atomic(out/'state.json',dict(status='running',stage='long',qualified_phy=False))
            t,v,long=execute('long',i['stop_ns'],2);available=2*(long['rising_edges']-1)
            bound(out)
            if available<4096:raise ValueError('Genuine source trace too short for 4096 payload bit intervals')
            atomic(out/'summary.json',dict(observed_parity=control,metrics=long,available_complete_ddr_bit_intervals=available,
                physical_parent=json.loads((BASE/'summary.json').read_text())['physical_parent'],
                extraction_scope=json.loads((BASE/'summary.json').read_text())['extraction_scope'],
                raw_sha256=sha(out/'long/bench.raw'),clock_sha256=sha(out/'long/clock.csv'),
                long_capture_launched=True,minimum_4096_source_intervals_present=True,qualified_phy=False,
                full_link_payload_admitted=False,closed_loop_physical_jitter_qualified=False,
                scope='Actual fixed-code TT25/1.8V capacitance-extracted DCO, KLU after observed output parity only; no source rescaling/tiling or complete PHY admission'))
            atomic(out/'state.json',dict(status='complete',qualified_phy=False))
        except Exception as exc:
            atomic(out/'state.json',dict(status='failed',error=str(exc),qualified_phy=False));raise
    return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('prepare','run'));p.add_argument('artifact',type=Path,nargs='?');p.add_argument('--stop-ns',type=int,default=20000);a=p.parse_args()
    print(prepare(a.stop_ns) if a.action=='prepare' else run(a.artifact.resolve()),flush=True)
