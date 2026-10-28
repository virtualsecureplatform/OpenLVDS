#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Exercise the pinned OpenPLL wrapper and optionally import physical traces."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import numpy as np

ROOT=Path(__file__).resolve().parents[1]

def rtl_sources():
    pll=ROOT/'thirdparties/OpenPLL'
    names=['IntegerPLL_B2TH','IntegerPLL_Divider','IntegerPLL_DLF','IntegerPLL_MMD_Retimer',
        'IntegerPLL_DigitalCore','IntegerPLL_25MHzModeConfig_modern','IntegerPLL_25MHzModeController',
        'IntegerPLL_HardMacroTop_EINVP','IntegerPLL_HardMacroTop_EINVP_25MHzConfigured']
    return [pll/'rtl'/(n+'.v') for n in names]+[
        pll/'models/IntegerPLL_BBPD_model.v',pll/'models/IntegerPLL_DCO_25MHzCoarse_modern_model.v',
        ROOT/'models/openpll_dco_adapter.v',ROOT/'examples/openlvds_openpll.v',ROOT/'tb/tb_openpll.v']

def stats(times,levels):
    rising=times[levels==1];falling=times[levels==0]
    if len(rising)<8:raise ValueError('Need at least eight rising edges')
    periods=np.diff(rising);duties=[]
    for a,b in zip(rising[:-1],rising[1:]):
        f=falling[(falling>a)&(falling<b)]
        if len(f)!=1:raise ValueError('Nonalternating clock edges')
        duties.append(float((f[0]-a)/(b-a)))
    mhz=1000/float(np.mean(periods))
    return dict(passed=380<=mhz<=420 and min(duties)>=.45 and max(duties)<=.55,
        frequency_mhz=mhz,duty_min=min(duties),duty_max=max(duties),
        period_jitter_pp_ps=float(np.ptp(periods)*1000),rising_edges=len(rising))

def main():
    p=argparse.ArgumentParser();p.add_argument('--import-waveform',type=Path)
    a=p.parse_args();out=ROOT/'build/openpll';out.mkdir(parents=True,exist_ok=True)
    (out/('physical_summary.json' if a.import_waveform else 'summary.json')).unlink(missing_ok=True)
    if a.import_waveform:
        # Archive the original trace so no external checkout is needed at run time.
        data=a.import_waveform.read_bytes();dest=out/'physical_dco.prn';dest.write_bytes(data)
        rows=[]
        for line in data.decode().splitlines():
            try:rows.append(list(map(float,line.split())))
            except ValueError:pass
        wave=np.array(rows);t=wave[:,1]*1e9;v=wave[:,2]-.9
        i=np.where(v[:-1]*v[1:]<0)[0]
        edges=t[i]-v[i]*(t[i+1]-t[i])/(v[i+1]-v[i]);levels=(v[i+1]>0).astype(int)
        keep=edges>t[-1]*.4;edges=edges[keep];levels=levels[keep]
        result=stats(edges,levels)
        np.savetxt(out/'physical_clock.csv',np.column_stack([edges-edges[0],levels]),
            delimiter=',',header='time_ns,level',comments='',fmt=['%.9f','%d'])
        result.update(kind='extracted OpenPLL DCO waveform at fixed characterized code; not a closed-loop jitter claim',
            input_sha256=hashlib.sha256(data).hexdigest(),original_path=str(a.import_waveform),
            trace=str(dest.relative_to(ROOT)))
        result['clock_sha256']=hashlib.sha256((out/'physical_clock.csv').read_bytes()).hexdigest()
        (out/'physical_summary.json').write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps(result,indent=2));return 0 if result['passed'] else 1
    sources=rtl_sources()
    result=subprocess.run(['iverilog','-g2012','-Wall','-DOPENPLL_DCO_MODEL_COARSE','-s','tb_openpll',
        '-o',str(out/'pll.vvp'),*map(str,sources)],capture_output=True,text=True)
    (out/'compile.log').write_text(result.stdout+result.stderr)
    if result.returncode:print(result.stderr);return 1
    result=subprocess.run(['vvp',str(out/'pll.vvp')],cwd=ROOT,capture_output=True,text=True)
    (out/'simulation.log').write_text(result.stdout+result.stderr)
    if result.returncode:print(result.stdout+result.stderr);return 1
    wave=np.loadtxt(out/'clock.csv',delimiter=',',skiprows=1)
    summary=stats(wave[:,0],wave[:,1]);summary.update(
        kind='real OpenPLL RTL/controller with extracted-calibrated behavioral DCO and behavioral BBPD',
        source_sha256=hashlib.sha256(b''.join(x.read_bytes() for x in sources)).hexdigest(),
        pdk_pin=json.loads((ROOT/'requirements.json').read_text())['pdk_version'])
    summary['clock_sha256']=hashlib.sha256((out/'clock.csv').read_bytes()).hexdigest()
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary,indent=2));return 0 if summary['passed'] else 1

if __name__=='__main__':sys.exit(main())
