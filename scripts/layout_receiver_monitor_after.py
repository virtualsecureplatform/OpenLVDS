#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Move the unloaded reference monitor away from the decision-to-restorer path."""
import argparse
import json
from pathlib import Path

from receiver_layout_reference import build as build_reference
from layout_receiver_tail_headroom_candidate import place_monitor


def place(devices):
    # Preserve the admitted order of every functional device and monitor finger.
    reference=place_monitor(devices)
    monitor=[d for d in reference if '__XTRACK__' in d['name']]
    return [d for d in reference if '__XTRACK__' not in d['name']]+monitor


def build(reference):
    return build_reference(reference,place,
        dict(placement='Six unloaded reference monitor devices after all functional devices; other device order retained'),
        [Path(__file__).name])


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('reference',type=Path);args=parser.parse_args()
    out,report=build(args.reference.resolve())
    print(json.dumps(dict(output=str(out),passed=report['passed'])),flush=True)
    raise SystemExit(0 if report['passed'] else 1)
