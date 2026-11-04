# SPDX-License-Identifier: GPL-3.0-only
"""Drive the actual phase-release REQUEST fanout through a native RC buffer.

External REQUEST retains its original fast edges. This adds the physical
buf8_o4 component ahead of both guarded readiness FFs and sticky NAND feedback;
all buffer terminals remain part of the voltage screen. Whole-controller
interconnect and guarded-FF physical RC remain qualification requirements.
"""
import guarded_phase_clock_release_v2 as previous

components=previous.components
NAME='openlvds_buffered_request_phase_release_v2'
PORTS=previous.PORTS


def source(library,rc,guard_nodes,size):
    old=previous.source(library,rc,guard_nodes,size).splitlines()
    body=[' '.join('request_i' if token=='REQUEST' else token for token in row.split())
          for row in old[1:-1]]
    buffer=components.instance('request_driver',components.CLOCK_BUFFER,
        dict(A='REQUEST',X='request_i',VPWR='VPWR',VGND='VGND'),rc)
    return '\n'.join(['.subckt '+NAME+' '+' '.join(PORTS),buffer,*body,'.ends '+NAME,''])
