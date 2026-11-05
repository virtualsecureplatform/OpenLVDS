# SPDX-License-Identifier: GPL-3.0-only
"""Further TG widening to test the 1.6 ps quarter-period headroom bottleneck.

Retains the regular-PMOS diagnostic's borrowed inverter RC. All bank/native
connections remain intact; new TG junctions are explicit prelayout estimates.
"""
import tg_driver_experiment_v9 as previous
from build_compound_drivers_v3 import cell_definition
from spice_library import replace

baseline = previous.baseline
PROFILES = {'regular_oct': (True, 4)}


def name(profile):
    if profile not in PROFILES:
        raise ValueError('Unknown headroom experiment profile')
    return 'openlvds_dcdl_tg_c16_f32_'+profile+'_v12'


def transform(cells, bank, profile):
    name(profile)
    cells, bank, report = previous.transform(cells, bank, 'regular_quad')
    model = baseline.previous.tg_name(baseline.PROFILE)
    old = cell_definition(cells, model)
    rows = []
    for row in old.splitlines():
        if row.startswith(('XN ', 'XP ')):
            width = 3.36 if row.startswith('XN ') else 6.72
            row = row[:row.index('w=')]+f'w={width:g} l=0.15 ad={width*.29:.9g} as={width*.29:.9g} pd={2*(width+.29):.9g} ps={2*(width+.29):.9g}'
        rows.append(row)
    cells = replace(cells, model, '\n'.join(rows))
    old_name = previous.name('regular_quad')
    bank = bank.replace('.subckt '+old_name+' ', '.subckt '+name(profile)+' ', 1).replace('.ends '+old_name+'\n', '.ends '+name(profile)+'\n', 1)
    return cells, bank, dict(report, tg_widths_um=[3.36, 6.72],
                            rationale='Regular-quad zero-code headroom is only 1.620 ps before common routing',
                            whole_bank_rc_retained=False, electrical_qualification_passed=False, qualified_phy=False)
