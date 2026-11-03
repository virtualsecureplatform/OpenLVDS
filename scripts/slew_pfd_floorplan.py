# SPDX-License-Identifier: GPL-3.0-only
"""Translated PFD input-chain placement targets and a final-DEF geometry check.

Placement matching alone does not prove matching of routed RC or phase error.
The native electrical coverage remains mandatory after routing and extraction.
"""
from copy import deepcopy
import re

from pfd_slew_policy import chains


def units(text):
    found = re.findall(r'\bUNITS DISTANCE MICRONS (\d+)\s*;', text)
    if len(found) != 1 or int(found[0]) <= 0: raise ValueError('Require explicit DEF database units')
    return int(found[0])


def section(text, name):
    found = re.findall(r'(?ms)^' + name + r' \d+\s*;(.*?)^END ' + name + r'\b', text)
    if len(found) != 1: raise ValueError('Require one DEF ' + name + ' section')
    return found[0]


def pin_records(text):
    records = {}
    for m in re.finditer(r'(?ms)^\s*-\s+(\S+)\s+\+ NET\s+.*?;', section(text, 'PINS')):
        if m[1] in records: raise ValueError('Duplicate DEF pin')
        records[m[1]] = m[0]
    return records


def location(record):
    found = re.findall(r'\+ (?:PLACED|FIXED)\s*\(\s*(-?\d+)\s+(-?\d+)\s*\)\s+(\w+)', record)
    if len(found) != 1: raise ValueError('Require one placed DEF object')
    x, y, orient = found[0]
    return int(x), int(y), orient


def plan(baseline, variant):
    gates = chains(variant); dbu = units(baseline)
    rows = []
    for m in re.finditer(r'(?m)^ROW \S+ (\S+) (\d+) (\d+) (\w+) DO (\d+) BY 1 STEP (\d+) 0\s*;', baseline):
        site, x, y, orient, count, step = m.groups()
        rows.append(dict(site=site, x=int(x), y=int(y), orientation=orient, count=int(count), step=int(step)))
    rows.sort(key=lambda r: r['y'])
    if len(rows) < 17: raise ValueError('Require at least seventeen complete placement rows')
    ref, middle, fb = rows[8], rows[12], rows[16]
    for row in (middle, fb):
        if any(row[k] != ref[k] for k in ('site', 'x', 'orientation', 'count', 'step')):
            raise ValueError('Matched chains require translated, equally oriented rows')
    if ref['count'] < 180: raise ValueError('Placement rows too narrow for the bounded PFD floorplan')
    pitch = rows[1]['y'] - rows[0]['y']
    if pitch <= 0 or any(b['y'] - a['y'] != pitch for a, b in zip(rows, rows[1:])):
        raise ValueError('Require a regular full-row grid')
    placements = {}; pairs = []
    for first, second, column, master in [
            ('ref_condition', 'fb_condition', 50, gates['ref_condition'][0]),
            *([] if variant.startswith('clkbuf') else [('ref_restore', 'fb_restore', 76, 'inv_4')]),
            ('ref_ff', 'fb_ff', 104, 'dfrtp_4'), ('up_drive', 'dn_drive', 148, 'buf_8')]:
        for name, row in [(first, ref), (second, fb)]:
            placements[name] = dict(location=[(row['x'] + column * row['step']) / dbu, row['y'] / dbu], orientation=row['orientation'])
        pairs.append(dict(first=first, second=second, master='sky130_fd_sc_hd__' + master))
    for name, column in [('reset_disable', 104), ('clear', 125)]:
        placements[name] = dict(location=[(middle['x'] + column * middle['step']) / dbu, middle['y'] / dbu], orientation=middle['orientation'])
    pins = pin_records(baseline)
    if not {'REF', 'FB'} <= set(pins): raise ValueError('Require both external clock pins')
    for name in ('REF', 'FB'):
        if not re.search(r'\+ NET\s+' + name + r'\b', pins[name]) or '+ DIRECTION INPUT' not in pins[name]:
            raise ValueError('Require correctly named input clock pins')
    ref_x, _, _ = location(pins['REF'])
    # Same input-pin geometry and orientation at translated row centers.
    ref_record = re.sub(r'\+ (?:PLACED|FIXED)\s*\([^)]*\)\s+\w+',
                        f'+ PLACED ( {ref_x} {ref["y"] + pitch // 2} ) N', pins['REF'])
    fb_record = re.sub(r'(?m)^(\s*-\s+)REF\b', r'\1FB', ref_record)
    fb_record = re.sub(r'\+ NET\s+REF\b', '+ NET FB', fb_record)
    fb_record = re.sub(r'\+ PLACED\s*\([^)]*\)\s+\w+',
                       f'+ PLACED ( {ref_x} {fb["y"] + pitch // 2} ) N', fb_record)
    template = baseline.replace(pins['REF'], ref_record).replace(pins['FB'], fb_record)
    return dict(variant=variant, dbu_per_um=dbu, translation_dbu=[0, fb['y'] - ref['y']],
                manual_global_placements=placements, pairs=pairs, pin_template=template)


