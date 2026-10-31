# SPDX-License-Identifier: GPL-3.0-only
"""Averaged loop model from measured PFD gain, delay sensitivity and AC G/Y."""
import numpy as np


def margins(frequency,transfer,kpd,kdelay,reference_hz):
    f=np.asarray(frequency,float);transfer=np.asarray(transfer,complex)
    if (len(f)<3 or f.shape!=transfer.shape or np.any(np.diff(f)<=0) or np.any(f<=0)
        or not np.isfinite(transfer).all() or not np.isfinite([kpd,kdelay,reference_hz]).all()
        or kpd<=0 or kdelay>=0 or reference_hz<=0):
        raise ValueError('Invalid measured loop model or feedback sign')
    loop=-kpd*kdelay*transfer*np.exp(-2j*np.pi*f/reference_hz)
    db=20*np.log10(np.maximum(abs(loop),1e-300));phase=np.rad2deg(np.unwrap(np.angle(loop)))
    if phase[0]>90:phase-=360
    logf=np.log10(f)
    crossings=np.flatnonzero((db[:-1]>=0)!=(db[1:]>=0))
    pm=[];unity=[]
    for i in crossings:
        alpha=-db[i]/(db[i+1]-db[i]);unity.append(float(10**(logf[i]+alpha*(logf[i+1]-logf[i]))))
        pm.append(float(180+phase[i]+alpha*(phase[i+1]-phase[i])))
    gm=[]
    for target in np.arange(-180,min(-181,float(phase.min())-1),-360):
        for i in np.flatnonzero((phase[:-1]>target)&(phase[1:]<=target)):
            alpha=(target-phase[i])/(phase[i+1]-phase[i]);gm.append(float(-(db[i]+alpha*(db[i+1]-db[i]))))
    valid=bool(unity and gm and db[0]>0 and db[-1]<0 and max(unity)<reference_hz/10)
    return dict(passed=bool(valid and min(pm)>=60 and min(gm)>=6),model_valid=valid,
                unity_gain_hz=unity,phase_margin_min_deg=min(pm) if pm else None,
                gain_margin_min_db=min(gm) if gm else None,
                model='Measured G/Y with one-reference-cycle conservative latency',
                loop=loop)


def predicted_step(frequency,loop,kdelay,delta_delay_s):
    """Small-signal CTRL step prediction; 0.5ns spacing over 16.384us."""
    n=32768;dt=.5e-9;bins=np.fft.rfftfreq(n,dt)
    f=np.asarray(frequency);closed=np.asarray(loop)/(1+np.asarray(loop))
    response=np.interp(bins,f,closed.real)+1j*np.interp(bins,f,closed.imag)
    response[0]=closed[0].real
    return np.arange(n)*dt,np.cumsum(np.fft.irfft(response,n=n))*delta_delay_s/kdelay
