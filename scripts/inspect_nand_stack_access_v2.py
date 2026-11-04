#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Inspect actual native NAND diffusion access before adding physical shunts.

No contacts or masks are changed. Preserve native MAG/EXT/SPICE and local mask
rectangles around each schematic stack coordinate. This is not an LVS or RC
certificate and must not be used as one.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import layout
import inspect_mim_switch_pcells_v2 as environment
from build_compound_drivers_v3 import cell_definition

ROOT=layout.ROOT
VERSION='native-nand-stack-mask-access-inspection-v2.1'
sha=environment.sha


def private_nodes(text):
    lines=text.splitlines();ports=lines[0].split()[2:];nodes=set()
    for line in lines[1:-1]:
        w=line.split()
        if not w or w[0].startswith('*'):continue
        if not w[0].startswith('X') or len(w)<6 or not w[5].startswith('sky130_fd_pr__'):
            raise ValueError('Unexpected native NAND transistor')
        nodes.update(w[1:5])
    result=sorted(nodes-set(ports))
    if not result or any(re.fullmatch(r'a_\d+_\d+#',n) is None for n in result):
        raise ValueError('Unexpected native NAND private-node naming')
    return result


def local_rectangles(text,x,y,radius=1.):
    layer=None;result=[]
    for line in text.splitlines():
        if line.startswith('<< '):layer=line[3:-3]
        if line.startswith('rect '):
            r=[int(v)*layout.GRID for v in line.split()[1:]]
            if len(r)!=4:raise ValueError('Invalid native MAG rectangle')
            if r[0]<=x+radius and r[2]>=x-radius and r[1]<=y+radius and r[3]>=y-radius:
                result.append(dict(layer=layer,rectangle_um=r,contains_source_coordinate=r[0]<=x<=r[2] and r[1]<=y<=r[3]))
    return result


def inspect():
    pdk=Path(os.environ['PDK_ROOT'])/'sky130A';sc=pdk/'libs.ref/sky130_fd_sc_hd'
    files=[sc/'gds/sky130_fd_sc_hd.gds',sc/'spice/sky130_fd_sc_hd.spice',pdk/'libs.tech/magic/sky130A.magicrc']
    identity=dict(version=VERSION,pdk_files={str(p):sha(p) for p in files},tools=environment.tools(),
        code={str(p.relative_to(ROOT)):sha(p) for p in [Path(__file__),Path(layout.__file__),Path(environment.__file__),ROOT/'scripts/build_compound_drivers_v3.py']})
    out=ROOT/'build/diagnostics/nand_stack_native_inspection_v2'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);(out/'manifest.json').write_text(json.dumps(identity,indent=2)+'\n');rows=[]
    library=files[1].read_text()
    for short in ['nand2_1','nand2_2','nand2_8']:
        name='sky130_fd_sc_hd__'+short;folder=out/short;folder.mkdir();source=cell_definition(library,name)
        (folder/'native_source.spice').write_text(source)
        layout.invoke_magic(folder,f'''gds readonly false
gds read {{{files[0]}}}
load {name} -silent
save {{{folder/name}}}
extract all
ext2spice lvs
ext2spice -o native_geometry.spice {name}.ext
''','native_geometry')
        mag=(folder/(name+'.mag')).read_text();points=[]
        for node in private_nodes(source):
            a,b=re.fullmatch(r'a_(\d+)_(\d+)#',node).groups();x,y=int(a)*layout.GRID,int(b)*layout.GRID
            points.append(dict(source_node=node,source_coordinate_um=[x,y],nearby_native_masks=local_rectangles(mag,x,y)))
        rows.append(dict(model=name,points=points,mag_sha256=sha(folder/(name+'.mag')),
            source_sha256=sha(folder/'native_source.spice'),extracted_spice_sha256=sha(folder/'native_geometry.spice')))
    if any(sha(Path(n))!=h for n,h in identity['pdk_files'].items()):raise ValueError('Native PDK inputs changed during inspection')
    (out/'summary.json').write_text(json.dumps(dict(identity=identity,rows=rows,qualified_phy=False,
        scope='Native source naming and mask access inspection only; no mask modification, DRC/LVS, RC or timing admission'),indent=2)+'\n')
    return out


if __name__=='__main__':print(inspect(),flush=True)
