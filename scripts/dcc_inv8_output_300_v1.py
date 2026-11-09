# SPDX-License-Identifier: GPL-3.0-only
"""One-factor native DCC output-drive change; never admit from source topology."""
import re
import dcc_full_native_fixture_300_v3 as baseline
import probe_dcc_clock_hold_v2 as source

OLD='sky130_fd_sc_hd__inv_4'
NEW='sky130_fd_sc_hd__inv_8'


def cell(pdk):
    found=re.findall(r'(?ims)^\.subckt\s+'+NEW+r'\s[^\n]*\n.*?^\.ends\b[^\n]*',pdk)
    if len(found)!=1:raise ValueError('Require exact PDK INV8 definition')
    ports,body=baseline.inventory.native.definitions(found[0])[NEW]
    if ports!=['A','VGND','VNB','VPB','VPWR','Y'] or len(body)!=16:
        raise ValueError('Native INV8 interface or primitive count changed')
    return found[0]+'\n'


def transform(cells,hold,pdk):
    if hold!=source.circuit(1):raise ValueError('Original symmetric clock-hold topology changed')
    if NEW in baseline.inventory.native.definitions(cells):raise ValueError('Retain prior output-drive experiment')
    old='Xoutput QT VSS VSS VDD VDD Q '+OLD
    if hold.count(old)!=1:raise ValueError('Original DCC output driver changed')
    new_cells=cells+'\n'+cell(pdk);new_hold=hold.replace(old,old.removesuffix(OLD)+NEW,1)
    original=baseline.observations(cells+'\n'+hold)
    devices,passives=baseline.inventory.mapped_mos(new_cells+'\n'+new_hold,
        dict(zip(baseline.PORTS,['P0','P180','RESET_N','Q','VDD','0'])),'XD')
    before={d['name']:d for d in original['devices'] if not d['name'].startswith('XD:Xoutput:')}
    after={d['name']:d for d in devices if not d['name'].startswith('XD:Xoutput:')}
    if before!=after or len(devices)!=144 or passives!=original['passive_resistors']:
        raise ValueError('Non-output native DCC devices or resistor maps changed')
    return new_cells,new_hold
