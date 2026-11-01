# SPDX-License-Identifier: GPL-3.0-only
"""Keep every segment of the weaker summing-node pull-ups in the local row."""
import re
import receiver_frontend_geometry as original

_critical = original.critical


def critical(device):
    return _critical(device) or any(re.search(r'__(?:PP|PN)BOOST[12]$', n) for n in device['nodes'])


def draw_macro(out, top, ports, devices, library):
    previous = original.critical
    try:
        original.critical = critical
        return original.draw_macro(out, top, ports, devices, library)
    finally:
        original.critical = previous
