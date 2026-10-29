# SPDX-License-Identifier: GPL-3.0-only
"""Generate isolated pulse-area DLL candidates without changing the active design."""
from pathlib import Path
from layout import circuits,flatten,schematic_text
from screen_dll import variant_source
from spice_library import replace

ROOT=Path(__file__).resolve().parents[1]
ANALOG_PORTS='CLK PD_ENABLE PH0 PH90 PH180 PH270 FB PD_REF PHASE_BAD UP DN PB VDDIO VDDD VSS'.split()
PFD_PORTS='REF FB RESET_N PD_ENABLE UP DN VDDD VSS'.split()
CORE_PORTS='CLK RESET_N PD_ENABLE PH0 PH90 PH180 PH270 FB PHASE_BAD UP DN PB VDDIO VDDD VSS'
CP_VARIANTS={'cp_b1_c4':(1,4),'cp_b2_c2':(2,2),'cp_b2_c4':(2,4)}
OTA_VARIANTS={f'ota_w{w}_c{c}':(w,c) for w in [4,8] for c in [4,8]}

def block(name,ports,instances):
    lines=['.subckt '+name+' '+' '.join(ports)]
    for label,nodes,model,params in instances:
        lines.append(label+' '+' '.join(nodes)+' '+model+' '+' '.join(f'{k}={v}' for k,v in params.items()))
    return '\n'.join(lines+['.ends '+name])

def bias_block(source):
    names={'XBR',*[f'XBN{i}' for i in range(5)],*[f'XBP{i}' for i in range(5)],*[f'XBPN{i}' for i in range(5)]}
    rows=[r for r in circuits(source)['openlvds_dll_analog'][1] if r[0] in names]
    return block('screen_bias','PB PC NC VDDIO VDDD VSS'.split(),rows)

def ota_block(width):
    return f'''.subckt lvds_phase_ota UF DF OUT PB VDDIO VDDD VSS
* UF>DF -> left current rises -> source mirror wins -> CTRL increases.
XTAIL T PB VDDIO VDDIO sky130_fd_pr__pfet_g5v0d10v5 w=2 l=2.5
XPL NL DF T VDDIO sky130_fd_pr__pfet_g5v0d10v5 w={width} l=1
XPR NR UF T VDDIO sky130_fd_pr__pfet_g5v0d10v5 w={width} l=1
XNDL NL NL VSS VSS sky130_fd_pr__nfet_01v8 w=8 l=1
XNDR NR NR VSS VSS sky130_fd_pr__nfet_01v8 w=8 l=1
XNM PLATE NL VSS VSS sky130_fd_pr__nfet_01v8 w=8 l=1
XNO OUT NR VSS VSS sky130_fd_pr__nfet_01v8 w=8 l=1
XPD PLATE PLATE VDDD VDDD sky130_fd_pr__pfet_01v8 w=16 l=1
XPO OUT PLATE VDDD VDDD sky130_fd_pr__pfet_01v8 w=16 l=1
.ends lvds_phase_ota'''

