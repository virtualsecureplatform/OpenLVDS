#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Fresh whole-bank passive RC and expanded native-device topology proof.

Require clean bank routing, GDS DRC/LVS, exact final connections and final
power-grid continuity. This does not qualify delay range or legal-code ROM.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import harden_dcdl_bank_v12 as physical
import extract_native_flat_v4 as rc
import dcdl_bank_native_reference_v2 as native
from audit_rc_comments_v2 import collapse
from lvs_utils import strict_setup,clean_match
from spice_library import checked_netlist

ROOT=physical.ROOT
sha=physical.sha
VERSION='whole-routed-dcdl-bank-passive-rc-native-topology-v2.1'


def parent_files(parent):
    m=physical.bound(parent);r=json.loads((parent/'summary.json').read_text())
    keys=['route__drc_errors','magic__drc_error__count','klayout__drc_error__count',
          'design__lvs_error__count','antenna__violating__nets','antenna__violating__pins']
    if (not r['physical_implementation_passed'] or not r['interface_verified'] or r['returncode']!=0
        or any(r['metrics'].get(k)!=0 for k in keys)):raise ValueError('Require clean whole-bank physical signoff')
    folder=ROOT/r['run'];name=physical.bank.name()
    gds=folder/'final/gds'/(name+'.gds');db=folder/'final/odb'/(name+'.odb')
    config=m['identity']['configuration']
    sources={model:Path(row['spice'][0]) for model,row in config['MACROS'].items()}
    sc=Path(os.environ['PDK_ROOT'])/'sky130A/libs.ref/sky130_fd_sc_hd/spice/sky130_fd_sc_hd.spice'
    files=[parent/n for n in ['manifest.json','summary.json','state.json','config.json']]
    files += [gds,db,sc,*sources.values()]
    return gds,db,sc,sources,files


def prepare(parent):
    gds,db,sc,sources,files=parent_files(parent)
    code=[Path(__file__),Path(native.__file__),Path(rc.__file__),Path(physical.__file__),
          ROOT/'scripts/audit_rc_comments_v2.py',ROOT/'scripts/audit_rc.py',ROOT/'scripts/audit_passive_rc_v3.py',
          ROOT/'scripts/reduce_rc.py',ROOT/'scripts/lvs_utils.py',ROOT/'scripts/spice_library.py']
    identity=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),tools=physical.tool_identity(),
        inputs={str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p):sha(p) for p in files+code})
    out=ROOT/'build/diagnostics/dcdl_bank_rc_v2'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);physical.atomic(out/'manifest.json',dict(identity=identity,qualified_phy=False))
    return out


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    if (i['version']!=VERSION or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or physical.tool_identity()!=i['tools']):raise ValueError('Bank RC identity changed')
    for n,h in i['inputs'].items():
        p=Path(n) if Path(n).is_absolute() else ROOT/n
        if sha(p)!=h:raise ValueError('Bank RC witness changed: '+n)
    parent_files(ROOT/i['parent']);return m


def power_grid(out,db):
    script=out/'power_grid.tcl'
    script.write_text('read_db {'+str(db)+'}\n'+'''foreach net {VPWR VGND} {
  if {[catch {check_power_grid -net $net} problem]} {puts "GRID_FAILED $net: $problem"; exit 1}
  puts "GRID_CHECKED $net"
}
exit
''')
    log=out/'power_grid.log'
    with log.open('w') as f:p=subprocess.run(['openroad','-no_init','-exit',str(script)],stdout=f,stderr=subprocess.STDOUT)
    text=log.read_text()
    return p.returncode==0 and all('GRID_CHECKED '+n in text and 'All shapes on net '+n+' are connected.' in text for n in ['VPWR','VGND'])


def run(out):
    m=bound(out);parent=ROOT/m['identity']['parent'];gds,db,sc,sources,_=parent_files(parent);name=physical.bank.name()
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain existing whole-bank RC attempt')
        physical.atomic(out/'state.json',dict(status='extracting',qualified_phy=False))
        if not physical.check_db(out,db) or not power_grid(out,db):raise ValueError('Final bank connection/power audit failed')
        fingerprint=hashlib.sha256(gds.read_bytes()+Path(rc.__file__).read_bytes()).hexdigest()[:16]
        if (ROOT/'build/extracted'/fingerprint/name).exists():raise ValueError('Retain existing extraction namespace')
        rows=[line.split('\t') for line in (out/'connections.tsv').read_text().splitlines()]
        ports=(out/'ports.txt').read_text().splitlines()
        reference,counts=native.reference(name,ports,rows,sc.read_text(),{k:v.read_text() for k,v in sources.items()})
        schematic=out/'native_reference.spice';schematic.write_text(reference)
        physical.atomic(out/'native_instance_counts.json',counts)
        info=rc.extract(name,gds,sha(parent/'manifest.json'),source_scope=sha(schematic))
        physical.atomic(out/'extraction.json',info);matched=False
        if info['passed'] and set(info['ports'])==set(ports) and len(info['ports'])==len(ports):
            net=out/'wire_collapsed.spice';net.write_text(collapse(checked_netlist(info)))
            setup=strict_setup(out/'setup.tcl',Path(os.environ['PDK_ROOT'])/'sky130A/libs.tech/netgen/sky130A_setup.tcl')
            report=out/'lvs.log'
            p=subprocess.run(['netgen','-batch','lvs',f'{net} {name}',f'{schematic} {name}',str(setup),str(report)],
                             cwd=out,capture_output=True,text=True)
            (out/'lvs_console.log').write_text(p.stdout+p.stderr)
            matched=clean_match(report.read_text() if report.exists() else '',p.returncode)
        bound(out)
        result=dict(extraction=info,rc_topology_passed=matched,power_grid_verified=True,interface_verified=True,
            native_primitives=sum(counts.values()),routed_instances=len(counts),passed=bool(info['passed'] and matched),
            qualified_phy=False,electrical_qualification_passed=False,
            scope='Fresh passive whole-bank RC and fully expanded native-device DC topology; delay range, code ROM and full-clock qualification remain required')
        physical.atomic(out/'summary.json',result)
        physical.atomic(out/'state.json',dict(status='bank_rc_complete',passed=result['passed'],qualified_phy=False))
        return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','campaign']);p.add_argument('artifact',type=Path)
    a=p.parse_args();out=a.artifact.resolve()
    if a.action in ['prepare','campaign']:out=prepare(out);print(out,flush=True)
    if a.action in ['run','campaign']:print(json.dumps(run(out),indent=2),flush=True)
