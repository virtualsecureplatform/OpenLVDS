#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Measure fixed-epoch low-phase headroom in complete native counter receipts."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
import diagnose_strong_counter_clear_v266 as old
import diagnose_fast_clear_counter_v299 as fast
from native_binary_raw_v2 import validate
from regenerated_bank_periodic_measure_v67 import crossings

ROOT=old.ROOT
sha=old.sha
VERSION='completed-native-counter-fixed-epoch-low-windows-v305.1'
CONTEXT='counter_low_windows_v305'
STAGES=('low0','low1','armed')


def windows(t,signals):
    if (set(signals)!={'CLK',*STAGES} or len(t)<2 or t[0]<0 or t[0]>1e-6 or t[-1]<25999
        or not np.isfinite(t).all() or np.any(np.diff(t)<=0)
        or any(len(v)!=len(t) or not np.isfinite(v).all() for v in signals.values())):
        raise ValueError('Require complete finite original 26ns native clock and phase traces')
    clk=signals['CLK'];rises=crossings(t,clk,.9,True);falls=crossings(t,clk,.9,False)
    downs=crossings(t,clk,.18,False);ups=crossings(t,clk,.18,True)
    if len(rises)!=7 or len(falls) not in (6,7):raise ValueError('Require all seven original buffered-clock cycles')
    rows=[]
    for k,stage in enumerate(STAGES):
        events=crossings(t,signals[stage],.9,True)
        if not events:raise ValueError('Missing original first phase assertion')
        event=events[0];a,b=rises[k:k+2]
        mid=[v for v in falls if a<v<b]
        if len(mid)!=1:raise ValueError('Ambiguous original clock low epoch')
        down=[v for v in downs if mid[0]<v<b];up=[v for v in ups if mid[0]<v<b]
        if len(down)!=1 or len(up)!=1 or down[0]>=up[0]:raise ValueError('No unique original guaranteed-low voltage window')
        voltage=float(np.interp(event,t,clk));head=up[0]-event
        rows.append(dict(stage=stage,assertion_ps=event,preceding_clock_rise_ps=a,next_clock_rise_ps=b,
            clock_fall_50_percent_ps=mid[0],clock_fall_10_percent_ps=down[0],clock_rise_10_percent_ps=up[0],
            guaranteed_low_window_ps=up[0]-down[0],assertion_from_clock_fall_50_percent_ps=event-mid[0],
            clock_rising_slew_10_to_50_ps=b-up[0],remaining_low_window_ps=head,
            clock_voltage_at_assertion_v=voltage,clock_low_voltage_margin_v=.18-voltage,
            assertion_in_original_low_window=bool(down[0]<event<up[0] and voltage<.18)))
    return dict(stages=rows,minimum_remaining_low_window_ps=min(r['remaining_low_window_ps'] for r in rows),
        minimum_clock_low_voltage_margin_v=min(r['clock_low_voltage_margin_v'] for r in rows),
        all_three_assertions_in_original_low_windows=all(r['assertion_in_original_low_window'] for r in rows))


def receipt(folder):
    m=json.loads((folder/'manifest.json').read_text());i=m['identity'];r=json.loads((folder/'summary.json').read_text())
    choices={old.VERSION:old,fast.VERSION:fast};producer=choices.get(i['version'])
    if (producer is None or folder.parent!=ROOT/'build/diagnostics'/producer.CONTEXT
        or folder.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or json.loads((folder/'state.json').read_text())!=dict(status='complete',analysis_completed=True,qualified_phy=False)
        or r.get('analysis_completed') is not True or r.get('parameters_changed') is not False
        or [row['case'] for row in r['rows']]!=i['cases'] or len(set(i['cases']))!=len(i['cases'])
        or any(sha(ROOT/n)!=h for n,h in i['inputs'].items())):
        raise ValueError('Require unchanged complete original native counter diagnosis receipt')
    paths=[folder/n for n in ('manifest.json','summary.json','state.json')]+[ROOT/n for n in i['inputs']];rows=[]
    for row in r['rows']:
        case=ROOT/row['case'];native=json.loads((case/'summary.json').read_text());measured=native['result']
        if (row.get('original_metrics_reproduced') is not True or row['task']!=native['task'] or native['error'] is not None
            or row['recorded_gates']!={k:v for k,v in measured.items() if k.endswith('_passed')}):
            raise ValueError('Original native diagnosis/task gates changed')
        names,w=validate(case/'bench.raw',{'v(clk)',*[f'v(xd.xr.{n})' for n in STAGES]},26e-9)
        t=w[:,names.index('time')]*1e12;signals={'CLK':w[:,names.index('v(clk)')],
            **{n:w[:,names.index(f'v(xd.xr.{n})')] for n in STAGES}}
        result=windows(t,signals)
        actual={v['stage']:v['clock_voltage_at_assertion_v'] for v in result['stages']}
        if (actual!=measured['clock_at_low_phase_assertion_v']
            or abs(result['minimum_clock_low_voltage_margin_v']-measured['minimum_clock_low_voltage_margin_v'])>1e-12):
            raise ValueError('Original low-phase voltage gate does not reproduce')
        rows.append(dict(case=row['case'],task=row['task'],native_mos_observed=row['native_mos_observed'],
            original_native_receipt=str(folder.relative_to(ROOT)),original_metrics_receipt_unchanged=True,
            original_low_voltage_gate_reproduced=True,recorded_gates=row['recorded_gates'],low_windows=result,
            original_clear=row['clear']))
    return rows,paths


def run(folders):
    if not folders or len(set(folders))!=len(folders):raise ValueError('Require explicit unique native receipts')
    rows=[];paths=[]
    for folder in folders:
        group,files=receipt(folder);rows+=group;paths+=files
    if len({r['case'] for r in rows})!=len(rows):raise ValueError('Do not duplicate the same native case across receipts')
    paths += sorted({Path(mod.__file__).resolve() for mod in list(sys.modules.values()) if getattr(mod,'__file__',None)
        and Path(mod.__file__).resolve().parent==ROOT/'scripts'})
    identity=dict(version=VERSION,receipts=[str(p.relative_to(ROOT)) for p in folders],
        inputs={str(p.relative_to(ROOT)):sha(p) for p in sorted(set(paths))},numpy=np.__version__,byteorder=sys.byteorder)
    if any(sha(ROOT/n)!=h for n,h in identity['inputs'].items()):raise ValueError('Original native low-window evidence changed during analysis')
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False)
    (out/'manifest.json').write_text(json.dumps(dict(identity=identity,qualified_phy=False),indent=2)+'\n')
    (out/'summary.json').write_text(json.dumps(dict(rows=rows,analysis_completed=True,parameters_changed=False,
        electrical_qualification_passed=False,qualified_phy=False,
        scope='Fixed original startup epochs and actual CLK voltage windows only; no epoch wrapping, thresholds relaxed, new circuit or PVT admission'),indent=2)+'\n')
    (out/'state.json').write_text('{"status":"complete","analysis_completed":true,"qualified_phy":false}\n');return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('receipts',nargs='+',type=Path);a=p.parse_args()
    print(run([f.resolve() for f in a.receipts]),flush=True)
