# SPDX-License-Identifier: GPL-3.0-only
"""Restrict a declared macro interface to its designated M3 access rails."""
import mim_switch_abstract_v2 as geometry


def restrict(text,ports,types):
    pins=list(geometry.PIN.finditer(text))
    if len(pins)!=len(ports) or {m[1] for m in pins}!=set(ports) or set(ports)!=set(types):
        raise ValueError('Unexpected declared macro interface')
    hidden=[];views={}
    def pin(match):
        name=match[1];shapes=geometry.rectangles(match[2]);point=ports[name]
        selected=[s for s in shapes if s[0]=='met3' and s[1][0]<=point['x_um']<=s[1][2] and s[1][1]<=point['y_um']<=s[1][3]]
        if len(selected)!=1:raise ValueError('Require one designated M3 rail for '+name)
        direction,usage=types[name]
        if (direction,usage) not in [('INPUT','SIGNAL'),('INOUT','POWER'),('INOUT','GROUND')]:raise ValueError('Invalid macro pin type')
        hidden.extend(s for s in shapes if s!=selected[0] and s[0] in geometry.ROUTING)
        antenna=''.join(line+'\n' for line in match[2].splitlines() if line.strip().startswith('ANTENNA'))
        views[name]=dict(direction=direction,use=usage,layer='met3',rectangle=selected[0][1])
        return f'  PIN {name}\n    DIRECTION {direction} ;\n    USE {usage} ;\n'+antenna+'    PORT\n'+geometry.render(selected)+f'    END\n  END {name}\n'
    result=geometry.PIN.sub(pin,text);blocks=list(geometry.OBS.finditer(result))
    if len(blocks)!=1:raise ValueError('Require one original obstruction block')
    shapes=[s for s in geometry.rectangles(blocks[0][1]) if s[0] in geometry.ROUTING]+hidden
    result=geometry.OBS.sub('  OBS\n'+geometry.render(shapes)+'  END\n',result)
    if geometry.geometry(result)!=geometry.geometry(text):raise ValueError('Routing geometry changed during access restriction')
    return result,views
