#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Bounded switched-MIM fine-bank implementation; no automatic experiments."""
from copy import deepcopy
import json
from pathlib import Path
import single_fine_driver_300 as single
import probe_mim_isolated_fine_bank_v321 as retained

SOURCE=single.SOURCE
ROOT=single.parent.ROOT
MATERIAL=ROOT/'build/diagnostics/retained_mim_fine_rc_v320/ddf3c29ce3fc44da'
MODEL='openlvds_mim_switch_2x3_v2'
OLD_UNIT='openlvds_measured_gangs_b2_v125_unit'
PORTS=['NODE','EN','ENB','VDD','VSS']
OLD_PREFIXES=tuple('XD:'+name+str(k)+':' for name in ('Xfine_unit','Xfine_copy') for k in range(31))


def qualified_cell():
    """Check retained numerical bytes; full physical proof is required by materials()."""
    report=json.loads((MATERIAL/'summary.json').read_text())
    row=next(r for r in report['rows'] if r['variant']=='2x3')
    info=row['extraction'];path=ROOT/info['netlist']
    if (row['retained_component_rc_qualified'] is not True or row['macro']!=MODEL
            or retained.sha(path)!=info['netlist_sha256']):
        raise ValueError('Qualified switched-MIM numerical source changed')
    return SOURCE.definition(path.read_text(),MODEL)


def materials():
    """Full retained geometry/native/Schur proof, before scientific capture."""
    cells,paths,identity=retained.materials(MATERIAL)
    if cells['2x3']!=qualified_cell():raise ValueError('Full MIM proof and numerical model disagree')
    return cells['2x3'],paths,identity


def gate_controls(cell):
    """Resolve the actual extracted switch gates through their resistor networks."""
    defs=SOURCE.native.definitions(cell)
    if set(defs)!={MODEL} or defs[MODEL][0]!=PORTS:
        raise ValueError('Require exact five-port MIM macro')
    graph={}
    for w in defs[MODEL][1]:
        if w[0][0].upper()=='R':
            graph.setdefault(w[1],set()).add(w[2]);graph.setdefault(w[2],set()).add(w[1])
    def reachable(start):
        seen={start};todo=[start]
        while todo:
            for node in graph.get(todo.pop(),()):
                if node not in seen:seen.add(node);todo.append(node)
        return seen
    networks={n:reachable(n) for n in ('EN','ENB')}
    if networks['EN']&networks['ENB']:raise ValueError('Programming controls shorted in extracted RC')
    devices=SOURCE.native.mapped_mos(cell,MODEL,{p:p for p in PORTS},'UNIT')
    controls={}
    for d in devices:
        gate=d['terminals'][1].removeprefix('UNIT:')
        matches=[n for n,nodes in networks.items() if gate in nodes]
        if len(matches)!=1:raise ValueError('Unresolved native programming gate')
        controls[d['name'].removeprefix('UNIT:')]=matches[0]
    if controls!={'X0':'ENB','X3':'EN','X4':'ENB'}:
        raise ValueError('Unexpected native three-switch MIM controls')
    return controls


