# SPDX-License-Identifier: GPL-3.0-only
"""Render the exact bank for the physical flow and place all standard controls."""
import math

SC='sky130_fd_sc_hd__'
POWER=dict(VPWR='VPWR',VPB='VPWR',VGND='VGND',VNB='VGND')


def parse(text,orders):
    cells=[];ports=None;top=None;seen=set()
    for line in text.splitlines():
        w=line.split()
        if not w or w[0].startswith('*'):continue
        if w[0].lower()=='.subckt':
            if ports is not None:raise ValueError('Require one complete bank source')
            top=w[1];ports=w[2:]
        elif w[0].lower()=='.ends':continue
        elif w[0].startswith('X'):
            name=w[0][1:];model=w[-1]
            if name in seen or model not in orders or len(w[1:-1])!=len(orders[model]):raise ValueError('Physical-flow source instance changed')
            seen.add(name);cells.append(dict(name=name,model=model,pins=dict(zip(orders[model],w[1:-1]))))
        else:raise ValueError('Unsupported physical-flow source statement')
    if ports is None or len(cells)!=94 or len(ports)!=24:raise ValueError('Require all 94 bank instances and 24 ports')
    return dict(top=top,ports=ports,cells=cells)


def verilog(spec):
    inputs=[p for p in spec['ports'] if p not in ['OUT','VPWR','VGND']]
    nets=sorted({n for c in spec['cells'] for n in c['pins'].values()}-set(spec['ports']))
    rows=['// SPDX-License-Identifier: GPL-3.0-only','// Unqualified physical-flow view; standard body/power pins connect through the bound global-power rules.',
          '`default_nettype none',f'module {spec["top"]}(input wire '+','.join(inputs)+', output wire OUT, inout wire VPWR,VGND);','wire '+','.join(nets)+';']
    for c in spec['cells']:
        pins=dict(c['pins'])
        if c['model'].startswith(SC):
            if c['model'] not in [SC+'buf_4',SC+'conb_1'] or any(pins.get(p)!=n for p,n in POWER.items()):raise ValueError('Cannot hide nonstandard body/power wiring')
            pins={p:n for p,n in pins.items() if p not in POWER}
        rows.append('(* keep="true", dont_touch="true" *) '+c['model']+' '+c['name']+' ('+','.join('.'+p+'('+n+')' for p,n in pins.items())+');')
    return '\n'.join(rows+['endmodule','`default_nettype wire',''])


def blackboxes(macros,orders,pins):
    rows=['// SPDX-License-Identifier: GPL-3.0-only','`default_nettype none']
    for model in sorted(macros):
        if set(orders[model])!=set(pins[model]):raise ValueError('Macro interface differs from native source')
        declarations=[]
        for pin in orders[model]:
            direction=pins[model][pin]['direction']
            if direction not in ['INPUT','OUTPUT','INOUT']:raise ValueError('Unknown macro pin direction')
            declarations.append(direction.lower()+' wire '+pin)
        rows.append('(* blackbox *) module '+model+'('+','.join(declarations)+'); endmodule')
    return '\n'.join(rows+['`default_nettype wire',''])


def control_placements(spec,widths,macros,die):
    # The fine bank leaves a real empty strip above its fifth row and base MIM.
    fine=[(name,p,model) for model,m in macros.items() for name,p in m['instances'].items() if name.startswith('fine') or name=='shared_base']
    left=math.ceil(min(p['location'][0] for _,p,_ in fine)/.46)*.46
    bottom=max(p['location'][1]+widths[model]['height'] for _,p,model in fine)
    y=math.ceil((bottom+10.)/2.72)*2.72;x=left;right=die[2]-10.;result={}
    for c in spec['cells']:
        if not c['model'].startswith(SC):continue
        width=widths[c['model']]['width']
        if x+width>right:x=left;y+=2.72
        if x+width>right or y+2.72>die[3]-10.:raise ValueError('Native control placement strip exhausted')
        result[c['name']]=dict(location=[round(x,3),round(y,3)],orientation='N' if round(y/2.72)%2 else 'FS')
        x+=math.ceil(width/.46)*.46+.92
    if len(result)!=16:raise ValueError('Require all fifteen coarse buffers and the tie cell')
    return result


def connections_pass(rows,terms,spec):
    cells={}
    for name,model,pin,net in rows:
        c=cells.setdefault(name,dict(model=model,pins={}))
        if c['model']!=model or pin in c['pins']:return False
        c['pins'][pin]=net
    highs={c['pins'].get('HI') for c in cells.values() if c['model']==SC+'conb_1'}-{None,''}
    lows={c['pins'].get('LO') for c in cells.values() if c['model']==SC+'conb_1'}-{None,''}
    if not highs or not lows or highs&lows:return False
    names={c['name'] for c in spec['cells']}
    for c in spec['cells']:
        if c['name'] not in cells or cells[c['name']]['model']!=c['model']:return False
        for pin,net in c['pins'].items():
            actual=cells[c['name']]['pins'].get(pin)
            if net=='high':
                if actual not in highs:return False
            elif net=='low':
                if actual not in lows:return False
            elif actual!=net:return False
    for name,c in cells.items():
        if name not in names and (not c['model'].startswith(SC) or not c['model'].removeprefix(SC).startswith(('fill_','tapvpwrvgnd_','conb_','diode_'))):return False
        if name not in names and any(net!=POWER[pin] for pin,net in c['pins'].items() if pin in POWER):return False
    return set(terms)==set(spec['ports'])
