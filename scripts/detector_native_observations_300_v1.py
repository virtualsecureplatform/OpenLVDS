# SPDX-License-Identifier: GPL-3.0-only
"""Observe every actual MOS terminal in the unchanged detector source assembly."""
import native_clock_components_v2 as native

LIBRARIES=('cells.spice','frontend.spice','bias.spice','arbiter.spice','threshold.spice')


def devices(parent,deck):
    calls=[line.split() for line in deck.splitlines() if line.startswith('X')]
    if {w[0] for w in calls}!={'XB','XF','XT','XD'} or len(calls)!=4:
        raise ValueError('Detector active top-level hierarchy changed')
    expected={'XB':'lvds_bias','XF':'lvds_slew_analog_pair_v2t','XT':'phase_threshold_pair','XD':'tag_arbiter'}
    if any(w[-1]!=expected[w[0]] for w in calls):
        raise ValueError('Detector active top-level models changed')
    library='\n'.join((parent/n).read_text() for n in LIBRARIES)
    definitions=native.definitions(library)
    if any(w[-1] not in definitions for w in calls):raise ValueError('Missing detector source model')
    ports=sorted({n for w in calls for n in w[1:-1] if n!='0'})
    top='detector_source_observation_300_v1'
    text=library+'\n.subckt '+top+' '+' '.join(ports)+'\n'+'\n'.join(' '.join(w) for w in calls)+'\n.ends '+top+'\n'
    defs=native.definitions(text);result=[]
    def walk(model,pins,path,ancestors):
        if model in ancestors:raise ValueError('Recursive detector hierarchy')
        order,body=defs[model]
        if set(order)!=set(pins):raise ValueError('Detector native port mismatch')
        def net(n):return '0' if n=='0' else pins.get(n,path+':'+n)
        for w in body:
            if w[0][0].upper() in ('R','C'):continue
            if w[0][0].upper()!='X':raise ValueError('Unexpected detector active element')
            stop=next((k for k,v in enumerate(w) if '=' in v),len(w))
            child=w[stop-1];nodes=[net(n) for n in w[1:stop-1]];name=path+':'+w[0]
            if child in defs:
                if len(nodes)!=len(defs[child][0]):raise ValueError('Detector child pin mismatch')
                walk(child,dict(zip(defs[child][0],nodes)),name,ancestors|{model})
            elif child=='sky130_fd_pr__cap_mim_m3_1' and len(nodes)==2:continue
            elif child=='sky130_fd_pr__res_high_po_0p35' and len(nodes)==3:continue
            elif child.startswith('sky130_fd_pr__') and ('nfet_' in child or 'pfet_' in child) and len(nodes)==4:
                if '01v8' in child:limit=1.95
                elif child in ('sky130_fd_pr__nfet_g5v0d10v5','sky130_fd_pr__pfet_g5v0d10v5'):limit=5.5
                else:raise ValueError('Unknown detector native MOS voltage domain')
                result.append(dict(name=name,model=child,limit_v=limit,terminals=nodes))
            else:raise ValueError('Unknown detector native leaf '+child)
    walk(top,{n:n for n in ports},'OBS',set())
    for d in result:
        d['name']=d['name'].removeprefix('OBS:')
        d['terminals']=[n.removeprefix('OBS:') for n in d['terminals']]
    if len({d['name'] for d in result})!=len(result) or not result:
        raise ValueError('Empty or duplicated full detector MOS inventory')
    return result
