# SPDX-License-Identifier: GPL-3.0-only
"""Require native clock-cell and paired-driver physical/passive-RC receipts."""
import json
import os
from pathlib import Path
import subprocess
import sys
import probe_native_clock_components_v7 as clock
import extract_compound_drivers_v2 as compound
from audit_passive_rc_v3 import audit
from spice_library import checked_netlist

ROOT=clock.ROOT
sha=clock.sha


def witnesses(parent):
    if parent.parent.name!='compound_driver_rc_v2':return clock.witnesses(parent)
    m=json.loads((parent/'manifest.json').read_text());i=m['identity']
    # Recreate only the stored tool lookup for the read-only bound check. It
    # verifies the exact paths/binary hashes; no physical job is rerun.
    env=dict(os.environ)
    env['PATH']=os.pathsep.join(dict.fromkeys(str(Path(v['path']).parent) for v in i['tools'].values()))+os.pathsep+env['PATH']
    code='import sys; from pathlib import Path; sys.path.insert(0,str(Path(sys.argv[1])/"scripts")); import extract_compound_drivers_v2 as c; c.bound(Path(sys.argv[2]))'
    subprocess.run([sys.executable,'-c',code,str(ROOT),str(parent)],env=env,check=True)
    report=json.loads((parent/'summary.json').read_text())
    if not report['passed'] or len(report['rows'])!=4:raise ValueError('Require all four native compound RC proofs')
    physical=ROOT/i['parent'];pm=json.loads((physical/'manifest.json').read_text())['identity']
    pr=json.loads((physical/'summary.json').read_text())
    if not pr['passed'] or len(pr['rows'])!=4:raise ValueError('Require all four clean compound physical proofs')
    paths=[parent/n for n in ['manifest.json','summary.json','state.json']]
    paths += [ROOT/n for n in {**i['code'],**i['inputs'],**pm['code']}]
    paths += [physical/n for n in ['manifest.json','summary.json','state.json']]
    cells={}
    for row in report['rows']:
        name=row['macro'];info=row['extraction'];text=checked_netlist(info)
        p=next(r for r in pr['rows'] if r['macro']==name)
        if (not row['rc_topology_passed'] or not audit(text)['elementwise_passive_passed']
            or not p['passed'] or p['drc_count']!='0' or not p['lvs_passed']
            or sha(physical/name/(name+'.gds'))!=info['gds_sha256']
            or sha(physical/name/(name+'.sch.spice'))!=info['source_scope_sha256']):
            raise ValueError('Compound physical/passive-RC witness failed')
        paths += [ROOT/info['netlist'],ROOT/info['raw_netlist'],parent/name/'extraction.json',parent/name/'lvs.log']
        cells[name]=dict(info=info,text=text)
    return cells,paths
