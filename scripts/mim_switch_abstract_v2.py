# SPDX-License-Identifier: GPL-3.0-only
"""Expose only designated M3 rails; obstruct underlying component geometry."""
from collections import Counter,defaultdict
import math
import re

ROUTING={'li1','met1','met2','met3','met4','met5'}
PIN=re.compile(r'(?ms)^  PIN (\S+)\n(.*?)^  END \1\n')
OBS=re.compile(r'(?ms)^  OBS\n(.*?)^  END\n')


def rectangles(text):
    layer=None;result=[]
    for line in text.splitlines():
        words=line.split()
        if words and words[0]=='LAYER':layer=words[1]
        elif words and words[0]=='RECT':
            if layer is None or len(words)!=6 or words[-1]!=';':raise ValueError('Unsupported LEF rectangle')
            coordinates=tuple(map(float,words[1:5]))
            if not all(map(math.isfinite,coordinates)) or coordinates[0]>=coordinates[2] or coordinates[1]>=coordinates[3]:
                raise ValueError('Invalid LEF rectangle')
            result.append((layer,coordinates))
        elif words and words[0] in ['POLYGON','PATH','VIA']:raise ValueError('Unsupported LEF geometry')
    return result


def geometry(text):
    return Counter((layer,rect) for match in [*PIN.finditer(text),*OBS.finditer(text)]
                   for layer,rect in rectangles(match[2] if match.re is PIN else match[1]) if layer in ROUTING)


def render(shapes):
    groups=defaultdict(list)
    for layer,rect in shapes:groups[layer].append(rect)
    return ''.join('      LAYER '+layer+' ;\n'+''.join('        RECT '+' '.join(f'{v:.6f}' for v in rect)+' ;\n' for rect in rects)
                   for layer,rects in groups.items())


def abstract(text,ports):
    blocks=list(PIN.finditer(text))
    if len(blocks)!=5 or {m[1] for m in blocks}!=set(ports) or set(ports)!={'NODE','EN','ENB','VDD','VSS'}:
        raise ValueError('Unexpected fine-unit pin interface')
    additions=[];views={}
    def pin(match):
        name,body=match[1],match[2];point=ports[name]
        shapes=rectangles(body)
        candidates=[(layer,r) for layer,r in shapes if layer=='met3' and r[0]<=point['x_um']<=r[2] and r[1]<=point['y_um']<=r[3]]
        if len(candidates)!=1:raise ValueError('No unique designated public M3 rail: '+name)
        selected=candidates[0];removed=False
        for shape in shapes:
            if shape==selected and not removed:removed=True
            elif shape[0] in ROUTING:additions.append(shape)
        direction='INOUT' if name in ['VDD','VSS'] else 'INPUT'
        usage='POWER' if name=='VDD' else 'GROUND' if name=='VSS' else 'SIGNAL'
        views[name]=dict(direction=direction,use=usage,layer='met3',rectangle=selected[1])
        antenna=''.join(line+'\n' for line in body.splitlines() if line.strip().startswith('ANTENNA'))
        return f'  PIN {name}\n    DIRECTION {direction} ;\n    USE {usage} ;\n'+antenna+'    PORT\n'+render([selected])+f'    END\n  END {name}\n'
    result=PIN.sub(pin,text)
    obstructions=list(OBS.finditer(result))
    if len(obstructions)!=1:raise ValueError('Require one original obstruction block')
    old=rectangles(obstructions[0][1]);all_shapes=[s for s in old if s[0] in ROUTING]+additions
    result=OBS.sub('  OBS\n'+render(all_shapes)+'  END\n',result)
    if geometry(result)!=geometry(text):raise ValueError('Routing geometry lost or added during abstraction')
    return result,views
