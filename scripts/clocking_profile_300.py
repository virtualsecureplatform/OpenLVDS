#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Load the isolated 300 MHz policy without rewriting captured legacy inputs."""
import hashlib
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def load():
    path=ROOT/'clocking_300mhz.json'
    profile=json.loads(path.read_text())
    r=profile['requirements']
    if (profile['schema']!='openlvds-300mhz-v1' or profile['qualified_phy'] is not False
        or r['nominal_clock_mhz']!=300 or r['bits_per_cycle']!=2
        or r['clock_test_mhz']!=[290,300,310] or r['clock_duty']!=[.4,.5,.6]
        or profile['lane_rate_mbps']!=600 or profile['openpll_feedback_divider']!=12):
        raise ValueError('300 MHz contract changed')
    for name,expected in profile['legacy_inputs'].items():
        if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=expected:
            raise ValueError('Captured legacy contract changed: '+name)
    return profile

def budgets():
    p=load();freq=p['requirements']['clock_test_mhz']
    return dict(nominal_period_ps=1e6/300,minimum_quarter_ps=1e6/max(freq)/4,
                maximum_quarter_ps=1e6/min(freq)/4,minimum_ui_ps=1e6/max(freq)/2,
                minimum_raw_interval_ps=1e6/max(freq)*.4,
                minimum_rx_span_ps=1e6/min(freq)+p['clocking']['search']['rx_extra_range_ps'])

if __name__=='__main__':print(json.dumps(budgets(),indent=2))
