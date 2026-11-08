#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Fresh 300 MHz DDR-core regression; ideal phase source, no analog admission."""
import hashlib,itertools,json,re,shutil,subprocess,sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import clocking_profile_300 as policy
ROOT=policy.ROOT

def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def passed(log,returncode):
    m=re.search(r'^PASS bits=(\d+) pairs=(\d+) transitions=ffff ',log,re.M)
    return dict(passed=bool(returncode==0 and m and int(m[1])>=22000 and int(m[2])>=11000),
                bits=int(m[1]) if m else 0,pairs=int(m[2]) if m else 0)

def run():
    req=policy.load()['requirements']
    sources=sorted((ROOT/'rtl').glob('*.v'))+[ROOT/'tb/tb_link.v']
    models=[ROOT/'models/sky130_tx_functional.v',ROOT/'models/experiments/sky130_rx_functional.v']
    files=sources+models+[Path(__file__).resolve(),ROOT/'scripts/clocking_profile_300.py',ROOT/'clocking_300mhz.json']
    inputs={str(p.relative_to(ROOT)):digest(p) for p in files}
    runtime={name:dict(path=shutil.which(name),sha256=digest(Path(shutil.which(name)))) for name in ['iverilog','vvp']}
    cases=list(itertools.product(['rtl','sky130_functional'],req['clock_test_mhz'],req['clock_duty'],req['channel_skew_ps']))
    identity=dict(version='ddr-core-functional-300-v1',inputs=inputs,runtime=runtime,cases=cases,cycles=22000,jitter_ns=.05)
    out=ROOT/'build/diagnostics/ddr_core_functional_300'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False)
    def write(name,data):(out/name).write_text(json.dumps(data,indent=2)+'\n')
    write('manifest.json',dict(identity=identity,qualified_phy=False))
    write('state.json',dict(status='running',qualified_phy=False))
    try:
        for mode in ['rtl','sky130_functional']:
            flags=[] if mode=='rtl' else ['-DOPENLVDS_SKY130_TX','-DOPENLVDS_SKY130_RX']
            command=['iverilog','-g2012','-Wall',*flags,'-s','tb_link','-o',str(out/(mode+'.vvp')),*map(str,sources),*map(str,models if flags else [])]
            result=subprocess.run(command,capture_output=True,text=True)
            (out/(mode+'_compile.log')).write_text(result.stdout+result.stderr);result.check_returncode()
        def one(case):
            mode,mhz,duty,skew=case;name=f'{mode}_{mhz}_{duty}_{skew}'
            command=['vvp',str(out/(mode+'.vvp')),f'+PERIOD={1000/mhz:.12f}',f'+DUTY={duty}',f'+SKEW={skew/1000}','+CYCLES=22000','+JITTER=0.05']
            result=subprocess.run(command,capture_output=True,text=True);log=result.stdout+result.stderr
            (out/(name+'.log')).write_text(log)
            return dict(mode=mode,frequency_mhz=mhz,duty=duty,skew_ps=skew,command=command,**passed(log,result.returncode))
        with ThreadPoolExecutor(max_workers=2) as pool:rows=list(pool.map(one,cases))
        totals={mode:sum(r['bits'] for r in rows if r['mode']==mode) for mode in ['rtl','sky130_functional']}
        if any(digest(ROOT/n)!=h for n,h in inputs.items()):raise ValueError('Inputs changed during regression')
        ok=all(r['passed'] for r in rows) and min(totals.values())>=req['minimum_behavioral_bits']
        write('summary.json',dict(passed=ok,checked_bits=totals,cases=rows,qualified_phy=False,
            scope='DDR core with ideal quarter-phase clock, readiness forced by bench, functional I/O models only; no DLL/DCC/training/analog or full PHY admission'))
        write('state.json',dict(status='complete' if ok else 'failed',qualified_phy=False))
        if not ok:raise ValueError('DDR core regression failed')
    except Exception as exc:
        write('state.json',dict(status='failed',error=str(exc),qualified_phy=False));raise
    return out

if __name__=='__main__':print(run(),flush=True)
