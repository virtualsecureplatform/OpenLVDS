#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Capture a fresh fixed-code extracted DCO using the pinned native engine.

Requires the isolated physical rebuild to complete first. This characterizes
one clock source, never a closed-loop PLL or complete PHY.
"""
import argparse
from datetime import datetime,timezone
import hashlib,json,os,subprocess,sys
from pathlib import Path
from types import SimpleNamespace
import numpy as np
from clocking_profile_300 import ROOT,load
from check_openpll_contract import metrics
from native_binary_raw_v2 import validate
from spice_dispatch import lease

def sha(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def edges(time,voltage,threshold=.9):
    if not np.isfinite(time).all() or not np.isfinite(voltage).all() or np.any(np.diff(time)<=0):
        raise ValueError('Invalid native clock waveform')
    rising=(voltage[:-1]<threshold)&(voltage[1:]>=threshold)
    falling=(voltage[:-1]>threshold)&(voltage[1:]<=threshold)
    idx=np.nonzero(rising|falling)[0]
    t=time[idx]+(threshold-voltage[idx])*(time[idx+1]-time[idx])/(voltage[idx+1]-voltage[idx])
    level=rising[idx].astype(int)
    keep=t>time[-1]*.4
    if not np.any(keep):raise ValueError('No late extracted clock edges')
    t=t[keep];level=level[keep];indices=idx[keep]
    if len(t)<16 or np.any(np.diff(level)==0):raise ValueError('Incomplete or nonalternating physical clock')
    late=voltage[time>time[-1]*.4]
    if late.min()<-.15 or late.max()>1.95:raise ValueError('Clock exceeds digital input voltage screen')
    for start,end,state in zip(indices[:-1],indices[1:],level[:-1]):
        segment=voltage[start:end+2]
        if (state and segment.max()<1.62) or (not state and segment.min()>.18):
            raise ValueError('Incomplete physical clock swing')
    return np.column_stack(((t-t[0])*1e9,level))

def run(parent):
    p=load();parent=parent.resolve()
    if parent.parent!=ROOT/'build/diagnostics/openpll_physical_300':raise ValueError('Unexpected physical context')
    if json.loads((parent/'state.json').read_text())!=dict(status='complete',qualified_phy=False):
        raise ValueError('Physical rebuild/extraction must complete before simulation')
    proof=json.loads((parent/'summary.json').read_text());i=proof['identity']
    if (i['profile_sha256']!=sha(ROOT/'clocking_300mhz.json') or i['openpll_commit']!=p['requirements']['openpll_commit']
        or (i['coarse_code'],i['fine_code'])!=(2,12)):raise ValueError('Physical mode/profile differs')
    rc=ROOT/proof['netlist']
    if not rc.is_relative_to(parent/'source') or sha(rc)!=proof['netlist_sha256']:raise ValueError('Extracted DCO changed')
    source=parent/'source';sys.path.insert(0,str(source/'scripts'))
    import spice_dco_postlayout as generator
    args=SimpleNamespace(pdk_root=os.environ['PDK_ROOT'],pdk='sky130A',rcx_netlist=str(rc),
        subckt_name='IntegerPLL_DCO_EINVP_COARSE',corner='tt',vdd=1.8,temperature_c=25,
        simulator='ngspice',therm_invert=True,ngspice_threads=2,reset_release_ns=5.,
        sim_time_ns=70.,meas_start_ns=12.,step_ps=2.,max_step_ps=2.)
    ports=generator.parse_subckt_ports(rc,args.subckt_name)
    if len([v for v in ports if v.startswith('DCO_THERM[')])!=255 or len([v for v in ports if v.startswith('COARSETHERMAL_CODE[')])!=47:
        raise ValueError('Incomplete native thermometer interfaces')
    deck=generator.dco_netlist(args,12,2,ports)
    out=ROOT/'build/diagnostics/openpll_trace_300'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out.mkdir(parents=True,exist_ok=False);(out/'bench.cir').write_text(deck)
    runtime=ROOT/'build/tools/ngspice.json';runtime_files=json.loads(runtime.read_text())['files']
    paths=[Path(__file__),ROOT/'clocking_300mhz.json',parent/'manifest.json',parent/'summary.json',parent/'state.json',rc,runtime,
           *[ROOT/n for n in runtime_files],out/'bench.cir']
    paths+=list((Path(args.pdk_root)/'sky130A/libs.tech/ngspice').rglob('*.spice'))
    paths+=list((Path(args.pdk_root)/'sky130A/libs.ref/sky130_fd_pr/spice').rglob('*.spice'))
    paths+=[Path(m.__file__).resolve() for m in list(sys.modules.values()) if getattr(m,'__file__',None)
            and (Path(m.__file__).resolve().parent==ROOT/'scripts' or Path(m.__file__).resolve().is_relative_to(source/'scripts'))]
    inputs={str(f.relative_to(ROOT)) if f.is_relative_to(ROOT) else str(f):sha(f) for f in sorted(set(paths))}
    (out/'manifest.json').write_text(json.dumps(dict(inputs=inputs,physical_parent=str(parent.relative_to(ROOT)),qualified_phy=False),indent=2)+'\n')
    print(out,flush=True)
    with lease(ROOT,priority=1,label='openpll_physical_300_coarse2_code12'):
        if any(sha(ROOT/n)!=v for n,v in inputs.items()):raise ValueError('Native source/model/runtime changed')
        result=subprocess.run([str(ROOT/'build/tools/ngspice-runtime/ld-linux-x86-64.so.2'),'--library-path',
            str(ROOT/'build/tools/ngspice-runtime'),str(ROOT/'build/tools/ngspice-root/usr/bin/ngspice'),'-n','-b',
            '-r',str(out/'bench.raw'),'-o',str(out/'ngspice.log'),str(out/'bench.cir')],
            cwd=Path(args.pdk_root)/'sky130A/libs.tech/ngspice',capture_output=True,text=True)
        (out/'console.log').write_text(result.stdout+result.stderr)
    result.check_returncode()
    names,wave=validate(out/'bench.raw',{'v(pllout)'},70e-9)
    clock=edges(wave[:,names.index('time')],wave[:,names.index('v(pllout)')])
    measured=metrics(clock,p['requirements'])
    np.savetxt(out/'clock.csv',clock,delimiter=',',header='time_ns,level',comments='',fmt=['%.9f','%d'])
    if any(sha(ROOT/n)!=v for n,v in inputs.items()):raise ValueError('Native evidence context changed')
    (out/'summary.json').write_text(json.dumps(dict(metrics=measured,inputs=inputs,clock_sha256=sha(out/'clock.csv'),
        raw_sha256=sha(out/'bench.raw'),physical_parent=str(parent.relative_to(ROOT)),qualified_phy=False,
        scope='Fresh extracted fixed-code coarse2/fine12 DCO waveform at TT25/1.8V; no closed-loop PLL jitter or PHY admission'),indent=2)+'\n')
    if not measured['passed']:raise ValueError('Extracted DCO clock is outside the 300MHz contract')
    return out
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('physical_context',type=Path)
    run(parser.parse_args().physical_context)
