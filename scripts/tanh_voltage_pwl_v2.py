# SPDX-License-Identifier: GPL-3.0-only
"""Bounded PWL representation of the retained two-pulse tanh voltage fixture.

This changes stimulus representation, not circuit parameters or solver limits.
The interpolation bound uses max |f''| h^2/8 on every interval, including tails.
"""
import math

CENTERS_PS=[2100.,6100.,12100.,16100.]
STOP_PS=20000.
ERROR_LIMIT_V=50e-6


def waveform(t_ps,slew_ps):
    width=slew_ps/(2*math.atanh(.8))
    return .9*sum(sign*math.tanh((t_ps-center)/width) for center,sign in zip(CENTERS_PS,[1,-1,1,-1]))


def crossings(points,level,rising):
    edges=[]
    for (a,x),(b,y) in zip(points,points[1:]):
        if (x<level<=y) if rising else (x>level>=y):edges.append(a+(level-x)*(b-a)/(y-x))
    return edges


def samples(slew_ps,step_ps=.5):
    if not math.isfinite(slew_ps) or slew_ps<=0 or not math.isfinite(step_ps) or step_ps<=0:
        raise ValueError('Require finite positive source slew and PWL step')
    count=round(1200/step_ps)
    if abs(count*step_ps-1200)>1e-9:raise ValueError('PWL step must exactly divide the transition window')
    times={float(t) for t in range(0,20001,100)}
    for center in CENTERS_PS:times.update(center-600+j*step_ps for j in range(count+1))
    points=[(t,waveform(t,slew_ps)) for t in sorted(times)];width=slew_ps/(2*math.atanh(.8));bounds=[];slope_bounds=[]
    peak_curvature=.9*4/(3*math.sqrt(3)*width**2)
    for (a,_),(b,_) in zip(points,points[1:]):
        curvature=0.
        for center in CENTERS_PS:
            distance=0 if a<=center<=b else min(abs(a-center),abs(b-center))
            curvature+=min(peak_curvature,8*.9/width**2*math.exp(-2*distance/width))
        bounds.append(curvature*(b-a)**2/8+1e-12)
        slope_bounds.append(curvature*(b-a)/2*1000+1e-9)
    maximum=max(bounds)
    if maximum>ERROR_LIMIT_V:raise ValueError('PWL representation exceeds its declared voltage-error bound')
    rises={level:crossings(points,level,True) for level in [.18,.9,1.62]}
    falls={level:crossings(points,level,False) for level in [.18,.9,1.62]}
    if any(len(v)!=2 for v in [*rises.values(),*falls.values()]):raise ValueError('PWL input event count changed')
    epochs=sorted(rises[.9]+falls[.9]);slews=[]
    for j in range(2):slews.extend([rises[1.62][j]-rises[.18][j],falls[.18][j]-falls[1.62][j]])
    if any(abs(a-b)>.001 for a,b in zip(epochs,CENTERS_PS)) or any(abs(s-slew_ps)>.001 for s in slews):
        raise ValueError('PWL midpoint epochs or 10--90% slew changed')
    certificate=dict(points=len(points),maximum_interpolation_bound_v=maximum,error_limit_v=ERROR_LIMIT_V,
        maximum_slope_error_bound_v_per_ns=max(slope_bounds),
        midpoint_epochs_ps=epochs,slew_10_90_ps=slews,transition_step_ps=step_ps,stop_ps=STOP_PS,
        method='Per-interval analytic curvature bound; full tanh pulse sum retained, no voltage clipping')
    return points,certificate


def statement(points):
    rows=['VIN IN 0 PWL(']
    for start in range(0,len(points),6):
        rows.append('+ '+' '.join(f'{t:.17g}p {v:.17g}' for t,v in points[start:start+6]))
    return '\n'.join(rows+['+ )'])
