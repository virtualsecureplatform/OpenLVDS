# SPDX-License-Identifier: GPL-3.0-only
"""Bounded piecewise-linear simplification of the four physical receive-pin vectors."""
import numpy as np
from simulate_link import edge_times
PINS=('RP','RN','RCP','RCN')
TOLERANCE_V=1e-4
CROSSING_TOLERANCE_PS=.1


def simplify(t,values,tolerance=TOLERANCE_V):
    if (len(t)<2 or values.shape!=(len(t),4) or not np.isfinite(t).all() or
            not np.isfinite(values).all() or np.any(np.diff(t)<=0) or tolerance<=0):raise ValueError('Invalid recorded pin vectors')
    retained={0,len(t)-1}
    # Preserve each original zero-crossing bracket exactly, including narrow
    # pulses, while allowing irrelevant fine-scale curvature to be simplified.
    for a,b in [(0,1),(2,3)]:
        high=values[:,a]-values[:,b]>=0
        for i in np.flatnonzero(high[:-1]!=high[1:]):retained.update([int(i),int(i+1)])
    knots=sorted(retained);pending=list(zip(knots[:-1],knots[1:]))
    while pending:
        a,b=pending.pop()
        if b-a<2:continue
        fraction=(t[a+1:b]-t[a])/(t[b]-t[a])
        linear=values[a]+fraction[:,None]*(values[b]-values[a])
        error=np.max(abs(values[a+1:b]-linear),axis=1);i=int(np.argmax(error))+a+1
        if error[i-a-1]>tolerance:retained.add(i);pending.extend([(a,i),(i,b)])
    indices=np.array(sorted(retained));rebuilt=np.column_stack([np.interp(t,t[indices],values[indices,j]) for j in range(4)])
    maximum=np.max(abs(values-rebuilt),axis=0)
    if np.max(maximum)>tolerance*(1+1e-8):raise ValueError('Pin replay exceeds its voltage-error bound')
    crossings={}
    for name,a,b in [('data',0,1),('clock',2,3)]:
        for rising in [True,False]:
            old=edge_times(t,values[:,a]-values[:,b],0,rising);new=edge_times(t[indices],values[indices,a]-values[indices,b],0,rising)
            if len(old)!=len(new):raise ValueError('Pin replay changes differential crossing count')
            error=float(np.max(abs(old-new))*1e12) if len(old) else 0.
            if error>CROSSING_TOLERANCE_PS:raise ValueError('Pin replay changes differential crossing timing')
            crossings[name+('_rising' if rising else '_falling')]=dict(count=len(old),maximum_error_ps=error)
    spacing=float(np.min(np.diff(t[indices])))
    if spacing<1e-15:raise ValueError('Pin replay retains sub-femtosecond source vertices')
    return indices,dict(original_vertices=len(t),retained_vertices=len(indices),tolerance_v=tolerance,
        maximum_pin_error_v={n:float(v) for n,v in zip(PINS,maximum)},crossing_tolerance_ps=CROSSING_TOLERANCE_PS,
        differential_crossings=crossings,minimum_vertex_spacing_s=spacing,
        scope='Maximum voltage error is checked at every original knot, bounding the difference between both piecewise-linear curves. Differential zero-crossing counts and times are checked separately. This is not a receiver or loading-feedback qualification.')
