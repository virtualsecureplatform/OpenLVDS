# SPDX-License-Identifier: GPL-3.0-only
"""Local output-only bank revision; four coarse regenerators retain their guards."""
from collections import Counter
import re
import native_bank_inventory_v51 as inventory
from build_compound_drivers_v3 import cell_definition

TOP='openlvds_balanced_b2_physical_v126'
NEW_TOP='openlvds_balanced_b2_unguarded_v164'
PAIR='openlvds_parallel_inv8_registered_v114'
NEW_PAIR='openlvds_parallel_inv8_output_v164'
INV='ov114_ffe77b9d_187cefec'
NEW_INV='openlvds_output_inv8_v164'
CAP='ov114_ffe77b9d_e19a9ccd'
SCHEM_INV='openlvds_inv_8_nlvt_o2_v34'
NEW_SCHEM_INV='openlvds_output_inv8_native_v164'


def schematic(text):
    inv=cell_definition(text,SCHEM_INV)
    lines=inv.splitlines(keepends=True);caps=[n for n,l in enumerate(lines) if 'sky130_fd_pr__cap_mim_m3_1' in l]
    if len(caps)!=1 or lines[caps[0]].split()[1:]!=['Y','VGND','sky130_fd_pr__cap_mim_m3_1','l=2','w=2']:
        raise ValueError('Require exactly one native 2x2 output guard per INV8')
    del lines[caps[0]]
    new_inv=re.sub(r'\b'+SCHEM_INV+r'\b',NEW_SCHEM_INV,''.join(lines))
    pair=cell_definition(text,PAIR)
    new_pair=re.sub(r'\b'+PAIR+r'\b',NEW_PAIR,pair)
    new_pair=re.sub(r'\b'+SCHEM_INV+r'\b',NEW_SCHEM_INV,new_pair)
    rows=re.findall(r'(?m)^Xfine_compound [^\n]+$',text)
    if len(rows)!=1 or rows[0].split()!=['Xfine_compound','selected','OUT','VPWR','VGND',PAIR]:
        raise ValueError('Require exactly the final output instance')
    result=text.replace(rows[0],rows[0][:-len(PAIR)]+NEW_PAIR,1)
    result=re.sub(r'\b'+TOP+r'\b',NEW_TOP,result)+'\n'+new_inv+'\n'+new_pair+'\n'
    before_ports,before=inventory.native_leaves(text,TOP);after_ports,after=inventory.native_leaves(result,NEW_TOP)
    removed=[d for d in before if d['model']=='sky130_fd_pr__cap_mim_m3_1' and d['name'].startswith('native__Xfine_compound__')]
    if len(removed)!=2 or [d for d in before if d not in removed]!=after or before_ports!=after_ports:
        raise ValueError('Bank revision changed another native device, net, parameter or port')
    def census(devices):return Counter(d['model'] for d in devices)
    a=census(before);b=census(after)
    if sum(n for m,n in a.items() if 'fet_' in m)!=1453 or a['sky130_fd_pr__cap_mim_m3_1']!=42 or b['sky130_fd_pr__cap_mim_m3_1']!=40:
        raise ValueError('Require exact 1453-MOS, 42-to-40 MIM bank revision')
    return result,dict(native_mos=1453,native_mims=40,removed_output_guards=[d['name'] for d in removed],
                       all_other_native_devices_nets_parameters_and_ports_identical=True,qualified_phy=False)


def geometry(source,target,position):
    import klayout.db as db
    lib=db.Layout();lib.read(str(source));top=lib.cell(TOP);old=lib.cell(PAIR);inv=lib.cell(INV)
    if top is None or old is None or inv is None or lib.cell(CAP) is None or lib.dbu!=.001:
        raise ValueError('Require original registered bank hierarchy')
    for name in (NEW_TOP,NEW_PAIR,NEW_INV):
        if lib.cell(name) is not None:raise ValueError('Candidate cell name already exists')
    new_inv=lib.create_cell(NEW_INV);new_inv.copy_shapes(inv)
    removed=0
    for i in inv.each_inst():
        if lib.cell(i.cell_index).name==CAP:removed+=1
        else:new_inv.insert(i.cell_inst)
    if removed!=1:raise ValueError('Require one registered output guard placement')
    new_pair=lib.create_cell(NEW_PAIR);new_pair.copy_shapes(old);count=0
    for i in old.each_inst():
        if lib.cell(i.cell_index).name!=INV:raise ValueError('Unexpected output component child')
        clone=new_pair.insert(i.cell_inst);clone.cell_index=new_inv.cell_index();count+=1
    if count!=2:raise ValueError('Require two original INV8 placements')
    wanted=tuple(round(v/lib.dbu) for v in position);pairs=[i for i in top.each_inst() if lib.cell(i.cell_index).name==PAIR]
    selected=[i for i in pairs if (i.trans.disp.x,i.trans.disp.y)==wanted]
    if len(pairs)!=5 or len(selected)!=1:raise ValueError('Require final output plus four coarse regenerators')
    selected[0].cell_index=new_pair.cell_index();top.name=NEW_TOP;lib.write(str(target))
    return mask_check(source,target,position)


