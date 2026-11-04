# SPDX-License-Identifier: GPL-3.0-only
"""Load only the complete, independently verified five-cell fine RC family."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import verify_weighted_fine_units_rc_v2 as verification
from audit_passive_rc_v3 import audit
from lvs_utils import clean_match
from spice_library import checked_netlist

ROOT=verification.ROOT
sha=verification.sha


def witnesses(parent):
    m=json.loads((parent/'manifest.json').read_text());i=m['identity']
    if (parent.parent!=ROOT/'build/diagnostics/weighted_fine_unit_rc_verification_v2'
        or i['version']!=verification.VERSION
        or parent.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or any(sha(ROOT/n)!=h for n,h in {**i['inputs'],**i['code']}.items())):
        raise ValueError('Weighted fine verification identity changed')
    # Restore only the saved tool lookup for the read-only binding check.
    # This checks PDK/tool/source identities without rerunning physical jobs.
    env=dict(os.environ)
    env['PATH']=os.pathsep.join(dict.fromkeys(str(Path(v['path']).parent) for v in i['tools'].values()))+os.pathsep+env['PATH']
    code='import sys; from pathlib import Path; sys.path.insert(0,str(Path(sys.argv[1])/"scripts")); import extract_weighted_fine_units_v2 as e; e.bound(Path(sys.argv[2]))'
    subprocess.run([sys.executable,'-c',code,str(ROOT),str(ROOT/i['extraction'])],env=env,check=True)
    report=json.loads((parent/'summary.json').read_text())
    state=json.loads((parent/'state.json').read_text())
    physical=ROOT/i['parent'];pr=json.loads((physical/'summary.json').read_text())
    verification.extraction.validate_physical(pr,json.loads((physical/'state.json').read_text()))
    expected=[verification.extraction.clock_cells.unit.name(b) for b in range(5)]
    if (state!=dict(status='verified',passed=True,qualified_phy=False)
        or not report['passed'] or [r['macro'] for r in report['rows']]!=expected):
        raise ValueError('Require exact complete independent fine RC verification')
    paths=[parent/n for n in ['manifest.json','summary.json','state.json']]
    paths += [ROOT/n for n in {**i['inputs'],**i['code']}]
    cells={}
    for row,p in zip(report['rows'],pr['rows']):
        name=row['macro'];info=row['extraction'];text=checked_netlist(info)
        raw=checked_netlist(dict(info,netlist=info['raw_netlist'],netlist_sha256=info['reduction']['source_sha256']))
        if (not row['rc_topology_passed'] or not row['elementwise_passive_passed']
            or not all(audit(t)['elementwise_passive_passed'] for t in [raw,text])
            or not clean_match((parent/name/'lvs.log').read_text())
            or info['ports']!=list(p['ports'])
            or info['source_sha256']!=sha(physical/'manifest.json')
            or info['gds_sha256']!=sha(physical/name/(name+'.gds'))
            or info['source_scope_sha256']!=sha(physical/name/(name+'.sch.spice'))):
            raise ValueError('Fine-cell physical/passive/topology proof failed')
        paths += [parent/name/n for n in ['summary.json','extraction.json','lvs.log','setup.tcl','console.log']]
        cells[name]=dict(info=info,text=text)
    return cells,paths
