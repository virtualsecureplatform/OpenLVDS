# SPDX-License-Identifier: GPL-3.0-only
"""Five-cell tapped rows for native output-buffer RC characterization."""
import bank_floorplan_v49 as floor
from build_compound_drivers_v3 import cell_definition

MODELS=dict(buf1=floor.SC+'buf_1',buf4=floor.SC+'buf_4')


def design(profile,records):
    if profile not in MODELS:raise ValueError('Unknown tapped output cell')
    model=MODELS[profile];name='openlvds_tapped_output_'+profile+'_v72'
    pins=dict(A='IN',X='OUT',VGND='VGND',VNB='VGND',VPB='VPWR',VPWR='VPWR')
    cell=dict(name='u_output',native_name='Xoutput',model=model,pins=pins)
    graph=dict(top=name,ports=['IN','OUT','VPWR','VGND'],cells=[cell],orders={model:['A','VGND','VNB','VPB','VPWR','X']})
    rows=[('p_fill_l',floor.FILL),('p_tap_l',floor.TAP),('u_output',model),('p_tap_r',floor.TAP),('p_fill_r',floor.FILL)]
    cells=[];places={};x0=4*floor.SITE;y=2*floor.ROW;x=x0
    for tag,master in rows:
        c=cell if tag=='u_output' else dict(name=tag,model=master,pins={p:'VGND' if p in ('VGND','VNB') else 'VPWR' for p in records[master]['pins']},role='physical_support')
        cells.append(c);places[tag]=[floor.q(x),y];x+=records[master]['size_um'][0]
    group=dict(name='output',origin_um=[x0,y],cells=[tag for tag,_ in rows],width_um=floor.q(x-x0))
    die=[0.,0.,floor.upward(x+4*floor.SITE,floor.SITE),4*floor.ROW]
    ports={};dx,dy=places['u_output']
    for public,pin in (('IN','A'),('OUT','X'),('VPWR','VPWR'),('VGND','VGND')):
        shapes=[(layer,rect) for layer,rect in records[model]['pins'][pin]['shapes'] if layer in ('li1','met1')]
        if not shapes:raise ValueError('Native output cell has no real signal/supply pin')
        layer,rect=shapes[0];ports[public]=dict(layer=layer,rect=[floor.q(v+(dx if k%2==0 else dy)) for k,v in enumerate(rect)])
    plan=dict(cells=cells,placements=places,tapped_groups=[group],die=die,ports=ports,fixed_routes=[],qualified_phy=False)
    plan['boxes']=floor.validate(cells,places,records,die);floor.validate_groups(cells,places,records,[group])
    return graph,plan


def reference(graph,library):
    model=graph['cells'][0]['model']
    return cell_definition(library,model)+'\n.subckt '+graph['top']+' IN OUT VPWR VGND\n'+\
        'Xoutput IN VGND VGND VPWR VPWR OUT '+model+'\n.ends '+graph['top']+'\n'