def transform(original,observations,cell,*,copies=4,driver='p40'):
    if copies not in (2,4,8) or driver not in ('p40','p80'):
        raise ValueError('Only approved two/four/eight copies and single/two-parallel P40 drivers')
    if cell!=qualified_cell():raise ValueError('Require verbatim qualified 2x3 switched-MIM RC')
    controls=gate_controls(cell)
    if driver=='p40':
        text,previous=single.transform(original,observations);old_top=single.TOP
    else:
        text=original;previous=deepcopy(observations);old_top=single.parent.TOP
    defs=SOURCE.native.definitions(text);ports,body=defs[old_top]
    if (len(previous['devices'])!=(2070 if driver=='p40' else 2126)
            or len(previous['controls'])!=86 or len(previous['programming_gates'])!=266
            or (MODEL in defs and SOURCE.definition(text,MODEL)!=cell)):
        raise ValueError('Require exact original full bank and observation inventory')
    expected={name+str(k):[name+str(k),'fine_node',f'fine{k}',f'fine_b{k}','VPWR','VGND',OLD_UNIT]
              for name in ('Xfine_unit','Xfine_copy') for k in range(31)}
    if ({w[0]:w for w in body if w[0] in expected}!=expected
            or sum(w[0] in expected for w in body)!=62
            or any(w[-1]==OLD_UNIT and w[0] not in expected for w in body)):
        raise ValueError('Original two-copy MOSCAP fine wiring changed')
    top=f'openlvds_mim_fine_300_{driver}_c{copies}'
    calls=[[f'Xfine_mim{k}_c{j}','fine_node',f'fine{k}',f'fine_b{k}','VPWR','VGND',MODEL]
           for k in range(31) for j in range(copies)]
    keep=[w for w in body if w[0] not in expected]
    replacement='\n'.join(['.subckt '+top+' '+' '.join(ports),
                            *[' '.join(w) for w in keep+calls],'.ends '+top,''])
    result=text.replace(SOURCE.definition(text,old_top),replacement,1)+('' if MODEL in defs else '\n'+cell)
    if any(SOURCE.definition(result,n)!=SOURCE.definition(text,n) for n in defs if n!=old_top):
        raise ValueError('Unrelated qualified native definition changed')
    pins={p:'0' if p=='VGND' else 'VDD' if p=='VPWR' else p for p in ports}
    devices=SOURCE.native.mapped_mos(result,top,pins,'XD')
    before={d['name']:d for d in previous['devices']};after={d['name']:d for d in devices}
    unchanged={n:d for n,d in before.items() if not n.startswith(OLD_PREFIXES)}
    expected_mos=(1760 if driver=='p40' else 1816)+31*copies*3
    expected_mims=(76 if driver=='p40' else 77)+31*copies*2
    if (len(after)!=len(devices) or len(after)!=expected_mos
            or len(before)-len(unchanged)!=310 or any(after.get(n)!=d for n,d in unchanged.items())
            or any(n.startswith(OLD_PREFIXES) for n in after)):
        raise ValueError('Non-fine native terminals or fine census changed')
    old_gates=[g for g in previous['programming_gates'] if g['device'].startswith(OLD_PREFIXES)]
    if (len(old_gates)!=186 or len({g['device'] for g in old_gates})!=186
            or {g['device'] for g in old_gates}!={prefix+leaf for prefix in OLD_PREFIXES for leaf in ('X0','X4','X5')}):
        raise ValueError('Original fine programming-gate coverage changed')
    gates=deepcopy([g for g in previous['programming_gates'] if not g['device'].startswith(OLD_PREFIXES)])
    if len(gates)!=80 or any(after[g['device']]['terminals'][1]!=g['gate_node'] for g in gates):
        raise ValueError('Non-fine programming-gate map changed')
    for k in range(31):
        for j in range(copies):
            prefix=f'XD:Xfine_mim{k}_c{j}'
            unit=SOURCE.native.mapped_mos(cell,MODEL,
                dict(NODE='XD:fine_node',EN=f'XD:fine{k}',ENB=f'XD:fine_b{k}',VDD='VDD',VSS='0'),prefix)
            if any(after.get(d['name'])!=d for d in unit):
                raise ValueError('Actual fine native terminals differ from qualified unit expansion')
            for d in unit:
                leaf=d['name'].removeprefix(prefix+':');control=controls[leaf]
                gates.append(dict(device=d['name'],gate_node=d['terminals'][1],
                                  control=f'fine{k}' if control=='EN' else f'fine_b{k}',kind='fine'))
    if len(gates)!=80+31*copies*3 or len({g['device'] for g in gates})!=len(gates):
        raise ValueError('Incomplete or duplicate actual programming-gate observations')
    _,leaves=SOURCE.inventory.native_leaves(SOURCE.collapse(result),top)
    if (sum('fet_' in d['model'] for d in leaves)!=expected_mos
            or sum('cap_mim' in d['model'] for d in leaves)!=expected_mims):
        raise ValueError('Actual reachable native MOS/MIM census changed')
    return result,dict(devices=devices,controls=deepcopy(previous['controls']),programming_gates=gates),dict(
        macro_top=top,copies_per_enable=copies,driver=driver,native_mos=expected_mos,native_mims=expected_mims,
        controls=86,programming_gates=len(gates),whole_bank_rc_qualified=False,qualified_phy=False)


