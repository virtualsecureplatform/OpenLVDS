# SPDX-License-Identifier: GPL-3.0-only
"""Narrow the gate-cap quantum below the measured 0.84 um slew near miss."""
import re
import moscap_fine_bank_v75 as original

source = original.source
WIDTHS = dict(w076='.76', w080='.8')


def name(profile):
    if profile not in WIDTHS:
        raise ValueError('Unknown narrowed gate-cap fine quantum')
    return 'openlvds_internal_moscap_'+profile+'_v88'


def rescale(text, profile):
    top = name(profile); old = original.name('w084')
    if text.count('.subckt '+old+' ') != 1 or text.count('.subckt '+old+'_unit ') != 1:
        raise ValueError('Require original 0.84 um gate-cap bank and unit')
    lines = text.splitlines(keepends=True); seen = set()
    for i, line in enumerate(lines):
        words = line.split()
        if words and words[0] in ('Xgatecap_n', 'Xgatecap_p'):
            if words[0] in seen or words[-2:] != ['w=.84', 'l=.15']:
                raise ValueError('Original capacitor transistor dimensions changed')
            seen.add(words[0]); lines[i] = line.replace('w=.84 l=.15', 'w='+WIDTHS[profile]+' l=.15')
    if seen != {'Xgatecap_n', 'Xgatecap_p'}:
        raise ValueError('Incomplete original gate-cap pair')
    return re.sub(r'\b'+re.escape(old)+r'(?=_unit\b|\b)', top, ''.join(lines))


def transform(text, profile):
    result = rescale(original.transform(text, 'w084'), profile)
    counts = source.primitive_counts(result, name(profile))
    if sum(v for k, v in counts.items() if 'fet_' in k) != 1013 or counts.get('sky130_fd_pr__cap_mim_m3_1') != 37:
        raise ValueError('Narrowed native gate-cap bank inventory changed')
    return result
