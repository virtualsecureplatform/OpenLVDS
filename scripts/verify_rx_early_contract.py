#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Check early RX word ordering and first-valid behavior through async reset."""
import hashlib
import itertools
import json
from pathlib import Path
import subprocess
ROOT=Path(__file__).resolve().parents[1]


def main():
    paths=[ROOT/p for p in ['rtl/openlvds_ddr_rx.v','rtl/experiments/openlvds_ddr_rx_early.v',
        'rtl/openlvds_reset.v','models/sky130_tx_functional.v',
        'models/experiments/sky130_rx_early_functional.v','tb/tb_rx_early_contract.v']]+[Path(__file__)]
    identity={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    out=ROOT/'build/diagnostics/rx_early_contract'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=True)
    reference=out/'reference.v';reference.write_text(paths[0].read_text().replace('module openlvds_ddr_rx (','module reference_rx ('))
    results=[]
    for native in [False,True]:
        name='native' if native else 'generic';binary=out/(name+'.vvp')
        command=['iverilog','-g2012','-s','tb_rx_early_contract','-o',str(binary)]
        if native:command+=['-DOPENLVDS_SKY130_RX']
        result=subprocess.run(command+[str(reference)]+list(map(str,paths[1:-1])),capture_output=True,text=True)
        (out/(name+'_compile.log')).write_text(result.stdout+result.stderr);result.check_returncode()
        for mhz,duty in itertools.product([390,400,410],[0.45,0.5,0.55]):
            case=f'{name}_{mhz}_{duty}'
            result=subprocess.run(['vvp',str(binary),f'+PERIOD={1000/mhz}',f'+DUTY={duty}'],capture_output=True,text=True)
            log=result.stdout+result.stderr;(out/(case+'.log')).write_text(log)
            results.append(dict(case=case,passed=result.returncode==0 and 'PASS first-word/reset' in log))
    unchanged=all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h for p,h in identity.items())
    passed=unchanged and all(r['passed'] for r in results)
    (out/'summary.json').write_text(json.dumps(dict(passed=passed,identity=identity,cases=results,qualified_phy=False),indent=2)+'\n')
    print(out/'summary.json',flush=True)
    return 0 if passed else 1


if __name__=='__main__':raise SystemExit(main())
