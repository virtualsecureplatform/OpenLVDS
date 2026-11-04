# SPDX-License-Identifier: GPL-3.0-only
"""Require the independent native NAND2B guard RC and retained clock families."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import phase_release_rc_families_v2 as base
from lvs_utils import clean_match

ROOT=base.ROOT
sha=base.sha
compound=base.compound
VERSION='independent-native-nand2b-bodytap-passive-rc-verification-v2.1'


def witnesses(parent):
    if parent.parent.name!='nand2b_bodytap_rc_verification_v2':return base.witnesses(parent)
    m=json.loads((parent/'manifest.json').read_text());i=m['identity']
    if (i['version']!=VERSION or parent.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or any(sha(ROOT/n)!=h for n,h in {**i['inputs'],**i['code']}.items())):raise ValueError('NAND2B verification identity changed')
    env=dict(os.environ);env['PATH']=os.pathsep.join(dict.fromkeys(str(Path(v['path']).parent) for v in i['tools'].values()))+os.pathsep+env['PATH']
    code='import sys; from pathlib import Path; sys.path.insert(0,str(Path(sys.argv[1])/"scripts")); import extract_nand2b_bodytap_v2 as e; e.bound(Path(sys.argv[2]))'
    subprocess.run([sys.executable,'-c',code,str(ROOT),str(ROOT/i['extraction'])],env=env,check=True)
    report=json.loads((parent/'summary.json').read_text());physical=ROOT/i['parent'];pr=json.loads((physical/'summary.json').read_text())
    expected=['openlvds_nand2b_4_o1_shunted_bodytap_v2','openlvds_nand2b_4_o2_shunted_bodytap_v2']
    if (not report['passed'] or not pr['passed'] or [r['macro'] for r in report['rows']]!=expected
        or [r['macro'] for r in pr['rows']]!=expected):raise ValueError('Require both exact guarded NAND2B variants')
    paths=[parent/n for n in ['manifest.json','summary.json','state.json']]+[ROOT/n for n in {**i['inputs'],**i['code']}];cells={}
    for row,p in zip(report['rows'],pr['rows']):
        name=row['macro'];info=row['extraction'];text=base.checked_netlist(info)
        if (not row['rc_topology_passed'] or not row['elementwise_passive_passed'] or not base.audit(text)['elementwise_passive_passed']
            or not clean_match((parent/name/'lvs.log').read_text()) or p['drc_count']!='0' or not p['lvs_passed']
            or info['gds_sha256']!=sha(physical/name/(name+'.gds'))
            or info['source_scope_sha256']!=sha(physical/name/(name+'.sch.spice'))):raise ValueError('Guarded NAND2B physical/passive-RC proof failed')
        paths += [ROOT/info['netlist'],ROOT/info['raw_netlist'],parent/name/'summary.json',parent/name/'extraction.json',parent/name/'lvs.log']
        cells[name]=dict(info=info,text=text)
    return cells,paths
