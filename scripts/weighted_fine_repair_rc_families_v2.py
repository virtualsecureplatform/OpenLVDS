# SPDX-License-Identifier: GPL-3.0-only
"""Replace only bit 4 in the complete native fine RC family after verification."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import weighted_fine_rc_families_v2 as original
import verify_weighted_fine_repair_rc_v2 as verification
from audit_passive_rc_v3 import audit
from lvs_utils import clean_match
from spice_library import checked_netlist

ROOT=original.ROOT
sha=original.sha


def witnesses(parent,repair):
    cells,paths=original.witnesses(parent)
    m=json.loads((repair/'manifest.json').read_text());i=m['identity']
    if (repair.parent!=ROOT/'build/diagnostics/weighted_fine_repair_rc_verification_v2' or i['version']!=verification.VERSION
        or repair.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or any(sha(ROOT/n)!=h for n,h in {**i['inputs'],**i['code']}.items())):raise ValueError('Fine repair verification identity changed')
    env=dict(os.environ);env['PATH']=os.pathsep.join(dict.fromkeys(str(Path(v['path']).parent) for v in i['tools'].values()))+os.pathsep+env['PATH']
    code='import sys; from pathlib import Path; sys.path.insert(0,str(Path(sys.argv[1])/"scripts")); import extract_weighted_fine_repair_v2 as e; e.bound(Path(sys.argv[2]))'
    subprocess.run([sys.executable,'-c',code,str(ROOT),str(ROOT/i['extraction'])],env=env,check=True)
    report=json.loads((repair/'summary.json').read_text());state=json.loads((repair/'state.json').read_text());physical=ROOT/i['parent']
    pm=json.loads((physical/'manifest.json').read_text());pr=json.loads((physical/'summary.json').read_text())
    old=json.loads((parent/'manifest.json').read_text())['identity'];name=verification.extraction.clock_cells.unit.NAME
    if (pm['identity']['original_physical']!=old['parent'] or name!=original.verification.extraction.clock_cells.unit.name(4)
        or state!=dict(status='verified',passed=True,qualified_phy=False) or not report['passed'] or not pr['passed']
        or len(report['rows'])!=1 or len(pr['rows'])!=1 or report['rows'][0]['macro']!=name):raise ValueError('Require exact original-family bit-4 replacement')
    row=report['rows'][0];p=pr['rows'][0];info=row['extraction'];text=checked_netlist(info)
    raw=checked_netlist(dict(info,netlist=info['raw_netlist'],netlist_sha256=info['reduction']['source_sha256']))
    if (not row['rc_topology_passed'] or not row['elementwise_passive_passed'] or not p['passed'] or p['drc_count']!='0' or not p['lvs_passed']
        or not all(audit(t)['elementwise_passive_passed'] for t in [raw,text]) or not clean_match((repair/name/'lvs.log').read_text())
        or p['macro']!=name or p['bit']!=4 or info['ports']!=cells[name]['info']['ports'] or info['ports']!=list(p['ports'])
        or info['source_sha256']!=sha(physical/'manifest.json') or info['gds_sha256']!=sha(physical/name/(name+'.gds'))
        or info['source_scope_sha256']!=sha(physical/name/(name+'.sch.spice'))):raise ValueError('Fine repair physical/passive/topology proof failed')
    paths += [repair/n for n in ['manifest.json','summary.json','state.json']]+[ROOT/n for n in {**i['inputs'],**i['code']}]
    paths += [repair/name/n for n in ['summary.json','extraction.json','lvs.log','setup.tcl','console.log']]
    cells[name]=dict(info=info,text=text)
    if len(cells)!=5:raise ValueError('Incomplete native five-bit family')
    return cells,paths
