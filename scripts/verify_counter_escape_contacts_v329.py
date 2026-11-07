#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Check edge/corner contacts missed by positive-area escape overlap checks."""
import hashlib
import json
from pathlib import Path
import sys
import klayout.db as db
import plan_counter_buffer_escapes_v328 as planner

ROOT=planner.ROOT
PARENT=ROOT/'build/diagnostics/counter_buffer_escape_plan_v328/34a91d9cf9e8e4ae'
VERSION='native-counter-escape-edge-and-corner-contact-verification-v329.1'
CONTEXT='counter_escape_contact_check_v329'
sha=planner.sha


def contacts(shapes):
    result=[]
    for k,a in enumerate(shapes):
        for b in shapes[k+1:]:
            if a['net']==b['net'] or a['layer']!=b['layer']:continue
            x,y=a['rect'],b['rect']
            if min(x[2],y[2])>=max(x[0],y[0])-1e-9 and min(x[3],y[3])>=max(x[1],y[1])-1e-9:
                result.append(dict(first=a,second=b))
    return result


def native_contacts(identity,proposed):
    libraries={};checks=0
    for cell in identity['cells']:
        model=cell['model'];macro=identity['macros'][model]
        if model not in libraries:
            lib=db.Layout();lib.read(str(ROOT/macro['folder']/(model+'.gds')))
            libraries[model]=(lib,lib.cell(model))
        lib,top=libraries[model];pos=identity['plan']['placements'][cell['name']]
        translate=db.Trans(round(pos['x']/lib.dbu),round(pos['y']/lib.dbu))
        for layer,number in planner.LAYERS.items():
            native=db.Region(top.begin_shapes_rec(lib.layer(*number))).merged().transformed(translate)
            for shape in proposed['buffer_shapes']:
                if shape['layer']!=layer:continue
                allowed=db.Region()
                for pin,net in cell['pins'].items():
                    port=macro['row']['ports'][pin]
                    if net!=shape['net'] or port['layer']!=layer:continue
                    x=round((pos['x']+port['x_um'])/lib.dbu);y=round((pos['y']+port['y_um'])/lib.dbu)
                    allowed+=native.interacting(db.Region(db.Box(x-1,y-1,x+1,y+1)))
                addition=db.Region(db.Box(*[round(v/lib.dbu) for v in shape['rect']]))
                if not addition.interacting(native-allowed).is_empty():
                    raise ValueError('Buffer escape contacts foreign native '+layer+' in '+cell['name']+': '+shape['kind'])
                checks+=1
    return dict(native_component_instances=len(identity['cells']),native_master_types=len(libraries),
        native_layer_contact_checks=checks,foreign_native_m4_m5_contacts_including_boundaries=0)


def run():
    m=json.loads((PARENT/'manifest.json').read_text());i=m['identity'];r=json.loads((PARENT/'summary.json').read_text())
    if (PARENT.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
            or i['version']!=planner.VERSION or r.get('escape_plan_contact_checks_passed') is not True
            or json.loads((PARENT/'state.json').read_text())!=dict(status='complete',planning_completed=True,qualified_phy=False)
            or any(sha(ROOT/n if not Path(n).is_absolute() else Path(n))!=h for n,h in i['inputs'].items())):
        raise ValueError('Require unchanged complete native escape proposal')
    identity=json.loads((ROOT/i['parent']/'manifest.json').read_text())['identity']
    if i['proposed']!=planner.routes(identity):raise ValueError('Native escape proposal does not regenerate')
    if contacts(i['proposed']['shapes']):raise ValueError('Planned different-net M4/M5 edge/corner contact')
    proof=native_contacts(identity,i['proposed'])
    inputs={**i['inputs'],str(Path(__file__).relative_to(ROOT)):sha(Path(__file__)),
        **{str((PARENT/n).relative_to(ROOT)):sha(PARENT/n) for n in ('manifest.json','summary.json','state.json')}}
    record=dict(version=VERSION,parent=str(PARENT.relative_to(ROOT)),inputs=inputs)
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(record,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False)
    (out/'manifest.json').write_text(json.dumps(dict(identity=record,qualified_phy=False),indent=2)+'\n')
    (out/'summary.json').write_text(json.dumps(dict(**proof,planned_different_net_m4_m5_contacts_including_boundaries=0,
        boundary_contact_checks_passed=True,geometry_built=False,shared_wire_rc_qualified=False,qualified_phy=False,
        scope='M4/M5 proposed rectangle contacts and native foreign polygon contacts including shared edges/corners; no minimum spacing, via, complete connectivity, DRC/LVS/RC/timing/PVT/PHY admission'),indent=2)+'\n')
    (out/'state.json').write_text('{"status":"complete","planning_completed":true,"qualified_phy":false}\n')
    return out


if __name__=='__main__':print(run(),flush=True)
