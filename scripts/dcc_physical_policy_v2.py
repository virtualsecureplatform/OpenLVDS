# SPDX-License-Identifier: GPL-3.0-only
"""Require exact source-candidate pulse/reset/toggle connectivity after P&R."""
import re


def interface_retained(text):
    cells={}
    for kind,name,body in re.findall(r'\bsky130_fd_sc_hd__(\w+)\s+(\\[^\s]+|[A-Za-z_$][\w$/.]*)\s*\((.*?)\);',text,re.S):
        name=name.lstrip('\\')
        if name in cells:return False
        cells[name]=(kind,dict(re.findall(r'\.(\w+)\s*\(\s*([^()\s]+)\s*\)',body)))
    def pins(name,kind):
        value=cells.get(name)
        return value[1] if value and value[0]==kind else {}
    tie=pins('tie','conb_1');high=tie.get('HI')
    if not high:return False
    pulses=[]
    for prefix,clock in [('first','phase0'),('second','phase180')]:
        ff=pins(prefix+'_ff','dfrtp_1');phase=pins(prefix+'_phase_inverse','inv_1')
        pulse=pins(prefix+'_pulse_inverse','inv_1');hold=pins(prefix+'_hold','a21oi_1');clear=pins(prefix+'_clear','and2b_1')
        if (ff.get('CLK')!=clock or ff.get('D')!=high or not ff.get('Q') or phase.get('A')!=clock
            or not phase.get('Y') or pulse.get('A')!=ff['Q'] or not pulse.get('Y')
            or hold.get('A1')!=pulse['Y'] or not clear.get('X') or hold.get('A2')!=clear['X']
            or hold.get('B1')!=phase['Y'] or not hold.get('Y') or clear.get('A_N')!=hold['Y']
            or clear.get('B')!='reset_n' or ff.get('RESET_B')!=clear['X']):return False
        pulses.append(ff['Q'])
    combine=pins('combine','or2_1');toggle=pins('toggle_ff','dfrtp_1')
    feedback=pins('toggle_feedback','inv_1');output=pins('output_drive','inv_4')
    if (pulses[0]==pulses[1] or combine.get('A')!=pulses[0] or combine.get('B')!=pulses[1]
        or not combine.get('X') or toggle.get('CLK')!=combine['X'] or toggle.get('RESET_B')!='reset_n'
        or not toggle.get('Q') or feedback.get('A')!=toggle['Q'] or not feedback.get('Y')
        or toggle.get('D')!=feedback['Y'] or output.get('A')!=toggle['Q'] or output.get('Y')!='clock_out'):
        return False
    expected={'tie','first_ff','first_phase_inverse','first_pulse_inverse','first_hold','first_clear',
              'second_ff','second_phase_inverse','second_pulse_inverse','second_hold','second_clear',
              'combine','toggle_ff','toggle_feedback','output_drive'}
    # Filler/tap/tie/antenna cells are permissible. New signal cells or delay
    # buffers would change the timing architecture and require explicit revision.
    if any(name not in expected and not re.fullmatch(r'(fill|tapvpwrvgnd|conb|diode)_\w+',kind)
           for name,(kind,_) in cells.items()):return False
    return not re.search(r'\bsky130_fd_sc_hd__clkdlybuf\w*\b',text)
