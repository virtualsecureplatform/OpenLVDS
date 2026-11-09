# SPDX-License-Identifier: GPL-3.0-only
"""Fresh true-slew routed DCC fixture with an explicit phase-zero release epoch.

Ideal phase inputs and scheduled reset isolate the routed macro. Actual release
logic, clock-chain loading and full qualification remain separate requirements.
"""
import re
from collections import Counter
import dcc_input_waveforms_300_v2 as waveform
import qualify_retained_dcc_rc_300_v1 as proof
from run_native_binary_v2 import translate

SIGNALS={'pulse0':'first_ff.Q','pulse180':'second_ff.Q','events':'combine.X',
         'clear0':'first_ff.RESET_B','clear180':'second_clear.X'}
PINS={'VGND':'0','VPWR':'VDD','clock_out':'Q','phase0':'P0','phase180':'P180','reset_n':'RESET_N'}


def release_ps(s):
    period,first,_,_=waveform.parameters(s,'P0')
    # Suppress the fourth P0 event; the next P180 event must be captured first.
    return first+3*period+150


def fixture(out,s,info,text):
    waveform.check(s);defs=proof.definitions(text)
    if len(defs)!=1 or proof.NAME not in defs or set(info['ports'])!=set(PINS) or defs[proof.NAME][0]!=info['ports']:
        raise ValueError('Require the exact flat routed DCC interface')
    leaves=proof.leaves(text,proof.NAME)
    if dict(Counter(d['model'] for d in leaves))!=proof.EXPECTED:
        raise ValueError('Routed DCC native inventory changed')
    def target(n):return '0' if n=='0' else PINS.get(n,'XD:'+n)
    devices=[];resistors=[];known=set(info['ports'])
    for w in defs[proof.NAME][1]:
        if w[0][0].upper() in ('R','C'):known.update(w[1:3])
        elif w[0][0].upper()=='X':
            end=next((k for k,v in enumerate(w) if '=' in v),len(w));known.update(w[1:end-1])
    for d in leaves:
        row=dict(name='XD:'+d['name'].removeprefix(proof.NAME+':'),model=d['model'],
                 terminals=[target(n.removeprefix(proof.NAME+':')) for n in d['nodes']])
        if 'fet_' in d['model']:devices.append(dict(row,limit_v=1.95))
        else:resistors.append(row)
    if not set(SIGNALS.values())<=known:raise ValueError('Required routed DCC signal labels are missing')
    observations=dict(devices=devices,passive_resistors=resistors,signals={k:target(n) for k,n in SIGNALS.items()},
        release_50_ps=release_ps(s),expected_first_active_phase='P180',expected_output_rising_phase='P0',
        actual_release_circuit_qualified=False,qualified_phy=False)
    deck=waveform.fixture(out,s)
    include=r'(?m)^\.include "[^"\n]+/(cells|hold1)\.spice"$'
    if len(re.findall(include,deck))!=2:raise ValueError('Original source include contract changed')
    deck=re.sub(include,lambda m:f'.include "{out}/dcc_native.spice"' if m[1]=='cells' else '',deck)
    old='XD P0 P180 RESET_N Q VDD 0 dcc_source'
    if deck.count(old)!=1:raise ValueError('Original source DCC call changed')
    deck=deck.replace(old,'XD '+' '.join(PINS[p] for p in info['ports'])+' '+proof.NAME,1)
    old='VR RESET_N 0 PWL(0 0 1n 0 1.02n 1.8)'
    if deck.count(old)!=1:raise ValueError('Original reset source changed')
    release=release_ps(s);stop=waveform.capture_stop_ps(s)
    deck=deck.replace(old,f'VR RESET_N 0 PWL(0 0 {release-10:.17g}p 0 {release+10:.17g}p 1.8 {stop:.17g}p 1.8)',1)
    required={'P0','P180','Q','VDD','RESET_N',*observations['signals'].values()}
    required.update(n for d in devices+resistors for n in d['terminals'] if n!='0')
    unique=[];seen=set()
    for n in sorted(required):
        key=n.lower().replace(':','.')
        if key not in seen:unique.append('V('+n+')');seen.add(key)
    matches=list(re.finditer(r'(?m)^\.print tran .+$',deck))
    if len(matches)!=1:raise ValueError('Original source observation statement changed')
    deck=deck[:matches[0].start()]+'.print tran '+' '.join(unique)+deck[matches[0].end():]
    deck=deck.replace(deck.splitlines()[0],'OpenLVDS routed-DCC-corrected-input-release-300-v1',1)
    translate(deck)
    return deck,observations