def configuration(base, target, *, source, blackboxes, shared_models, sdc, template):
    cfg = deepcopy(base)
    cfg.update(VERILOG_FILES=[str(source)], EXTRA_VERILOG_MODELS=[str(shared_models), str(blackboxes)],
               PNR_SDC_FILE=str(sdc), SIGNOFF_SDC_FILE=str(sdc),
               FP_DEF_TEMPLATE=str(template), FP_TEMPLATE_MATCH_MODE='strict',
               MANUAL_GLOBAL_PLACEMENTS=target['manual_global_placements'],
               RSZ_DONT_TOUCH_LIST=sorted(set(target['manual_global_placements']) |
                                         {'REF', 'FB', 'ref_conditioned', 'fb_conditioned', 'raw_up', 'raw_dn', 'clear_b', 'disallow'} |
                                         (set() if target['variant'].startswith('clkbuf') else {'ref_mid', 'fb_mid'})),
               RUN_CTS=False, RUN_POST_GPL_DESIGN_REPAIR=False, RUN_POST_GRT_DESIGN_REPAIR=False,
               RUN_POST_CTS_RESIZER_TIMING=False, RUN_POST_GRT_RESIZER_TIMING=False,
               DESIGN_REPAIR_BUFFER_INPUT_PORTS=False, DESIGN_REPAIR_BUFFER_OUTPUT_PORTS=False)
    if cfg.get('DESIGN_NAME') != 'lvds_pfd' or not cfg.get('SYNTH_ELABORATE_ONLY'):
        raise ValueError('Require the elaboration-only PFD flow')
    return cfg


def check(definition, target):
    dbu = units(definition)
    if dbu != target['dbu_per_um']: raise ValueError('Final DEF database units changed')
    components = {}
    for m in re.finditer(r'(?ms)^\s*-\s+(\S+)\s+(\S+)(.*?);', section(definition, 'COMPONENTS')):
        if m[1] in components: raise ValueError('Duplicate DEF component')
        components[m[1]] = (m[2], location(m[3]))
    errors = []; dx, dy = target['translation_dbu']
    for pair in target['pairs']:
        a = components.get(pair['first']); b = components.get(pair['second'])
        if a is None or b is None:
            errors.append('Missing pair: ' + pair['first']); continue
        if a[0] != pair['master'] or b[0] != pair['master']:
            errors.append('Cell master changed: ' + pair['first'])
        if (b[1][0] - a[1][0], b[1][1] - a[1][1], b[1][2]) != (dx, dy, a[1][2]):
            errors.append('Cell pair lost translation/orientation: ' + pair['first'])
    pins = pin_records(definition); expected_pins = pin_records(target['pin_template'])
    for name in ('REF', 'FB'):
        if name not in pins:
            errors.append('Missing input pin: ' + name); continue
        if location(pins[name]) != location(expected_pins[name]): errors.append('Input pin moved: ' + name)
        shapes = lambda record: re.findall(r'\+ LAYER\s+(\S+)\s+\(\s*(-?\d+)\s+(-?\d+)\s*\)\s+\(\s*(-?\d+)\s+(-?\d+)\s*\)', record)
        if not shapes(pins[name]) or shapes(pins[name]) != shapes(expected_pins[name]): errors.append('Input pin shape changed: ' + name)
    return dict(placement_matched=not errors, errors=errors, route_matching_verified=False,
                physical_admission=False, qualified_phy=False)
