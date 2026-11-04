#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Fresh native RC and topology audits for all five root-weighted fine cells."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import build_weighted_fine_units_v3 as clock_cells
import extract_native_flat_v4 as rc
from audit_rc_comments_v2 import collapse
from lvs_utils import strict_setup,clean_match
from spice_library import checked_netlist

ROOT=rc.ROOT
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
VERSION='passivity-gated-five-weighted-fine-cells-rc-v2.1'

def family(parent):
    if parent.parent.name!='weighted_fine_unit_physical_v2':raise ValueError('Require root-weighted fine-cell geometry')
    return clock_cells

def tools_for(physical):
    return physical.environment.environment.tools()


def validate_physical(report,state):
    expected=[clock_cells.unit.name(bit) for bit in range(5)]
    if (state.get('status')!='physical_complete' or not state.get('passed')
        or not report.get('passed') or [r['macro'] for r in report['rows']]!=expected
        or [r['bit'] for r in report['rows']]!=list(range(5))
        or any(r['drc_count']!='0' or not r['lvs_passed'] or not r['passed']
               or set(r['ports'])!=set(clock_cells.unit.PORTS) for r in report['rows'])):
        raise ValueError('Require all five exact DRC/LVS-clean weighted fine cells')


def prepare(parent):
    physical=family(parent);physical.bound(parent);report=json.loads((parent/'summary.json').read_text())
    validate_physical(report,json.loads((parent/'state.json').read_text()))
    paths=[parent/'manifest.json',parent/'summary.json',parent/'state.json']
    for row in report['rows']:
        macro=row['macro'];folder=parent/macro
        if row['drc_count']!='0' or not row['lvs_passed'] or not row['passed']:raise ValueError('Weighted fine DRC/LVS failed')
        if sha(folder/(macro+'.gds'))!=row['gds_sha256'] or sha(folder/(macro+'.lef'))!=row['lef_sha256']:
            raise ValueError('Weighted fine physical output changed')
        paths += [folder/n for n in ['summary.json',macro+'.gds',macro+'.lef',macro+'.mag',macro+'.sch.spice',macro+'.lvs.log',macro+'.drc_count.txt']]
    code=[Path(__file__),Path(physical.__file__),Path(rc.__file__),ROOT/'scripts/audit_rc.py',ROOT/'scripts/audit_rc_comments_v2.py',ROOT/'scripts/reduce_rc.py',ROOT/'scripts/audit_passive_rc_v3.py',
        ROOT/'scripts/lvs_utils.py',ROOT/'scripts/spice_library.py']
    identity=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),code={str(p.relative_to(ROOT)):sha(p) for p in code},
        inputs={str(p.relative_to(ROOT)):sha(p) for p in paths},tools=tools_for(physical))
    out=ROOT/'build/diagnostics/weighted_fine_unit_rc_v2'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);(out/'manifest.json').write_text(json.dumps(dict(identity=identity,qualified_phy=False),indent=2)+'\n')
    return out


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity'];physical=family(ROOT/i['parent'])
    if (out.parent!=ROOT/'build/diagnostics/weighted_fine_unit_rc_v2' or i['version']!=VERSION
        or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or any(sha(ROOT/n)!=v for n,v in {**i['code'],**i['inputs']}.items()) or tools_for(physical)!=i['tools']):
        raise ValueError('Weighted fine extraction inputs changed')
    physical.bound(ROOT/i['parent']);return m


def run(out):
    m=bound(out);parent=ROOT/m['identity']['parent'];report=json.loads((parent/'summary.json').read_text())
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain prior weighted_fine extraction')
        (out/'state.json').write_text('{"status":"extracting","qualified_phy":false}\n');rows=[]
        try:
            for row in report['rows']:
                macro=row['macro'];source=parent/macro;folder=out/macro;folder.mkdir();gds=source/(macro+'.gds')
                digest=hashlib.sha256(gds.read_bytes()+Path(rc.__file__).read_bytes()).hexdigest()[:16]
                if (ROOT/'build/extracted'/digest/macro).exists():raise ValueError('Retain existing weighted_fine RC namespace')
                info=rc.extract(macro,gds,sha(parent/'manifest.json'),ports=row['ports'],source_scope=sha(source/(macro+'.sch.spice')))
                (folder/'extraction.json').write_text(json.dumps(info,indent=2)+'\n');passed=False
                if info['passed']:
                    collapsed=folder/'wire_collapsed.spice';collapsed.write_text(collapse(checked_netlist(info)))
                    setup=strict_setup(folder/'setup.tcl',Path(os.environ['PDK_ROOT'])/'sky130A/libs.tech/netgen/sky130A_setup.tcl')
                    log=folder/'lvs.log'
                    process=subprocess.run(['netgen','-batch','lvs',f'{collapsed} {macro}',f'{source/(macro+".sch.spice")} {macro}',
                        str(setup),str(log)],cwd=folder,capture_output=True,text=True)
                    (folder/'console.log').write_text(process.stdout+process.stderr)
                    passed=clean_match(log.read_text() if log.exists() else '',process.returncode)
                rows.append(dict(macro=macro,extraction=info,rc_topology_passed=passed,
                    qualified_phy=False,electrical_qualification_passed=False))
                (folder/'summary.json').write_text(json.dumps(rows[-1],indent=2)+'\n')
            bound(out);result=dict(rows=rows,passed=all(r['extraction']['passed'] and r['rc_topology_passed'] for r in rows),
                qualified_phy=False,electrical_qualification_passed=False,scope='All five root fine cells: actual GDS RC and strict topology only; no timing, bank ROM or PHY admission')
            (out/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
            (out/'state.json').write_text(json.dumps(dict(status='compound_rc_complete',passed=result['passed'],qualified_phy=False))+'\n')
            return result
        except Exception as error:
            (out/'state.json').write_text(json.dumps(dict(status='extraction_exception',error=str(error),qualified_phy=False))+'\n')
            raise


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','campaign']);p.add_argument('artifact',type=Path);a=p.parse_args();out=a.artifact.resolve()
    if a.action in ['prepare','campaign']:out=prepare(out);print(out,flush=True)
    if a.action in ['run','campaign']:print(json.dumps(run(out),indent=2),flush=True)
