#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Bind genuine 300 MHz clock sources; never scale or synthesize trace edges."""
import argparse,hashlib,io,json,sys,subprocess
from pathlib import Path
import numpy as np
import clocking_profile_300 as policy
import capture_openpll_physical_300 as physical
from native_binary_raw_v2 import validate
ROOT=policy.ROOT
RTL=ROOT/'build/openpll_300'
EXTRACTED=ROOT/'build/diagnostics/openpll_trace_300/20261108T013035Z'
VERSION='verified-genuine-clock-sources-300-v1'


def independent_metrics(clock,requirements):
    a=np.asarray(clock,dtype=float)
    if (a.ndim!=2 or a.shape[1]!=2 or len(a)<16 or not np.isfinite(a).all()
            or np.any(np.diff(a[:,0])<=0) or not np.isin(a[:,1],(0,1)).all()
            or np.any(a[1:,1]==a[:-1,1])):raise ValueError('Require complete alternating finite native clock edges')
    rise=a[a[:,1]==1,0];fall=a[a[:,1]==0,0]
    if len(rise)<3:raise ValueError('Too few complete clock periods')
    periods=np.diff(rise);duty=[]
    for start,end in zip(rise[:-1],rise[1:]):
        mid=fall[(fall>start)&(fall<end)]
        if len(mid)!=1:raise ValueError('Missing or duplicate clock half-cycle')
        duty.append(float((mid[0]-start)/(end-start)))
    frequency=1000/float(periods.mean())
    return dict(frequency_mhz=frequency,duty_min=min(duty),duty_max=max(duty),
        period_jitter_pp_ps=float(np.ptp(periods)*1000),rising_edges=len(rise),
        passed=bool(min(requirements['clock_test_mhz'])-1e-6<=frequency<=max(requirements['clock_test_mhz'])+1e-6
            and min(duty)>=min(requirements['clock_duty'])-1e-9 and max(duty)<=max(requirements['clock_duty'])+1e-9))


def compare_metrics(actual,recorded):
    for key,value in actual.items():
        if isinstance(value,bool):
            if value is not recorded[key]:raise ValueError('Clock classification changed')
        elif key=='rising_edges':
            if value!=recorded[key]:raise ValueError('Clock edge count changed')
        elif not np.isfinite(recorded[key]) or abs(value-recorded[key])>1e-5:
            raise ValueError('Independent native clock metric does not reproduce: '+key)


def verify():
    p=policy.load();inputs={};rows=[]
    pin=subprocess.check_output(['git','-C',str(ROOT/'thirdparties/OpenPLL'),'rev-parse','HEAD'],text=True).strip()
    if pin!=p['requirements']['openpll_commit']:raise ValueError('Current OpenPLL checkout differs from the pinned source')
    for kind,folder in (('rtl_controller',RTL),('capacitance_extracted_dco',EXTRACTED)):
        m=json.loads((folder/'manifest.json').read_text());r=json.loads((folder/'summary.json').read_text())
        if m['qualified_phy'] is not False or r['qualified_phy'] is not False or m['inputs']!=r['inputs']:
            raise ValueError('Unexpected source trace scope or captured inputs')
        for name,digest in m['inputs'].items():
            if name in inputs and inputs[name]!=digest:raise ValueError('Conflicting source inputs')
            inputs[name]=digest
        if physical.sha(folder/'clock.csv')!=r['clock_sha256']:raise ValueError('Captured edge CSV changed')
        clock=np.loadtxt(folder/'clock.csv',delimiter=',',skiprows=1)
        independent=independent_metrics(clock,p['requirements']);compare_metrics(independent,r['metrics'])
        if not independent['passed']:raise ValueError('Native clock source outside the new contract')
        row=dict(kind=kind,trace=str((folder/'clock.csv').relative_to(ROOT)),metrics=independent,scope=r['scope'],
                 available_complete_periods=independent['rising_edges']-1,qualified_phy=False)
        if kind=='rtl_controller':
            if r['openpll_commit']!=p['requirements']['openpll_commit'] or r['profile_sha256']!=physical.sha(ROOT/'clocking_300mhz.json'):
                raise ValueError('Controller source pin/profile changed')
        else:
            if json.loads((folder/'state.json').read_text())!=dict(status='complete',qualified_phy=False):raise ValueError('Physical transient is not terminal complete')
            if physical.sha(folder/'bench.raw')!=r['raw_sha256']:raise ValueError('Captured native waveform changed')
            if m['physical_parent']!=r['physical_parent']:raise ValueError('Physical source context changed')
            parent=ROOT/r['physical_parent'];proof=json.loads((parent/'summary.json').read_text())
            if proof['identity']['openpll_commit']!=p['requirements']['openpll_commit']:raise ValueError('Extracted physical source pin changed')
            flow=parent/'source/openlane/IntegerPLL_DCO_EINVP_COARSE/runs/openlvds_300'
            checked=physical.physical_checks(json.loads((flow/'final/metrics.json').read_text()))
            extraction=json.loads((flow/'rcx-magic.config.json').read_text())
            if checked!=r['physical_metrics'] or any(extraction[k]!=v for k,v in r['extraction_scope'].items()):
                raise ValueError('Physical signoff or extraction scope changed')
            names,w=validate(folder/'bench.raw',{'v(pllout)'},70e-9)
            recovered=physical.edges(w[:,names.index('time')],w[:,names.index('v(pllout)')])
            text=io.StringIO();np.savetxt(text,recovered,delimiter=',',header='time_ns,level',comments='',fmt=['%.9f','%d'])
            if text.getvalue().encode()!= (folder/'clock.csv').read_bytes():raise ValueError('CSV is not the exact unscaled native crossing export')
            compare_metrics(independent_metrics(recovered,p['requirements']),r['metrics'])
            row.update(extraction_scope=r['extraction_scope'],full_4096_bit_payload_source_available=False,
                scope='Exact 70 ns TT25/1.8V fixed-code native DCO capture, late edges only; no interconnect resistance, noise/jitter statistics or closed-loop PLL admission')
            inputs[str((folder/'bench.raw').relative_to(ROOT))]=r['raw_sha256']
            inputs[str((folder/'state.json').relative_to(ROOT))]=physical.sha(folder/'state.json')
        for path in (folder/'manifest.json',folder/'summary.json',folder/'clock.csv'):
            inputs[str(path.relative_to(ROOT))]=physical.sha(path)
        rows.append(row)
    inputs.update({str(Path(mod.__file__).resolve().relative_to(ROOT)):physical.sha(Path(mod.__file__).resolve())
        for mod in list(sys.modules.values()) if getattr(mod,'__file__',None) and Path(mod.__file__).resolve().parent==ROOT/'scripts'})
    if any(physical.sha(ROOT/n)!=h for n,h in inputs.items()):raise ValueError('Captured clock-source context changed')
    identity=dict(version=VERSION,inputs=inputs,openpll_commit=p['requirements']['openpll_commit'],
                  clock_profile_sha256=physical.sha(ROOT/'clocking_300mhz.json'))
    out=ROOT/'build/diagnostics/verified_clock_sources_300'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False)
    (out/'manifest.json').write_text(json.dumps(dict(identity=identity,qualified_phy=False),indent=2)+'\n')
    (out/'summary.json').write_text(json.dumps(dict(rows=rows,all_source_contracts_passed=True,
        qualified_phy=False,full_link_payload_admitted=False,
        scope='Source-only verification. Physical DCO trace is too short for 4096 payload bits; longer capture remains required.'),indent=2)+'\n')
    return out


if __name__=='__main__':
    argparse.ArgumentParser(description=__doc__).parse_args();print(verify(),flush=True)
