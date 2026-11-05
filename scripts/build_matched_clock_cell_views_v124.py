#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Normalize measured stronger coarse buffers and the middle-bus fine cell.

Standalone library additions only. Existing registries, bank timing and PHY
admission are not modified. Preserve every manufacturing mask under translation.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import layout
import build_clock_cell_views_v114 as common
import build_bank_cell_registry_v44 as registry
import physical_cell_adapter_v44 as adapter
import native_bank_inventory_v51 as inventory

ROOT=layout.ROOT
sha=registry.sha
VERSION='matched-coarse-and-middle-fine-canonical-physical-views-v124.1'
CONTEXT='clock_cell_views_v124'
FINE=ROOT/'build/diagnostics/moscap_fine_rc_v105/3198638a648681ac'
COARSE=ROOT/'build/diagnostics/parallel_coarse_cells_v121/be7fd56d4ea74868'
FINE_ALIASES=dict(NODE='A',EN='CTRL',ENB='CTRL_B',VDD='VPWR',VSS='VGND')
PAIR_ALIASES=dict(IN='A',OUT='Y',VPWR='VPWR',VGND='VGND')


reference=common.reference
normalize=common.normalize
audit=common.audit
native=common.native


def sources():
    code='import sys;sys.path.insert(0,"scripts");import strong_coarse_bank_v122 as c;c.checked_cell(c.ROOT/sys.argv[1]);c.checked_coarse("b2");c.checked_coarse("b3")'
    subprocess.run([str(ROOT/'build/tools/exact-rc-venv/bin/python'),'-c',code,str(FINE.relative_to(ROOT))],cwd=ROOT,check=True)
    fi=json.loads((FINE/'manifest.json').read_text());fr=json.loads((FINE/'summary.json').read_text())
    ci=json.loads((COARSE/'manifest.json').read_text())['identity'];cr=json.loads((COARSE/'summary.json').read_text())
    fp=ROOT/fi['parent'];fs='openlvds_moscap_fine_w126_v77'
    fg=ROOT/fr['native_geometry']['gds']
    specs={'openlvds_fine_moscap_w126_middle_v124':dict(source_top=fs,gds=str(fg),lef=str(fg.with_suffix('.lef')),
        schematic=str(fp/(fs+'.sch.spice')),native_reference=str(fp/(fs+'.lvs.spice')),
        aliases=FINE_ALIASES,order=['A','CTRL','CTRL_B','VPWR','VGND'],
        directions=dict(A='inout',CTRL='input',CTRL_B='input',VPWR='inout',VGND='inout'),mim_area_um2=4.,native_primitives=6)}
    for row in cr['rows']:
        profile=row['profile'];source=row['graph']['top'];file=ROOT/row['physical']['gds']
        if profile not in ('b2','b3'):raise ValueError('Unknown qualified coarse profile')
        specs['openlvds_coarse_'+profile+'_registered_v124']=dict(source_top=source,gds=str(file),lef=str(file.with_suffix('.lef')),
            schematic=str(COARSE/'inv2/native'/(source+'.sch.spice')),
            native_reference=str(COARSE/profile/'native'/(source+'.lvs.spice')),
            aliases=dict(IN='A',OUT='X',VPWR='VPWR',VGND='VGND'),order=['A','X','VPWR','VGND'],
            directions=dict(A='input',X='output',VPWR='inout',VGND='inout'),mim_area_um2=0.,native_primitives=20*int(profile[1]))
        specs['openlvds_coarse_'+profile+'_registered_v124']['schematic']=str(COARSE/profile/'native'/(source+'.sch.spice'))
    paths=[]
    for parent,i,r,extracted in [(FINE,fi,fr,'original_extracted_files'),(COARSE,ci,cr,'extracted_files')]:
        paths += [parent/'manifest.json',parent/'summary.json',*[ROOT/n for n in i['inputs']],*[parent/n for n in r['files']],*[ROOT/n for n in r[extracted]]]
    for spec in specs.values():paths += [Path(spec[k]) for k in ['gds','lef','schematic','native_reference']]
    return specs,sorted(set(paths))


