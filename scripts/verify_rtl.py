#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Run all requested clock/duty/skew combinations and archive real results."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import itertools
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--smoke',action='store_true')
    p.add_argument('--jobs',type=int,default=8)
    a=p.parse_args()
    req=json.loads((ROOT/'requirements.json').read_text())
    out=ROOT/'build/rtl'; out.mkdir(parents=True,exist_ok=True)
    (out/'summary.json').unlink(missing_ok=True)
    sources=sorted((ROOT/'rtl').glob('*.v'))+[ROOT/'tb/tb_link.v']
    compile=subprocess.run(['iverilog','-g2012','-Wall','-s','tb_link','-o',str(out/'link.vvp'),
                            *map(str,sources)],capture_output=True,text=True)
    (out/'compile.log').write_text(compile.stdout+compile.stderr)
    if compile.returncode: print(compile.stderr); return 1
    dll_sources=[ROOT/'rtl/openlvds_dll_control.v',ROOT/'tb/tb_dll_control.v']
    subprocess.run(['iverilog','-g2012','-s','tb_dll_control','-o',str(out/'dll.vvp'),
                    *map(str,dll_sources)],check=True)
    control=subprocess.run(['vvp',str(out/'dll.vvp')],capture_output=True,text=True)
    (out/'dll_control.log').write_text(control.stdout+control.stderr)
    phy_sources=sorted((ROOT/'rtl').glob('*.v'))+[ROOT/'models/analog_functional.v',ROOT/'tb/tb_phy.v']
    subprocess.run(['iverilog','-g2012','-s','tb_phy','-o',str(out/'phy.vvp'),*map(str,phy_sources)],check=True)
    phy=subprocess.run(['vvp',str(out/'phy.vvp')],capture_output=True,text=True)
    (out/'phy.log').write_text(phy.stdout+phy.stderr)
    cases=list(itertools.product(req['clock_test_mhz'],req['clock_duty'],req['channel_skew_ps']))
    if a.smoke: cases=[(400,.5,0)]
    def run(case):
        mhz,duty,skew=case
        name=f'{mhz}m_d{duty:.2f}_s{skew:+d}'
        result=subprocess.run(['vvp',str(out/'link.vvp'),f'+PERIOD={1000/mhz:.12f}',
            f'+DUTY={duty}',f'+SKEW={skew/1000}',f'+CYCLES={1000 if a.smoke else 22000}',
            '+JITTER=0.05'],capture_output=True,text=True)
        log=result.stdout+result.stderr
        (out/f'{name}.log').write_text(log)
        bits=re.search(r'PASS bits=(\d+) pairs=(\d+)',log)
        return dict(case=name,passed=result.returncode==0 and bits is not None,
                    bits=int(bits[1]) if bits else 0,pairs=int(bits[2]) if bits else 0)
    with ThreadPoolExecutor(max_workers=a.jobs) as pool: results=list(pool.map(run,cases))
    total=sum(r['bits'] for r in results)
    summary=dict(passed=control.returncode==0 and phy.returncode==0 and all(r['passed'] for r in results) and (a.smoke or total>=req['minimum_behavioral_bits']),
                 dll_control_passed=control.returncode==0,
                 functional_phy_passed=phy.returncode==0,
                 smoke=a.smoke,total_bits=total,cases=results,
                 source_hash=hashlib.sha256(b''.join(p.read_bytes() for p in sources)+
                     b''.join(p.read_bytes() for p in dll_sources)+
                     b''.join(p.read_bytes() for p in phy_sources)+
                     (ROOT/'requirements.json').read_bytes()+Path(__file__).read_bytes()).hexdigest())
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(dict(passed=summary['passed'],dll_control_passed=summary['dll_control_passed'],
        total_bits=total,cases=len(results),failed=[r['case'] for r in results if not r['passed']]),indent=2))
    return 0 if summary['passed'] else 1

if __name__=='__main__': sys.exit(main())
