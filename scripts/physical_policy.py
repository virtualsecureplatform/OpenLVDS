# SPDX-License-Identifier: GPL-3.0-only
"""Physical clock and pulse paths must retain the intended detector interface."""
import re


def delay_cells_absent(netlist):
    return not re.search(r'\bsky130_fd_sc_hd__clkdlybuf\w*\b',netlist)


def pfd_paths_retained(netlist):
    def pins(kind,name):
        match=re.search(r'\bsky130_fd_sc_hd__'+kind+r'\s+'+name+r'\s*\((.*?)\);',netlist,re.S)
        return dict(re.findall(r'\.(\w+)\s*\(\s*([^()\s]+)\s*\)',match[1])) if match else {}
    raw=[]
    for instance,clock,output,driver in [('ref_ff','REF','UP','up_drive'),('fb_ff','FB','DN','dn_drive')]:
        ff=pins('dfrtp_4',instance);buf=pins('buf_8',driver)
        if ff.get('CLK')!=clock or not ff.get('Q'):return False
        if buf.get('A')!=ff['Q'] or buf.get('X')!=output:return False
        raw.append(ff['Q'])
    coincidence=pins('and2_4','coincidence')
    if not (len(set(raw))==2 and set(raw).isdisjoint({'UP','DN'}) and
            {coincidence.get('A'),coincidence.get('B')}=={'UP','DN'}):return False
    # Require the restored raw-clock qualifier, independently of the PFD Qs.
    nodes={}
    for kind,name,inputs,output in [
        ('buf_8','qual_ref',{'A':'QREF'},'X'),
        ('buf_8','qual_fb',{'A':'QFB'},'X'),
        ('buf_8','qual_window_first',{'A':'QWIN'},'X'),
        ('buf_8','qual_window_second',{'A':'qual_window_first'},'X'),
        ('inv_4','qual_ref_inv',{'A':'qual_ref'},'Y'),
        ('inv_4','qual_fb_inv',{'A':'qual_fb'},'Y'),
        ('a22oi_4','qual_compare',{'A1':'qual_ref','A2':'qual_fb_inv',
                               'B1':'qual_fb','B2':'qual_ref_inv'},'Y'),
        ('inv_16','qual_error_drive',{'A':'qual_compare'},'Y'),
        ('and2_4','qual_mask',{'A':'qual_error_drive','B':'qual_window_second'},'X')]:
        cell=pins(kind,name)
        if any(cell.get(pin)!=nodes.get(net,net) for pin,net in inputs.items()):return False
        net=cell.get(output)
        if not net or net in set(nodes.values())|set(raw)|{'UP','DN','QREF','QFB','QWIN'}:return False
        if (name=='qual_mask')!=(net=='ERR'):return False
        nodes[name]=net
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


def pfd_area_paths_retained(netlist):
    """Pulse-area PFD: direct clocks, buffered coincidence, no XOR monitor."""
    def pins(kind,name):
        m=re.search(r'\bsky130_fd_sc_hd__'+kind+r'\s+'+name+r'\s*\((.*?)\);',netlist,re.S)
        return dict(re.findall(r'\.(\w+)\s*\(\s*([^()\s]+)\s*\)',m[1])) if m else {}
    header=re.search(r'\bmodule\s+lvds_pfd\s*\((.*?)\);',netlist,re.S)
    if not header or re.search(r'\b(ERR|QREF|QFB|QWIN)\b',header[1]):return False
    if not all(re.search(r'\b'+p+r'\b',header[1]) for p in ['REF','FB','RESET_N','PD_ENABLE','UP','DN']):return False
    raw=[]
    for name,clock,out,driver in [('ref_ff','REF','UP','up_drive'),('fb_ff','FB','DN','dn_drive')]:
        ff=pins('dfrtp_4',name);buf=pins('buf_8',driver)
        if ff.get('CLK')!=clock or not ff.get('Q') or buf.get('A')!=ff['Q'] or buf.get('X')!=out:return False
        raw.append(ff['Q'])
    both=pins('and2_4','coincidence');clear=pins('and2b_4','clear');ena=pins('and2_1','ena')
    if len(set(raw))!=2 or not set(raw).isdisjoint({'UP','DN'}):return False
    if {both.get('A'),both.get('B')}!={'UP','DN'} or clear.get('A_N')!=both.get('X'):return False
    if {ena.get('A'),ena.get('B')}!={'RESET_N','PD_ENABLE'} or clear.get('B')!=ena.get('X'):return False
    if not clear.get('X') or any(pins('dfrtp_4',name).get('RESET_B')!=clear['X'] for name in ['ref_ff','fb_ff']):return False
    return delay_cells_absent(netlist) and not re.search(r'\bqual_\w+',netlist)