VERSION='bounded-qualified-switched-mim-bank-materials-300-v1'
CONTEXT='mim_fine_bank_materials_300_v1'
PARENT=ROOT/'build/diagnostics/pullup_restored_bank_v360/8dba212d4f9eafd5'


def variants():
    return [(f'{driver}_c{copies}',driver,copies) for driver in ('p40','p80') for copies in (2,4,8)]


def prepare():
    import hashlib,sys
    import clocking_profile_300 as policy
    policy.load();parent=single.parent.bound(PARENT,full=False)
    cell,paths,material_identity=materials()
    paths += [PARENT/'manifest.json',PARENT/'bank.spice',ROOT/'clocking_300mhz.json']
    paths += sorted({Path(m.__file__).resolve() for m in list(sys.modules.values())
                     if getattr(m,'__file__',None) and Path(m.__file__).resolve().parent==ROOT/'scripts'})
    i=parent['identity']
    inputs={**i['guards'],**i['pdk_files'],**i['external_files'],**material_identity['external_files'],
            **{str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path):retained.sha(path)
               for path in paths}}
    identity=dict(version=VERSION,parent=str(PARENT.relative_to(ROOT)),material=str(MATERIAL.relative_to(ROOT)),
                  inputs=inputs,variants=variants(),scope='Circuit materials only; no timing, routed-bank RC, PVT or PHY qualification')
    # JSON round trip makes tuple/list representation identical on reload.
    identity=json.loads(json.dumps(identity))
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);records={}
    original=(PARENT/'bank.spice').read_text()
    for name,driver,copies in variants():
        text,obs,revision=transform(original,i['observations'],cell,copies=copies,driver=driver)
        folder=out/name;folder.mkdir();(folder/'bank.spice').write_text(text)
        single.parent.atomic(folder/'observations.json',obs)
        records[name]=dict(revision=revision,files={n:retained.sha(folder/n) for n in ('bank.spice','observations.json')})
    single.parent.atomic(out/'manifest.json',dict(identity=identity,variants=records,qualified_phy=False))
    bound(out)
    single.parent.atomic(out/'state.json',dict(status='prepared_unqualified',simulations=0,qualified_phy=False))
    return out


def bound(out):
    import hashlib
    manifest=json.loads((out/'manifest.json').read_text());identity=manifest['identity']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or identity['version']!=VERSION
            or out.name!=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
            or identity['parent']!=str(PARENT.relative_to(ROOT)) or identity['material']!=str(MATERIAL.relative_to(ROOT))
            or identity['variants']!=json.loads(json.dumps(variants())) or manifest['qualified_phy'] is not False
            or set(manifest['variants'])!={v[0] for v in variants()}):
        raise ValueError('Switched-MIM circuit-material identity changed')
    for name,digest in identity['inputs'].items():
        if retained.sha(ROOT/name)!=digest:raise ValueError('Captured circuit-material input changed: '+name)
    cell=qualified_cell();original=(PARENT/'bank.spice').read_text()
    observations=json.loads((PARENT/'manifest.json').read_text())['identity']['observations']
    for name,driver,copies in variants():
        text,obs,revision=transform(original,observations,cell,copies=copies,driver=driver)
        folder=out/name;record=manifest['variants'][name]
        if (record['revision']!=revision or set(record['files'])!={'bank.spice','observations.json'}
                or any(retained.sha(folder/n)!=digest for n,digest in record['files'].items())
                or (folder/'bank.spice').read_text()!=text or json.loads((folder/'observations.json').read_text())!=obs):
            raise ValueError('Actual native circuit, programming gates or inventory changed')
    return manifest


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('prepare','check'));parser.add_argument('artifact',type=Path,nargs='?')
    args=parser.parse_args()
    if args.action=='prepare':print(prepare(),flush=True)
    else:
        if args.artifact is None:parser.error('Supply a captured circuit-material directory')
        bound(args.artifact.resolve());print('Captured native circuit materials verified; no electrical admission',flush=True)
