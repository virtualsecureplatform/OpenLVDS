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
    expected=dict(output_logic='mux2_4',select_clock='buf_4',
        rise_sample='dfrtp_4',held_sample='dfrtp_4',fall_sample='dfrtp_4')
    for lane,capture,select in [('data_launch','clk_400','clk_90'),
                                ('clock_launch','clk_90','clk_400')]:
        selected={}
        for instance,cell in expected.items():
            value=cells.get(lane+'/'+instance)
            if not value or value[0]!='sky130_fd_sc_hd__'+cell:return False
            pins=value[1]
            required={'dfrtp_4':['CLK','D','RESET_B','Q'],
                      'mux2_4':['A0','A1','S','X'],'buf_4':['A','X']}[cell]
            if any(not pins.get(pin) for pin in required):return False
            selected[instance]=pins
        clocks=[v for name,v in cells.items() if re.fullmatch(lane+r'/falling_clock(?:_\d+)?',name)]
        if len(clocks)!=1 or clocks[0][0]!='sky130_fd_sc_hd__inv_4':return False
        if not all(clocks[0][1].get(pin) for pin in ['A','Y']):return False
        rise,fall,held=[selected[x] for x in ['rise_sample','fall_sample','held_sample']]
        output=selected['output_logic'];selector=selected['select_clock']
        if output['A1']!=rise['Q'] or output['A0']!=fall['Q']:return False
        if fall['D']!=held['Q']:return False
        if fall['CLK']!=clocks[0][1]['Y'] or clocks[0][1]['A']!=capture:return False
        if rise['CLK']!=capture or held['CLK']!=capture:return False
        if output['S']!=selector['X'] or selector['A']!=select:return False
    return True