def candidate_source(base,variant,monitor):
    if variant not in CP_VARIANTS and variant not in OTA_VARIANTS:raise ValueError('Unknown DLL variant')
    source=base
    if variant in CP_VARIANTS:
        scale,copy_pf=CP_VARIANTS[variant]
        source=variant_source(source,'nmos')
        ports,rows=circuits(source)['lvds_ctrl_buffer'];new=[]
        for name,nodes,model,params in rows:
            params=dict(params)
            if name!='XCC':params['w']=str(float(params['w'])*scale)
            else:params['w']=str(25*copy_pf/2)
            new.append((name,nodes,model,params))
        source=replace(source,'lvds_ctrl_buffer',block('lvds_ctrl_buffer',ports,new))
    defs=circuits(source);rows=[]
    quiet={'XQUAL','XQ270R','XQ270C','XQFBR','XQFBC'}
    keep={'XR0','XR1','XL','XREPL','XPDINV','XBR','XRP0','XEN','XPREN','XPREP'}
    keep|={f'{prefix}{i}' for prefix in ['XBN','XBP','XBPN'] for i in range(5)}
    for row in defs['openlvds_dll_analog'][1]:
        name=row[0]
        if name in quiet:continue
        if variant in OTA_VARIANTS and name not in keep:continue
        rows.append(row)
    rows.append(('XAREA','UP DN UF DF PHASE_BAD PC VDDD VSS'.split(),'lvds_phase_area',{}))
    if variant in OTA_VARIANTS:
        width,cap_pf=OTA_VARIANTS[variant]
        for i in range(cap_pf//2):
            for suffix,size in [('0',30),('1',10)]:
                rows.append((f'XCC{i}_{suffix}',['CTRL','VSS'],'sky130_fd_pr__cap_mim_m3_1',dict(w=str(size),l=str(size))))
        rows += [('XOTA','UF DF DRIVE PB VDDIO VDDD VSS'.split(),'lvds_phase_ota',{}),
                 ('XON',['CTRL','PD_ENABLE','DRIVE','VSS'],'sky130_fd_pr__nfet_01v8',dict(w='2',l='.15')),
                 ('XOP',['CTRL','ENB','DRIVE','VDDD'],'sky130_fd_pr__pfet_01v8',dict(w='4',l='.15')),
                 ('XRP1',['VDDD','PRE','VSS'],'sky130_fd_pr__res_high_po_0p35',dict(w='.35',l='1.25'))]
        source+='\n'+ota_block(width)+'\n'
    source=replace(source,'openlvds_dll_analog',block('openlvds_dll_analog',ANALOG_PORTS,rows))
    pfdrows=[r for r in defs['lvds_pfd'][1] if r[0] in {'XCLR','XAND','XRST','XU','XD','XUPBUF','XDNBUF'}]
    source=replace(source,'lvds_pfd',block('lvds_pfd',PFD_PORTS,pfdrows))
    core=f'''.subckt openlvds_dll_core {CORE_PORTS}
XA CLK PD_ENABLE PH0 PH90 PH180 PH270 FB PD_REF PHASE_BAD UP DN PB VDDIO VDDD VSS openlvds_dll_analog
XPFD PD_REF PH180 RESET_N PD_ENABLE UP DN VDDD VSS lvds_pfd
.ends openlvds_dll_core'''
    source=replace(source,'openlvds_dll_core',core)
    return source+'\n'+monitor+'\n'+bias_block(base)+'\n'

def native_block(source,top):
    ports,devices=flatten(circuits(source),top)
    return schematic_text(top,ports,devices)

def hybrid_library(source,captured,pfd_ports):
    """SC controller + captured exact PFD/delay line; explicitly diagnostic."""
    defs=circuits(source);ports,rows=defs['openlvds_dll_analog']
    delay=next(r for r in rows if r[0]=='XL')
    defs['openlvds_dll_analog']=(ports,[r for r in rows if r[0]!='XL'])
    _,devices=flatten(defs,'openlvds_dll_analog')
    body=schematic_text('openlvds_dll_analog',ports,devices)
    mapped=[n if n in ports else 'openlvds_dll_analog__'+n for n in delay[1]]
    body=body.replace('.ends openlvds_dll_analog','XL '+' '.join(mapped)+' openlvds_delay_line\n.ends openlvds_dll_analog')
    lib=replace(captured,'openlvds_dll_analog',body)
    for name in ['openlvds_dll_core','lvds_ctrl_buffer']:
        if name=='openlvds_dll_core':lib=replace(lib,name,block(name,defs[name][0],defs[name][1]))
    # Existing captured PFD has extra sense terminals; tie unused qualifier inputs.
    mapping={p:p for p in PFD_PORTS};mapping.update(QREF='VSS',QFB='VSS',QWIN='VSS',ERR='UNUSED')
    old=block('pfd_capture_adapter',pfd_ports,[])
    import re
    match=re.search(r'(?ims)^\.subckt lvds_pfd\s.*?^\.ends[^\n]*',lib)
    old=match[0].replace('.subckt lvds_pfd ','.subckt pfd_capture_adapter ',1)
    old=re.sub(r'(?im)^\.ends[^\n]*','.ends pfd_capture_adapter',old)
    adapter='.subckt lvds_pfd '+' '.join(PFD_PORTS)+'\nXOLD '+' '.join(mapping[p] for p in pfd_ports)+' pfd_capture_adapter\n.ends lvds_pfd'
    return replace(lib,'lvds_pfd',old+'\n'+adapter)
