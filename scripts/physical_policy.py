# SPDX-License-Identifier: GPL-3.0-only
"""Physical clock and pulse paths must retain the intended detector interface."""
import re


def delay_cells_absent(netlist):
    return not re.search(r'\bsky130_fd_sc_hd__clkdlybuf\w*\b',netlist)


def pfd_ports_direct(netlist):
    for instance,clock,output in [('ref_ff','REF','UP'),('fb_ff','FB','DN')]:
        match=re.search(r'\bsky130_fd_sc_hd__dfrtp_4\s+'+instance+r'\s*\((.*?)\);',netlist,re.S)
        if not match:return False
        pins=dict(re.findall(r'\.(\w+)\s*\(\s*([^()\s]+)\s*\)',match[1]))
        if pins.get('CLK')!=clock or pins.get('Q')!=output:return False
    return True


def tx_cells_retained(netlist):
    cells={}
    for cell,name,body in re.findall(r'\b(sky130_fd_sc_hd__\w+)\s+(\\?\S+)\s*\((.*?)\);',netlist,re.S):
        cells[name.lstrip('\\')]=(cell,dict(re.findall(r'\.(\w+)\s*\(\s*([^()\s]+)\s*\)',body)))
    expected=dict(rise_logic='xor2_1',fall_logic='xor2_1',output_logic='xor2_4',
        rise_sample='dfrtp_4',held_sample='dfrtp_4',fall_sample='dfrtp_4')
    for lane in ['data_launch','clock_launch']:
        selected={}
        for instance,cell in expected.items():
            value=cells.get(lane+'/'+instance)
            if not value or value[0]!='sky130_fd_sc_hd__'+cell:return False
            pins=value[1]
            required=['CLK','D','RESET_B','Q'] if cell=='dfrtp_4' else ['A','B','X']
            if any(not pins.get(pin) for pin in required):return False
            selected[instance]=pins
        clocks=[v for name,v in cells.items() if re.fullmatch(lane+r'/falling_clock(?:_\d+)?',name)]
        if len(clocks)!=1 or clocks[0][0]!='sky130_fd_sc_hd__inv_4':return False
        if not all(clocks[0][1].get(pin) for pin in ['A','Y']):return False
        rise,fall,held=[selected[x] for x in ['rise_sample','fall_sample','held_sample']]
        output=selected['output_logic'];feedback=selected['fall_logic']
        if not all(x.get('Q') for x in [rise,fall,held]):return False
        if {output.get('A'),output.get('B')}!={rise['Q'],fall['Q']}:return False
        if {feedback.get('A'),feedback.get('B')}!={held['Q'],rise['Q']}:return False
        if fall['Q'] not in {selected['rise_logic']['A'],selected['rise_logic']['B']}:return False
        if rise.get('D')!=selected['rise_logic'].get('X') or fall.get('D')!=feedback.get('X'):return False
        if fall.get('CLK')!=clocks[0][1].get('Y'):return False
    return True
