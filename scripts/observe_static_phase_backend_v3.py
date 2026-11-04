#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Expose existing internal M5 buses for full-RC counter characterization.

Only labels/port attributes change. All masks are flattened from the clean
original GDS; five unloaded observation ports preserve original phase checks.
The original six-port backend and its immutable certificates remain intact.
"""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import layout
import build_static_phase_backend_v3 as parent_build
import restrict_macro_rails_v6 as access

ROOT=parent_build.ROOT
native=parent_build.native
sha=parent_build.sha
NAME='openlvds_static_phase_observed_v2'
VERSION='whole-static-counter-mask-preserving-observation-view-v2.2'
CONTEXT='static_phase_observed_physical_v2'
OBSERVATIONS=['low0','high1','low1','armed','request_i']
PORTS=[*parent_build.PORTS,*OBSERVATIONS]


def source(text):
    old='.subckt '+parent_build.NAME+' '+' '.join(parent_build.PORTS)
    end='.ends '+parent_build.NAME
    if text.count(old+'\n')!=1 or text.count(end+'\n')!=1:raise ValueError('Original native source interface changed')
    return text.replace(old+'\n','.subckt '+NAME+' '+' '.join(PORTS)+'\n').replace(end+'\n','.ends '+NAME+'\n')


def add_observations(text,points):
    if text.count('<< labels >>')!=1 or 'magscale 1 2\n' not in text:raise ValueError('Unsupported flattened native label/grid representation')
    start=text.index('<< labels >>');end=text.index('<<',start+len('<< labels >>'));labels=[]
    for index,name in enumerate(OBSERVATIONS,len(parent_build.PORTS)+1):
        x=round(points[name]['x_um']/layout.GRID);y=round(points[name]['y_um']/layout.GRID)
        labels += [f'rlabel metal5 {x} {y} {x} {y} 0 {name}',f'port {index} nsew']
    changed=text[:end]+'\n'.join(labels)+'\n'+text[end:]
    # The geometry is the same byte-for-byte prefix. Added labels carry no
    # physical shapes or ideal electrical paths.
    if changed[:start]!=text[:start]:raise ValueError('Observation changed native masks')
    return changed,hashlib.sha256(text[:start].encode()).hexdigest()


def prepare(parent):
    m=parent_build.bound(parent);report=json.loads((parent/'summary.json').read_text())
    if not report['passed'] or len(report['rows'])!=1:raise ValueError('Require complete clean native counter')
    row=report['rows'][0];folder=parent/parent_build.NAME
    if (row['macro']!=parent_build.NAME or row['drc_count']!='0' or not row['lvs_passed']
        or sha(folder/(parent_build.NAME+'.gds'))!=row['gds_sha256']
        or sha(folder/(parent_build.NAME+'.lef'))!=row['lef_sha256']
        or sha(folder/(parent_build.NAME+'.sch.spice'))!=row['lvs_source_sha256']):raise ValueError('Original whole-counter view changed')
    points={p:row['ports'][p] for p in parent_build.PORTS};i=m['identity']
    for name in OBSERVATIONS:
        candidates=[p for p in i['points'][name] if p['cell']=='request_driver' or (p['cell'].endswith('_q') and p['pin']=='Y')]
        if len(candidates)!=1:raise ValueError('Missing unique physical observation driver')
        points[name]=dict(layer='metal5',x_um=candidates[0]['x'],y_um=i['buses'][name],width_um=i['configuration']['bus_width_um'])
    files=[parent/n for n in ['manifest.json','summary.json','state.json']]+[folder/(parent_build.NAME+n) for n in ['.gds','.lef','.sch.spice','.lvs.log','.drc_count.txt']]
    code=[Path(__file__),Path(parent_build.__file__),Path(layout.__file__),Path(access.__file__),Path(access.geometry.__file__),ROOT/'scripts/lvs_utils.py']
    identity=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),ports=points,
        inputs={str(p.relative_to(ROOT)):sha(p) for p in files},code={str(p.relative_to(ROOT)):sha(p) for p in code},pdk_files=i['pdk_files'],tools=native.environment.tools())
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);(out/'manifest.json').write_text(json.dumps(dict(identity=identity,qualified_phy=False),indent=2)+'\n');return out


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION
        or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or any(sha(ROOT/n)!=h for n,h in {**i['inputs'],**i['code']}.items())
        or any(sha(Path(n))!=h for n,h in i['pdk_files'].items()) or native.environment.tools()!=i['tools']):raise ValueError('Counter observation context changed')
    parent_build.bound(ROOT/i['parent']);return m


def run(out):
    m=bound(out);i=m['identity'];parent=ROOT/i['parent'];original=parent/parent_build.NAME
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain prior observation view')
        (out/'state.json').write_text('{"status":"annotating","qualified_phy":false}\n');folder=out/NAME;folder.mkdir()
        try:
            commands=['gds readonly false',f'gds read {{{original/(parent_build.NAME+".gds")}}}',f'load {parent_build.NAME}']
            # GDS retains labels but loses Magic port numbers. Restore the six
            # original ports explicitly before flattening and adding monitors.
            for number,pin in enumerate(parent_build.PORTS,1):
                p=i['ports'][pin];x=p['x_um'];y=p['y_um']
                commands += [f'box values {x-.1:.6f}um {y-.1:.6f}um {x+.1:.6f}um {y+.1:.6f}um',f'port make {number}']
            commands += [f'flatten {NAME}',f'load {NAME}',f'save {{{folder/NAME}}}']
            layout.invoke_magic(folder,'\n'.join(commands),'flatten_original')
            path=folder/(NAME+'.mag');text,mask_sha=add_observations(path.read_text(),i['ports']);path.write_text(text)
            (folder/(NAME+'.sch.spice')).write_text(source((original/(parent_build.NAME+'.sch.spice')).read_text()))
            row=layout.qualify(folder,NAME);raw=folder/(NAME+'.raw.lef');raw.write_bytes((folder/(NAME+'.lef')).read_bytes())
            types={p:('INPUT' if p in ['CLK','REQUEST'] else 'OUTPUT','SIGNAL') for p in PORTS if p not in ['VPWR','VGND']};types.update(VPWR=('INOUT','POWER'),VGND=('INOUT','GROUND'))
            restricted,view=access.restrict(raw.read_text(),i['ports'],types);(folder/(NAME+'.lef')).write_text(restricted)
            row.update(macro=NAME,ports=i['ports'],integration_pins=view,observation_ports=OBSERVATIONS,mask_prefix_sha256_before=mask_sha,mask_prefix_sha256_after=mask_sha,
                gds_sha256=sha(folder/(NAME+'.gds')),lef_sha256=sha(folder/(NAME+'.lef')),qualified_phy=False,electrical_qualification_passed=False)
            (folder/'summary.json').write_text(json.dumps(row,indent=2)+'\n');bound(out)
            report=dict(rows=[row],passed=row['passed'],qualified_phy=False,electrical_qualification_passed=False,
                scope='Mask-preserving unloaded internal observation ports on whole native counter; fresh DRC/LVS only, no RC timing or PHY admission')
            (out/'summary.json').write_text(json.dumps(report,indent=2)+'\n');(out/'state.json').write_text(json.dumps(dict(status='physical_complete',passed=report['passed'],qualified_phy=False))+'\n');return report
        except Exception as e:
            (out/'state.json').write_text(json.dumps(dict(status='observation_exception',error=str(e),qualified_phy=False))+'\n');raise


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','campaign']);p.add_argument('artifact',type=Path);a=p.parse_args();out=a.artifact.resolve()
    if a.action in ['prepare','campaign']:out=prepare(out);print(out,flush=True)
    if a.action in ['run','campaign']:print(json.dumps(run(out),indent=2),flush=True)
