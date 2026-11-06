#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Normalize strong-discharge fine drivers and their native BUF8 regenerator.

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
import qualify_discharge_fine_driver_rc_v219 as driver_rc
import mixed_access_cell_views_v237 as mixed

ROOT=layout.ROOT
sha=driver_rc.sha
VERSION='isolated-fine-stage-mixed-metal-canonical-physical-views-v236.1'
CONTEXT='isolated_fine_cell_views_v236'
DRIVERS=ROOT/'build/diagnostics/discharge_fine_driver_rc_v219/7a09244f3f729a64'
BUFFER=ROOT/'build/diagnostics/clock_cell_shunts_physical_v2/5b3cb85905697901/openlvds_buf_8_o4_shunted_v2'


reference=common.reference
normalize=mixed.normalize
audit=common.audit
native=common.native


def sources():
    m=driver_rc.bound(DRIVERS);di=m['identity'];r=json.loads((DRIVERS/'summary.json').read_text())
    if (json.loads((DRIVERS/'state.json').read_text())!=dict(status='complete',passed=True,qualified_phy=False)
        or r.get('balanced_driver_local_rc_qualified') is not True
        or any(sha(DRIVERS/n)!=h for n,h in r['files'].items())
        or any(sha(ROOT/n)!=h for n,h in r['extracted_files'].items())):
        raise ValueError('Require unchanged qualified driver RC')
    parent=ROOT/di['parent'];pr=json.loads((parent/'summary.json').read_text())
    driver_rc.require_physical(json.loads((parent/'state.json').read_text()),pr)
    paths=[DRIVERS/n for n in ('manifest.json','summary.json','state.json',*r['files'])]
    paths += [ROOT/n for n in {*di['inputs'],*r['extracted_files']}]
    specs={}
    rows=[(parent/row['macro'],row,4.,37 if row['spec']['p_fingers']==20 else 41) for row in pr['rows']]
    br=json.loads((BUFFER/'summary.json').read_text())
    if not br['passed'] or br['drc_count']!='0' or not br['lvs_passed']:
        raise ValueError('Require passing native BUF8 geometry')
    if sha(BUFFER/(br['macro']+'.gds'))!=br['gds_sha256'] or sha(BUFFER/(br['macro']+'.lef'))!=br['lef_sha256']:
        raise ValueError('Native BUF8 physical views changed')
    rows.append((BUFFER,br,20.,24))
    for folder,row,area,count in rows:
        source=row['macro'];target=source.replace('_v218','_registered_v236').replace('_shunted_v2','_registered_v236')
        order=['A','Y' if 'p_fingers' in row.get('spec',{}) else 'X','VPWR','VGND']
        specs[target]=dict(source_top=source,gds=str(folder/(source+'.gds')),lef=str(folder/(source+'.lef')),
            schematic=str(folder/(source+'.sch.spice')),native_reference=str(folder/(source+'.lvs.spice')),
            aliases={p:p for p in order},order=order,
            directions={p:'input' if p=='A' else 'output' if p in ('X','Y') else 'inout' for p in order},
            access_layers={p:row['ports'][p]['layer'].replace('metal','met') for p in order},
            mim_area_um2=area,native_primitives=count)
        paths += [folder/'summary.json',*[Path(specs[target][k]) for k in ('gds','lef','schematic','native_reference')]]
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
