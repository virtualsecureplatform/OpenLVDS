#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Real guarded-MOS TG XOR macros from the retained source sizing candidates."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import layout
import dcc_tg_ratio_v2 as circuit
import inspect_mim_switch_pcells_v2 as environment
import restrict_macro_rails_v4 as abstract

ROOT=layout.ROOT
VERSION='native-custom-tg-xor-p3-p4-physical-v2.1'
sha=environment.sha
PORTS=['a_iso','a_qb_iso','b_iso','b_qb_iso','xor_out','VDDD','VSS']


def name(variant):
    if variant not in ['p3','p4']:raise ValueError('Undeclared physical TG ratio')
    return 'openlvds_tg_xor_'+variant+'_v2'


def source(variant,retained):
    rows=[];caps=[]
    for line in retained.splitlines():
        w=line.split()
        if not w:continue
        if w[0].startswith('Xtg_'):rows.append(line)
        elif len(w)>3 and w[0].startswith('XOUTCAP') and w[1]=='xor_out':caps.append(line)
    if len(rows)!=8 or len(caps)!=1:raise ValueError('Require exact eight-TG-MOS and one output MIM source')
    translated=[]
    for row in rows+caps:
        translated.append(' '.join({'VGND':'VSS','VPWR':'VDDD'}.get(w,w) for w in row.split()))
    text='.subckt '+name(variant)+' '+' '.join(PORTS)+'\n'+'\n'.join(translated)+'\n.ends '+name(variant)+'\n'
    ports,devices=layout.flatten(layout.circuits(text),name(variant))
    if ports!=PORTS or len(devices)!=9:raise ValueError('TG source interface or finger count changed')
    return text,devices


def prepare(parent):
    m=json.loads((parent/'manifest.json').read_text());i=m['identity']
    if (i['version']!='native-buffered-tg-width-ratio-source-pilot-v2.1'
        or parent.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or any(sha(ROOT/n)!=h for n,h in i['inputs'].items()) or any(sha(Path(n))!=h for n,h in i['pdk_files'].items())):
        raise ValueError('Retained native sizing context changed')
    library=Path(i['pdk']).read_text();paths=[parent/'manifest.json']
    for variant in ['p3','p4']:
        p=parent/(variant+'.spice')
        if p.read_text()!=circuit.source(variant,library)[0] or sha(p)!=m['libraries'][p.name]:raise ValueError('Retained TG source differs from native generator')
        source(variant,p.read_text());paths.append(p)
    pdk=Path(os.environ['PDK_ROOT'])/'sky130A';pdks=[pdk/'libs.tech/magic/sky130A.magicrc',pdk/'libs.tech/netgen/sky130A_setup.tcl']
    code=[Path(__file__),Path(layout.__file__),Path(circuit.__file__),Path(environment.__file__),Path(abstract.__file__),Path(abstract.geometry.__file__),ROOT/'scripts/lvs_utils.py']
    identity=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),inputs={str(p.relative_to(ROOT)):sha(p) for p in paths},
        code={str(p.relative_to(ROOT)):sha(p) for p in code},pdk_files={str(p):sha(p) for p in pdks},tools=environment.tools())
    out=ROOT/'build/diagnostics/tg_xor_physical_v2'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);(out/'manifest.json').write_text(json.dumps(dict(identity=identity,qualified_phy=False),indent=2)+'\n');return out


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    if (i['version']!=VERSION or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or any(sha(ROOT/n)!=h for n,h in {**i['inputs'],**i['code']}.items())
        or any(sha(Path(n))!=h for n,h in i['pdk_files'].items()) or environment.tools()!=i['tools']):raise ValueError('TG physical context changed')
    return m


def run(out):
    m=bound(out);parent=ROOT/m['identity']['parent'];rows=[]
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain prior TG physical experiment')
        (out/'state.json').write_text('{"status":"routing","qualified_phy":false}\n')
        for variant in ['p3','p4']:
            top=name(variant);folder=out/top;folder.mkdir();text,devices=source(variant,(parent/(variant+'.spice')).read_text());(folder/'retained_source.spice').write_text(text)
            library={};body=[]
            for model,w,l in sorted({layout.primitive_key(d) for d in devices}):
                cell='tg_primitive_'+hashlib.sha256(f'{model}:{w}:{l}'.encode()).hexdigest()[:12]
                body += [f'load {cell} -silent','box values 0 0 0 0',f'set p [sky130::{model}_defaults]',f'dict set p w {w}',f'dict set p l {l}']
                if 'nfet' in model or 'pfet' in model:body.append('dict set p botc 0')
                body += [f'sky130::{model}_draw $p',f'save {cell}'];library[(model,w,l)]=cell
            layout.invoke_magic(folder,'\n'.join(body),'pcells')
            library={k:(v,layout.pcell_info(folder/(v+'.mag'))) for k,v in library.items()}
            geometry=layout.draw_macro(folder,top,PORTS,devices,library);result=layout.qualify(folder,top)
            raw=folder/(top+'.raw.lef');raw.write_bytes((folder/(top+'.lef')).read_bytes())
            types={p:('OUTPUT' if p=='xor_out' else 'INPUT','SIGNAL') for p in PORTS if p not in ['VDDD','VSS']}
            types.update(VDDD=('INOUT','POWER'),VSS=('INOUT','GROUND'))
            restricted,pins=abstract.restrict(raw.read_text(),geometry['ports'],types);(folder/(top+'.lef')).write_text(restricted)
            row=dict(result,macro=top,variant=variant,ports=geometry['ports'],integration_pins=pins,geometry=geometry,
                gds_sha256=sha(folder/(top+'.gds')),lef_sha256=sha(folder/(top+'.lef')),qualified_phy=False,electrical_qualification_passed=False)
            rows.append(row);(folder/'summary.json').write_text(json.dumps(row,indent=2)+'\n')
        bound(out);result=dict(rows=rows,passed=all(r['passed'] for r in rows),qualified_phy=False,electrical_qualification_passed=False,
            scope='Two guarded native-MOS TG XOR layouts with original eight transistor widths and output MIM; geometry/connectivity only, no RC or DCC timing admission')
        (out/'summary.json').write_text(json.dumps(result,indent=2)+'\n');(out/'state.json').write_text(json.dumps(dict(status='physical_complete',passed=result['passed'],qualified_phy=False))+'\n');return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','campaign']);p.add_argument('artifact',type=Path);a=p.parse_args();out=a.artifact.resolve()
    if a.action in ['prepare','campaign']:out=prepare(out);print(out,flush=True)
    if a.action in ['run','campaign']:print(json.dumps(run(out),indent=2))
