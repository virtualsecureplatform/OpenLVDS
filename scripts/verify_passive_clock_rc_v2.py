#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Reaudit fresh flat/passive RC with inline-comment-aware topology collapse."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import extract_passive_clock_components_v2 as extraction
from audit_rc_comments_v2 import collapse
from audit_passive_rc_v3 import audit
from lvs_utils import strict_setup,clean_match
from spice_library import checked_netlist

ROOT=extraction.ROOT
sha=extraction.sha
VERSION='passivity-gated-flat-RC-independent-topology-v2.1'


def verify(parent):
    m=extraction.bound(parent);i=m['identity'];physical=ROOT/i['parent'];report=json.loads((parent/'summary.json').read_text())
    files=[parent/'manifest.json',parent/'summary.json',parent/'state.json']
    files += [ROOT/n for n in {**i['code'],**i['inputs']}]
    for row in report['rows']:
        if not row['extraction']['passed'] or not audit(checked_netlist(row['extraction']))['elementwise_passive_passed']:raise ValueError('Require passive fresh RC')
        info=row['extraction'];files += [ROOT/info['netlist'],ROOT/info['raw_netlist'],parent/row['macro']/'extraction.json']
    code=[Path(__file__),Path(extraction.__file__),ROOT/'scripts/audit_rc_comments_v2.py',ROOT/'scripts/audit_rc.py',ROOT/'scripts/audit_passive_rc_v3.py',ROOT/'scripts/lvs_utils.py',ROOT/'scripts/spice_library.py']
    identity=dict(version=VERSION,parent=str(physical.relative_to(ROOT)),extraction=str(parent.relative_to(ROOT)),
        inputs={str(p.relative_to(ROOT)):sha(p) for p in files},code={str(p.relative_to(ROOT)):sha(p) for p in code},tools=i['tools'])
    out=ROOT/'build/diagnostics/passive_clock_rc_verification_v2'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);(out/'manifest.json').write_text(json.dumps(dict(identity=identity,qualified_phy=False),indent=2)+'\n');rows=[]
    for row in report['rows']:
        name=row['macro'];info=row['extraction'];folder=out/name;folder.mkdir();path=folder/'wire_collapsed.spice';path.write_text(collapse(checked_netlist(info)))
        setup=strict_setup(folder/'setup.tcl',Path(os.environ['PDK_ROOT'])/'sky130A/libs.tech/netgen/sky130A_setup.tcl');log=folder/'lvs.log'
        reference=physical/name/(name+'.sch.spice')
        p=subprocess.run(['netgen','-batch','lvs',f'{path} {name}',f'{reference} {name}',str(setup),str(log)],cwd=folder,capture_output=True,text=True)
        (folder/'console.log').write_text(p.stdout+p.stderr);passed=clean_match(log.read_text() if log.exists() else '',p.returncode)
        (folder/'extraction.json').write_text(json.dumps(info,indent=2)+'\n')
        result=dict(macro=name,extraction=info,rc_topology_passed=passed,elementwise_passive_passed=True,qualified_phy=False,electrical_qualification_passed=False)
        rows.append(result);(folder/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
    extraction.bound(parent);result=dict(rows=rows,passed=all(r['rc_topology_passed'] for r in rows),qualified_phy=False,
        scope='Unmodified flat single-pass GDS RC, positive element gate and fresh comment-aware topology proof; no timing or PHY admission')
    (out/'summary.json').write_text(json.dumps(result,indent=2)+'\n');(out/'state.json').write_text(json.dumps(dict(status='verified',passed=result['passed'],qualified_phy=False))+'\n');return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('artifact',type=Path);a=p.parse_args();print(verify(a.artifact.resolve()),flush=True)
