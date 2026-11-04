# SPDX-License-Identifier: GPL-3.0-only
"""Native source readiness FFs with the unchanged passive-RC DCC and drivers."""
import native_clock_components_v3 as previous
import native_ff_clock_release_v2 as release

dcc=previous.dcc
clean=previous.clean
MODELS=previous.MODELS
CLOCK_BUFFER=previous.CLOCK_BUFFER
definitions=previous.definitions
mapped_mos=previous.mapped_mos


def compose(rc,library):
    before=previous.compose(rc)
    result={k:v for k,v in before.items() if k in ['cells.spice','clean.spice']}
    result['release.spice']='* Readiness FFs and output buffer are defined in the selected variant.\n'
    for drive in [1,2]:result[f'ff{drive}_c1.spice']=release.source(drive,library,rc)+before['p3_c1.spice']
    return result
