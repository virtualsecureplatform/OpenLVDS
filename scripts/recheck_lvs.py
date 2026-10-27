#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Requalify existing immutable analog geometry against current source and strict LVS."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from layout import circuits,flatten
from lvs_utils import schematic_parameters,clean_match

ROOT=Path(__file__).resolve().parents[1]

def main():
    path=ROOT/'build/layout/current.json';manifest=json.loads(path.read_text())
    source=(ROOT/'analog/openlvds.spice').read_bytes()
    if manifest['source_sha256']!=hashlib.sha256(source).hexdigest():raise ValueError('Layout source changed')
    definitions=circuits(source.decode())
    setup=Path(os.environ['PDK_ROOT'])/'sky130A/libs.tech/netgen/sky130A_setup.tcl'
    for name,info in manifest['designs'].items():
        out=(ROOT/info['gds']).parent
        ports,devices=flatten(definitions,name)
        lines=['* SPDX-License-Identifier: GPL-3.0-only','.subckt '+name+' '+' '.join(ports)]
        for d in devices:
            lines.append('X'+d['name']+' '+' '.join(d['nodes'])+' '+d['model']+' '+
                         ' '.join(f'{k}={v}' for k,v in schematic_parameters(d).items()))
        lines.append('.ends '+name)
        schematic=out/(name+'.sch.spice');schematic.write_text('\n'.join(lines)+'\n')
        report=out/(name+'.lvs.log')
        result=subprocess.run(['netgen','-batch','lvs',f'{out}/{name}.lvs.spice {name}_flat',
            f'{schematic} {name}',str(setup),str(report)],capture_output=True,text=True,cwd=out)
        (out/(name+'.netgen.log')).write_text(result.stdout+result.stderr)
        info['lvs_passed']=clean_match(report.read_text() if report.exists() else '',result.returncode)
        info['passed']=info['lvs_passed'] and info['drc_count']=='0'
        info['lvs_source_sha256']=hashlib.sha256(schematic.read_bytes()).hexdigest()
        info['lvs_report_sha256']=hashlib.sha256(report.read_bytes()).hexdigest() if report.exists() else None
        print(name,'PASS' if info['passed'] else 'FAIL',flush=True)
    manifest['passed']=all(i['passed'] for i in manifest['designs'].values())
    manifest['lvs_policy_sha256']=hashlib.sha256((ROOT/'scripts/lvs_utils.py').read_bytes()).hexdigest()
    path.write_text(json.dumps(manifest,indent=2)+'\n')
    (ROOT/manifest['output']/'summary.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return 0 if manifest['passed'] else 1

if __name__=='__main__':sys.exit(main())
