#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Trace clock pulse loss through a completed exact-RC link without rescoring it."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from dll_campaign import atomic
from dll_measurements import read_wave
from simulate_link import edge_times

ROOT = Path(__file__).resolve().parents[1]


def pulse_transport(t, differential, output, start, end):
    rises = edge_times(t, differential, 0, True)
    falls = edge_times(t, differential, 0, False)
    output_rises = edge_times(t, output, .9, True)
    output_falls = edge_times(t, output, .9, False)
    pulses = []
    for polarity, inputs, opposite, outputs in [('rising', rises, falls, output_rises),
                                                ('falling', falls, rises, output_falls)]:
        for at, next_at in zip(inputs[:-1], inputs[1:]):
            if at < start or next_at > end: continue
            other = opposite[(opposite > at) & (opposite < next_at)]
            matches = outputs[(outputs > at) & (outputs < next_at)]
            mask = (t >= at) & (t <= (other[0] if len(other) else next_at))
            if not len(other) or not np.any(mask): continue
            pulses.append(dict(polarity=polarity, input_edge_ns=float(at*1e9),
                input_pulse_width_ps=float((other[0]-at)*1e12),
                input_peak_magnitude_v=float(np.max(abs(differential[mask]))),
                output_edges_in_next_input_period=len(matches),
                first_output_latency_ps=float((matches[0]-at)*1e12) if len(matches) else None))
    missing = [p for p in pulses if p['output_edges_in_next_input_period'] == 0]
    return dict(pulses=pulses, missing_output_edges=len(missing),
                rising_missing=sum(p['polarity']=='rising' for p in missing),
                falling_missing=sum(p['polarity']=='falling' for p in missing),
                matching_rule='Same-polarity output crossing within the next same-polarity input period; diagnostic, not aperture qualification')


def diagnose(folder, start_ns, end_ns):
    if not folder.is_relative_to(ROOT/'build/link'): raise ValueError('Use a saved link artifact')
    files = ['bench.cir.prn', 'summary.json', 'bench.cir', 'runner.py', 'library.spice']
    hashes = {n: hashlib.sha256((folder/n).read_bytes()).hexdigest() for n in files}
    result = json.loads((folder/'summary.json').read_text())
    for name, key in [('bench.cir.prn','waveform_sha256'), ('bench.cir','deck_sha256'),
                      ('runner.py','runner_sha256'), ('library.spice','library_sha256')]:
        if hashes[name] != result[key]: raise ValueError('Captured link evidence changed: '+name)
    wave, header = read_wave(folder/'bench.cir.prn'); t = wave[:,1]
    if not t[0] <= start_ns*1e-9 < end_ns*1e-9 <= t[-1]: raise ValueError('Observation interval unavailable')
    def column(name): return wave[:,header['V('+name+')']]
    stages = {}
    for name, signal, level in [('source',column('CLK0'),.9), ('tx_digital',column('TXCLOCK'),.9),
            ('tx_differential',column('CP')-column('CN'),0),
            ('rx_differential',column('RCP')-column('RCN'),0), ('rx_digital',column('RXCLOCK'),.9)]:
        stages[name] = {}; crossing = {}
        for polarity in [True, False]:
            events = edge_times(t,signal,level,polarity)
            crossing[polarity] = events
            events = events[(events>=start_ns*1e-9)&(events<=end_ns*1e-9)]
            stages[name]['rising_ns' if polarity else 'falling_ns'] = (events*1e9).tolist()
        for polarity, label in [(True,'high'),(False,'low')]:
            widths = []
            for at in crossing[polarity]:
                later = crossing[not polarity][crossing[not polarity]>at]
                if len(later) and start_ns*1e-9 <= at < later[0] <= end_ns*1e-9:
                    widths.append(float((later[0]-at)*1e12))
            stages[name][label+'_pulse_width_ps'] = dict(min=min(widths),max=max(widths)) if widths else None
    transport = pulse_transport(t,column('RCP')-column('RCN'),column('RXCLOCK'),start_ns*1e-9,end_ns*1e-9)
    identity = dict(link=str(folder.relative_to(ROOT)), files=hashes, interval_ns=[start_ns,end_ns],
        producer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        dependencies={name:hashlib.sha256((ROOT/'scripts'/name).read_bytes()).hexdigest()
                      for name in ['simulate_link.py','dll_measurements.py','dll_campaign.py']})
    root = ROOT/'build/diagnostics/link_clock'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    root.mkdir(parents=True,exist_ok=True)
    report = dict(identity=identity,qualified_phy=False,qualification_verdict=None,
        original_link_passed=result['passed'],stages=stages,receiver_transport=transport)
    atomic(root/'summary.json',report); print(root/'summary.json',flush=True)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('link',type=Path)
    parser.add_argument('--start-ns',type=float,default=60); parser.add_argument('--end-ns',type=float,default=120)
    args = parser.parse_args(); diagnose(args.link.resolve(),args.start_ns,args.end_ns)
