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
import probe_moscap_component_rc_bank_v91 as producer
from native_binary_raw_v2 import validate
from regenerated_bank_periodic_measure_v67 import crossings
from native_bank_inventory_v51 import exact_number
from build_compound_drivers_v3 import cell_definition

ROOT = producer.ROOT
sha = producer.sha


def stage_nodes(bank, top):
    defs = producer.circuit.source.native.definitions(bank)
    ports, body = defs[top]; instances = {w[0]: w for w in body if w[0].startswith('X')}
    points = [dict(stage='input', node='IN', inverted=False, representative_wire_resistance_ohm=0.)]
    for instance, port, stage, inverted in [
        ('Xgroup_inverse0', 'A', 'group_input', False),
        ('Xgroup_inverse0', 'Y', 'group_output', True),
        ('Xswitch1_0_0', 'Z', 'root_mux_output', True),
        ('Xfine_driver', 'A', 'final_inverter_input', True)]:
        w = instances[instance]; cell_ports, cell_body = defs[w[-1]]
        pins = dict(zip(cell_ports, w[1:-1])); graph = {}; candidates = set()
        for words in cell_body:
            if words[0][0].upper() == 'R':
                a, b = words[1:3]; resistance = float(exact_number(words[3]))
                if resistance <= 0:
                    raise ValueError('Nonpositive component wire resistance')
                graph.setdefault(a, []).append((b, resistance)); graph.setdefault(b, []).append((a, resistance))
            elif words[0][0].upper() == 'X':
                end = next((k for k, token in enumerate(words) if '=' in token), len(words))
                if 'fet_' in words[end-1]:
                    candidates.update(words[1:5])
        distance = {port: 0.}; queue = [(0., port)]
        while queue:
            cost, n = heapq.heappop(queue)
            if cost != distance[n]:
                continue
            for other, resistance in graph.get(n, []):
                following = cost+resistance
                if following < distance.get(other, float('inf')):
                    distance[other] = following; heapq.heappush(queue, (following, other))
        matches = [(distance[n], n) for n in candidates if n in distance]
        if not matches:
            raise ValueError('No saved MOS terminal connected to stage port')
        cost, local = min(matches)
        if local in cell_ports:
            parent = pins[local]
            node = ('VDD' if parent == 'VPWR' else '0' if parent == 'VGND' else parent) if parent in ports else 'XD:'+parent
        else:
            node = 'XD:'+instance+':'+local
        points.append(dict(stage=stage, node=node, inverted=inverted,
                           representative_wire_resistance_ohm=cost, component=instance, port=port))
    points.append(dict(stage='output', node='OUT', inverted=False, representative_wire_resistance_ohm=0.))
    return points


def run(case):
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
    binding = dict(version='measured-bank-native-stage-delay-and-slew-attribution-v96.1',
                   case=str(case.relative_to(ROOT)), inputs={str(p.relative_to(ROOT)): sha(p) for p in sorted(set(paths))},
                   math_runtime=exact.math_runtime())
    out = ROOT/'build/diagnostics/moscap_stage_analysis_v96'/hashlib.sha256(
        json.dumps(binding, sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True, exist_ok=False)
    (out/'manifest.json').write_text(json.dumps(binding, indent=2)+'\n')
    (out/'summary.json').write_text(json.dumps(dict(events=events, qualified_phy=False,
        scope='Nearest saved terminal stage diagnostic only; no new electrical or PHY admission'), indent=2)+'\n')
    print(out, flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('case', type=Path)
    run(p.parse_args().case.resolve())
