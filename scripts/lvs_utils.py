# SPDX-License-Identifier: GPL-3.0-only
"""Strict LVS policy, including fixed-width resistor model normalization."""
import re

def schematic_parameters(device):
    parameters=dict(device['params'])
    if device['model']=='sky130_fd_pr__res_high_po_0p35':
        # The physical/extracted PDK model encodes width in its name and emits
        # only L. Check the requested width before removing the redundant W.
        if abs(float(parameters.get('w',.35))-.35)>1e-12:
            raise ValueError('res_high_po_0p35 has fixed 0.35 um width')
        parameters.pop('w',None)
    return parameters

def clean_match(report,returncode=0):
    return returncode==0 and 'Circuits match uniquely.' in report and not re.search(
        r'property errors (?:were found|found)|with property errors|do not match',report,re.I)
