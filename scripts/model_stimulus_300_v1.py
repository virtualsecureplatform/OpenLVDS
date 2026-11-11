# SPDX-License-Identifier: GPL-3.0-only
"""Smooth device-control inputs with explicit 50% epochs and 10-90 slew."""
import math
import re


def smooth_inputs(text):
    for name,node,voltage in [('VIN','IN',1.8),('VIN33','IN33',3.3)]:
        terms=[]
        for rise,fall,slew in [(1.0125e-9,2.5125e-9,20e-12),(4.15625e-9,5.65625e-9,250e-12)]:
            sigma=slew/(2*math.atanh(.8))
            terms.append(f'{voltage/2}*(tanh((time-{rise:.17g})/{sigma:.17g})-tanh((time-{fall:.17g})/{sigma:.17g}))')
        text,count=re.subn(r'(?m)^'+name+r' '+node+r' 0 PWL\([^\n]+\)$','B'+name+' '+node+' 0 V={'+ '+'.join(terms)+'}',text)
        if count!=1:
            raise ValueError('Expected device-control source changed')
    return text
