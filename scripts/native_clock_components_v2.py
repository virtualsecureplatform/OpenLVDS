# SPDX-License-Identifier: GPL-3.0-only
"""Compose clock logic from actual extracted cells and preserve every MOS node.

Component RC is real; inter-component connections remain ideal wires pending
whole-backend placement/routing/extraction. This is a diagnostic assembly only.
"""
import dcc_tg_ratio_v2 as dcc
import native_clock_release_v3 as release
import continuous_clock_conditioner_v2 as clean

MODELS={'nand2_2':'openlvds_nand2_2_shunted_v2','nand2_8':'openlvds_nand2_8_shunted_v2',
    'nand2_4':'openlvds_nand2_4_o3_shunted_v2','nand3_2':'openlvds_nand3_2_o3_shunted_v2',
    'inv_1':'openlvds_inv_1_o2_shunted_v2','inv_8':'openlvds_inv_8_o4_shunted_v2','buf_8':'openlvds_buf_8_o2_shunted_v2'}
CLOCK_BUFFER='openlvds_buf_8_o4_shunted_v2'


def instance(tag,model,pins,rc):
    if model not in rc:raise ValueError('Missing extracted clock macro '+model)
    ports=rc[model]['info']['ports']
    if set(ports)!=set(pins):raise ValueError('Extracted component pin mismatch: '+model)
    return 'X'+tag+' '+' '.join(pins[n] for n in ports)+' '+model


def logic(name,ports,cells,rc):
    rows=['.subckt '+name+' '+' '.join(ports)]
    for tag,short,pins in cells:
        rows.append(instance(tag,MODELS[short],dict(VPWR='VPWR',VGND='VGND',**pins),rc))
    return '\n'.join(rows+['.ends '+name,''])


def compose(rc):
    result={}
    result['release.spice']=logic(release.NAME,release.PORTS,release.gates(),rc)
    rows=['.subckt '+clean.NAME+' '+' '.join(clean.PORTS)]
    for suffix in ['0','180']:
        rows += [instance('clean'+suffix,CLOCK_BUFFER,dict(A='F'+suffix,X='P'+suffix,VPWR='VPWR',VGND='VGND'),rc),
            instance('monitor'+suffix,CLOCK_BUFFER,dict(A='P'+suffix,X='MON'+suffix,VPWR='VPWR',VGND='VGND'),rc)]
    result['clean.spice']='\n'.join(rows+['.ends '+clean.NAME,''])
    for variant in ['p3','p4']:
        cells=[c for c in dcc.storage.gates(2) if not c[0].startswith('xor_')]
        cells += [('isolate_'+n,'buf_8',dict(A=n,X=n+'_iso')) for n in ['a','a_qb','b','b_qb']]
        text=logic(dcc.NAME,dcc.PORTS,cells,rc);rows=text.splitlines()[:-1]
        rows.append(instance('xor','openlvds_tg_xor_'+variant+'_v2',dict(a_iso='a_iso',a_qb_iso='a_qb_iso',b_iso='b_iso',b_qb_iso='b_qb_iso',xor_out='xor_out',VDDD='VPWR',VSS='VGND'),rc))
        result[variant+'.spice']='\n'.join(rows+['.ends '+dcc.NAME,''])
    result['cells.spice']='\n'.join(rc[n]['text'].rstrip() for n in sorted(rc))+'\n'
    return result


def definitions(text):
    logical=[]
    for line in text.splitlines():
        if line.startswith('+'):
            if not logical:raise ValueError('Orphan native SPICE continuation')
            logical[-1]+=' '+line[1:]
        else:logical.append(line)
    result={};current=None
    for line in logical:
        w=line.split()
        if not w or w[0].startswith('*'):continue
        if w[0].lower()=='.subckt':
            if current is not None or w[1] in result:raise ValueError('Nested/duplicate native definition')
            current=w[1];result[current]=(w[2:],[])
        elif w[0].lower()=='.ends':current=None
        elif current is not None:result[current][1].append(w)
        else:raise ValueError('Unexpected native library statement')
    if current is not None:raise ValueError('Unterminated native definition')
    return result


def mapped_mos(text,top,mapping,prefix):
    """Recursively save true R/C-separated body/drain/source/gate terminals."""
    defs=definitions(text);result=[]
    def walk(model,pins,path,ancestors):
        if model in ancestors:raise ValueError('Recursive native clock hierarchy')
        ports,body=defs[model]
        if set(pins)!=set(ports):raise ValueError('Native hierarchy interface mismatch')
        def net(n):return '0' if n=='0' else pins.get(n,path+':'+n)
        for w in body:
            if w[0][0].upper() in ['R','C']:continue
            if w[0][0].upper()!='X':raise ValueError('Non-native active clock element')
            first=next((i for i,v in enumerate(w) if '=' in v),len(w));child=w[first-1];nodes=[net(n) for n in w[1:first-1]];name=path+':'+w[0]
            if child in defs:
                if len(nodes)!=len(defs[child][0]):raise ValueError('Native child pin count changed')
                walk(child,dict(zip(defs[child][0],nodes)),name,ancestors|{model})
            elif child=='sky130_fd_pr__cap_mim_m3_1':
                if len(nodes)!=2:raise ValueError('Native MIM port count changed')
            elif child.startswith('sky130_fd_pr__') and ('nfet_' in child or 'pfet_' in child) and len(nodes)==4:
                if '01v8' in child:limit=1.95
                elif child in ['sky130_fd_pr__pfet_g5v0d10v5','sky130_fd_pr__nfet_g5v0d10v5']:limit=5.5
                else:raise ValueError('Unknown native MOS voltage domain')
                result.append(dict(name=name,model=child,limit_v=limit,terminals=nodes))
            else:raise ValueError('Unknown native clock leaf '+child)
    walk(top,mapping,prefix,set());return result
