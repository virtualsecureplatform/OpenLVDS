# SPDX-License-Identifier: GPL-3.0-only
"""Bind the measured middle-bus capacitor cell to balanced clock-path drive."""
from balanced_drive_bank_v103 import ROOT, source, WIDTHS, name, transform, observations
from moscap_component_rc_bank_v90 import fine_pattern, sha, physical
import hashlib
import json
from pathlib import Path


def checked_cell(parent):
    parent = parent.resolve()
    i = json.loads((parent/'manifest.json').read_text())
    r = json.loads((parent/'summary.json').read_text())
    if (parent.parent != ROOT/'build/diagnostics/moscap_fine_rc_v105'
        or i['version'] != 'middle-cap-bus-native-mask-derived-junctions-and-component-rc-v105.1'
        or parent.name != hashlib.sha256(json.dumps(i, sort_keys=True).encode()).hexdigest()[:16]
        or any(sha(ROOT/n) != h for n, h in i['inputs'].items())
        or any(sha(Path(n)) != h for n, h in i['external_files'].items())
        or any(sha(parent/n) != h for n, h in r['files'].items())
        or any(sha(ROOT/n) != h for n, h in r['original_extracted_files'].items())
        or any(sha(Path(t['path'])) != t['sha256'] for t in i['tools'].values())
        or not r['fine_cell_geometry_and_component_rc_passed']
        or not r['rc_proof']['component_rc_passed'] or not r['rc_proof']['native_topology_verified']
        or not r['rc_proof']['independent_terminal_current_witness']['proof']['passed']
        or not r['original_extraction_preserved'] or r['qualified_phy']):
        raise ValueError('Require unchanged complete measured fine-cell component RC')
    net = ROOT/r['extraction']['netlist']
    if sha(net) != r['extraction']['netlist_sha256']:
        raise ValueError('Measured fine-cell RC netlist changed')
    fine_pattern(net.read_text(), physical.name(r['profile']))
    return i, r, net.read_text()