def mask_check(source,target,position):
    import klayout.db as db
    a=db.Layout();a.read(str(source));b=db.Layout();b.read(str(target));wanted=tuple(round(v/a.dbu) for v in position)
    if a.dbu!=.001 or b.dbu!=a.dbu:raise ValueError('Bank mask scale changed')
    expected={NEW_TOP if c.name==TOP else c.name for c in a.each_cell()}|{NEW_PAIR,NEW_INV}
    if {c.name for c in b.each_cell()}!=expected:raise ValueError('Unexpected bank hierarchy change')
    layers={(x.get_info(i).layer,x.get_info(i).datatype) for x in (a,b) for i in x.layer_indexes()}
    def region(lib,c,layer):
        n=lib.find_layer(*layer)
        return db.Region() if n is None else db.Region(c.shapes(n)).merged()
    def shape_match(x,y):
        for layer in layers:
            if not (region(a,x,layer)^region(b,y,layer)).is_empty():raise ValueError('Original root/MOS/body/wire masks changed')
    def placements(lib,c,transform=lambda n,i:n):
        return Counter((transform(lib.cell(i.cell_index).name,i),i.cplx_trans.to_s(),i.a.x,i.a.y,i.b.x,i.b.y,i.na,i.nb) for i in c.each_inst())
    for old in a.each_cell():
        new=b.cell(NEW_TOP if old.name==TOP else old.name);shape_match(old,new)
        def remap(n,i):
            if old.name==TOP and n==PAIR and (i.trans.disp.x,i.trans.disp.y)==wanted:return NEW_PAIR
            return n
        if placements(a,old,remap)!=placements(b,new):raise ValueError('Original bank placement or non-output instance changed')
    shape_match(a.cell(INV),b.cell(NEW_INV));shape_match(a.cell(PAIR),b.cell(NEW_PAIR))
    inv_expected=placements(a,a.cell(INV));inv_expected=Counter({k:v for k,v in inv_expected.items() if k[0]!=CAP})
    if inv_expected!=placements(b,b.cell(NEW_INV)) or placements(a,a.cell(PAIR),lambda n,i:NEW_INV if n==INV else n)!=placements(b,b.cell(NEW_PAIR)):
        raise ValueError('Output-only cloned hierarchy differs beyond guard removal')
    return dict(all_original_cell_masks_identical=True,all_original_placements_identical_except_final_output_model=True,
                native_output_mim_placements_removed=2,four_coarse_regenerators_unchanged=True,
                all_routed_wire_masks_identical=True,qualified_phy=False)


def component_match(bank,component):
    import klayout.db as db
    a=db.Layout();a.read(str(bank));b=db.Layout();b.read(str(component))
    ac=a.cell(NEW_PAIR);bc=b.cell('openlvds_parallel_inv8_unguarded_v162')
    if a.dbu!=.001 or b.dbu!=a.dbu or ac is None or bc is None:raise ValueError('Replacement component top or scale changed')
    layers={(x.get_info(i).layer,x.get_info(i).datatype) for x in (a,b) for i in x.layer_indexes()}
    for layer in layers:
        def region(lib,c):
            n=lib.find_layer(*layer)
            return db.Region() if n is None else db.Region(c.begin_shapes_rec(n)).merged()
        if not (region(a,ac)^region(b,bc).transformed(db.Trans(-2000,-2000))).is_empty():
            raise ValueError('Registered output differs from qualified component under original -2um translation')
    return dict(qualified_unguarded_component_masks_match_under_translation=True,translation_um=[-2,-2],qualified_phy=False)
