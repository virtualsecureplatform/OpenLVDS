# SPDX-License-Identifier: GPL-3.0-only
"""Use retained local-drop routing with the distinct larger-MIM schematic.

The routing algorithm is unchanged. Placement is separately supplied and bound
after inspecting the actual new PCell geometry. No original artifact is edited.
"""
import mim_switch_unit_layout_v3 as routing
import mim_switch_2x3_v2 as unit

VERSION='mim-switch-2x3-local-drop-routing-v2.1'


def draw(out,library,configuration):
    previous=routing.unit
    routing.unit=unit
    try:return routing.draw(out,library,configuration)
    finally:routing.unit=previous
