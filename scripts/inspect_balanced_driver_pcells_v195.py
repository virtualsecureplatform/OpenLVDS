#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Inspect compact native MOS finger banks for a balanced fine-driver candidate.

Drain/source terminals remain separate: this is primitive geometry and count
characterization, not an inverter, routed macro or electrical qualification.
"""
import argparse
from collections import Counter
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import layout
import native_bank_inventory_v51 as inventory
import inspect_mim_switch_pcells_v2 as environment

ROOT=layout.ROOT
VERSION='balanced-driver-connected-gate-native-finger-inspection-v195.1'
CONTEXT='balanced_driver_pcells_v195'
PROFILES=[dict(kind=kind,model='sky130_fd_pr__'+kind+'fet_01v8',width_um=w,length_um=.15,fingers=n,conn_gates=1,botc=0)
          for kind,w,counts in [('n',.65,(10,12)),('p',1.,(20,24))] for n in counts]
SCOPE='Actual pinned PDK connected-gate MOS finger geometry/DRC/count/width characterization only; drain/source strapping, full-driver LVS, RC, timing/all-PVT/PHY admission remain open'


def atomic(path,value):
    temporary=path.with_name(path.name+'.tmp');temporary.write_text(json.dumps(value,indent=2)+'\n');temporary.replace(path)


def name(s):return 'openlvds_'+s['kind']+str(s['fingers'])+'_fine_v195'


def characterize(text,top,s):
    ports,devices=inventory.native_leaves(re.sub(r'\n[ \t]*\+[ \t]*',' ',text),top+'_flat')
    counts=dict(Counter(d['model'] for d in devices))
    exact=counts=={s['model']:s['fingers']} and all(inventory.exact_number(d['params']['w'])==inventory.exact_number(s['width_um']) and inventory.exact_number(d['params']['l'])==inventory.exact_number(s['length_um']) for d in devices)
    return dict(ports=ports,native_model_counts=counts,extracted_fingers=len(devices),finger_count_and_dimensions_match=exact,
        extracted_gate_nodes=sorted({d['nodes'][1] for d in devices}),extracted_body_nodes=sorted({d['nodes'][3] for d in devices}),
        all_gates_on_named_gate=bool(devices and all(d['nodes'][1]=='G' for d in devices)),
        all_bodies_on_named_bulk=bool(devices and all(d['nodes'][3]=='B' for d in devices)),qualified_phy=False)


def terminal_accesses(text):
    result=[]
    for line in text.splitlines():
        if line.startswith('rlabel '):
            w=line.split();label=w[-1]
            if label=='B' or label=='G' or re.fullmatch('[DS][0-9]*',label):
                result.append(dict(name=label,layer=w[1],x_um=(int(w[2])+int(w[4]))/2*layout.GRID,y_um=(int(w[3])+int(w[5]))/2*layout.GRID))
    return result


def prepare():
    pdk=Path(os.environ['PDK_ROOT'])/'sky130A';magic=pdk/'libs.tech/magic'
    files=[Path(__file__),Path(layout.__file__),Path(inventory.__file__),Path(environment.__file__),ROOT/'scripts/lvs_utils.py',ROOT/'requirements.json']
    external=[magic/'sky130A.magicrc',*magic.glob('*.tcl'),pdk/'libs.tech/netgen/sky130A_setup.tcl']
    sha=environment.sha
    identity=dict(version=VERSION,profiles=PROFILES,inputs={str(p.relative_to(ROOT)):sha(p) for p in files},
        external_files={str(p):sha(p) for p in external},tools=environment.tools(),scope=SCOPE)
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16];out.mkdir(parents=True,exist_ok=False)
    atomic(out/'manifest.json',dict(identity=identity,qualified_phy=False));return out


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity'];sha=environment.sha
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or i['profiles']!=PROFILES or any(sha(ROOT/n)!=h for n,h in i['inputs'].items()) or any(sha(Path(n))!=h for n,h in i['external_files'].items()) or environment.tools()!=i['tools']):raise ValueError('Balanced primitive inspection inputs changed')
    return m


def run(out):
    m=bound(out)
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain previous or partial primitive inspection')
        atomic(out/'state.json',dict(status='inspecting',qualified_phy=False));rows=[]
        try:
            for s in PROFILES:
                top=name(s);folder=out/top;folder.mkdir()
                script=f'''load {top} -silent
box values 0 0 0 0
set p [sky130::{s['model']}_defaults]
dict set p w {s['width_um']}
dict set p l {s['length_um']}
dict set p nf {s['fingers']}
dict set p conn_gates 1
dict set p botc 0
sky130::{s['model']}_draw $p
save {top}
gds write {top}.gds
flatten {top}_flat
load {top}_flat
select top cell
box values -100um -100um 10000um 10000um
drc euclidean on
drc on
drc check
drc catchup
set f [open drc_count.txt w]
puts $f [drc listall count total]
close $f
set f [open drc_details.txt w]
puts $f [drc listall why]
close $f
extract style ngspice()
extract do unique
extract all
ext2spice lvs
ext2spice merge none
ext2spice -o {top}.lvs.spice {top}_flat.ext
'''
                layout.invoke_magic(folder,script,'inspect')
                geometry=layout.pcell_info(folder/(top+'.mag'));terminals=terminal_accesses((folder/(top+'.mag')).read_text())
                extracted=characterize((folder/(top+'.lvs.spice')).read_text(),top,s);drc=(folder/'drc_count.txt').read_text().strip()
                row=dict(spec=s,top=top,geometry=geometry,terminal_accesses=terminals,extracted=extracted,drc_count=drc,
                    primitive_inspection_passed=drc=='0' and extracted['finger_count_and_dimensions_match'],routed_driver=False,qualified_phy=False)
                row['files']={p.name:environment.sha(p) for p in folder.iterdir() if p.is_file()};atomic(folder/'summary.json',row);rows.append(row)
            bound(out);atomic(out/'summary.json',dict(rows=rows,primitive_inspection_passed=all(r['primitive_inspection_passed'] for r in rows),scope=SCOPE,routed_driver=False,qualified_phy=False))
            atomic(out/'state.json',dict(status='complete',passed=all(r['primitive_inspection_passed'] for r in rows),qualified_phy=False));return out
        except Exception as e:atomic(out/'state.json',dict(status='failed',error=str(e),qualified_phy=False));raise


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','campaign']);p.add_argument('artifact',nargs='?',type=Path);a=p.parse_args()
    if a.action in ('prepare','campaign'):out=prepare();print(out,flush=True)
    elif a.artifact is None:p.error('Provide the prepared artifact')
    else:out=a.artifact.resolve()
    if a.action in ('run','campaign'):print(run(out),flush=True)
