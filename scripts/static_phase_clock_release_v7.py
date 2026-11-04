# SPDX-License-Identifier: GPL-3.0-only
"""Six-port harness view of the complete native RC counter with real monitors.

The five unloaded monitor ports are the existing routed physical conductors.
The wrapper adds no devices, capacitance, voltage sources or internal shorts.
"""
import static_phase_clock_release_v6 as previous

components=previous.components
PORTS=previous.PORTS
NAME='openlvds_whole_rc_static_phase_release_v2'
MODEL='openlvds_static_phase_observed_v2'
OBSERVATIONS=['low0','high1','low1','armed','request_i']


def source(rc,variant):
    if variant!='backend' or set(rc[MODEL]['info']['ports'])!=set(PORTS+OBSERVATIONS):raise ValueError('Require exact full-counter observation RC interface')
    pins={p:p for p in PORTS+OBSERVATIONS}
    return '\n'.join(['.subckt '+NAME+' '+' '.join(PORTS),components.instance('core',MODEL,pins,rc),'.ends '+NAME,''])
