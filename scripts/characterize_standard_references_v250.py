#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Extract native standard-master junction references from the bank's exact GDS."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import klayout.db as db
import prepare_isolated_fine_placement_v238 as placement
import native_bank_inventory_v51 as native
from build_compound_drivers_v3 import cell_definition
from lvs_utils import strict_setup,clean_match
from native_public_port_order_v171 import canonicalize

ROOT=placement.ROOT
sha=placement.sha
VERSION='isolated-bank-native-standard-reference-named-header-order-v250.1'
CONTEXT='isolated_bank_standard_references_v250'


def prepare(parent):
    pi=placement.bound(parent);r=json.loads((parent/'summary.json').read_text())
    if (json.loads((parent/'state.json').read_text())!=dict(status='complete',passed=True,qualified_phy=False)
        or not r['placement_feasibility_passed'] or r['placement_geometry']['drc_count']!='0'
        or any(sha(parent/n)!=h for n,h in r['files'].items())):raise ValueError('Require exact zero-DRC native isolated bank placement')
    models={m:o for m,o in pi['graph']['orders'].items() if m.startswith('sky130_fd_sc_hd__')}
    if len(models)!=5:raise ValueError('Require original five functional standard masters')
    paths=[parent/n for n in ('manifest.json','summary.json','state.json',*r['files'])]
    paths += [ROOT/n for n in {*pi['inputs'],*pi['code']}]
    paths+=sorted({Path(m.__file__).resolve() for m in list(sys.modules.values()) if getattr(m,'__file__',None) and Path(m.__file__).resolve().parent==ROOT/'scripts'})
    i=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),models=models,records={m:pi['records'][m] for m in models},
        inputs={str(p.relative_to(ROOT)):sha(p) for p in sorted(set(paths))},external_files=pi['external_files'],tools=pi['tools'],
        scope='Exact registered GDS standard-master reference extraction, native parameters and strict LVS only; parent supplies placement DRC evidence, no new standalone tap/whole-bank routing/RC/timing/PHY admission')
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);(out/'manifest.json').write_text(json.dumps(dict(identity=i,qualified_phy=False),indent=2)+'\n');return out


def bound(out):
    i=json.loads((out/'manifest.json').read_text())['identity']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION
        or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or any(sha(ROOT/n)!=h for n,h in i['inputs'].items())
        or any(sha(Path(n))!=h for n,h in i['external_files'].items())
        or any(sha(Path(t['path']))!=t['sha256'] for t in i['tools'].values())):raise ValueError('Native standard reference inputs changed')
    return i


def run(out):
    i=bound(out);parent=ROOT/i['parent'];rows=[];error=None
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain existing or partial native standard references')
        (out/'state.json').write_text('{"status":"extracting","qualified_phy":false}\n')
        try:
            lib=db.Layout();lib.read(str(parent/'library.gds'));reference=(parent/'reference.spice').read_text()
            for model,order in i['models'].items():
                folder=out/model;folder.mkdir();gds=folder/(model+'.gds');options=db.SaveLayoutOptions();options.select_cell(lib.cell(model).cell_index());lib.write(str(gds),options)
                source=cell_definition(reference,model);(folder/(model+'.sch.spice')).write_text(source)
                commands=['gds readonly false',f'gds read {{{gds}}}',f'load {model}']
                for k,pin in enumerate(order,1):
                    x,y=i['records'][model]['pins'][pin]['anchor_um'];commands += [f'box values {x-.02}um {y-.02}um {x+.02}um {y+.02}um',f'port make {k}']
                commands += [f'save {model}',f'flatten {model}_flat',f'load {model}_flat','extract all','ext2spice lvs',f'ext2spice -o {model}.lvs.spice {model}_flat.ext']
                placement.stock.assembly.layout.invoke_magic(folder,'\n'.join(commands),'extract_native_standard')
                actual=re.sub(r'\n[ \t]*\+[ \t]*',' ',(folder/(model+'.lvs.spice')).read_text())
                actual,header_proof=canonicalize(actual,model+'_flat',order)
                ordered=folder/(model+'.ordered.lvs.spice');ordered.write_text(actual)
                a,expected=native.native_leaves(source,model);b,devices=native.native_leaves(actual,model+'_flat')
                if a!=b:raise ValueError('Native standard master port order differs: '+model)
                params=native.compare_parameters(expected,devices)
                setup=strict_setup(folder/'setup.tcl',Path(os.environ['PDK_ROOT'])/'sky130A/libs.tech/netgen/sky130A_setup.tcl')
                proc=subprocess.run(['netgen','-batch','lvs',f'{ordered} {model}_flat',f'{folder/(model+".sch.spice")} {model}',str(setup),str(folder/'lvs.log')],cwd=folder,capture_output=True,text=True)
                (folder/'netgen-console.log').write_text(proc.stdout+proc.stderr)
                if not clean_match((folder/'lvs.log').read_text(),proc.returncode):raise ValueError('Native standard reference strict LVS failed: '+model)
                rows.append(dict(model=model,ports=a,native_reference_file=ordered.name,port_header_proof=header_proof,native_parameters=params,native_reference_lvs_passed=True,native_mask_source_sha256=sha(gds),
                    files={p.name:sha(p) for p in folder.iterdir() if p.is_file()},qualified_phy=False))
        except Exception as e:error=type(e).__name__+': '+str(e)
        bound(out);passed=error is None and len(rows)==5
        r=dict(rows=rows,error=error,native_standard_references_passed=passed,qualified_phy=False,scope=i['scope'])
        r['files']={str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.is_file() and p.name not in ('state.json','.execution.lock')}
        (out/'summary.json').write_text(json.dumps(r,indent=2)+'\n');(out/'state.json').write_text(json.dumps(dict(status='complete',passed=passed,qualified_phy=False))+'\n')
    return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','campaign']);p.add_argument('artifact',type=Path);a=p.parse_args();out=a.artifact.resolve()
    if a.action in ('prepare','campaign'):out=prepare(out);print(out,flush=True)
    if a.action in ('run','campaign'):print(run(out),flush=True)
