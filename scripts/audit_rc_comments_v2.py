# SPDX-License-Identifier: GPL-3.0-only
"""Strip SPICE inline comments before the unchanged R/C topology collapse."""
from audit_rc import collapse as original


def collapse(text):
    return original('\n'.join(line.split('$',1)[0].rstrip() for line in text.splitlines())+'\n')
