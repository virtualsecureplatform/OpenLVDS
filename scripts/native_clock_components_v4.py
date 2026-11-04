# SPDX-License-Identifier: GPL-3.0-only
"""Compare phase-armed reset release using unchanged passive native RC cells."""
import native_clock_components_v3 as previous
import native_phase_clock_release_v2 as release

dcc=previous.dcc
clean=previous.clean
MODELS=previous.MODELS
CLOCK_BUFFER=previous.CLOCK_BUFFER
definitions=previous.definitions
mapped_mos=previous.mapped_mos


def compose(rc):
    result=previous.compose(rc)
    result['release.spice']=previous.base.logic(release.NAME,release.PORTS,release.gates(),rc)
    return result
