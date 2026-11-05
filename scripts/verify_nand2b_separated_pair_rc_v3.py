#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Reaudit fresh flat/passive RC with inline-comment-aware topology collapse."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import extract_nand2b_separated_pair_v3 as extraction
from audit_rc_comments_v2 import collapse
from audit_passive_rc_v3 import audit
from lvs_utils import strict_setup,clean_match
from spice_library import checked_netlist

ROOT=extraction.ROOT
sha=extraction.sha
VERSION='independent-native-nand2b-separated-pair-passive-rc-verification-v3.1'


def verify(parent):
    m=extraction.bound(parent);i=m['identity'];physical=ROOT/i['parent'];report=json.loads((parent/'summary.json').read_text())
    state=json.loads((parent/'state.json').read_text());pr=json.loads((physical/'summary.json').read_text())
    if (state['status']!='compound_rc_complete' or len(report['rows'])!=1 or report['rows'][0]['macro']!=extraction.clock_cells.NAME
        or [r['macro'] for r in report['rows']]!=[r['macro'] for r in pr['rows']]):
        raise ValueError('Require complete exact guarded NAND2B pair RC coverage')
    for row,p in zip(report['rows'],pr['rows']):
        info=row['extraction'];name=row['macro']
        if (info['ports']!=list(p['ports']) or info['gds_sha256']!=sha(physical/name/(name+'.gds'))
            or info['source_scope_sha256']!=sha(physical/name/(name+'.sch.spice'))):
            raise ValueError('NAND2B GDS/source/interface identity changed')
    files=[parent/'manifest.json',parent/'summary.json',parent/'state.json']
    files += [ROOT/n for n in {**i['code'],**i['inputs']}]
    for row in report['rows']:
        if not row['extraction']['passed'] or not audit(checked_netlist(row['extraction']))['elementwise_passive_passed']:raise ValueError('Require passive fresh RC')
        info=row['extraction'];files += [ROOT/info['netlist'],ROOT/info['raw_netlist'],parent/row['macro']/'extraction.json']
    code=[Path(__file__),Path(extraction.__file__),ROOT/'scripts/audit_rc_comments_v2.py',ROOT/'scripts/audit_rc.py',ROOT/'scripts/audit_passive_rc_v3.py',ROOT/'scripts/lvs_utils.py',ROOT/'scripts/spice_library.py']
    identity=dict(version=VERSION,parent=str(physical.relative_to(ROOT)),extraction=str(parent.relative_to(ROOT)),
        inputs={str(p.relative_to(ROOT)):sha(p) for p in files},code={str(p.relative_to(ROOT)):sha(p) for p in code},tools=i['tools'])
    out=ROOT/'build/diagnostics/nand2b_separated_pair_rc_verification_v3'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
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


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    if (out.parent!=ROOT/'build/diagnostics/nand2b_separated_pair_rc_verification_v3' or i['version']!=VERSION
        or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or any(sha(ROOT/n)!=h for n,h in {**i['inputs'],**i['code']}.items())):
        raise ValueError('Separated-pair independent RC identity changed')
    em=extraction.bound(ROOT/i['extraction']);physical=ROOT/i['parent']
    if str(physical.relative_to(ROOT))!=em['identity']['parent']:raise ValueError('Separated pair physical parent changed')
    pr=json.loads((physical/'summary.json').read_text());er=json.loads((ROOT/i['extraction']/'summary.json').read_text())
    r=json.loads((out/'summary.json').read_text());state=json.loads((out/'state.json').read_text());name=extraction.clock_cells.NAME
    if (not r['passed'] or state.get('status')!='verified' or not state.get('passed') or len(r['rows'])!=1
        or [v['macro'] for v in r['rows']]!=[name] or not pr['passed'] or not er['passed']):
        raise ValueError('Require one complete clean separated-pair native RC receipt')
    row=r['rows'][0];info=row['extraction'];p=pr['rows'][0]
    if (info!=er['rows'][0]['extraction'] or not row['rc_topology_passed'] or not row['elementwise_passive_passed']
        or set(info['ports'])!={'A_N','B','Y','VGND','VPWR'} or info['gds_sha256']!=sha(physical/name/(name+'.gds'))
        or info['source_scope_sha256']!=sha(physical/name/(name+'.sch.spice')) or info['source_sha256']!=sha(physical/'manifest.json')
        or p['drc_count']!='0' or not p['lvs_passed'] or not clean_match((out/name/'lvs.log').read_text())
        or not audit(checked_netlist(info))['elementwise_passive_passed']
        or not audit(checked_netlist(dict(info,netlist=info['raw_netlist'],netlist_sha256=info['reduction']['source_sha256'])))['elementwise_passive_passed']):
        raise ValueError('Separated-pair native topology/passivity/interface proof changed')
    return m


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('artifact',type=Path);a=p.parse_args();print(verify(a.artifact.resolve()),flush=True)
