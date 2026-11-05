#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Attribute completed measured-RC bank delays to actual saved stage nodes.

Representative MOS terminals nearest each component port are selected by
wire resistance. This is a diagnostic, not a boundary timing certificate.
"""
import argparse
import hashlib
import heapq
import json
from pathlib import Path
import sys
import numpy as np
import exact_rc_candidate as exact
import probe_moscap_component_rc_bank_v91 as original
import probe_short_cap_bus_bank_v95 as short
import probe_parallel_root_bank_v98 as root
import probe_parallel_final_bank_v101 as final
from analyze_moscap_bank_stages_v96 import stage_nodes
PRODUCERS = dict(original=original, short=short, root=root, final=final)
from native_binary_raw_v2 import validate
from regenerated_bank_periodic_measure_v67 import crossings
from native_bank_inventory_v51 import exact_number
from build_compound_drivers_v3 import cell_definition

ROOT = original.ROOT
sha = original.sha


def run(case, kind):
    producer = PRODUCERS[kind]
    parent = case.parent; manifest = producer.bound(parent); identity = manifest['identity']
    row = json.loads((case/'summary.json').read_text())
    if (case.name not in ('0', '1') or row['error'] is not None or row['spec']['coarse'] != 0
        or any(sha(case/n) != h for n, h in row['files'].items())):
        raise ValueError('Require a complete, unchanged zero/fine31 case')
    profile = row['spec']['profile']; bank = (parent/('bank_'+profile+'.spice')).read_text()
    points = stage_nodes(bank, producer.circuit.name(profile))
    def column(node):
        return 'v('+node.replace(':', '.').lower()+')'
    names, wave = validate(case/'bench.raw', {column(p['node']) for p in points}, 20e-9)
    index = {n: i for i, n in enumerate(names)}; time = wave[:, index['time']]*1e12
    def value(node):
        return wave[:, index[column(node)]]
    events = []
    for sample in (0, 1):
        epoch = (time >= sample*10000)&(time <= (sample+1)*10000)
        for up, edge in ((True, 'rise'), (False, 'fall')):
            reference = crossings(time[epoch], value('IN')[epoch], .9, up)
            if len(reference) != 1:
                raise ValueError('Native input event epoch changed')
            start = reference[0]; window = (time >= start-250)&(time <= start+3000)
            stages = []; previous = 0.
            for point in points:
                rising = up != point['inverted']; values = value(point['node'])[window]
                middle = crossings(time[window], values, .9, rising)
                low = crossings(time[window], values, .18, rising)
                high = crossings(time[window], values, 1.62, rising)
                delay = middle[0]-start if len(middle) == 1 else None
                slew = abs(high[0]-low[0]) if len(high) == len(low) == 1 else None
                stages.append(dict(point, delay_from_input_ps=delay, slew_10_90_ps=slew,
                    incremental_delay_ps=delay-previous if delay is not None and previous is not None else None,
                    threshold_crossing_counts=dict(low=len(low), middle=len(middle), high=len(high))))
                previous = delay
            output = stages[-1]['delay_from_input_ps']
            if output is None or abs(output-row['result']['samples'][sample][edge+'_delay_ps']) > 1e-6:
                raise ValueError('Stage analysis does not reproduce complete measured output delay')
            events.append(dict(sample=sample, input_edge=edge, stages=stages))
    paths = [parent/'manifest.json', case/'summary.json', *[case/n for n in row['files']],
             *[ROOT/n for n in identity['inputs']]]
    paths += [Path(m.__file__).resolve() for m in list(sys.modules.values())
              if getattr(m, '__file__', None) and Path(m.__file__).resolve().parent == ROOT/'scripts']
    binding = dict(version='compared-drive-bank-native-stage-attribution-v102.1',
                   kind=kind, case=str(case.relative_to(ROOT)), inputs={str(p.relative_to(ROOT)): sha(p) for p in sorted(set(paths))},
                   math_runtime=exact.math_runtime())
    out = ROOT/'build/diagnostics/drive_stage_analysis_v102'/hashlib.sha256(
        json.dumps(binding, sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True, exist_ok=False)
    (out/'manifest.json').write_text(json.dumps(binding, indent=2)+'\n')
    (out/'summary.json').write_text(json.dumps(dict(events=events, qualified_phy=False,
        scope='Nearest saved terminal stage diagnostic only; no new electrical or PHY admission'), indent=2)+'\n')
    print(out, flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('case', type=Path); p.add_argument('--kind', choices=list(PRODUCERS), required=True)
    args = p.parse_args(); run(args.case.resolve(), args.kind)
