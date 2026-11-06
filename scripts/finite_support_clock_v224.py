# SPDX-License-Identifier: GPL-3.0-only
"""Finite-support tanh input with exact slew and a global voltage error bound.

Only testbench input precision changes. No device, solver tolerance, DUT
load, timing limit or native terminal observation is modified.
"""
import math

LIMIT=9.
AMPLITUDE=1.8


def parameters(slew_ps,cycles):
    if not math.isfinite(slew_ps) or slew_ps<=0 or type(cycles) is not int or not 1<=cycles<=8:raise ValueError('Require positive finite slew and at most eight pulses')
    t=math.tanh(LIMIT)
    old_width=slew_ps*1e-12/(2*math.atanh(.8))
    width=slew_ps*1e-12/(2*math.atanh(.8*t))
    # For any u, |u| sech(u)^2 <= 1/2: sinh(|u|)>=|u| and
    # cosh(u)^2>=1+u^2>=2|u|. Integrating in log(width) bounds
    # the slew-renormalization error without relying on a sampled grid.
    per_edge=AMPLITUDE/2*(1-t)+AMPLITUDE/4*abs(math.log(width/old_width))
    bound=2*cycles*per_edge
    if bound>1e-6:raise ValueError('Finite-support clock exceeds one-microvolt global input error')
    return dict(limit=LIMIT,tanh_limit=t,width_s=width,old_width_s=old_width,
                cycles=cycles,slew_10_90_ps=slew_ps,amplitude_v=AMPLITUDE,
                global_input_difference_bound_v=bound,exactly_flat_outside_support=True,
                scope='Analytic testbench input perturbation bound only; native waveform/terminal/timing parity still requires complete replay',qualified_phy=False)


def step(time,center,p):
    u=(time-center)/p['width_s']
    return 0. if u<=-LIMIT else 1. if u>=LIMIT else .5+.5*math.tanh(u)/p['tanh_limit']


def expression(s):
    p=parameters(s['input_slew_ps'],s['cycles']);w=p['width_s'];t=p['tanh_limit'];period=1e-6/s['frequency_mhz']
    def edge(center):
        return f'(time<={center-LIMIT*w:.17g}?0:(time>={center+LIMIT*w:.17g}?1:(0.5+0.5*tanh((time-{center:.17g})/{w:.17g})/{t:.17g})))'
    return '+'.join(f'1.8*({edge(2.1e-9+k*period)}-{edge(2.1e-9+(k+s["duty"])*period)})' for k in range(s['cycles'])),p
