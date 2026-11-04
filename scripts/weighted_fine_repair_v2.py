# SPDX-License-Identifier: GPL-3.0-only
"""Double only the largest fine bit's transmission-gate widths."""
import weighted_fine_unit_v2 as previous
NAME=previous.name(4)
PORTS=previous.PORTS


def schematic():
    text=previous.schematic(4);rows=[];changed=[]
    for line in text.splitlines():
        words=line.split()
        if words and words[0] in ['XSWN','XSWP']:
            expected=1.68 if words[0]=='XSWN' else 3.36
            entries=[i for i,v in enumerate(words) if v.startswith('w=')]
            if len(entries)!=1 or float(words[entries[0]][2:])!=expected:raise ValueError('Original largest transmission gate changed')
            words[entries[0]]='w='+format(2*expected,'g');line=' '.join(words);changed.append(words[0])
        rows.append(line)
    if changed!=['XSWN','XSWP']:raise ValueError('Missing largest native transmission gate')
    return '\n'.join(rows)+'\n'
