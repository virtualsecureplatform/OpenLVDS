#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Freeze selected native stage histories from a live original v352 zero run.

Only complete records already present at capture are read. Partial timing is
diagnostic evidence; it never substitutes for completed full-native checks.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import numpy as np
from capture_native_live_tail_v290 import process
from regenerated_bank_periodic_measure_v67 import crossings, timing
import probe_restored_balanced_bank_v352 as source

ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT/'build/diagnostics/restored_balanced_bank_v352/67d491be912b3621'
NODES = ('time', 'v(in)', 'v(xd.selected)', 'v(xd.pre_out)', 'v(xd.fine_node)', 'v(out)')


def project(path):
    with path.open('rb') as stream:
        stat = os.fstat(stream.fileno())
        header = b''
        while b'Binary:\n' not in header:
            block = stream.read(65536)
            if not block or len(header) > 64*1024*1024:
                raise ValueError('Missing bounded binary header')
            header += block
        offset = header.index(b'Binary:\n')+8
        header = header[:offset]
        text = header.decode()
        variables = list(re.finditer(r'^\s*(\d+)\s+(\S+)\s+\S+\s*$', text, re.M))
        match = re.search(r'No\. Variables:\s*(\d+)', text)
        if (not match or 'complex' in text.lower() or int(match[1]) != len(variables)
                or [int(m[1]) for m in variables] != list(range(len(variables)))):
            raise ValueError('Ambiguous native vector table')
        names = [m[2].lower() for m in variables]
        if len(set(names)) != len(names) or not set(NODES) <= set(names) or names[0] != 'time':
            raise ValueError('Missing, duplicate or unordered required native vectors')
        width = len(names)*8
        frames = (stat.st_size-offset)//width
        if frames < 2:
            raise ValueError('Need at least two complete native records')
        mapped = np.memmap(path, dtype='<f8', mode='r', offset=offset, shape=(frames, len(names)))
        data = np.array(mapped[:, [names.index(n) for n in NODES]], copy=True)
        del mapped
        digest = hashlib.sha256()
        stream.seek(offset)
        remaining = frames*width
        while remaining:
            block = stream.read(min(1024*1024, remaining))
            if not block:
                raise ValueError('Native file shrank during projection')
            digest.update(block)
            remaining -= len(block)
        after = os.fstat(stream.fileno())
        current = path.stat()
        if (after.st_size < stat.st_size or (stat.st_dev, stat.st_ino) != (current.st_dev, current.st_ino)):
            raise ValueError('Native waveform shrank or was replaced')
    if not np.isfinite(data).all() or data[0, 0] != 0 or np.any(np.diff(data[:, 0]) <= 0):
        raise ValueError('Nonfinite/nonmonotonic selected native history or missing startup')
    metadata = dict(source_device=stat.st_dev, source_inode=stat.st_ino,
                    source_size_observed=stat.st_size, complete_frames_captured=frames,
                    ignored_partial_frame_bytes=(stat.st_size-offset) % width,
                    original_native_vectors=len(names), captured_vectors=list(NODES),
                    original_header_sha256=hashlib.sha256(header).hexdigest(),
                    complete_record_payload_sha256=digest.hexdigest(),
                    last_captured_ps=float(data[-1, 0]*1e12))
    return header, data, metadata


def histories(data, spec):
    if spec['cycles'] != 8 or spec['coarse'] != 0 or spec['fine'] != 0:
        raise ValueError('Require original eight-cycle zero-code diagnostic')
    t = data[:, 0]*1e12
    measured = timing(t, data[:, 1], data[:, -1], spec)
    parts = {}
    for rising, edge in ((True, 'rise'), (False, 'fall')):
        events = {name: np.asarray(crossings(t, data[:, k], .9,
                          not rising if name in ('v(xd.selected)', 'v(xd.fine_node)') else rising))
                  for k, name in enumerate(NODES) if k}
        counts = {name: len(v) for name, v in events.items()}
        if any(n != 8 for n in counts.values()):
            parts[edge] = dict(available_crossing_counts=counts, all_eight_stage_events_captured=False)
            continue
        stage_names = NODES[1:]
        stages = {a+' -> '+b: events[b]-events[a] for a, b in zip(stage_names, stage_names[1:])}
        total = events[stage_names[-1]]-events[stage_names[0]]
        if not all(np.all(v > 0) for v in stages.values()):
            raise ValueError('Native stage events are not causally ordered; never reassign epochs')
        parts[edge] = dict(available_crossing_counts=counts, all_eight_stage_events_captured=True,
                           crossing_times_ps={n: v.tolist() for n, v in events.items()},
                           stage_delays_ps={n: v.tolist() for n, v in stages.items()},
                           total_delays_ps=total.tolist(),
                           maximum_sum_residual_ps=float(np.max(np.abs(sum(stages.values())-total))))
    return dict(prefix_timing=measured, stage_histories=parts, source_waveform_complete=False,
                native_voltage_and_control_checks_complete=False, qualified_phy=False,
                scope='Selected live-prefix crossing diagnostics only; all completed full-native gates remain required')


def capture(pid):
    binding = process(pid)
    raw = ROOT/binding['raw']
    if raw != PARENT/'0/bench.raw':
        raise ValueError('Require original live v352 zero-code engine')
    manifest = source.bound(PARENT, full=False)
    paths = [Path(__file__), ROOT/'scripts/capture_native_live_tail_v290.py',
             ROOT/'scripts/regenerated_bank_periodic_measure_v67.py',
             PARENT/'manifest.json', PARENT/'bank.spice', PARENT/'0/bench.cir']
    inputs = {str(p.relative_to(ROOT)): source.sha(p) for p in paths}
    header, data, metadata = project(raw)
    result = histories(data, manifest['tasks'][0]['spec'])
    if process(pid) != binding or any(source.sha(ROOT/n) != h for n, h in inputs.items()):
        raise ValueError('Original live engine or diagnostic context changed during capture')
    out = ROOT/'build/reports/live_bank_history_v364'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out.mkdir(parents=True, exist_ok=False)
    (out/'original_header.bin').write_bytes(header)
    np.savez(out/'selected_native_history.npz', data=data, names=np.asarray(NODES))
    files = {name: source.sha(out/name) for name in ('original_header.bin', 'selected_native_history.npz')}
    report = dict(process=binding, inputs=inputs, task=manifest['tasks'][0], files=files,
                  **metadata, **result)
    (out/'summary.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')
    print(out, flush=True)
    return out


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pid', type=int, required=True)
    capture(parser.parse_args().pid)
