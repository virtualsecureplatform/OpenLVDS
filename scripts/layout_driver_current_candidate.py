#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Build an isolated 110:1 driver mirror with the existing audited layout flow."""
import json
from pathlib import Path

import layout_driver_restore_candidate as physical
from driver_current_variant import source_variant, VARIANT


def build():
    previous = physical.VARIANTS, physical.selected_source, physical.CODE
    source = source_variant((physical.ROOT/'analog/openlvds.spice').read_text())
    def selected(name):
        if name != VARIANT:
            raise ValueError('Unknown current variant')
        return source
    try:
        physical.VARIANTS = {VARIANT: True}
        physical.selected_source = selected
        physical.CODE = sorted(set(physical.CODE) | {Path(__file__).name, 'driver_current_variant.py'})
        return physical.build(VARIANT)
    finally:
        physical.VARIANTS, physical.selected_source, physical.CODE = previous


if __name__ == '__main__':
    root, summary = build()
    print(json.dumps(dict(output=str(root), passed=summary['passed'], qualified_phy=False)), flush=True)
    raise SystemExit(0 if summary['passed'] else 1)
