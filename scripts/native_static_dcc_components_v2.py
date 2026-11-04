# SPDX-License-Identifier: GPL-3.0-only
"""Join the static counter and native DCC with common or early data prepare.

Three actual clock drivers per phase support the combined DCC/counter fanout.
Inter-component wires and physical parallel-driver routing still need fresh
whole-backend proof. Only two DCC data qualifiers change in prepare mode.
"""
import native_clock_components_v3 as base
import static_phase_clock_release_v5 as release
import guarded_clock_prepare_v2 as prepare

clean=base.clean
mapped_mos=base.mapped_mos
MODES=['common','prepare']
DRIVERS=3


def dcc_interface(mode):
    if mode=='common':return base.dcc.NAME,base.dcc.PORTS
    if mode=='prepare':return prepare.DCC_NAME,prepare.DCC_PORTS
    raise ValueError('Unknown native DCC preparation mode')


def compose(rc,variant):
    before=base.compose(rc);prefix=base.clean_source(rc,1);combined=before['p3_c1.spice']
    if not combined.startswith(prefix):raise ValueError('Native common DCC/clock definition changed')
    common=combined[len(prefix):]
    result={'cells.spice':before['cells.spice'],'clean.spice':base.clean_source(rc,DRIVERS),
            'release.spice':'* The selected variant defines the actual static release controller.\n'}
    for mode in MODES:
        result[mode+'.spice']=release.source(rc,variant)+(common if mode=='common' else prepare.dcc_source(rc))
    return result


def devices(modules,front_devices,mode):
    text='\n'.join(modules[n] for n in ['cells.spice','clean.spice','release.spice',mode+'.spice'])
    result=[d for d in front_devices if d['name'].startswith(('XF:','XB:'))]
    result+=mapped_mos(text,clean.NAME,dict(F0='F0',F180='F180',P0='P0',P180='P180',MON0='MON0',MON180='MON180',VPWR='VDD',VGND='0'),'XC')
    name,ports=dcc_interface(mode);pins=dict(VGND='0',VPWR='VDD',clock_out='Q',phase0='P0',phase180='P180',reset_n='RESET_N')
    if mode=='prepare':pins['prepare_n']='PREPARE_0'
    result+=mapped_mos(text,name,pins,'XD')
    for tag,clk,ready,reset in [('XR0','P0','PREPARE_0','RESET_N'),('XR180','P180','PREPARE_180','RESET_180')]:
        result+=mapped_mos(text,release.NAME,dict(CLK=clk,REQUEST='REQUEST',PREPARE=ready,RESET_N=reset,VPWR='VDD',VGND='0'),tag)
    if len({d['name'] for d in result})!=len(result):raise ValueError('Duplicate joint native MOS witness')
    return result
