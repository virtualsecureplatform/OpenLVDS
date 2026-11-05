#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Independently recheck the native clock-pair source, passivity and flat LVS."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import extract_clock_buffer_pair_v2 as extraction
from reduce_rc import reduce_netlist

ROOT=extraction.ROOT
sha=extraction.sha
VERSION='independent-parallel-buf8-passive-rc-topology-v2.1'
CONTEXT='clock_buffer_pair_rc_verification_v2'


def checked(parent):
    m=extraction.bound(parent);r=json.loads((parent/'summary.json').read_text())
    if (json.loads((parent/'state.json').read_text())['status']!='clock_pair_rc_complete' or not r['passed']
        or not r['rc_topology_passed'] or not r['reduced_passivity_passed']):raise ValueError('Require completed positive clock-pair extraction')
    physical=ROOT/m['identity']['parent'];pm,row,source=extraction.parent_row(physical)
    _,_,child=extraction.physical.parent_row(ROOT/pm['identity']['parent']);name=extraction.physical.NAME
    native=extraction.physical.schematic((child/(extraction.physical.CHILD+'.sch.spice')).read_text())
    if native!=(source/(name+'.sch.spice')).read_text():raise ValueError('Two unchanged native buffer source scopes cannot be regenerated')
    info=r['extraction'];raw=ROOT/info['raw_netlist'];text=extraction.checked_netlist(info)
    if (json.loads((parent/'extraction.json').read_text())!=info or info['ports']!=list(row['ports'])
        or info['gds_sha256']!=sha(source/(name+'.gds')) or info['source_scope_sha256']!=sha(source/(name+'.sch.spice'))
        or sha(raw)!=info['reduction']['source_sha256'] or not extraction.audit(raw.read_text())['elementwise_passive_passed']
        or not extraction.audit(text)['elementwise_passive_passed']):raise ValueError('Native clock-pair GDS/source/interface/passivity changed')
    return m,r,source,native


def verify(parent):
    m,r,source,native=checked(parent);name=extraction.physical.NAME
    files=[p for p in parent.iterdir() if p.is_file() and p.name!='.execution.lock']
    files += [ROOT/r['extraction'][k] for k in ['raw_netlist','netlist']]
    files += [Path(__file__),Path(extraction.__file__),Path(extraction.physical.__file__),ROOT/'scripts/reduce_rc.py',
              ROOT/'scripts/audit_rc_comments_v2.py',ROOT/'scripts/audit_passive_rc_v3.py',ROOT/'scripts/lvs_utils.py',ROOT/'scripts/spice_library.py']
    identity=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),tools=m['identity']['tools'],inputs={str(p.relative_to(ROOT)):sha(p) for p in files})
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);(out/'manifest.json').write_text(json.dumps(dict(identity=identity,qualified_phy=False),indent=2)+'\n')
    schematic=out/'native_reference.spice';schematic.write_text(native)
    net=out/'regenerated.spice';reduction=reduce_netlist(ROOT/r['extraction']['raw_netlist'],net)
    if sha(net)!=r['extraction']['netlist_sha256'] or reduction!=r['extraction']['reduction']:
        raise ValueError('Native clock-pair raw-to-simulator reduction changed')
    collapsed=out/'wire_collapsed.spice';collapsed.write_text(extraction.collapse(net.read_text()))
    setup=extraction.strict_setup(out/'setup.tcl',Path(os.environ['PDK_ROOT'])/'sky130A/libs.tech/netgen/sky130A_setup.tcl');log=out/'lvs.log'
    p=subprocess.run(['netgen','-batch','lvs',f'{collapsed} {name}',f'{schematic} {name}',str(setup),str(log)],cwd=out,capture_output=True,text=True)
    (out/'console.log').write_text(p.stdout+p.stderr);passed=extraction.clean_match(log.read_text() if log.exists() else '',p.returncode)
    checked(parent);outputs={p.name:sha(p) for p in out.iterdir() if p.is_file() and p.name!='manifest.json'}
    result=dict(extraction=r['extraction'],outputs=outputs,passed=passed,rc_topology_passed=passed,
        raw_and_reduced_passivity_passed=True,exact_reduction_regenerated=True,native_pair_source_regenerated=True,
        qualified_phy=False,electrical_qualification_passed=False,
        scope='Native two-buffer source regeneration, raw/reduced passivity, exact reduction and repeated strict flat LVS; no clock phase, full-PVT or PHY admission')
    (out/'summary.json').write_text(json.dumps(result,indent=2)+'\n');return out


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity'];r=json.loads((out/'summary.json').read_text())
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION
        or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or any(sha(ROOT/n)!=h for n,h in i['inputs'].items()) or not r['passed'] or not r['rc_topology_passed']
        or not r['outputs'] or any(sha(out/n)!=h for n,h in r['outputs'].items())
        or not all(r[k] is True for k in ['raw_and_reduced_passivity_passed','exact_reduction_regenerated','native_pair_source_regenerated'])):
        raise ValueError('Independent native clock-pair RC receipt changed or failed')
    _,parent,_,native=checked(ROOT/i['parent'])
    if (r['extraction']!=parent['extraction'] or sha(out/'regenerated.spice')!=r['extraction']['netlist_sha256']
        or (out/'native_reference.spice').read_text()!=native or not extraction.clean_match((out/'lvs.log').read_text())):
        raise ValueError('Independent native clock-pair RC proof changed')
    return m


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('artifact',type=Path)
    a=p.parse_args();print(verify(a.artifact.resolve()),flush=True)
