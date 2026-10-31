#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Check isolated buffered RX functionality with the existing link scoreboard."""
from concurrent.futures import ThreadPoolExecutor
import argparse
import hashlib
import itertools
import json
from pathlib import Path
import re
import subprocess

ROOT=Path(__file__).resolve().parents[1]


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,default=ROOT/'rtl/experiments/openlvds_ddr_rx_buffer4.v')
    p.add_argument('--rx-model',type=Path,default=ROOT/'models/experiments/sky130_rx_functional.v')
    a=p.parse_args();source=a.source.resolve();rx_model=a.rx_model.resolve()
    if not all(path.is_relative_to(ROOT) for path in [source,rx_model]):raise ValueError('Keep RX sources/models in OpenLVDS')
    sources=[p for p in sorted((ROOT/'rtl').glob('*.v')) if p.name!='openlvds_ddr_rx.v']
    sources += [source,ROOT/'tb/tb_link.v',ROOT/'models/sky130_tx_functional.v',rx_model]
    requirements=json.loads((ROOT/'requirements.json').read_text())
    identity=dict(files={str(p.relative_to(ROOT)):digest(p) for p in sources+[Path(__file__),ROOT/'requirements.json']})
    out=ROOT/'build/diagnostics/rx_buffered_rtl'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=True)
    for native in [False,True]:
        mode='native_rx' if native else 'generic'
        cmd=['iverilog','-g2012','-Wall']+(['-DOPENLVDS_SKY130_RX'] if native else [])+['-s','tb_link','-o',str(out/(mode+'.vvp')),*map(str,sources)]
        result=subprocess.run(cmd,capture_output=True,text=True)
        (out/(mode+'_compile.log')).write_text(result.stdout+result.stderr);result.check_returncode()
    def run(case):
        mode,mhz,duty,skew=case;name=f'{mode}_{mhz}_{duty}_{skew}'
        result=subprocess.run(['vvp',str(out/(mode+'.vvp')),f'+PERIOD={1000/mhz:.12f}',f'+DUTY={duty}',
            f'+SKEW={skew/1000}','+CYCLES=22000','+JITTER=0.05'],capture_output=True,text=True)
        log=result.stdout+result.stderr;(out/(name+'.log')).write_text(log)
        bits=re.search(r'PASS bits=(\d+) pairs=(\d+)',log)
        return dict(case=name,mode=mode,passed=result.returncode==0 and bits is not None,bits=int(bits[1]) if bits else 0)
    cases=itertools.product(['generic','native_rx'],requirements['clock_test_mhz'],requirements['clock_duty'],requirements['channel_skew_ps'])
    with ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(run,cases))
    totals={mode:sum(r['bits'] for r in results if r['mode']==mode) for mode in ['generic','native_rx']}
    unchanged=identity['files']=={str(p.relative_to(ROOT)):digest(p) for p in sources+[Path(__file__),ROOT/'requirements.json']}
    passed=unchanged and all(r['passed'] for r in results) and all(n>=requirements['minimum_behavioral_bits'] for n in totals.values())
    report=dict(passed=passed,qualified_phy=False,electrical_qualification=False,identity=identity,totals=totals,cases=results)
    (out/'summary.json').write_text(json.dumps(report,indent=2)+'\n');print(out/'summary.json',flush=True)
    return 0 if passed else 1


if __name__=='__main__':raise SystemExit(main())