def prepare():
    import klayout.db as db
    specs,paths=sources();pdk=Path(os.environ['PDK_ROOT'])/'sky130A'
    external=[pdk/'libs.ref/sky130_fd_sc_hd/techlef/sky130_fd_sc_hd__nom.tlef',
              pdk/'libs.tech/magic/sky130A.magicrc',pdk/'libs.tech/netgen/sky130A_setup.tcl']
    code=sorted({Path(m.__file__).resolve() for m in list(sys.modules.values())
                 if getattr(m,'__file__',None) and Path(m.__file__).resolve().parent==ROOT/'scripts'})
    tools={n:dict(path=shutil.which(n),sha256=sha(Path(shutil.which(n)))) for n in ['openroad','magic','netgen']}
    i=dict(version=VERSION,specs=specs,inputs={str(p.relative_to(ROOT)):sha(p) for p in paths},
           code={str(p.relative_to(ROOT)):sha(p) for p in code},external_files={str(p):sha(p) for p in external},
           tech_lef=str(external[0]),openroad=tools['openroad'],tools=tools,
           klayout=dict(version=db.__version__,module_sha256=sha(Path(db.__file__))))
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);(out/'manifest.json').write_text(json.dumps(dict(identity=i,qualified_phy=False),indent=2)+'\n');return out


def bound(out):
    import klayout.db as db
    i=json.loads((out/'manifest.json').read_text())['identity']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION
        or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or any(sha(ROOT/n)!=h for n,h in {**i['inputs'],**i['code']}.items())
        or any(sha(Path(n))!=h for n,h in i['external_files'].items())
        or any(sha(Path(t['path']))!=t['sha256'] for t in i['tools'].values())
        or i['klayout']!=dict(version=db.__version__,module_sha256=sha(Path(db.__file__)))):
        raise ValueError('Canonical component inputs changed')
    return i


def run(out):
    import klayout.db as db
    i=bound(out)
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain existing or partial canonical views')
        (out/'state.json').write_text('{"status":"qualifying","qualified_phy":false}\n')
        (out/'gds').mkdir();(out/'lef').mkdir();records={};proofs={};combined=db.Layout();combined.dbu=.001;names=set();lefs=[]
        for model,spec in i['specs'].items():
            lib,top,lef,record=normalize(spec,model)
            gds=out/'gds'/(model+'.gds');options=db.SaveLayoutOptions();options.select_cell(top.cell_index());lib.write(str(gds),options)
            path=out/'lef'/(model+'.lef');path.write_text('VERSION 5.7 ;\n'+lef)
            record['audit']=audit(spec,model,gds,path,record)
            fresh=db.Layout();fresh.read(str(gds));incoming={c.name for c in fresh.each_cell()}
            if names&incoming:raise ValueError('Canonical component hierarchy names collide')
            names|=incoming;combined.read(str(gds));lefs.append(lef);records[model]=record
            proofs[model]=native(out,spec,model,record,gds)
        combined.write(str(out/'library.gds'))
        (out/'library.lef').write_text('VERSION 5.7 ;\nDIVIDERCHAR "/" ;\nBUSBITCHARS "[]" ;\n'+''.join(lefs)+'END LIBRARY\n')
        opendb=registry.check_opendb(out,i,records);bound(out)
        report=dict(cells=records,native_qualification=proofs,opendb=opendb,canonical_component_views_passed=True,
                    complete_bank_interconnect_qualified=False,electrical_qualification_passed=False,qualified_phy=False)
        report['files']={str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.is_file() and p.name not in ['state.json','.execution.lock']}
        (out/'summary.json').write_text(json.dumps(report,indent=2)+'\n');(out/'state.json').write_text('{"status":"complete","passed":true,"qualified_phy":false}\n')
    return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','campaign']);p.add_argument('artifact',type=Path,nargs='?');a=p.parse_args()
    if a.action=='run' and a.artifact is None:p.error('run requires an artifact')
    out=prepare() if a.action in ['prepare','campaign'] else a.artifact.resolve();print(out,flush=True)
    if a.action in ['run','campaign']:print(run(out),flush=True)
